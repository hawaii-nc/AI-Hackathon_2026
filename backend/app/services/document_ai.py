from google import genai
from app.core.config import GEMINI_API_KEY

client = genai.Client(api_key=GEMINI_API_KEY)

def process_handwritten_note(image_bytes: bytes) -> str:
    import base64
    image_b64 = base64.b64encode(image_bytes).decode('utf-8')
    response = client.models.generate_content(
        model='gemini-2.0-flash',
        contents=[
            {
                'parts': [
                    {'text': 'Please transcribe all handwritten text in this image exactly as written. Return only the transcribed text, nothing else.'},
                    {'inline_data': {'mime_type': 'image/jpeg', 'data': image_b64}}
                ]
            }
        ]
    )
    return response.text
