"""
gap_analysis.py

Milestone 3D — deterministic gap/evidence analysis.

Compares JobDescription + Resume + GitHubEvidence and classifies each JD
requirement as matched (found in GitHub evidence), weak_unverified (only
claimed in the resume, no supporting GitHub evidence), or missing.

Deliberately NOT an LLM call — this is simple, explainable substring
matching, which is enough for this milestone and easy to defend in a viva.
"""

from pathlib import Path

from src.ingestion.schemas import (
    JobDescription,
    Resume,
    GitHubEvidence,
    GapAnalysis,
    GapAnalysisEntry,
)

OUTPUT_DIR = Path(__file__).resolve().parent.parent.parent / "output"


def _contains(haystack: str, needle: str) -> bool:
    return needle.lower() in haystack.lower()


def analyze_gap(jd: JobDescription, resume: Resume, github: GitHubEvidence) -> GapAnalysis:
    resume_only_text = " ".join(
        resume.skills
        + [c.claim + " " + c.evidence for c in resume.claims]
        + [p.name + " " + p.description + " " + " ".join(p.technologies) for p in resume.projects]
    )

    github_only_text = " ".join(
        lang for repo in github.repositories for lang in repo.languages
    ) + " " + " ".join(repo.readme_excerpt for repo in github.repositories)

    matched, missing, weak = [], [], []

    all_requirements = list(jd.must_have_skills) + list(jd.nice_to_have_skills)

    for requirement in all_requirements:
        in_resume = _contains(resume_only_text, requirement)
        in_github = _contains(github_only_text, requirement)

        if in_github:
            evidence = ["github"] + (["resume"] if in_resume else [])
            matched.append(GapAnalysisEntry(requirement=requirement, status="matched", evidence=evidence))
        elif in_resume:
            weak.append(GapAnalysisEntry(
                requirement=requirement,
                status="weak_unverified",
                evidence=["resume claim only — no supporting GitHub evidence found"],
            ))
        else:
            missing.append(GapAnalysisEntry(requirement=requirement, status="missing", evidence=[]))

    return GapAnalysis(matched=matched, missing=missing, weak_unverified=weak)


def save_gap_analysis(analysis: GapAnalysis, output_dir: Path = OUTPUT_DIR) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "gap_analysis.json"
    path.write_text(analysis.model_dump_json(indent=2), encoding="utf-8")
    return path