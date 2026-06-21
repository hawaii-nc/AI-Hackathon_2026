from google import genai
from app.core.config import GEMINI_API_KEY
from app.services.supabase_client import get_all_shelters
import numpy as np
import json

client = genai.Client(api_key=GEMINI_API_KEY)

def get_embedding(text: str) -> list:
    result = client.models.embed_content(
        model='text-embedding-004',
        contents=text
    )
    return result.embeddings[0].values

def cosine_similarity(a: list, b: list) -> float:
    a, b = np.array(a), np.array(b)
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))

def match_client_to_shelters(client_needs: str, island: str = None, top_k: int = 5):
    shelters = get_all_shelters()
    if island:
        shelters = [s for s in shelters if s['island'] == island]
    client_embedding = get_embedding(client_needs)
    scored = []
    for shelter in shelters:
        shelter_text = f"{shelter['name']} {shelter['type']} {shelter['city']}"
        shelter_embedding = get_embedding(shelter_text)
        score = cosine_similarity(client_embedding, shelter_embedding)
        scored.append({**shelter, 'match_score': round(score * 100, 1)})
    scored.sort(key=lambda x: x['match_score'], reverse=True)
    return scored[:top_k]

def extract_client_tags(raw_notes: str) -> dict:
    response = client.models.generate_content(
        model='gemini-2.0-flash',
        contents=f'You are a case worker assistant. Extract structured tags from social worker notes. Return JSON with these fields only: needs (list: housing/mental_health/substance_abuse/medical/food/domestic_violence/employment), urgency (low/medium/high/critical), languages (list), has_children (bool), veteran (bool), summary (one sentence). Be factual and unbiased. Return only valid JSON no extra text. Notes: {raw_notes}'
    )
    cleaned = response.text.strip()
    if cleaned.startswith('`'):
        cleaned = cleaned.split('`')[-2] if '`' in cleaned else cleaned
    return json.loads(cleaned)