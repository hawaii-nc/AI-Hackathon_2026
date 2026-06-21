from google import genai
from app.core.config import GEMINI_API_KEY
from google.cloud import documentai
from app.core.config import GOOGLE_PROJECT_ID
import os


def process_handwritten_note(image_bytes: bytes) -> str:
    client = documentai.DocumentProcessorServiceClient()
    
    # You will set this processor ID in Google Cloud Console
    processor_name = f'projects/{GOOGLE_PROJECT_ID}/locations/us/processors/YOUR_PROCESSOR_ID'
    
    raw_document = documentai.RawDocument(
        content=image_bytes,
        mime_type='image/jpeg'
    )
    
    request = documentai.ProcessRequest(
        name=processor_name,
        raw_document=raw_document
    )
    
    result = client.process_document(request=request)
    return result.document.text
