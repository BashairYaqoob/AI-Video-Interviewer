"""
test_structured_extractor.py

Milestone 3B acceptance test.

Makes REAL calls to the Gemini API using the synthetic fixtures from
Milestone 3A (not your real resume). Requires a valid GEMINI_API_KEY or
GOOGLE_API_KEY in .env, and tests/fixtures/ already generated.

Run:
    .\.venv\Scripts\python.exe tests\test_structured_extractor.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.ingestion.document_parser import parse_document
from src.ingestion.structured_extractor import (
    extract_jd,
    extract_resume,
    save_jd,
    save_resume,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def check(condition: bool, description: str):
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {description}")
    if not condition:
        raise AssertionError(description)


def test_jd_extraction():
    jd_doc = parse_document(FIXTURES_DIR / "sample_jd.txt", doc_type="job_description")
    jd = extract_jd(jd_doc.text)

    check(isinstance(jd.title, str) and len(jd.title) > 0, "jd: title extracted")
    check(len(jd.must_have_skills) > 0, "jd: must_have_skills extracted")
    check(isinstance(jd.seniority, str) and len(jd.seniority) > 0, "jd: seniority extracted")

    saved_path = save_jd(jd)
    check(saved_path.exists(), "jd: output/jd.json written")


def test_resume_extraction():
    resume_doc = parse_document(FIXTURES_DIR / "sample_resume.pdf", doc_type="resume")
    resume = extract_resume(resume_doc.text)

    check(isinstance(resume.candidate_name, str) and len(resume.candidate_name) > 0,
          "resume: candidate_name extracted")
    check(len(resume.skills) > 0 or len(resume.projects) > 0,
          "resume: skills or projects extracted")
    check("github.com" in resume.github_url or resume.github_url == "",
          "resume: github_url looks valid or empty")

    saved_path = save_resume(resume)
    check(saved_path.exists(), "resume: output/resume.json written")


if __name__ == "__main__":
    print("Running Milestone 3B structured extraction tests...\n")
    print("(These call the real Gemini API — may take a few seconds)\n")
    test_jd_extraction()
    test_resume_extraction()
    print("\nAll structured extraction tests passed.")