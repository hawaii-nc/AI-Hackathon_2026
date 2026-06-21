from google import genai
from app.core.config import GEMINI_API_KEY
import base64

client = genai.Client(api_key=GEMINI_API_KEY)

def process_handwritten_note(image_bytes: bytes) -> str:
    image_b64 = base64.b64encode(image_bytes).decode("utf-8")
    response = client.models.generate_content(
        model="gemini-2.0-flash",
        contents=[{"parts": [
            {"text": "Transcribe all handwritten text. Return only the text."},
            {"inline_data": {"mime_type": "image/jpeg", "data": image_b64}}
        ]}]
    )
    return response.text
