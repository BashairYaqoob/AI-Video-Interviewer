"""
agent.py

LiveKit Agent — AI Video Interviewer.

Milestone 5: wires the LangGraph interview flow (question planning +
adaptive follow-up + evidence collection) into the live Gemini realtime
voice pipeline. Manual turn control is used so every agent utterance is
explicitly driven by the graph's decision — Gemini never auto-replies on
its own based on static instructions.

Milestone 6: adds persistent (SQLite) checkpointing, durable thread IDs,
HITL control hooks (pause/resume/skip/override/terminate), and
reconnect/resume so a dropped call picks back up where it left off
instead of restarting. Also fixes a real control-flow bug in the
previous milestone's turn-taking (see the comment above `awaiting_answer`
below) and keeps the background-analysis / realtime-critical-path split
from Milestone 5 completely unchanged — Gemini answer analysis is still
never on the turn-by-turn critical path.

Requires output/jd.json, resume.json, github.json, gap_analysis.json, and
interview_plan.json to already exist — run scripts/run_prep_pipeline.py first.
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
from src.interview.schemas import InterviewPlan, QuestionRecord, AnswerRecord, HITLStatus
from src.interview.state import InterviewState
from src.interview.graph import build_interview_graph
from src.interview.answer_analysis import analyze_answer, AnswerAnalysisUnavailable
from src.interview.checkpointer import open_sqlite_checkpointer
from src.interview.hitl import HITLController

load_dotenv()

logger = logging.getLogger(__name__)

OUTPUT_DIR = Path(__file__).resolve().parent.parent.parent / "output"


def _load_prep_artifacts():
    """Loads the output of the offline prep pipeline (Milestones 3B-4B)."""
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
    return jd, resume, github_evidence, gap_analysis, interview_plan


def _derive_thread_id(ctx: agents.JobContext, jd: JobDescription, resume: Resume) -> str:
    """
    Stable thread_id so a dropped/reconnected call resumes the SAME
    interview instead of starting a fresh one at intro. Preference order:

      1. An explicit interview id in job metadata, if your dispatch/
         scheduling system sets one (e.g. `ctx.job.metadata = "<uuid>"`
         chosen once when the interview is scheduled). This is the most
         reliable option — it is stable no matter how many times the
         candidate reconnects, even across different LiveKit rooms.
      2. The LiveKit room name. LiveKit gives a rejoin to the same room
         the same room name, so this is stable across a dropped call /
         rejoin within a single scheduled session.
      3. A last-resort fallback derived from candidate name + role. This
         is the weakest option — two different interviews for the same
         candidate/role on the same day would collide on thread_id. Only
         reached if neither (1) nor (2) is available. Flagged again in
         ARCHITECTURE.md: pass real job metadata in production instead of
         relying on this.
    """
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
    jd, resume, github_evidence, gap_analysis, interview_plan = _load_prep_artifacts()

    initial_state = InterviewState(
        candidate_name=resume.candidate_name,
        target_role=jd.title,
        jd=jd,
        resume=resume,
        github_evidence=github_evidence,
        gap_analysis=gap_analysis,
        interview_plan=interview_plan.questions,
    )

    thread_id = _derive_thread_id(ctx, jd, resume)
    config = {"configurable": {"thread_id": thread_id}}
    logger.info("interview thread_id=%s", thread_id)

    # Explicit, single-purpose control-flow flags, MUTATED IN PLACE only
    # (never reassigned) so every closure below always observes the
    # current value.
    #
    # BUGFIX (Milestone 6): the previous version of this file had
    #   awaiting_answer = {"value": False}
    #   processing_answer = {"value": False}
    # lines *inside* _advance_and_ask, near the end of the function. In
    # Python, that assignment makes both names LOCAL to _advance_and_ask
    # for the entire function body (a well-known closure gotcha), which
    # shadowed the outer dicts that _on_user_transcript reads. Combined
    # with there being no `awaiting_answer["value"] = True` anywhere,
    # this meant _on_user_transcript's `if not awaiting_answer["value"]:
    # return` was effectively always true — candidate transcripts could
    # be silently ignored. Fixed by declaring these once here, only ever
    # mutating `["value"]` (never rebinding the name) anywhere below, and
    # explicitly setting awaiting_answer["value"] = True right after a
    # question is actually asked (see _speak_question).
    awaiting_answer = {"value": False}
    processing_answer = {"value": False}

    # In-process mirror of HITL pause state, so the SYNCHRONOUS
    # `user_input_transcribed` event handler (LiveKit callbacks are not
    # awaitable) can cheaply check "are we paused?" without an async
    # round-trip to the checkpointer on every transcript. Kept in sync by
    # handle_pause/handle_resume below. LIMITATION: if something other
    # than this process's own handle_pause/handle_resume mutates
    # hitl_status directly against the SQLite file (e.g. a future MCP
    # tool running in a separate process), this mirror will be stale
    # until the next handle_pause/handle_resume call in THIS process —
    # see ARCHITECTURE.md.
    hitl_mirror = {"paused": False}

    # Serializes ALL writers to this interview's checkpointed state: the
    # main graph-advancing flow, background evidence analysis, and HITL
    # actions. Coarse-grained on purpose — turn-taking in a live
    # interview is inherently sequential, so the only realistic
    # contention is background analysis of a PREVIOUS turn overlapping
    # with the graph advancing to the NEXT turn or a HITL action; a
    # single lock makes that race impossible rather than merely unlikely.
    # See ARCHITECTURE.md for the finer-grained alternative considered
    # and why it wasn't worth the complexity here.
    state_lock = asyncio.Lock()

    async with open_sqlite_checkpointer() as checkpointer:
        graph = build_interview_graph(realtime_mode=True, checkpointer=checkpointer)
        hitl = HITLController(graph, config, state_lock)

        def _as_question_record(value) -> QuestionRecord:
            return value if isinstance(value, QuestionRecord) else QuestionRecord(**value)

        def _as_answer_record(value) -> AnswerRecord:
            return value if isinstance(value, AnswerRecord) else AnswerRecord(**value)

        async def _analyze_answer_background(question: QuestionRecord, answer: AnswerRecord) -> None:
            """
            Runs Gemini-based answer analysis OFF the realtime critical
            path. Unchanged from Milestone 5 except that persisting the
            result now goes through native async checkpoint calls
            (aget_state/aupdate_state against AsyncSqliteSaver) instead
            of asyncio.to_thread-wrapped sync ones — analyze_answer()
            itself is still a synchronous Gemini call, so IT still runs
            in a worker thread; only the state I/O around it changed.

            Must never block or crash the live interview: always runs in
            a worker thread, and any failure (503/429/timeout, or
            anything else) is logged and swallowed here rather than
            propagated. Worst case, that turn is simply missing from the
            final evidence report.
            """
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

        async def _finish_interview():
            await session.generate_reply(
                instructions=(
                    "Thank the candidate for their time, let them know "
                    "the interview is complete, and say goodbye warmly."
                )
            )
            awaiting_answer["value"] = False

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
            """
            Drives the graph forward exactly one step — either the very
            first invoke (resume_value=None) or resuming the current
            receive_answer interrupt with a candidate transcript or a
            HITL skip sentinel — then either speaks the next question or
            wraps up if the interview is now complete/terminated.

            All graph reads/writes for this step happen under
            state_lock, as a single unit, so a concurrent background
            evidence write or HITL action can't interleave with this
            step's own read-modify-write of state.
            """
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
                        # Background only — NEVER await this, and never
                        # start it while still holding state_lock (it
                        # acquires the same lock itself when it later
                        # persists evidence).
                        asyncio.create_task(
                            _analyze_answer_background(answered_question, answered_answer)
                        )

                values = (await graph.aget_state(config)).values

            if values.get("is_complete") or values.get("hitl_status") == HITLStatus.TERMINATED:
                await _finish_interview()
                return

            await _speak_question(values, first_question=(resume_value is None), reconnect=False)

        # --- HITL control hooks -------------------------------------------------
        # These are the integration points a control channel (an MCP tool,
        # a small admin endpoint, a CLI — deliberately not decided here,
        # see ARCHITECTURE.md) would call into. Wiring an actual
        # out-of-process transport to these is out of scope for this
        # milestone; what's implemented is the state machine + these
        # in-process hooks, ready to be exposed however you choose next.

        async def handle_pause(actor: str = "recruiter", note: str = "") -> None:
            await hitl.pause(actor=actor, note=note)
            hitl_mirror["paused"] = True
            awaiting_answer["value"] = False  # don't process a turn that arrives after pause

        async def handle_resume(actor: str = "recruiter", note: str = "") -> None:
            await hitl.resume(actor=actor, note=note)
            hitl_mirror["paused"] = False

        async def handle_skip(actor: str = "recruiter", note: str = "") -> None:
            sentinel = await hitl.skip_current_question(actor=actor, note=note)
            await _advance_and_ask(resume_value=sentinel)

        async def handle_override_question(
            question: QuestionRecord, actor: str = "recruiter", note: str = ""
        ) -> None:
            await hitl.override_next_question(question, actor=actor, note=note)

        async def handle_terminate(actor: str = "recruiter", note: str = "") -> None:
            await hitl.terminate(actor=actor, note=note)
            await _finish_interview()

        # --------------------------------------------------------------------

        @session.on("user_input_transcribed")
        def _on_user_transcript(ev):
            if not ev.is_final:
                return
            if not awaiting_answer["value"]:
                return
            if processing_answer["value"]:
                return
            if hitl_mirror["paused"]:
                # Candidate transcripts that arrive while paused are
                # intentionally dropped rather than advancing the
                # interview. There is currently no buffering/replay of a
                # dropped transcript on resume — see ARCHITECTURE.md.
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

        # START LIVEKIT SESSION
        await session.start(
            agent=Interviewer(resume.candidate_name),
            room=ctx.room,
        )

        # RESUME / RECOVERY: check for existing checkpointed state under
        # this thread_id BEFORE starting fresh. If found, this is a
        # reconnect (or a retry of a job that crashed mid-interview) —
        # re-synchronize local flags and re-prompt instead of restarting
        # from intro (which would re-run intro/ask_question and duplicate
        # state).
        existing = await graph.aget_state(config)

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


if __name__ == "__main__":
    agents.cli.run_app(server)