from fastapi import APIRouter, UploadFile, File, HTTPException
from app.services.matching import match_client_to_shelters, extract_client_tags
from app.services.document_ai import process_handwritten_note
from app.services.referral import generate_referral
from app.services.supabase_client import save_client_profile, get_client_history, get_all_shelters
from pydantic import BaseModel

router = APIRouter()

class MatchRequest(BaseModel):
    notes: str
    island: str = None

class ReferralRequest(BaseModel):
    client_profile: dict
    shelter: dict

# Upload a photo of handwritten notes
@router.post('/upload-notes')
async def upload_notes(file: UploadFile = File(...)):
    image_bytes = await file.read()
    extracted_text = process_handwritten_note(image_bytes, filename=file.filename or "note.jpg")
    tags = extract_client_tags(extracted_text)
    return {'extracted_text': extracted_text, 'tags': tags}

# Match client to shelters
@router.post('/match')
async def match(request: MatchRequest):
    tags = extract_client_tags(request.notes)
    needs_text = ' '.join(tags.get('needs', [])) + ' ' + tags.get('summary', '')
    matches = match_client_to_shelters(needs_text, island=request.island)
    return {'tags': tags, 'matches': matches}

# Generate referral letter
@router.post('/referral')
async def referral(request: ReferralRequest):
    letter = generate_referral(request.client_profile, request.shelter)
    return {'referral': letter}

# Get all shelters
@router.get('/shelters')
async def shelters():
    return get_all_shelters()

# Save client profile
@router.post('/clients')
async def create_client(profile: dict):
    saved = save_client_profile(profile)
    return saved

# Get client note history
@router.get('/clients/{client_id}/history')
async def client_history(client_id: str):
    return get_client_history(client_id)
