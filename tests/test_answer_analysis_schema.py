"""
test_answer_analysis_schema.py

Milestone 4D acceptance test — answer analysis schema validation.
Does NOT call Gemini.
"""

import sys
from pathlib import Path

import pydantic

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.interview.schemas import EvidenceRecord


def check(condition: bool, description: str):
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {description}")
    if not condition:
        raise AssertionError(description)


def test_valid_evidence_record():
    record = EvidenceRecord(
        relevance="high",
        evidence_found=["mentioned using LangChain retriever with top-k=5"],
        claims_made=["built the RAG pipeline end to end"],
        missing_evidence=[],
        follow_up_warranted=False,
    )
    check(record.relevance == "high", "evidence: relevance preserved")
    check(record.follow_up_warranted is False, "evidence: follow_up_warranted preserved")


def test_missing_required_field_rejected():
    try:
        EvidenceRecord(
            relevance="low",
            evidence_found=[],
            claims_made=[],
            missing_evidence=["no specifics given"],
            # follow_up_warranted intentionally missing (required field)
        )
        check(False, "evidence: should reject record missing follow_up_warranted")
    except pydantic.ValidationError:
        check(True, "evidence: correctly rejected malformed EvidenceRecord")


if __name__ == "__main__":
    print("Running Milestone 4D answer analysis schema tests...\n")
    test_valid_evidence_record()
    test_missing_required_field_rejected()
    print("\nAll answer analysis schema tests passed.")