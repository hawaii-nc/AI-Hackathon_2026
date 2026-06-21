with open('app/services/document_ai.py', 'w', encoding='utf-8', newline='\n') as f:
    f.write('from google import genai\n')
    f.write('from app.core.config import GEMINI_API_KEY\n')
    f.write('import base64\n\n')
    f.write('client = genai.Client(api_key=GEMINI_API_KEY)\n\n')
    f.write('def process_handwritten_note(image_bytes: bytes) -> str:\n')
    f.write('    image_b64 = base64.b64encode(image_bytes).decode("utf-8")\n')
    f.write('    response = client.models.generate_content(\n')
    f.write('        model="gemini-2.0-flash",\n')
    f.write('        contents=[{"parts": [\n')
    f.write('            {"text": "Transcribe all handwritten text. Return only the text."},\n')
    f.write('            {"inline_data": {"mime_type": "image/jpeg", "data": image_b64}}\n')
    f.write('        ]}]\n')
    f.write('    )\n')
    f.write('    return response.text\n')

with open('app/services/document_ai.py', 'rb') as f:
    print('First bytes:', f.read(30))
