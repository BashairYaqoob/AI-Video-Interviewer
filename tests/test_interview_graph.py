"""
test_interview_graph.py

Milestone 4C + 4E acceptance test — LangGraph interview flow.

Uses a FAKE analyzer (no Gemini calls) to deterministically test routing:
sufficient answers advance straight to the next question / closing;
insufficient answers trigger a follow-up, capped by MAX_FOLLOW_UPS.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from langgraph.types import Command

from src.interview.graph import build_interview_graph
from src.interview.state import InterviewState, InterviewPhase
from src.interview.schemas import QuestionRecord, EvidenceRecord
from src.ingestion.schemas import JobDescription, Resume, GitHubEvidence, GapAnalysis


def check(condition: bool, description: str):
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {description}")
    if not condition:
        raise AssertionError(description)


def make_initial_state(num_questions: int = 2) -> InterviewState:
    plan = [
        QuestionRecord(
            question_id=f"q{i+1}",
            text=f"Question {i+1} text",
            competency="Python",
            evidence_sought="specific example",
            difficulty="medium",
            question_type="core_competency",
            follow_up_strategy="ask for a specific example",
        )
        for i in range(num_questions)
    ]
    return InterviewState(
        candidate_name="Jane Candidate",
        target_role="Junior AI Engineer",
        jd=JobDescription(title="Junior AI Engineer", seniority="0-2 years"),
        resume=Resume(candidate_name="Jane Candidate"),
        github_evidence=GitHubEvidence(username="jane", profile_url="https://github.com/jane"),
        gap_analysis=GapAnalysis(),
        interview_plan=plan,
    )


def make_fake_analyzer(responses):
    """Returns canned EvidenceRecord objects in sequence, one per call."""
    responses = list(responses)

    def _analyzer(question, answer, jd, resume, github_evidence):
        return responses.pop(0)

    return _analyzer


def test_two_sufficient_answers_reach_completion():
    responses = [
        EvidenceRecord(relevance="high", follow_up_warranted=False),
        EvidenceRecord(relevance="high", follow_up_warranted=False),
    ]
    graph = build_interview_graph(analyzer=make_fake_analyzer(responses))
    config = {"configurable": {"thread_id": "test-thread-1"}}

    initial_state = make_initial_state(num_questions=2)
    graph.invoke(initial_state.model_dump(), config=config)  # runs to first interrupt

    graph.invoke(Command(resume="My answer to question 1"), config=config)  # -> interrupt at Q2
    final_state = graph.invoke(Command(resume="My answer to question 2"), config=config)

    check(final_state["is_complete"] is True, "graph: interview marked complete after last question")
    check(final_state["current_phase"] == InterviewPhase.COMPLETE, "graph: phase is COMPLETE")
    check(len(final_state["evidence_collected"]) == 2, "graph: 2 evidence records collected, no follow-ups")


def test_follow_up_triggered_and_capped():
    responses = [
        EvidenceRecord(relevance="low", follow_up_warranted=True,
                        suggested_follow_up_direction="ask for a specific example"),
        EvidenceRecord(relevance="medium", follow_up_warranted=False),
    ]
    graph = build_interview_graph(analyzer=make_fake_analyzer(responses))
    config = {"configurable": {"thread_id": "test-thread-2"}}

    initial_state = make_initial_state(num_questions=1)
    graph.invoke(initial_state.model_dump(), config=config)  # -> interrupt waiting for answer to q1

    graph.invoke(Command(resume="a vague answer"), config=config)  # analyzed -> follow_up -> interrupt again
    final_state = graph.invoke(Command(resume="a more specific answer"), config=config)

    check(final_state["is_complete"] is True, "graph: interview completes after follow-up resolved")
    check(len(final_state["questions_asked"]) == 2, "graph: follow-up question was asked (2 total questions)")
    check(final_state["follow_up_count"] == 1, "graph: exactly one follow-up occurred before closing")


if __name__ == "__main__":
    print("Running Milestone 4C/4E interview graph routing tests (fake analyzer, no Gemini calls)...\n")
    test_two_sufficient_answers_reach_completion()
    test_follow_up_triggered_and_capped()
    print("\nAll interview graph tests passed.")