from google import genai
from app.core.config import GEMINI_API_KEY
from app.services.supabase_client import get_all_shelters
from app.services.referral import _strip_code_fences
import numpy as np
import json

# Build the client only when a key is present, so importing this module (and
# starting the API) never hard-fails just because GEMINI_API_KEY is unset.
# genai.Client(api_key=None) raises ValueError, which would crash app startup.
client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None


def _require_client():
    if client is None:
        raise RuntimeError(
            "GEMINI_API_KEY is not set — add it to backend/.env to enable "
            "matching/tag extraction."
        )
    return client

def get_embedding(text: str) -> list:
    result = _require_client().models.embed_content(
        model='gemini-embedding-001',
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
    response = _require_client().models.generate_content(
        model='gemini-2.5-flash',
        contents=f'You are a case worker assistant. Extract structured tags from social worker notes. Return JSON with these fields only: needs (list: housing/mental_health/substance_abuse/medical/food/domestic_violence/employment), urgency (low/medium/high/critical), languages (list), has_children (bool), veteran (bool), summary (one sentence). Be factual and unbiased. Return only valid JSON no extra text. Notes: {raw_notes}'
    )
    cleaned = _strip_code_fences(response.text)
    return json.loads(cleaned)
