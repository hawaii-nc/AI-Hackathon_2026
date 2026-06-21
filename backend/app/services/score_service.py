"""Orchestration: patient_raw (OCR) + services_parameters.csv -> scores -> store.

Glues the pieces together for the API and the local demo:

  load_patients_from_supabase()      patient_raw rows -> structured patient params
  load_services()                    services_parameters.csv -> service params
  compute_matrices(patients, ...)    -> confidence/compatibility matrices
  compute_and_store(...)             end-to-end: load, score, write CSV
  score_one(patient_name, service)   single pair (used by the email route)

Supabase imports are done lazily inside functions so the pure-scoring path
(load_services + compute_matrices) works without the supabase package installed.
"""

from app.services.service_params import load_service_params
from app.services.patient_params import extract_patient_params, combine_patient_submissions
from app.services import scoring, score_store


def load_services(csv_path=None) -> list[dict]:
    return load_service_params(csv_path)


def load_patients_from_supabase(use_llm: bool = True) -> list[dict]:
    """Read every patient_raw row and extract structured params from its OCR text."""
    from app.services.supabase_client import supabase, PATIENT_TABLE, NAME_COLUMN, DATA_COLUMNS

    rows = supabase.table(PATIENT_TABLE).select("*").execute().data or []
    patients = []
    for row in rows:
        name = (row.get(NAME_COLUMN) or "").strip()
        if not name:
            continue
        ocr_text = combine_patient_submissions(row, DATA_COLUMNS)
        patients.append(extract_patient_params(ocr_text, name=name, use_llm=use_llm))
    return patients


def compute_matrices(patients: list[dict], services: list[dict] | None = None) -> dict:
    services = services if services is not None else load_services()
    return scoring.build_matrices(patients, services)


def compute_and_store(use_llm: bool = True) -> dict:
    """Full pipeline against live Supabase patients. Scores are written to CSV."""
    services = load_services()
    patients = load_patients_from_supabase(use_llm=use_llm)
    matrices = scoring.build_matrices(patients, services)
    store = score_store.save_matrices(matrices)
    return {
        "n_patients": len(patients),
        "n_services": len(services),
        "matrices": matrices,
        "store": store,
    }


def find_service(services: list[dict], service_name: str) -> dict | None:
    target = (service_name or "").strip().lower()
    return next((s for s in services if s["name"].strip().lower() == target), None)


def score_one(patient: dict, service: dict) -> dict:
    """Score a single patient/service pair (thin pass-through to scoring)."""
    return scoring.score_patient_service(patient, service)
