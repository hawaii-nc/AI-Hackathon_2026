"""
document_ai.py — Handwriting OCR service used by the FastAPI routes.
Primary  : Anthropic Claude Vision (claude-sonnet-4-6)
Fallback : Google Cloud Document AI (needs GOOGLE_PROJECT_ID + GOOGLE_PROCESSOR_ID in .env)
"""

import base64
import json
import mimetypes
import os

import anthropic
from app.core.config import GOOGLE_PROJECT_ID

_CLAUDE_MODEL = "claude-sonnet-4-6"

_SYSTEM_PROMPT = """You are a clinical transcription assistant for social workers serving
unhoused individuals. Transcribe handwritten notes exactly, preserving all acronyms and
medical shorthand. Mark illegible sections as [illegible]. Never add information absent
from the image."""

_USER_PROMPT = """Transcribe this handwritten note completely and accurately.

Return ONLY a JSON object with this schema:
{
  "raw_transcription": "<verbatim text>",
  "client_name": "<name or null>",
  "date_of_note": "<date or null>",
  "presenting_needs": ["..."],
  "barriers": ["..."],
  "health_flags": ["..."],
  "veteran_flag": true | false,
  "urgency": "low" | "medium" | "high" | "crisis",
  "location_mentions": ["..."],
  "action_items": ["..."],
  "illegible_sections": ["..."],
  "worker_name": "<initials/name or null>"
}"""


def _mime_type(filename: str) -> str:
    mime, _ = mimetypes.guess_type(filename)
    return mime or "image/jpeg"


def process_handwritten_note(image_bytes: bytes, filename: str = "note.jpg") -> dict:
    """
    Primary entry point used by the API route.
    Returns a dict with 'raw_transcription' plus structured fields.
    Raises RuntimeError if both engines fail.
    """
    try:
        return _claude_ocr(image_bytes, filename)
    except Exception as claude_err:
        try:
            text = _google_docai_ocr(image_bytes, filename)
            return {
                "raw_transcription": text,
                "_engine": "google_document_ai",
                "_fallback_reason": str(claude_err),
            }
        except Exception as google_err:
            raise RuntimeError(
                f"Both OCR engines failed. Claude: {claude_err} | Google: {google_err}"
            )


def _claude_ocr(image_bytes: bytes, filename: str) -> dict:
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY not set")

    media_type = _mime_type(filename)
    b64 = base64.standard_b64encode(image_bytes).decode("utf-8")

    client = anthropic.Anthropic(api_key=api_key)
    response = client.messages.create(
        model=_CLAUDE_MODEL,
        max_tokens=2048,
        system=_SYSTEM_PROMPT,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {"type": "base64", "media_type": media_type, "data": b64},
                    },
                    {"type": "text", "text": _USER_PROMPT},
                ],
            }
        ],
    )

    raw = response.content[0].text.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]

    result = json.loads(raw)
    result["_engine"] = "claude_vision"
    return result


def _google_docai_ocr(image_bytes: bytes, filename: str) -> str:
    """Returns plain text string — structured parsing not available via Document AI."""
    from google.cloud import documentai

    processor_id = os.getenv("GOOGLE_PROCESSOR_ID")
    location = os.getenv("GOOGLE_PROCESSOR_LOCATION", "us")

    if not GOOGLE_PROJECT_ID or not processor_id:
        raise RuntimeError(
            "GOOGLE_PROJECT_ID and GOOGLE_PROCESSOR_ID must be set for Document AI fallback"
        )

    docai_client = documentai.DocumentProcessorServiceClient(
        client_options={"api_endpoint": f"{location}-documentai.googleapis.com"}
    )
    processor_name = docai_client.processor_path(GOOGLE_PROJECT_ID, location, processor_id)
    raw_doc = documentai.RawDocument(content=image_bytes, mime_type=_mime_type(filename))
    request = documentai.ProcessRequest(name=processor_name, raw_document=raw_doc)
    result = docai_client.process_document(request=request)
    return result.document.text or ""
