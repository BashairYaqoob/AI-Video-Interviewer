"""
answer_analysis.py

Milestone 4D — Answer analysis.

Given a question, the candidate's answer, and JD/resume/GitHub context,
produces structured EvidenceRecord: relevance, evidence found, claims
made, missing evidence, and whether a follow-up is warranted. This is
evidence collection, NOT final scoring.
"""

import os
from pathlib import Path

from dotenv import load_dotenv
from google import genai

from src.interview.schemas import QuestionRecord, AnswerRecord, EvidenceRecord
from src.ingestion.schemas import JobDescription, Resume, GitHubEvidence

load_dotenv()

API_KEY = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
MODEL_NAME = os.getenv("GEMINI_TEXT_MODEL", "gemini-flash-latest")

PROMPTS_DIR = Path(__file__).resolve().parent.parent.parent / "prompts"


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

    response = client.models.generate_content(
        model=MODEL_NAME,
        contents=f"{instructions}\n\n---\n{context}",
        config={
            "response_mime_type": "application/json",
            "response_schema": EvidenceRecord,
        },
    )
    return response.parsed