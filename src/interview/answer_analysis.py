"""
answer_analysis.py

Milestone 4D — Answer analysis.

Given a question, the candidate's answer, and JD/resume/GitHub context,
produces structured EvidenceRecord: relevance, evidence found, claims
made, missing evidence, and whether a follow-up is warranted. This is
evidence collection, NOT final scoring.
"""

import logging
import os
import time
from pathlib import Path

from dotenv import load_dotenv
from google import genai

from src.interview.schemas import QuestionRecord, AnswerRecord, EvidenceRecord
from src.ingestion.schemas import JobDescription, Resume, GitHubEvidence

load_dotenv()

logger = logging.getLogger(__name__)

API_KEY = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
MODEL_NAME = os.getenv("GEMINI_TEXT_MODEL", "gemini-flash-latest")

PROMPTS_DIR = Path(__file__).resolve().parent.parent.parent / "prompts"

# answer analysis runs off the realtime critical path (background thread —
# see src/realtime/agent.py), so it's fine for this to retry synchronously.
# This is purely resilience against transient 503/429; it does not change
# what gets asked next, since routing no longer waits on this result.
MAX_ANALYSIS_ATTEMPTS = 2
RETRY_BACKOFF_SECONDS = 1.5


class AnswerAnalysisUnavailable(RuntimeError):
    """Raised when Gemini answer analysis fails after retries. Callers
    (the background task in src/realtime/agent.py) must catch this and
    simply skip persisting evidence for that turn — it must never take
    down the interview."""


def _load_prompt(filename: str) -> str:
    return (PROMPTS_DIR / filename).read_text(encoding="utf-8")


def _get_client() -> genai.Client:
    if not API_KEY:
        raise RuntimeError("GEMINI_API_KEY or GOOGLE_API_KEY not set in .env")
    return genai.Client(api_key=API_KEY)


def analyze_answer(
    question: QuestionRecord,
    answer: AnswerRecord,
    jd: JobDescription,
    resume: Resume,
    github_evidence: GitHubEvidence,
) -> EvidenceRecord:
    """
    Real Gemini-based answer analyzer — the default analyzer used by the
    interview graph. Tests inject a fake analyzer instead of this one.
    """
    client = _get_client()
    instructions = _load_prompt("answer_analysis_v1.txt")

    context = (
        f"QUESTION: {question.text}\n"
        f"COMPETENCY BEING TESTED: {question.competency}\n"
        f"EVIDENCE SOUGHT: {question.evidence_sought}\n\n"
        f"CANDIDATE ANSWER: {answer.text}\n\n"
        f"RELEVANT RESUME SKILLS: {', '.join(resume.skills)}\n"
        f"RELEVANT GITHUB REPOS: {', '.join(r.name for r in github_evidence.repositories)}\n"
    )

    last_error = None
    for attempt in range(1, MAX_ANALYSIS_ATTEMPTS + 1):
        try:
            response = client.models.generate_content(
                model=MODEL_NAME,
                contents=f"{instructions}\n\n---\n{context}",
                config={
                    "response_mime_type": "application/json",
                    "response_schema": EvidenceRecord,
                },
            )
            return response.parsed
        except Exception as exc:  # e.g. 503 UNAVAILABLE, 429 rate limit, timeout
            last_error = exc
            logger.warning(
                "answer analysis attempt %d/%d failed for question %s: %s",
                attempt, MAX_ANALYSIS_ATTEMPTS, question.question_id, exc,
            )
            if attempt < MAX_ANALYSIS_ATTEMPTS:
                time.sleep(RETRY_BACKOFF_SECONDS)

    raise AnswerAnalysisUnavailable(
        f"answer analysis failed after {MAX_ANALYSIS_ATTEMPTS} attempts for "
        f"question {question.question_id}"
    ) from last_error