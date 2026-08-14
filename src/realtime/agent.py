"""
agent.py

LiveKit Agent — AI Video Interviewer.

Milestone 5: wires the LangGraph interview flow (question planning +
adaptive follow-up + evidence collection) into the live Gemini realtime
voice pipeline. Manual turn control is used so every agent utterance is
explicitly driven by the graph's decision — Gemini never auto-replies on
its own based on static instructions.

Requires output/jd.json, resume.json, github.json, gap_analysis.json, and
interview_plan.json to already exist — run scripts/run_prep_pipeline.py first.
"""

import asyncio
import logging
import uuid
from pathlib import Path

from dotenv import load_dotenv
from livekit import agents
from livekit.agents import Agent, AgentServer, AgentSession, TurnHandlingOptions
from livekit.plugins import google
from google.genai import types

from langgraph.types import Command

from src.ingestion.schemas import JobDescription, Resume, GitHubEvidence, GapAnalysis
from src.interview.schemas import InterviewPlan, QuestionRecord, AnswerRecord
from src.interview.state import InterviewState
from src.interview.graph import build_interview_graph
from src.interview.answer_analysis import analyze_answer, AnswerAnalysisUnavailable

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

    # In-memory checkpointer for now — Milestone 6 swaps in SQLite for real
    # dropped-call resume.
    #
    # realtime_mode=True: routing after an answer uses the cheap local
    # heuristic (route_immediate) instead of waiting on Gemini-based
    # answer analysis. Analysis still happens — see
    # _analyze_answer_background below — but purely in the background,
    # never gating what question gets asked next.
    graph = build_interview_graph(realtime_mode=True)
    thread_id = f"interview-{uuid.uuid4().hex[:8]}"
    config = {"configurable": {"thread_id": thread_id}}

    # Serializes background evidence writes so two overlapping analysis
    # tasks can't clobber each other's read-modify-write of
    # evidence_collected.
    evidence_lock = asyncio.Lock()

    def _as_question_record(value) -> QuestionRecord:
        return value if isinstance(value, QuestionRecord) else QuestionRecord(**value)

    def _as_answer_record(value) -> AnswerRecord:
        return value if isinstance(value, AnswerRecord) else AnswerRecord(**value)

    async def _analyze_answer_background(question: QuestionRecord, answer: AnswerRecord) -> None:
        """
        Runs Gemini-based answer analysis OFF the realtime critical path.

        This must never block or crash the live interview: it always
        runs in a worker thread, and any failure (503/429/timeout, or
        anything else) is logged and swallowed here rather than
        propagated. Worst case, that turn is simply missing from the
        final evidence report — the interview itself is never affected.
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
            async with evidence_lock:
                current = graph.get_state(config).values.get("evidence_collected", [])
                await asyncio.to_thread(
                    graph.update_state, config, {"evidence_collected": current + [evidence]}
                )
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


    awaiting_answer = {"value": False}

    def _current_question_text() -> str:
        last_question = graph.get_state(config).values["questions_asked"][-1]
        return last_question["text"] if isinstance(last_question, dict) else last_question.text

    def _is_complete() -> bool:
        return bool(graph.get_state(config).values["is_complete"])

    async def _advance_and_ask(resume_value=None):
        logger.info(
            "ADVANCE_AND_ASK resume=%r phase=%s",
            resume_value,
            graph.get_state(config).values.get("current_phase"),
        )

        if resume_value is None:
            await asyncio.to_thread(
                graph.invoke,
                initial_state.model_dump(),
                config=config,
            )
        else:
            # Capture question/answer BEFORE graph advances further.
            pre_state = graph.get_state(config).values

            answered_question = _as_question_record(
                pre_state["questions_asked"][-1]
            )

            await asyncio.to_thread(
                graph.invoke,
                Command(resume=resume_value),
                config=config,
            )

            post_state = graph.get_state(config).values

            answered_answer = _as_answer_record(
                post_state["candidate_answers"][-1]
            )

            # Background only — NEVER await this.
            asyncio.create_task(
                _analyze_answer_background(
                    answered_question,
                    answered_answer,
                )
            )

        if _is_complete():
            await session.generate_reply(
                instructions=(
                    "Thank the candidate for their time, "
                "let them know the interview is complete, "
                    "and say goodbye warmly."
                )
            )
            awaiting_answer["value"] = False
            return

        question_text = _current_question_text()

        is_first_question = resume_value is None

        if is_first_question:
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

        await session.generate_reply(
            instructions=instructions
        )

        awaiting_answer = {"value": False}
        processing_answer = {"value": False}

    @session.on("user_input_transcribed")
    def _on_user_transcript(ev):
        if not ev.is_final:
            return

        if not awaiting_answer["value"]:
            return

        if processing_answer["value"]:
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
    # Start graph and ask first question
    await _advance_and_ask()

if __name__ == "__main__":
    agents.cli.run_app(server)