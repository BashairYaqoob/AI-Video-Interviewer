"""
test_gap_analysis.py

Milestone 3D acceptance test — gap/evidence analysis.

Pure deterministic logic — no LLM calls, no GitHub API calls. Constructs
JobDescription / Resume / GitHubEvidence objects directly to test the
matching logic in isolation.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.ingestion.schemas import (
    JobDescription,
    Resume,
    ClaimEvidence,
    ProjectEntry,
    GitHubEvidence,
    RepoEvidence,
)
from src.ingestion.gap_analysis import analyze_gap, save_gap_analysis


def check(condition: bool, description: str):
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {description}")
    if not condition:
        raise AssertionError(description)


def build_sample_data():
    jd = JobDescription(
        title="Junior AI Engineer",
        seniority="0-2 years",
        must_have_skills=["Python", "LangChain", "RAG", "Git"],
        nice_to_have_skills=["Docker"],
        responsibilities=["Build LLM-powered features"],
        competencies=["Python fundamentals", "RAG systems"],
    )

    resume = Resume(
        candidate_name="Jane Candidate",
        education=["BS Computer Science"],
        skills=["Python", "LangChain", "Streamlit"],
        projects=[ProjectEntry(name="RAG Chatbot", description="A chatbot", technologies=["LangChain"])],
        github_url="https://github.com/example-candidate",
        claims=[ClaimEvidence(claim="Experienced with Git", evidence="")],
    )

    github = GitHubEvidence(
        username="example-candidate",
        profile_url="https://github.com/example-candidate",
        repositories=[
            RepoEvidence(
                name="rag-chatbot",
                description="RAG chatbot",
                languages=["Python"],
                readme_excerpt="Built using LangChain and RAG techniques.",
            )
        ],
    )
    return jd, resume, github


def test_matched_requirement_found_in_github():
    jd, resume, github = build_sample_data()
    analysis = analyze_gap(jd, resume, github)
    matched_names = [e.requirement for e in analysis.matched]
    check("Python" in matched_names, "Python matched via GitHub evidence")
    check("LangChain" in matched_names, "LangChain matched via GitHub evidence")


def test_weak_unverified_requirement():
    jd, resume, github = build_sample_data()
    analysis = analyze_gap(jd, resume, github)
    weak_names = [e.requirement for e in analysis.weak_unverified]
    check("Git" in weak_names, "Git flagged weak/unverified (resume claim, no GitHub evidence)")


def test_missing_requirement():
    jd, resume, github = build_sample_data()
    analysis = analyze_gap(jd, resume, github)
    missing_names = [e.requirement for e in analysis.missing]
    check("RAG" not in missing_names, "RAG matched via GitHub README, not missing")
    check("Docker" in missing_names, "Docker correctly flagged as missing")


def test_save_gap_analysis():
    jd, resume, github = build_sample_data()
    analysis = analyze_gap(jd, resume, github)
    path = save_gap_analysis(analysis)
    check(path.exists(), "output/gap_analysis.json written")


if __name__ == "__main__":
    print("Running Milestone 3D gap analysis tests...\n")
    test_matched_requirement_found_in_github()
    test_weak_unverified_requirement()
    test_missing_requirement()
    test_save_gap_analysis()
    print("\nAll gap analysis tests passed.")