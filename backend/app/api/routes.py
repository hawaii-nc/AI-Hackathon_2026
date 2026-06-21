from fastapi import APIRouter, UploadFile, File, HTTPException
from app.services.matching import match_client_to_shelters, extract_client_tags
from app.services.document_ai import process_handwritten_note
from app.services.referral import generate_referral, draft_referral_email, draft_patient_referral_email
from app.services.email_service import send_email
from app.services.supabase_client import (
    save_client_profile,
    get_client_history,
    get_all_shelters,
    get_client_by_id,
    get_shelter_by_id,
)
from app.services import score_service
from app.services.patient_params import extract_patient_params
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


class ScoreComputeRequest(BaseModel):
    use_llm: bool = True       # use Gemini to extract patient params (else heuristic)
    include_matrices: bool = True


class ServiceEmailRequest(BaseModel):
    # Identify the patient by name (looked up in patient_raw) or pass params directly.
    patient_name: str = None
    patient: dict = None          # structured patient params (skips the lookup)
    service_name: str = None      # the SELECTED service (must be in services_parameters.csv)
    shelter: dict = None          # optional contact override (email/type/city)
    sender: dict = None
    use_llm: bool = True
    send: bool = False

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


# ─── Confidence / compatibility scoring ───────────────────────────────────────

# Compute the patient x service confidence & compatibility matrices and write
# them to CSV in the backend. Rows = patients, columns = services.
@router.post('/scores/compute')
async def scores_compute(request: ScoreComputeRequest):
    result = score_service.compute_and_store(use_llm=request.use_llm)
    if not request.include_matrices:
        result.pop('matrices', None)
    return result


def _resolve_patient(req: ServiceEmailRequest) -> dict:
    """Patient params from the request dict, or extracted from patient_raw by name."""
    if req.patient:
        return req.patient
    if not req.patient_name:
        raise HTTPException(status_code=400, detail='Provide patient or patient_name.')
    from app.services.supabase_client import (
        supabase, PATIENT_TABLE, NAME_COLUMN, DATA_COLUMNS, _normalize_name,
    )
    from app.services.patient_params import combine_patient_submissions
    rows = supabase.table(PATIENT_TABLE).select('*').execute().data or []
    target = req.patient_name.strip()
    row = next((r for r in rows if _normalize_name(r.get(NAME_COLUMN)) == _normalize_name(target)), None)
    if row is None:
        raise HTTPException(status_code=404, detail=f'Patient not found in patient_raw: {target!r}')
    ocr_text = combine_patient_submissions(row, DATA_COLUMNS)
    return extract_patient_params(ocr_text, name=row.get(NAME_COLUMN), use_llm=req.use_llm)


def _resolve_shelter_contact(service_name: str, override: dict | None) -> dict:
    """Best-effort contact info (email/type/city) for a service by name."""
    contact = {'name': service_name}
    try:
        for s in get_all_shelters() or []:
            if (s.get('name') or '').strip().lower() == (service_name or '').strip().lower():
                contact = {**s, 'name': service_name}
                break
    except Exception:
        pass  # Supabase unavailable — fall back to whatever the caller provides.
    if override:
        contact = {**contact, **override}
    return contact


# Draft (and optionally send) a referral email for a SELECTED service, informed
# by the patient's scanned info and the confidence/compatibility comparison.
@router.post('/referral/email-for-service')
async def referral_email_for_service(request: ServiceEmailRequest):
    if not request.service_name:
        raise HTTPException(status_code=400, detail='service_name is required.')

    patient = _resolve_patient(request)
    services = score_service.load_services()
    service = score_service.find_service(services, request.service_name)
    if service is None:
        raise HTTPException(
            status_code=404,
            detail=f'Service not found in services_parameters.csv: {request.service_name!r}',
        )

    scores = score_service.score_one(patient, service)
    shelter = _resolve_shelter_contact(request.service_name, request.shelter)
    email = draft_patient_referral_email(
        patient, shelter, scores=scores, sender=request.sender, use_llm=request.use_llm,
    )
    result = {'email': email, 'scores': scores, 'sent': False}

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
