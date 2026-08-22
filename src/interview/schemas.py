"""
schemas.py

Pydantic schemas for the interview intelligence layer (Milestones 4A-4D,
extended in Milestone 6 with HITL records).
"""

from enum import Enum
from typing import List

from pydantic import BaseModel, Field


class QuestionRecord(BaseModel):
    question_id: str
    text: str
    competency: str
    evidence_sought: str
    difficulty: str          # "easy" | "medium" | "hard"
    question_type: str       # "core_competency" | "resume" | "github" |
                              # "gap_probe" | "behavioral" | "follow_up" | "closing"
    follow_up_strategy: str


class InterviewPlan(BaseModel):
    introduction: str
    questions: List[QuestionRecord] = Field(default_factory=list)
    closing: str


class AnswerRecord(BaseModel):
    question_id: str
    text: str
    # Milestone 6: set when this "answer" was actually a HITL skip
    # (see nodes.receive_answer_node / router.py) rather than something
    # the candidate said. Routers must not run follow-up logic on a
    # skipped answer.
    skipped: bool = False


class EvidenceRecord(BaseModel):
    question_id: str = ""
    relevance: str  # "high" | "medium" | "low"
    evidence_found: List[str] = Field(default_factory=list)
    claims_made: List[str] = Field(default_factory=list)
    missing_evidence: List[str] = Field(default_factory=list)
    follow_up_warranted: bool
    suggested_follow_up_direction: str = ""


# --- Milestone 6: HITL (human-in-the-loop) records ---------------------

class HITLStatus(str, Enum):
    RUNNING = "running"
    PAUSED = "paused"
    TERMINATED = "terminated"


class HITLActionRecord(BaseModel):
    """One durable, audit-log entry for a recruiter control action."""
    action: str  # "pause" | "resume" | "skip" | "override_question" | "terminate"
    actor: str = "recruiter"
    timestamp: float
    note: str = ""


# Sentinel key used to resume a paused `interrupt()` in receive_answer_node
# with a HITL "skip this question" instruction instead of a real candidate
# answer. Shared between nodes.py (consumer) and hitl.py (producer) so
# there is exactly one definition of what a "skip" resume value looks like.
HITL_SKIP_SENTINEL_KEY = "__hitl_skip__"

class PlanApprovalStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class PlanApprovalRecord(BaseModel):
    """Durable record of the recruiter's approve/edit/reject decision on
    the generated interview_plan.json, BEFORE any live interview may
    start. Kept separate from InterviewPlan itself (rather than adding
    fields to it) because InterviewPlan is Gemini's structured-output
    schema in question_planner.py — mixing approval bookkeeping into it
    would leak into the LLM response schema.
    """
    status: PlanApprovalStatus = PlanApprovalStatus.PENDING
    actor: str = "recruiter"
    timestamp: float = 0.0
    note: str = ""
    # If the recruiter edited the plan, the FINAL question list to use
    # for the interview. If None, the original interview_plan.json
    # questions are used unchanged.
    approved_questions: List[QuestionRecord] | None = None