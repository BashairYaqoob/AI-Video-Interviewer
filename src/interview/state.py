"""
state.py

Milestone 4A — Interview state model.

InterviewState is the single Pydantic object that flows through the
LangGraph interview graph (Milestone 4C). It holds who the candidate is,
what they're being assessed against, the approved plan, and everything
collected so far during the live interview.
"""

from enum import Enum
from typing import List

from pydantic import BaseModel, Field

from src.ingestion.schemas import JobDescription, Resume, GitHubEvidence, GapAnalysis
from src.interview.schemas import QuestionRecord, AnswerRecord, EvidenceRecord


class InterviewPhase(str, Enum):
    INTRO = "intro"
    QUESTIONING = "questioning"
    FOLLOW_UP = "follow_up"
    CLOSING = "closing"
    COMPLETE = "complete"


class InterviewState(BaseModel):
    # Candidate + role context (set once, at interview start)
    candidate_name: str
    target_role: str
    jd: JobDescription
    resume: Resume
    github_evidence: GitHubEvidence
    gap_analysis: GapAnalysis

    # The approved question plan this interview follows
    interview_plan: List[QuestionRecord] = Field(default_factory=list)

    # Live progress through the plan
    current_phase: InterviewPhase = InterviewPhase.INTRO
    current_question_index: int = 0
    follow_up_count: int = 0  # resets to 0 for each new plan question

    # Everything collected during the interview so far
    questions_asked: List[QuestionRecord] = Field(default_factory=list)
    candidate_answers: List[AnswerRecord] = Field(default_factory=list)
    evidence_collected: List[EvidenceRecord] = Field(default_factory=list)

    is_complete: bool = False