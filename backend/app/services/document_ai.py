import mimetypes
import os

from app.core.config import GOOGLE_PROJECT_ID


def _mime_type(filename: str) -> str:
    mime, _ = mimetypes.guess_type(filename)
    return mime or "image/jpeg"


def process_handwritten_note(image_bytes: bytes, filename: str = "note.jpg") -> str:
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
