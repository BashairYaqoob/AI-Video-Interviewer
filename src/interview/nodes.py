"""
nodes.py

LangGraph node functions for the interview state machine (Milestone 4C).

Each node takes the current InterviewState (a validated Pydantic instance)
and returns a dict of fields to update. Kept explicit and simple for viva
explainability — this is interview control + evidence collection ONLY,
no scoring.
"""

from langgraph.types import interrupt

from src.interview.state import InterviewState, InterviewPhase
from src.interview.schemas import QuestionRecord, AnswerRecord


def intro_node(state: InterviewState) -> dict:
    """Marks the interview as started and ready to ask the first question."""
    return {
        "current_phase": InterviewPhase.QUESTIONING,
        "current_question_index": 0,
    }


def ask_question_node(state: InterviewState) -> dict:
    """
    Selects the current question from the interview plan and records it
    as asked. This node is about interview control/state only — actually
    speaking the question is the (not-yet-built) realtime layer's job.
    """
    question = state.interview_plan[state.current_question_index]
    return {"questions_asked": state.questions_asked + [question]}


def receive_answer_node(state: InterviewState) -> dict:
    """
    Pauses graph execution and waits for the candidate's answer to the
    most recently asked question. Resumed with Command(resume="...") —
    in tests, by the test itself; later, this is where a live transcript
    turn will resume the graph.
    """
    current_question = state.questions_asked[-1]
    answer_text = interrupt({"awaiting_answer_for_question_id": current_question.question_id})
    answer = AnswerRecord(question_id=current_question.question_id, text=answer_text)
    return {"candidate_answers": state.candidate_answers + [answer]}


def analyze_answer_node(state: InterviewState, analyzer) -> dict:
    """
    Runs answer analysis (Milestone 4D) on the most recent question/answer
    pair. `analyzer` is injected by the graph builder so tests can supply
    a fake, deterministic analyzer instead of calling Gemini.
    """
    question = state.questions_asked[-1]
    answer = state.candidate_answers[-1]

    evidence = analyzer(
        question=question,
        answer=answer,
        jd=state.jd,
        resume=state.resume,
        github_evidence=state.github_evidence,
    )
    evidence.question_id = question.question_id  # always trust the real question, not the model's guess

    return {"evidence_collected": state.evidence_collected + [evidence]}


def ask_follow_up_node(state: InterviewState) -> dict:
    """
    Turns the most recent evidence analysis's suggested follow-up
    direction into a new question, appended to questions_asked, and
    increments the follow-up counter (capped elsewhere, in router.py).
    """
    last_evidence = state.evidence_collected[-1]
    last_question = state.questions_asked[-1]

    follow_up_question = QuestionRecord(
        question_id=f"{last_question.question_id}-followup-{state.follow_up_count + 1}",
        text=last_evidence.suggested_follow_up_direction or "Could you elaborate further on that?",
        competency=last_question.competency,
        evidence_sought=last_question.evidence_sought,
        difficulty=last_question.difficulty,
        question_type="follow_up",
        follow_up_strategy="probe deeper on same topic",
    )

    return {
        "questions_asked": state.questions_asked + [follow_up_question],
        "follow_up_count": state.follow_up_count + 1,
    }


def advance_question_node(state: InterviewState) -> dict:
    """Moves to the next question in the plan and resets the follow-up counter."""
    return {
        "current_question_index": state.current_question_index + 1,
        "follow_up_count": 0,
    }


def closing_node(state: InterviewState) -> dict:
    """Marks the interview as complete."""
    return {
        "current_phase": InterviewPhase.COMPLETE,
        "is_complete": True,
    }