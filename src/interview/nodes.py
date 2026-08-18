"""
nodes.py

LangGraph node functions for the interview state machine (Milestone 4C,
extended in Milestone 6 for HITL override/skip).

Each node takes the current InterviewState (a validated Pydantic instance)
and returns a dict of fields to update. Kept explicit and simple for viva
explainability — this is interview control + evidence collection ONLY,
no scoring.
"""

from langgraph.types import interrupt

from src.interview.state import InterviewState, InterviewPhase
from src.interview.schemas import QuestionRecord, AnswerRecord, HITL_SKIP_SENTINEL_KEY


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
    speaking the question is the realtime layer's job.

    Milestone 6 (HITL): if a recruiter has set hitl_override_question
    (via HITLController.override_next_question — see src/interview/hitl.py),
    that question is asked INSTEAD of interview_plan[current_question_index]
    for this turn, and the override is cleared immediately after use so it
    only ever applies once. current_question_index is untouched by an
    override — it still tracks position in the original plan, so
    advance_question_node continues to move through the plan normally on
    the following turn.
    """
    if state.hitl_override_question is not None:
        question = state.hitl_override_question
        return {
            "questions_asked": state.questions_asked + [question],
            "hitl_override_question": None,
        }

    question = state.interview_plan[state.current_question_index]
    return {"questions_asked": state.questions_asked + [question]}


def receive_answer_node(state: InterviewState) -> dict:
    """
    Pauses graph execution and waits for the candidate's answer to the
    most recently asked question. Resumed with Command(resume="...") —
    in tests, by the test itself; live, by a transcript turn; or, for a
    HITL skip, by Command(resume={HITL_SKIP_SENTINEL_KEY: True}) (see
    HITLController.skip_current_question in src/interview/hitl.py).

    A skip is recorded as a real AnswerRecord with skipped=True and
    empty/placeholder text, rather than being silently dropped, so the
    transcript and evidence trail both show what actually happened.
    Routers (router.py) must check answer.skipped and bypass follow-up
    logic for it.
    """
    current_question = state.questions_asked[-1]
    resume_value = interrupt({"awaiting_answer_for_question_id": current_question.question_id})

    if isinstance(resume_value, dict) and resume_value.get(HITL_SKIP_SENTINEL_KEY):
        answer = AnswerRecord(
            question_id=current_question.question_id,
            text="[skipped by recruiter]",
            skipped=True,
        )
    else:
        answer = AnswerRecord(question_id=current_question.question_id, text=resume_value)

    return {"candidate_answers": state.candidate_answers + [answer]}


def analyze_answer_node(state: InterviewState, analyzer) -> dict:
    """
    Runs answer analysis (Milestone 4D) on the most recent question/answer
    pair. `analyzer` is injected by the graph builder so tests can supply
    a fake, deterministic analyzer instead of calling Gemini.

    A skipped answer (HITL) is never sent to the analyzer — there is
    nothing to evaluate, and the router bypasses this node's output for
    skipped turns anyway (see router.route_after_analysis).
    """
    question = state.questions_asked[-1]
    answer = state.candidate_answers[-1]

    if answer.skipped:
        return {}

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

    In realtime_mode, routing to this node happens via route_immediate
    (router.py), which decides BEFORE the Gemini-based evidence analysis
    for the current answer has run (that analysis is backgrounded — see
    src/realtime/agent.py). So evidence_collected may not yet contain a
    record for last_question, or may still hold a stale record from an
    earlier question. Only use it when it actually matches; otherwise
    fall back to a generic probe rather than reusing a mismatched
    suggestion.
    """
    last_question = state.questions_asked[-1]

    follow_up_text = "Could you elaborate further on that?"
    if state.evidence_collected:
        last_evidence = state.evidence_collected[-1]
        if (
            last_evidence.question_id == last_question.question_id
            and last_evidence.suggested_follow_up_direction
        ):
            follow_up_text = last_evidence.suggested_follow_up_direction

    follow_up_question = QuestionRecord(
        question_id=f"{last_question.question_id}-followup-{state.follow_up_count + 1}",
        text=follow_up_text,
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