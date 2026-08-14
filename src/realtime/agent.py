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
import uuid
from pathlib import Path

from dotenv import load_dotenv
from livekit import agents
from livekit.agents import Agent, AgentServer, AgentSession
from livekit.plugins import google

from langgraph.types import Command

from src.ingestion.schemas import JobDescription, Resume, GitHubEvidence, GapAnalysis
from src.interview.schemas import InterviewPlan
from src.interview.state import InterviewState
from src.interview.graph import build_interview_graph

load_dotenv()

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
    graph = build_interview_graph()
    thread_id = f"interview-{uuid.uuid4().hex[:8]}"
    config = {"configurable": {"thread_id": thread_id}}

    session = AgentSession(
        llm=google.realtime.RealtimeModel(voice="Puck", temperature=0.7),
        turn_detection="manual",
    )

    awaiting_answer = {"value": False}

    def _current_question_text() -> str:
        last_question = graph.get_state(config).values["questions_asked"][-1]
        return last_question["text"] if isinstance(last_question, dict) else last_question.text

    def _is_complete() -> bool:
        return bool(graph.get_state(config).values["is_complete"])

    async def _advance_and_ask(resume_value=None):
        """Resumes the graph (or starts it) and speaks whatever it decides next."""
        if resume_value is None:
            graph.invoke(initial_state.model_dump(), config=config)
        else:
            graph.invoke(Command(resume=resume_value), config=config)

        if _is_complete():
            await session.generate_reply(
                instructions=(
                    "Thank the candidate for their time, let them know the "
                    "interview is complete, and say goodbye warmly."
                )
            )
            awaiting_answer["value"] = False
            return

        question_text = _current_question_text()
        is_first_question = resume_value is None

        if is_first_question:
            instructions = (
                f"Greet {resume.candidate_name} by name, briefly disclose that "
                f"you are an AI interviewer, and explain you'll be asking about "
                f"their background and experience for the {jd.title} role. Then "
                f"ask them exactly this question in your own natural words: {question_text}"
            )
        else:
            instructions = (
                f"Ask the candidate exactly this question, in your own natural words: {question_text}"
            )

        await session.generate_reply(instructions=instructions)
        awaiting_answer["value"] = True

    @session.on("user_input_transcribed")
    def _on_user_transcript(ev):
        if not ev.is_final or not awaiting_answer["value"]:
            return
        awaiting_answer["value"] = False
        session.commit_user_turn()
        asyncio.create_task(_advance_and_ask(resume_value=ev.transcript))

    await session.start(room=ctx.room, agent=Interviewer(candidate_name=resume.candidate_name))
    await _advance_and_ask()


if __name__ == "__main__":
    agents.cli.run_app(server)