from fastapi import APIRouter, UploadFile, File, HTTPException
from app.services.matching import match_client_to_shelters, extract_client_tags
from app.services.document_ai import process_handwritten_note
from app.services.referral import generate_referral, draft_referral_email
from app.services.email_service import send_email
from app.services.supabase_client import (
    save_client_profile,
    get_client_history,
    get_all_shelters,
    get_client_by_id,
    get_shelter_by_id,
)
from pydantic import BaseModel

router = APIRouter()

class MatchRequest(BaseModel):
    notes: str
    island: str = None

class ReferralRequest(BaseModel):
    client_profile: dict
    shelter: dict

class ReferralEmailRequest(BaseModel):
    # Provide either the ids (pulled from Supabase) or the dicts directly.
    client_id: str = None
    shelter_id: str = None
    client_profile: dict = None
    shelter: dict = None
    sender: dict = None
    send: bool = False  # when False, only draft + return the email

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

# Draft (and optionally send) a referral email to a housing home
@router.post('/referral/email')
async def referral_email(request: ReferralEmailRequest):
    profile = request.client_profile
    shelter = request.shelter

    # Pull parameters from Supabase when ids are supplied.
    if profile is None and request.client_id:
        profile = get_client_by_id(request.client_id)
    if shelter is None and request.shelter_id:
        shelter = get_shelter_by_id(request.shelter_id)

    if not profile or not shelter:
        raise HTTPException(
            status_code=400,
            detail='Provide client_profile + shelter, or client_id + shelter_id.',
        )

    email = draft_referral_email(profile, shelter, sender=request.sender)
    result = {'email': email, 'sent': False}

    if request.send:
        delivery = send_email(
            to_email=email['to_email'],
            subject=email['subject'],
            body=email['body'],
            from_email=email['from_email'],
            from_name=email['from_name'],
            to_name=email['to_name'],
        )
        result['sent'] = delivery.get('sent', False)
        result['delivery'] = delivery

    return result

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
