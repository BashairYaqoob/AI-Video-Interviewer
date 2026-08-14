"""
test_question_plan_schema.py

Milestone 4B acceptance test — question plan schema validation.

Does NOT call Gemini. Validates that InterviewPlan/QuestionRecord accept
well-formed data and reject malformed data — the same validation that
protects the graph from a bad Gemini response.
"""

import sys
from pathlib import Path

import pydantic

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.interview.schemas import InterviewPlan, QuestionRecord


def check(condition: bool, description: str):
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {description}")
    if not condition:
        raise AssertionError(description)


def test_valid_plan_validates():
    plan = InterviewPlan(
        introduction="Greet the candidate warmly and explain the format.",
        questions=[
            QuestionRecord(
                question_id="q1",
                text="Walk me through your rag-chatbot repository.",
                competency="RAG systems",
                evidence_sought="specific chunking/retrieval decisions",
                difficulty="medium",
                question_type="github",
                follow_up_strategy="ask about a specific retrieval failure mode",
            )
        ],
        closing="Thank the candidate and explain next steps.",
    )
    check(len(plan.questions) == 1, "plan: accepts a well-formed question list")
    check(plan.questions[0].question_type == "github", "plan: question_type preserved")


def test_missing_required_field_rejected():
    try:
        QuestionRecord(
            question_id="q1",
            text="Some question",
            competency="Python",
            # evidence_sought intentionally missing
            difficulty="easy",
            question_type="core_competency",
            follow_up_strategy="probe deeper",
        )
        check(False, "plan: should reject a QuestionRecord missing evidence_sought")
    except pydantic.ValidationError:
        check(True, "plan: correctly rejected malformed QuestionRecord")


if __name__ == "__main__":
    print("Running Milestone 4B question plan schema tests...\n")
    test_valid_plan_validates()
    test_missing_required_field_rejected()
    print("\nAll question plan schema tests passed.")