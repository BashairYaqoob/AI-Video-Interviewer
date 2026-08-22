"""
agent.py

LiveKit Agent — AI Video Interviewer.

Wires the LangGraph interview flow (question planning, adaptive
follow-up, evidence collection) into the live Gemini realtime voice
pipeline. Manual turn control means every agent utterance is explicitly
driven by the graph's decision — Gemini never auto-replies off static
instructions.

Adds: SQLite persistence, durable thread IDs, HITL controls (in-process
+ external via hitl_api.py), reconnect/resume, and a pre-interview plan
approval gate.

Requires output/jd.json, resume.json, github.json, gap_analysis.json,
interview_plan.json, and an approved interview_plan_approval.json —
run scripts/run_prep_pipeline.py then scripts/approve_plan.py first.

Run with: python -m src.realtime.agent dev  (from the repo root)
"""

import asyncio
import logging
from pathlib import Path

from dotenv import load_dotenv
from livekit import agents
from livekit.agents import Agent, AgentServer, AgentSession, TurnHandlingOptions
from livekit.plugins import google
from google.genai import types

from langgraph.types import Command

from src.ingestion.schemas import JobDescription, Resume, GitHubEvidence, GapAnalysis
from src.interview.schemas import (
    InterviewPlan,
    QuestionRecord,
    AnswerRecord,
    HITLStatus,
    HITL_SKIP_SENTINEL_KEY,
)
from src.interview.state import InterviewState
from src.interview.graph import build_interview_graph
from src.interview.answer_analysis import analyze_answer, AnswerAnalysisUnavailable
from src.interview.checkpointer import open_sqlite_checkpointer
from src.interview.hitl import HITLController
from src.interview.plan_approval import get_approved_questions

load_dotenv()

logger = logging.getLogger(__name__)

OUTPUT_DIR = Path(__file__).resolve().parent.parent.parent / "output"

POLL_INTERVAL_SECONDS = 3.0


def _load_prep_artifacts():
    """Loads the output of the offline prep pipeline, and the recruiter's
    approved (possibly edited) question list. Raises if the plan hasn't
    been approved yet — see scripts/approve_plan.py."""
    def _load(name, model):
        path = OUTPUT_DIR / name
        if not path.exists():
            raise FileNotFoundError(
                f"{path} not found. Run scripts/run_prep_pipeline.py first."
            )
        return model.model_validate_json(path.read_text(encoding="utf-8"))

    jd = _load("jd.json", JobDescription)
    resume = _load("resume.json", Resume)
    github_evidence = _load("github.json", GitHubEvidence)
    gap_analysis = _load("gap_analysis.json", GapAnalysis)
    interview_plan = _load("interview_plan.json", InterviewPlan)
    approved_questions = get_approved_questions(interview_plan)
    return jd, resume, github_evidence, gap_analysis, interview_plan, approved_questions


def _derive_thread_id(ctx: agents.JobContext, jd: JobDescription, resume: Resume) -> str:
    """Stable thread_id so a dropped/reconnected call resumes the SAME
    interview. Preference order: job metadata (most reliable) -> LiveKit
    room name (stable across a rejoin) -> candidate+role hash (last
    resort; can collide across same-day interviews — pass real job
    metadata in production instead)."""
    metadata = (getattr(ctx.job, "metadata", "") or "").strip()
    if metadata:
        return f"interview-{metadata}"

    room_name = getattr(ctx.room, "name", "") or ""
    if room_name:
        return f"interview-room-{room_name}"

    fallback_key = f"{resume.candidate_name}:{jd.title}"
    return f"interview-fallback-{abs(hash(fallback_key))}"


class Interviewer(Agent):
    def __init__(self, candidate_name: str) -> None:
        super().__init__(
            instructions=(
                f"You are an AI job interviewer speaking with {candidate_name}. "
                "You will be given the exact question to ask at each turn — ask "
                "it naturally in your own words, without changing its meaning "
                "and without asking anything else. Sound conversational, like a "
                "real interviewer, not robotic."
            )
        )


