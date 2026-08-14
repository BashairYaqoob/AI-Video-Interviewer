"""
test_interview_state.py

Milestone 4A acceptance test — interview state model.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.interview.state import InterviewState, InterviewPhase
from src.ingestion.schemas import JobDescription, Resume, GitHubEvidence, GapAnalysis


def check(condition: bool, description: str):
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {description}")
    if not condition:
        raise AssertionError(description)


def test_state_creation_with_defaults():
    state = InterviewState(
        candidate_name="Jane Candidate",
        target_role="Junior AI Engineer",
        jd=JobDescription(title="Junior AI Engineer", seniority="0-2 years"),
        resume=Resume(candidate_name="Jane Candidate"),
        github_evidence=GitHubEvidence(username="jane", profile_url="https://github.com/jane"),
        gap_analysis=GapAnalysis(),
    )

    check(state.current_phase == InterviewPhase.INTRO, "state: starts in INTRO phase")
    check(state.current_question_index == 0, "state: starts at question index 0")
    check(state.follow_up_count == 0, "state: starts with 0 follow-ups")
    check(state.questions_asked == [], "state: starts with no questions asked")
    check(state.is_complete is False, "state: starts not complete")


if __name__ == "__main__":
    print("Running Milestone 4A interview state tests...\n")
    test_state_creation_with_defaults()
    print("\nAll interview state tests passed.")