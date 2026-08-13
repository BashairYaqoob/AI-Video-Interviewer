"""
test_document_parser.py

Milestone 3A acceptance test.

Proves: input document -> parser -> normalized text

Run:
    .\.venv\Scripts\python.exe tests\test_document_parser.py

Requires fixtures to exist first:
    .\.venv\Scripts\python.exe tests\generate_fixtures.py
"""

import sys
from pathlib import Path

# Allow running this file directly (adds project root to the import path)
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.ingestion.document_parser import parse_document

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def check(condition: bool, description: str):
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {description}")
    if not condition:
        raise AssertionError(description)


def test_txt():
    doc = parse_document(FIXTURES_DIR / "sample_jd.txt", doc_type="job_description")
    check(doc.source_format == ".txt", "txt: correct source_format")
    check("Junior AI Engineer" in doc.text, "txt: extracted expected text")
    check(doc.char_count > 0, "txt: char_count is positive")


def test_md():
    doc = parse_document(FIXTURES_DIR / "sample_jd.md", doc_type="job_description")
    check(doc.source_format == ".md", "md: correct source_format")
    check("Junior AI Engineer" in doc.text, "md: extracted expected text")
    check(doc.char_count > 0, "md: char_count is positive")


def test_pdf():
    doc = parse_document(FIXTURES_DIR / "sample_resume.pdf", doc_type="resume")
    check(doc.source_format == ".pdf", "pdf: correct source_format")
    check("Jane Candidate" in doc.text, "pdf: extracted expected text")
    check(doc.char_count > 0, "pdf: char_count is positive")


def test_docx():
    doc = parse_document(FIXTURES_DIR / "sample_resume.docx", doc_type="resume")
    check(doc.source_format == ".docx", "docx: correct source_format")
    check("Jane Candidate" in doc.text, "docx: extracted expected text")
    check(doc.char_count > 0, "docx: char_count is positive")


def test_missing_file_raises():
    try:
        parse_document(FIXTURES_DIR / "does_not_exist.txt")
        check(False, "missing file: should have raised FileNotFoundError")
    except FileNotFoundError:
        check(True, "missing file: raised FileNotFoundError as expected")


def test_unsupported_format_raises():
    bad_file = FIXTURES_DIR / "not_supported.xyz"
    bad_file.write_text("irrelevant", encoding="utf-8")
    try:
        parse_document(bad_file)
        check(False, "unsupported format: should have raised ValueError")
    except ValueError:
        check(True, "unsupported format: raised ValueError as expected")
    finally:
        bad_file.unlink(missing_ok=True)


if __name__ == "__main__":
    print("Running Milestone 3A ingestion tests...\n")
    test_txt()
    test_md()
    test_pdf()
    test_docx()
    test_missing_file_raises()
    test_unsupported_format_raises()
    print("\nAll ingestion tests passed.")