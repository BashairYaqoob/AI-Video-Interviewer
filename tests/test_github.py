"""
test_github.py

Milestone 3C acceptance test — GitHub ingestion.

Uses a FAKE requests session (no live network/API calls) so this test runs
reliably regardless of GitHub API rate limits or connectivity.
"""

import base64
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.ingestion.github import (
    extract_github_username,
    build_github_evidence,
    save_github_evidence,
)


def check(condition: bool, description: str):
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {description}")
    if not condition:
        raise AssertionError(description)


class FakeResponse:
    def __init__(self, status_code: int, json_data):
        self.status_code = status_code
        self._json_data = json_data

    def json(self):
        return self._json_data


class FakeSession:
    """Stands in for requests.Session — returns canned GitHub API responses."""

    def get(self, url: str, headers=None, timeout=None):
        if url.endswith("/users/example-candidate/repos?sort=updated&per_page=20"):
            return FakeResponse(200, [
                {
                    "name": "rag-chatbot",
                    "description": "A RAG chatbot",
                    "fork": False,
                    "stargazers_count": 3,
                    "updated_at": "2026-01-01T00:00:00Z",
                    "html_url": "https://github.com/example-candidate/rag-chatbot",
                },
                {
                    "name": "forked-repo",
                    "description": "not mine really",
                    "fork": True,
                    "stargazers_count": 0,
                    "updated_at": "2025-01-01T00:00:00Z",
                    "html_url": "https://github.com/example-candidate/forked-repo",
                },
            ])
        if url.endswith("/repos/example-candidate/rag-chatbot/languages"):
            return FakeResponse(200, {"Python": 1234, "HTML": 100})
        if url.endswith("/repos/example-candidate/rag-chatbot/readme"):
            content = base64.b64encode(b"# RAG Chatbot\nBuilt with LangChain and ChromaDB.").decode()
            return FakeResponse(200, {"content": content})
        return FakeResponse(404, None)


def test_extract_github_username():
    text = "Check out my work: https://github.com/example-candidate and more."
    username = extract_github_username(text)
    check(username == "example-candidate", "extract_github_username: correct username parsed")


def test_extract_github_username_missing():
    username = extract_github_username("No GitHub link here.")
    check(username is None, "extract_github_username: returns None when absent")


def test_build_github_evidence_with_mock():
    evidence = build_github_evidence("example-candidate", session=FakeSession())

    check(evidence.username == "example-candidate", "evidence: username correct")
    check(len(evidence.repositories) == 1, "evidence: fork excluded, 1 real repo kept")

    repo = evidence.repositories[0]
    check(repo.name == "rag-chatbot", "evidence: repo name correct")
    check("Python" in repo.languages, "evidence: languages extracted")
    check("LangChain" in repo.readme_excerpt, "evidence: README content extracted")

    saved_path = save_github_evidence(evidence)
    check(saved_path.exists(), "evidence: output/github.json written")


if __name__ == "__main__":
    print("Running Milestone 3C GitHub ingestion tests (mocked, no live API calls)...\n")
    test_extract_github_username()
    test_extract_github_username_missing()
    test_build_github_evidence_with_mock()
    print("\nAll GitHub ingestion tests passed.")