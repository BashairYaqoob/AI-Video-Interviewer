"""
state.py

Milestone 4A — Interview state model. Extended in Milestone 6 with HITL
control fields so pause/resume/skip/override/terminate state is part of
the SAME checkpointed InterviewState as everything else -- durable for
free via the SQLite checkpointer, with no separate persistence path to
keep in sync.

InterviewState is the single Pydantic object that flows through the
LangGraph interview graph (Milestone 4C). It holds who the candidate is,
what they're being assessed against, the approved plan, and everything
collected so far during the live interview.
"""

from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field

from src.ingestion.schemas import JobDescription, Resume, GitHubEvidence, GapAnalysis
from src.interview.schemas import (
    QuestionRecord,
    AnswerRecord,
    EvidenceRecord,
    HITLStatus,
    HITLActionRecord,
)


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

    # --- Milestone 6: HITL control state ---
    # RUNNING/PAUSED/TERMINATED. Read by the realtime agent before every
    # turn to decide whether to keep driving the interview forward.
    hitl_status: HITLStatus = HITLStatus.RUNNING
    # When set, ask_question_node asks THIS question instead of the next
    # one from interview_plan, then clears the field. Lets a recruiter
    # replace the content of the upcoming question without touching the
    # plan or current_question_index.
    hitl_override_question: Optional[QuestionRecord] = None
    # Durable, append-only audit log of every HITL action taken, so
    # "what did the recruiter do and when" survives a restart same as
    # everything else.
    hitl_actions_log: List[HITLActionRecord] = Field(default_factory=list)