"""
schemas.py

Pydantic schemas for the interview intelligence layer (Milestones 4A-4D).
"""

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


class EvidenceRecord(BaseModel):
    question_id: str = ""
    relevance: str  # "high" | "medium" | "low"
    evidence_found: List[str] = Field(default_factory=list)
    claims_made: List[str] = Field(default_factory=list)
    missing_evidence: List[str] = Field(default_factory=list)
    follow_up_warranted: bool
    suggested_follow_up_direction: str = ""