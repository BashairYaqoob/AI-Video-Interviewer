"""
question_planner.py

Milestone 4B — Question Planner.

Combines JD + Resume + GitHub evidence + Gap Analysis into a structured
InterviewPlan, using Gemini structured output. Prompt lives in
prompts/question_planner_v1.txt, not hardcoded here.
"""

import os
from pathlib import Path

from dotenv import load_dotenv
from google import genai

from src.ingestion.schemas import JobDescription, Resume, GitHubEvidence, GapAnalysis
from src.interview.schemas import InterviewPlan

load_dotenv()

API_KEY = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
MODEL_NAME = os.getenv("GEMINI_TEXT_MODEL", "gemini-flash-latest")

PROMPTS_DIR = Path(__file__).resolve().parent.parent.parent / "prompts"
OUTPUT_DIR = Path(__file__).resolve().parent.parent.parent / "output"


def _load_prompt(filename: str) -> str:
    return (PROMPTS_DIR / filename).read_text(encoding="utf-8")


def _get_client() -> genai.Client:
    if not API_KEY:
        raise RuntimeError("GEMINI_API_KEY or GOOGLE_API_KEY not set in .env")
    return genai.Client(api_key=API_KEY)


def build_question_plan(
    jd: JobDescription,
    resume: Resume,
    github_evidence: GitHubEvidence,
    gap_analysis: GapAnalysis,
) -> InterviewPlan:
    client = _get_client()
    instructions = _load_prompt("question_planner_v1.txt")

    github_summary = "\n".join(
        f"- {repo.name}: languages={repo.languages}, "
        f"readme_excerpt={repo.readme_excerpt[:300]!r}"
        for repo in github_evidence.repositories
    ) or "(no GitHub repositories found)"

    gap_summary = (
        f"Matched: {[e.requirement for e in gap_analysis.matched]}\n"
        f"Weak/unverified: {[e.requirement for e in gap_analysis.weak_unverified]}\n"
        f"Missing: {[e.requirement for e in gap_analysis.missing]}"
    )

    context = (
        f"JOB DESCRIPTION\n"
        f"Title: {jd.title}, Seniority: {jd.seniority}\n"
        f"Must-have skills: {jd.must_have_skills}\n"
        f"Nice-to-have skills: {jd.nice_to_have_skills}\n"
        f"Competencies: {jd.competencies}\n\n"
        f"RESUME\n"
        f"Candidate: {resume.candidate_name}\n"
        f"Skills: {resume.skills}\n"
        f"Projects: {[p.name for p in resume.projects]}\n\n"
        f"GITHUB EVIDENCE\n{github_summary}\n\n"
        f"GAP ANALYSIS\n{gap_summary}\n"
    )

    response = client.models.generate_content(
        model=MODEL_NAME,
        contents=f"{instructions}\n\n---\n{context}",
        config={
            "response_mime_type": "application/json",
            "response_schema": InterviewPlan,
        },
    )
    return response.parsed


def save_interview_plan(plan: InterviewPlan, output_dir: Path = OUTPUT_DIR) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "interview_plan.json"
    path.write_text(plan.model_dump_json(indent=2), encoding="utf-8")
    return path