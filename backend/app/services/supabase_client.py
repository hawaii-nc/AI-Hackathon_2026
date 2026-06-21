import re
from supabase import create_client
from app.core.config import SUPABASE_URL, SUPABASE_ANON_KEY, SUPABASE_SERVICE_ROLE_KEY

# Prefer the service-role key for server-side writes (bypasses RLS); fall back to
# the publishable/anon key (read-only unless an RLS write policy is in place).
_key = SUPABASE_SERVICE_ROLE_KEY or SUPABASE_ANON_KEY
supabase = create_client(SUPABASE_URL, _key)

# ─── patient_raw (OCR output store) ───────────────────────────────────────────
# Row per patient: "Name" column + data_1..data_10, each holding one OCR
# submission string. New patient -> insert; existing -> append into next empty.
PATIENT_TABLE = "patient_raw"
NAME_COLUMN = "Name"
DATA_COLUMNS = [f"data_{i}" for i in range(1, 11)]  # data_1 .. data_10


def _normalize_name(name: str) -> str:
    """Identity key for matching: case-insensitive, whitespace-collapsed."""
    return re.sub(r"\s+", " ", (name or "").strip()).lower()


def upsert_patient_submission(name: str, ocr_text: str) -> dict:
    """Append one OCR submission to a patient's row in patient_raw.

    Matching is by normalized Name. A new patient inserts a row with data_1 set;
    an existing patient gets the text written into the first empty data_N column.
    Returns {action, name, column} where action is created | appended | full.
    """
    name = (name or "").strip()
    rows = supabase.table(PATIENT_TABLE).select("*").execute().data or []
    target = next(
        (r for r in rows if _normalize_name(r.get(NAME_COLUMN)) == _normalize_name(name)),
        None,
    )

    if target is None:
        supabase.table(PATIENT_TABLE).insert(
            {NAME_COLUMN: name, DATA_COLUMNS[0]: ocr_text}
        ).execute()
        return {"action": "created", "name": name, "column": DATA_COLUMNS[0]}

    for col in DATA_COLUMNS:
        if not target.get(col):
            (supabase.table(PATIENT_TABLE)
                .update({col: ocr_text})
                .eq(NAME_COLUMN, target[NAME_COLUMN])
                .execute())
            return {"action": "appended", "name": target[NAME_COLUMN], "column": col}

    # All data_1..data_10 are full.
    return {"action": "full", "name": target[NAME_COLUMN], "column": None}

def get_all_shelters():
    response = supabase.table('shelters').select('*').execute()
    return response.data

def get_shelters_by_island(island: str):
    response = supabase.table('shelters').select('*').eq('island', island).execute()
    return response.data

def get_shelter_by_id(shelter_id: str):
    response = supabase.table('shelters').select('*').eq('id', shelter_id).single().execute()
    return response.data

def get_client_by_id(client_id: str):
    response = supabase.table('clients').select('*').eq('id', client_id).single().execute()
    return response.data

def save_client_profile(profile: dict):
    response = supabase.table('clients').insert(profile).execute()
    return response.data

def get_client_history(client_id: str):
    response = supabase.table('notes').select('*').eq('client_id', client_id).order('created_at', desc=True).execute()
    return response.data
