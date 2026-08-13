"""
schemas.py

Pydantic schemas shared across Milestones 3B (structured extraction),
3C (GitHub ingestion), and 3D (gap analysis). These define the exact
structured shape of jd.json, resume.json, github.json, and gap_analysis.json.
"""

from typing import List
from pydantic import BaseModel, Field


class JobDescription(BaseModel):
    title: str
    seniority: str
    must_have_skills: List[str] = Field(default_factory=list)
    nice_to_have_skills: List[str] = Field(default_factory=list)
    responsibilities: List[str] = Field(default_factory=list)
    competencies: List[str] = Field(default_factory=list)


class ExperienceEntry(BaseModel):
    role: str
    organization: str = ""
    description: str = ""


class ProjectEntry(BaseModel):
    name: str
    description: str = ""
    technologies: List[str] = Field(default_factory=list)


class ClaimEvidence(BaseModel):
    claim: str
    evidence: str = ""


class Resume(BaseModel):
    candidate_name: str
    education: List[str] = Field(default_factory=list)
    experience: List[ExperienceEntry] = Field(default_factory=list)
    skills: List[str] = Field(default_factory=list)
    projects: List[ProjectEntry] = Field(default_factory=list)
    github_url: str = ""
    claims: List[ClaimEvidence] = Field(default_factory=list)


class RepoEvidence(BaseModel):
    name: str
    description: str = ""
    languages: List[str] = Field(default_factory=list)
    readme_excerpt: str = ""
    stars: int = 0
    last_updated: str = ""
    url: str = ""


class GitHubEvidence(BaseModel):
    username: str
    profile_url: str
    repositories: List[RepoEvidence] = Field(default_factory=list)


class GapAnalysisEntry(BaseModel):
    requirement: str
    status: str  # "matched" | "missing" | "weak_unverified"
    evidence: List[str] = Field(default_factory=list)


class GapAnalysis(BaseModel):
    matched: List[GapAnalysisEntry] = Field(default_factory=list)
    missing: List[GapAnalysisEntry] = Field(default_factory=list)
    weak_unverified: List[GapAnalysisEntry] = Field(default_factory=list)