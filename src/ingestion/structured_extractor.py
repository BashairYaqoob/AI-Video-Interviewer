"""
structured_extractor.py

Milestone 3B — Structured JD + Resume extraction.

Takes normalized text (from document_parser.ParsedDocument) and uses Gemini
structured output to produce validated JobDescription / Resume objects.
No prompt text is hardcoded here — it's loaded from prompts/.
"""

import os
from pathlib import Path

from dotenv import load_dotenv
from google import genai

from src.ingestion.schemas import JobDescription, Resume

load_dotenv()

API_KEY = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
MODEL_NAME = os.getenv(
    "GEMINI_TEXT_MODEL",
    "gemini-3.5-flash-lite",
)
PROMPTS_DIR = Path(__file__).resolve().parent.parent.parent / "prompts"
OUTPUT_DIR = Path(__file__).resolve().parent.parent.parent / "output"


def _load_prompt(filename: str) -> str:
    return (PROMPTS_DIR / filename).read_text(encoding="utf-8")


def _get_client() -> genai.Client:
    if not API_KEY:
        raise RuntimeError("GEMINI_API_KEY or GOOGLE_API_KEY not set in .env")
    return genai.Client(api_key=API_KEY)


def extract_jd(jd_text: str) -> JobDescription:
    """Extracts a structured JobDescription from normalized JD text."""
    client = _get_client()
    instructions = _load_prompt("jd_extraction_v1.txt")
    response = client.models.generate_content(
        model=MODEL_NAME,
        contents=f"{instructions}\n\n---\nJOB DESCRIPTION TEXT:\n{jd_text}",
        config={
            "response_mime_type": "application/json",
            "response_schema": JobDescription,
        },
    )
    return response.parsed


def extract_resume(resume_text: str) -> Resume:
    """Extracts a structured Resume from normalized resume text."""
    client = _get_client()
    instructions = _load_prompt("resume_extraction_v1.txt")
    response = client.models.generate_content(
        model=MODEL_NAME,
        contents=f"{instructions}\n\n---\nRESUME TEXT:\n{resume_text}",
        config={
            "response_mime_type": "application/json",
            "response_schema": Resume,
        },
    )
    return response.parsed


def save_jd(jd: JobDescription, output_dir: Path = OUTPUT_DIR) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "jd.json"
    path.write_text(jd.model_dump_json(indent=2), encoding="utf-8")
    return path


def save_resume(resume: Resume, output_dir: Path = OUTPUT_DIR) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "resume.json"
    path.write_text(resume.model_dump_json(indent=2), encoding="utf-8")
    return path