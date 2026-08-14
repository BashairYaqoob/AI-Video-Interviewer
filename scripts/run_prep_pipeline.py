"""
run_prep_pipeline.py

Runs the full offline prep pipeline against REAL input files, producing
all output/ artifacts needed before a live interview can run:

  inputs/jd.<ext> + inputs/resume.<ext>
    -> output/jd.json, output/resume.json        (Milestone 3B)
    -> output/github.json                         (Milestone 3C)
    -> output/gap_analysis.json                   (Milestone 3D)
    -> output/interview_plan.json                  (Milestone 4B)

Run once before starting a live interview:
    .\.venv\Scripts\python.exe scripts\run_prep_pipeline.py

Looks for inputs/jd.* and inputs/resume.* (.txt/.md/.pdf/.docx).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.ingestion.document_parser import parse_document, SUPPORTED_EXTENSIONS
from src.ingestion.structured_extractor import extract_jd, extract_resume, save_jd, save_resume
from src.ingestion.github import extract_github_username, build_github_evidence, save_github_evidence
from src.ingestion.gap_analysis import analyze_gap, save_gap_analysis
from src.interview.question_planner import build_question_plan, save_interview_plan

INPUTS_DIR = Path(__file__).parent.parent / "inputs"


def _find_input(stem: str) -> Path:
    for ext in SUPPORTED_EXTENSIONS:
        candidate = INPUTS_DIR / f"{stem}{ext}"
        if candidate.exists():
            return candidate
    raise FileNotFoundError(
        f"No inputs/{stem}.(txt|md|pdf|docx) found. "
        f"Place the job description as inputs/jd.<ext> and the candidate's "
        f"resume as inputs/resume.<ext>, then re-run."
    )


def main():
    print("Step 1/5: Parsing JD and resume...")
    jd_doc = parse_document(_find_input("jd"), doc_type="job_description")
    resume_doc = parse_document(_find_input("resume"), doc_type="resume")

    print("Step 2/5: Structured extraction (Gemini)...")
    jd = extract_jd(jd_doc.text)
    resume = extract_resume(resume_doc.text)
    save_jd(jd)
    save_resume(resume)
    print("  -> output/jd.json, output/resume.json saved")

    print("Step 3/5: GitHub ingestion...")
    username = extract_github_username(resume.github_url or resume_doc.text)
    if not username:
        raise RuntimeError(
            "No GitHub username found in the resume. Add a github.com/<username> "
            "link to inputs/resume.<ext> and re-run."
        )
    github_evidence = build_github_evidence(username)
    save_github_evidence(github_evidence)
    print(f"  -> output/github.json saved ({len(github_evidence.repositories)} repos)")

    print("Step 4/5: Gap analysis...")
    gap = analyze_gap(jd, resume, github_evidence)
    save_gap_analysis(gap)
    print(f"  -> output/gap_analysis.json saved "
          f"({len(gap.matched)} matched, {len(gap.weak_unverified)} weak, {len(gap.missing)} missing)")

    print("Step 5/5: Question plan (Gemini)...")
    plan = build_question_plan(jd, resume, github_evidence, gap)
    save_interview_plan(plan)
    print(f"  -> output/interview_plan.json saved ({len(plan.questions)} questions)")

    print("\nPrep pipeline complete. Ready to run the live agent:")
    print(r"  .\.venv\Scripts\python.exe src\realtime\agent.py dev")


if __name__ == "__main__":
    main()