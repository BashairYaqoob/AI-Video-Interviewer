"""
github.py

Milestone 3C — GitHub ingestion.

Extracts a GitHub username from resume text/URL, fetches public repository
metadata + README content via the GitHub REST API, and normalizes it into
structured evidence for gap analysis.

GITHUB_TOKEN is optional — public repos work unauthenticated (60 req/hr),
authenticated raises the limit to 5000 req/hr.
"""

from __future__ import annotations

import base64
import os
import re
from pathlib import Path
from typing import List, Optional

import requests
from dotenv import load_dotenv

from src.ingestion.schemas import GitHubEvidence, RepoEvidence

load_dotenv()

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
GITHUB_API_BASE = "https://api.github.com"
MAX_REPOS_TO_EVIDENCE = 5

OUTPUT_DIR = Path(__file__).resolve().parent.parent.parent / "output"

GITHUB_URL_PATTERN = re.compile(
    r"github\.com/([A-Za-z0-9\-]+)(?:/([A-Za-z0-9_.\-]+))?", re.IGNORECASE
)


def extract_github_username(text: str) -> Optional[str]:
    """Finds the first github.com/<username> reference in a block of text."""
    match = GITHUB_URL_PATTERN.search(text)
    if not match:
        return None
    return match.group(1)


def _headers() -> dict:
    headers = {"Accept": "application/vnd.github+json"}
    if GITHUB_TOKEN:
        headers["Authorization"] = f"Bearer {GITHUB_TOKEN}"
    return headers


def _get(url: str, session) -> Optional[dict | list]:
    response = session.get(url, headers=_headers(), timeout=10)
    if response.status_code != 200:
        return None
    return response.json()


def fetch_user_repos(username: str, session=None) -> List[dict]:
    session = session or requests.Session()
    data = _get(f"{GITHUB_API_BASE}/users/{username}/repos?sort=updated&per_page=20", session)
    if not data:
        return []
    return [repo for repo in data if not repo.get("fork", False)]


def fetch_repo_languages(username: str, repo_name: str, session=None) -> List[str]:
    session = session or requests.Session()
    data = _get(f"{GITHUB_API_BASE}/repos/{username}/{repo_name}/languages", session)
    if not data:
        return []
    return list(data.keys())


def fetch_repo_readme(username: str, repo_name: str, session=None) -> str:
    session = session or requests.Session()
    data = _get(f"{GITHUB_API_BASE}/repos/{username}/{repo_name}/readme", session)
    if not data or "content" not in data:
        return ""
    try:
        decoded = base64.b64decode(data["content"]).decode("utf-8", errors="ignore")
    except Exception:
        return ""
    return decoded[:1000]  # evidence excerpt, not the full README


def build_github_evidence(username: str, session=None) -> GitHubEvidence:
    """
    Fetches and normalizes GitHub evidence: top repos (by recent update,
    non-fork), each with languages and a README excerpt.
    """
    session = session or requests.Session()
    repos = fetch_user_repos(username, session)[:MAX_REPOS_TO_EVIDENCE]

    repo_evidence = []
    for repo in repos:
        name = repo.get("name", "")
        languages = fetch_repo_languages(username, name, session)
        readme_excerpt = fetch_repo_readme(username, name, session)
        repo_evidence.append(
            RepoEvidence(
                name=name,
                description=repo.get("description") or "",
                languages=languages,
                readme_excerpt=readme_excerpt,
                stars=repo.get("stargazers_count", 0),
                last_updated=repo.get("updated_at", "") or "",
                url=repo.get("html_url", "") or "",
            )
        )

    return GitHubEvidence(
        username=username,
        profile_url=f"https://github.com/{username}",
        repositories=repo_evidence,
    )


def save_github_evidence(evidence: GitHubEvidence, output_dir: Path = OUTPUT_DIR) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "github.json"
    path.write_text(evidence.model_dump_json(indent=2), encoding="utf-8")
    return path