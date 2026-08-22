"""
plan_approval.py

Phase 2 (post-Milestone 6) — pre-interview question-plan HITL approval
gate. Separate from HITLController (src/interview/hitl.py), which only
controls an interview ALREADY in progress. This module governs whether
an interview is allowed to start at all.

Persisted as output/interview_plan_approval.json, sitting next to (but
never overwriting) output/interview_plan.json.
"""

import time
from pathlib import Path
from typing import List, Optional

from src.interview.schemas import (
    InterviewPlan,
    QuestionRecord,
    PlanApprovalRecord,
    PlanApprovalStatus,
)

OUTPUT_DIR = Path(__file__).resolve().parent.parent.parent / "output"
APPROVAL_PATH = OUTPUT_DIR / "interview_plan_approval.json"


def load_plan_approval(path: Path = APPROVAL_PATH) -> Optional[PlanApprovalRecord]:
    if not path.exists():
        return None
    return PlanApprovalRecord.model_validate_json(path.read_text(encoding="utf-8"))


def _save(record: PlanApprovalRecord, path: Path = APPROVAL_PATH) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(record.model_dump_json(indent=2), encoding="utf-8")
    return path


def approve_plan(actor: str = "recruiter", note: str = "", path: Path = APPROVAL_PATH) -> PlanApprovalRecord:
    """Approve the plan exactly as generated — no edits."""
    record = PlanApprovalRecord(
        status=PlanApprovalStatus.APPROVED,
        actor=actor,
        timestamp=time.time(),
        note=note,
        approved_questions=None,
    )
    _save(record, path)
    return record


def edit_and_approve_plan(
    edited_questions: List[QuestionRecord],
    actor: str = "recruiter",
    note: str = "",
    path: Path = APPROVAL_PATH,
) -> PlanApprovalRecord:
    """Approve a recruiter-modified question list (reordered/edited/
    removed/added questions). This is the final list agent.py will use."""
    record = PlanApprovalRecord(
        status=PlanApprovalStatus.APPROVED,
        actor=actor,
        timestamp=time.time(),
        note=note,
        approved_questions=edited_questions,
    )
    _save(record, path)
    return record


def reject_plan(actor: str = "recruiter", note: str = "", path: Path = APPROVAL_PATH) -> PlanApprovalRecord:
    record = PlanApprovalRecord(
        status=PlanApprovalStatus.REJECTED,
        actor=actor,
        timestamp=time.time(),
        note=note,
        approved_questions=None,
    )
    _save(record, path)
    return record


def get_approved_questions(interview_plan: InterviewPlan, path: Path = APPROVAL_PATH) -> List[QuestionRecord]:
    """Raises if the plan is not approved. Returns the edited list if the
    recruiter edited it, otherwise the original plan's questions."""
    record = load_plan_approval(path)
    if record is None or record.status != PlanApprovalStatus.APPROVED:
        status = record.status.value if record else "no approval record found"
        raise RuntimeError(
            f"Interview plan is not approved (status: {status}). "
            f"Run scripts/approve_plan.py before starting the live agent."
        )
    return record.approved_questions if record.approved_questions is not None else interview_plan.questions