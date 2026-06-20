from openai import OpenAI
from app.core.config import OPENAI_API_KEY
from app.services.supabase_client import get_all_shelters
import numpy as np

client = OpenAI(api_key=OPENAI_API_KEY)

def get_embedding(text: str) -> list:
    response = client.embeddings.create(
        input=text,
        model='text-embedding-3-small'
    )
    return response.data[0].embedding

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
    response = client.chat.completions.create(
        model='gpt-4o',
        messages=[
            {
                'role': 'system',
                'content': '''You are a case worker assistant. Extract structured tags from social worker notes.
                Return JSON with these fields only:
                - needs: list of needs (housing, mental_health, substance_abuse, medical, food, domestic_violence, employment)
                - urgency: low / medium / high / critical
                - languages: list of languages spoken
                - has_children: true/false
                - veteran: true/false
                - summary: one sentence neutral summary
                Be factual and unbiased.'''
            },
            {'role': 'user', 'content': raw_notes}
        ],
        response_format={'type': 'json_object'}
    )
    import json
    return json.loads(response.choices[0].message.content)
