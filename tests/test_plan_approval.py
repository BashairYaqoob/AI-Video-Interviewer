import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.interview.schemas import InterviewPlan, QuestionRecord, PlanApprovalStatus
from src.interview.plan_approval import (
    approve_plan, edit_and_approve_plan, reject_plan,
    load_plan_approval, get_approved_questions,
)


def check(condition, description):
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {description}")
    if not condition:
        raise AssertionError(description)


def make_plan():
    return InterviewPlan(
        introduction="intro",
        questions=[
            QuestionRecord(question_id="q1", text="Q1", competency="Python",
                            evidence_sought="x", difficulty="easy",
                            question_type="core_competency", follow_up_strategy="probe"),
        ],
        closing="closing",
    )


def test_no_approval_record_blocks_start():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "approval.json"
        plan = make_plan()
        try:
            get_approved_questions(plan, path=path)
            check(False, "should have raised when no approval record exists")
        except RuntimeError:
            check(True, "get_approved_questions raises when unapproved")


def test_approve_as_is_uses_original_questions():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "approval.json"
        plan = make_plan()
        approve_plan(path=path)
        questions = get_approved_questions(plan, path=path)
        check(questions == plan.questions, "approve_plan uses original questions unchanged")


def test_edit_and_approve_overrides_questions():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "approval.json"
        plan = make_plan()
        edited = [QuestionRecord(question_id="q1-edited", text="Edited Q1", competency="Python",
                                   evidence_sought="x", difficulty="hard",
                                   question_type="core_competency", follow_up_strategy="probe harder")]
        edit_and_approve_plan(edited, path=path)
        questions = get_approved_questions(plan, path=path)
        check(questions[0].question_id == "q1-edited", "edited questions override the original plan")


def test_rejected_plan_blocks_start():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "approval.json"
        plan = make_plan()
        reject_plan(note="not good enough", path=path)
        record = load_plan_approval(path)
        check(record.status == PlanApprovalStatus.REJECTED, "rejection recorded")
        try:
            get_approved_questions(plan, path=path)
            check(False, "should have raised on rejected plan")
        except RuntimeError:
            check(True, "get_approved_questions raises when rejected")


if __name__ == "__main__":
    test_no_approval_record_blocks_start()
    test_approve_as_is_uses_original_questions()
    test_edit_and_approve_overrides_questions()
    test_rejected_plan_blocks_start()
    print("\nAll plan approval tests passed.")