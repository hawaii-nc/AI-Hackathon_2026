"""
document_ai.py — Handwriting OCR using Google Cloud Document AI.
Returns plain transcribed text from an image.

Requires in .env:
    GOOGLE_PROJECT_ID
    GOOGLE_PROCESSOR_ID
    GOOGLE_APPLICATION_CREDENTIALS  (path to service account JSON)
    GOOGLE_PROCESSOR_LOCATION       (default: us)
"""

import mimetypes
import os

from app.core.config import GOOGLE_PROJECT_ID


def _mime_type(filename: str) -> str:
    mime, _ = mimetypes.guess_type(filename)
    return mime or "image/jpeg"


def process_handwritten_note(image_bytes: bytes, filename: str = "note.jpg") -> str:
    """
    Send image bytes to Google Document AI OCR processor.
    Returns the transcribed text as a plain string.
    Raises RuntimeError if credentials or config are missing.
    """
    from google.cloud import documentai

    processor_id = os.getenv("GOOGLE_PROCESSOR_ID")
    location = os.getenv("GOOGLE_PROCESSOR_LOCATION", "us")

    if not GOOGLE_PROJECT_ID:
        raise RuntimeError("GOOGLE_PROJECT_ID not set in .env")
    if not processor_id:
        raise RuntimeError("GOOGLE_PROCESSOR_ID not set in .env")

    client = documentai.DocumentProcessorServiceClient(
        client_options={"api_endpoint": f"{location}-documentai.googleapis.com"}
    )
    processor_name = client.processor_path(GOOGLE_PROJECT_ID, location, processor_id)

    raw_doc = documentai.RawDocument(
        content=image_bytes,
        mime_type=_mime_type(filename),
    )
    request = documentai.ProcessRequest(name=processor_name, raw_document=raw_doc)
    result = client.process_document(request=request)

    return result.document.text or ""