server = AgentServer()


@server.rtc_session(agent_name="ai-interviewer")
async def ai_interviewer(ctx: agents.JobContext):
    jd, resume, github_evidence, gap_analysis, interview_plan, approved_questions = _load_prep_artifacts()

    initial_state = InterviewState(
        candidate_name=resume.candidate_name,
        target_role=jd.title,
        jd=jd,
        resume=resume,
        github_evidence=github_evidence,
        gap_analysis=gap_analysis,
        interview_plan=approved_questions,
    )

    thread_id = _derive_thread_id(ctx, jd, resume)
    config = {"configurable": {"thread_id": thread_id}}
    logger.info("interview thread_id=%s", thread_id)

    # Mutated in place only (never reassigned) so every closure below
    # always observes the current value.
    awaiting_answer = {"value": False}
    processing_answer = {"value": False}

    # In-process mirror of HITL pause state for the synchronous
    # user_input_transcribed handler. Can go briefly stale if hitl_status
    # changes via hitl_api.py — the poll loop below reconciles it.
    hitl_mirror = {"paused": False}

    # How many hitl_actions_log entries this process has already reacted
    # to, so the poll loop only acts on genuinely new ones (its own or
    # an external process's). Guarded by mirror_lock.
    processed_actions_count = {"value": 0}
    mirror_lock = asyncio.Lock()

    # Serializes every writer to this interview's state: graph
    # advancement, background evidence analysis, and HITL actions.
    # Coarse-grained on purpose — see ARCHITECTURE.md.
    state_lock = asyncio.Lock()

    async with open_sqlite_checkpointer() as checkpointer:
        graph = build_interview_graph(realtime_mode=True, checkpointer=checkpointer)
        hitl = HITLController(graph, config, state_lock)

        def _as_question_record(value) -> QuestionRecord:
            return value if isinstance(value, QuestionRecord) else QuestionRecord(**value)

        def _as_answer_record(value) -> AnswerRecord:
            return value if isinstance(value, AnswerRecord) else AnswerRecord(**value)

        def _field(record, name):
            return record[name] if isinstance(record, dict) else getattr(record, name)

        async def _analyze_answer_background(question: QuestionRecord, answer: AnswerRecord) -> None:
            """Runs Gemini answer analysis off the realtime critical path.
            Never blocks or crashes the live interview — failures are
            logged and swallowed; worst case that turn is missing from
            the final evidence report."""
            try:
                evidence = await asyncio.to_thread(
                    analyze_answer, question, answer, jd, resume, github_evidence
                )
            except AnswerAnalysisUnavailable as exc:
                logger.warning("answer analysis unavailable for %s: %s", question.question_id, exc)
                return
            except Exception:
                logger.exception("unexpected error analyzing answer for %s", question.question_id)
                return

            evidence.question_id = question.question_id
            try:
                async with state_lock:
                    current_state = await graph.aget_state(config)
                    current = current_state.values.get("evidence_collected", [])
                    await graph.aupdate_state(config, {"evidence_collected": current + [evidence]})
            except Exception:
                logger.exception("failed to persist evidence for %s", question.question_id)

        session = AgentSession(
            llm=google.realtime.RealtimeModel(
                voice="Puck",
                temperature=0.7,
                realtime_input_config=types.RealtimeInputConfig(
                    automatic_activity_detection=types.AutomaticActivityDetection(
                        disabled=True,
                    ),
                ),
            ),
            turn_handling=TurnHandlingOptions(
                turn_detection="vad",
                preemptive_generation={
                    "preemptive_llm": False,
                    "preemptive_tts": False,
                },
                endpointing={
                    "mode": "fixed",
                    "min_delay": 0.8,
                    "max_delay": 2.0,
                },
            ),
        )

        def _current_question_text(values: dict) -> str:
            last_question = values["questions_asked"][-1]
            return last_question["text"] if isinstance(last_question, dict) else last_question.text

        # Keeps the checkpointer's `async with` block (and its SQLite
        # connection) open for the interview's real lifetime — the
        # interview is actually driven by the event handler below, not
        # by this function's own control flow after this point.
        interview_done = asyncio.Event()

        async def _finish_interview():
            await session.generate_reply(
                instructions=(
                    "Thank the candidate for their time, let them know "
                    "the interview is complete, and say goodbye warmly."
                )
            )
            awaiting_answer["value"] = False
            interview_done.set()

        # Safety net: candidate just leaves without a natural finish.
        @ctx.room.on("participant_disconnected")
        def _on_participant_disconnected(*args, **kwargs):
            interview_done.set()

        async def _speak_question(values: dict, *, first_question: bool, reconnect: bool):
            question_text = _current_question_text(values)

            if reconnect:
                instructions = (
                    f"Welcome {resume.candidate_name} back — the call briefly "
                    f"dropped and has now reconnected. Let them know that's "
                    f"completely fine, and ask them again, in your own "
                    f"natural words: {question_text}"
                )
            elif first_question:
                instructions = (
                    f"Greet {resume.candidate_name} by name, briefly disclose "
                    f"that you are an AI interviewer, and explain you'll be "
                    f"asking about their background and experience for the "
                    f"{jd.title} role. Then ask them exactly this question "
                    f"in your own natural words: {question_text}"
                )
            else:
                instructions = (
                    f"Ask the candidate exactly this question, "
                    f"in your own natural words: {question_text}"
                )

            logger.info("QUESTION SENT: %s", question_text)
            await session.generate_reply(instructions=instructions)
            awaiting_answer["value"] = True

        async def _advance_and_ask(resume_value):
            """Steps the graph forward one turn, then speaks the next
            question or wraps up. All reads/writes happen under
            state_lock as a single unit."""
            async with state_lock:
                if resume_value is None:
                    await graph.ainvoke(initial_state.model_dump(), config=config)
                else:
                    pre_values = (await graph.aget_state(config)).values
                    answered_question = _as_question_record(pre_values["questions_asked"][-1])

                    await graph.ainvoke(Command(resume=resume_value), config=config)

                    post_values = (await graph.aget_state(config)).values
                    answered_answer = _as_answer_record(post_values["candidate_answers"][-1])

                    if not answered_answer.skipped:
                        # Background only — never awaited, never started
                        # while holding state_lock (it acquires it itself).
                        asyncio.create_task(
                            _analyze_answer_background(answered_question, answered_answer)
                        )

                values = (await graph.aget_state(config)).values

            if values.get("is_complete") or values.get("hitl_status") == HITLStatus.TERMINATED:
                await _finish_interview()
                return

            await _speak_question(values, first_question=(resume_value is None), reconnect=False)

        # --- In-process HITL hooks -----------------------------------
        # Integration points for any control channel (external API,
        # future MCP tool, etc.) that runs inside this process.

        async def handle_pause(actor: str = "recruiter", note: str = "") -> None:
            await hitl.pause(actor=actor, note=note)
            hitl_mirror["paused"] = True
            awaiting_answer["value"] = False
            async with mirror_lock:
                processed_actions_count["value"] += 1

        async def handle_resume(actor: str = "recruiter", note: str = "") -> None:
            await hitl.resume(actor=actor, note=note)
            hitl_mirror["paused"] = False
            async with mirror_lock:
                processed_actions_count["value"] += 1

        async def handle_skip(actor: str = "recruiter", note: str = "") -> None:
            sentinel = await hitl.skip_current_question(actor=actor, note=note)
            async with mirror_lock:
                processed_actions_count["value"] += 1
            await _advance_and_ask(resume_value=sentinel)

        async def handle_override_question(
            question: QuestionRecord, actor: str = "recruiter", note: str = ""
        ) -> None:
            await hitl.override_next_question(question, actor=actor, note=note)
            async with mirror_lock:
                processed_actions_count["value"] += 1

        async def handle_terminate(actor: str = "recruiter", note: str = "") -> None:
            await hitl.terminate(actor=actor, note=note)
            async with mirror_lock:
                processed_actions_count["value"] += 1
            await _finish_interview()

        # --- External HITL polling ------------------------------------
        # hitl_api.py runs as a SEPARATE process and only ever writes
        # durable state — it can't push into this running agent. This
        # loop notices actions it didn't originate itself (e.g. from
        # hitl_api.py) and reacts, so an external terminate/pause/skip
        # is still caught promptly even while silently awaiting a turn.
        # Skip is guarded against racing a real candidate answer.

        async def _external_hitl_poll_loop():
            while not interview_done.is_set():
                try:
                    await asyncio.wait_for(interview_done.wait(), timeout=POLL_INTERVAL_SECONDS)
                    break
                except asyncio.TimeoutError:
                    pass

                async with state_lock:
                    values = (await graph.aget_state(config)).values
                    log = values.get("hitl_actions_log", [])

                async with mirror_lock:
                    already_processed = processed_actions_count["value"]
                new_entries = log[already_processed:]

                for entry in new_entries:
                    action = _field(entry, "action")

                    if action == "terminate":
                        if not interview_done.is_set():
                            logger.info("external HITL terminate detected, ending interview")
                            await _finish_interview()

                    elif action == "pause":
                        hitl_mirror["paused"] = True
                        awaiting_answer["value"] = False

                    elif action == "resume":
                        hitl_mirror["paused"] = False

                    elif action == "skip":
                        if awaiting_answer["value"] and not processing_answer["value"]:
                            logger.info("external HITL skip detected, advancing")
                            awaiting_answer["value"] = False
                            processing_answer["value"] = True
                            try:
                                await _advance_and_ask(resume_value={HITL_SKIP_SENTINEL_KEY: True})
                            finally:
                                processing_answer["value"] = False
                        else:
                            logger.info("external HITL skip detected but no turn in flight; ignoring")

                    # override_question needs no proactive action — read
                    # naturally the next time ask_question_node runs.

                async with mirror_lock:
                    processed_actions_count["value"] = len(log)

        # ----------------------------------------------------------------

        @session.on("user_input_transcribed")
        def _on_user_transcript(ev):
            if not ev.is_final:
                return
            if not awaiting_answer["value"]:
                return
            if processing_answer["value"]:
                return
            if hitl_mirror["paused"]:
                # Dropped, not buffered — see ARCHITECTURE.md.
                logger.info("dropping transcript while HITL paused")
                return

            awaiting_answer["value"] = False
            processing_answer["value"] = True

            async def process_answer():
                try:
                    await _advance_and_ask(resume_value=ev.transcript)
                except Exception:
                    logger.exception("Error processing candidate answer")
                finally:
                    processing_answer["value"] = False

            asyncio.create_task(process_answer())

        await session.start(
            agent=Interviewer(resume.candidate_name),
            room=ctx.room,
        )

        # RESUME / RECOVERY: check for existing checkpointed state under
        # this thread_id before starting fresh — a reconnect re-prompts
        # instead of restarting from intro.
        existing = await graph.aget_state(config)
        processed_actions_count["value"] = len(existing.values.get("hitl_actions_log", []))

        if not existing.values:
            await _advance_and_ask(resume_value=None)
        elif existing.values.get("is_complete") or existing.values.get("hitl_status") == HITLStatus.TERMINATED:
            await _finish_interview()
        elif existing.values.get("hitl_status") == HITLStatus.PAUSED:
            hitl_mirror["paused"] = True
            await session.generate_reply(
                instructions=(
                    f"Let {resume.candidate_name} know the interview has "
                    "reconnected but is currently paused, and ask them to "
                    "hold for a moment."
                )
            )
        else:
            await _speak_question(existing.values, first_question=False, reconnect=True)

        asyncio.create_task(_external_hitl_poll_loop())
        await interview_done.wait()


if __name__ == "__main__":
    agents.cli.run_app(server)