"""Persist the confidence & compatibility matrices as CSV files in the backend.

The scores live as two CSVs next to services_parameters.csv — no database:

    backend/confidence_scores.csv
    backend/compatibility_scores.csv

Each has a first column "patient", then one column per service, one row per
patient (the same shape as services_parameters.csv). These CSVs are the single
source of truth for the scores; nothing is written to Supabase.
"""

import csv
from pathlib import Path

_BACKEND_DIR = Path(__file__).resolve().parents[2]

CONFIDENCE_CSV = _BACKEND_DIR / "confidence_scores.csv"
COMPATIBILITY_CSV = _BACKEND_DIR / "compatibility_scores.csv"

PATIENT_COL = "patient"


def _write_matrix_csv(path: Path, services: list[str], matrix: dict) -> Path:
    """Write one matrix (services as columns, patients as rows) to `path`."""
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([PATIENT_COL] + services)             # header row
        for patient, row in matrix.items():
            writer.writerow([patient] + [row.get(s, "") for s in services])
    return path


def save_matrices(matrices: dict) -> dict:
    """Write both matrices to CSV in the backend. Returns the two file paths."""
    services = matrices["services"]
    conf = _write_matrix_csv(CONFIDENCE_CSV, services, matrices["confidence"])
    comp = _write_matrix_csv(COMPATIBILITY_CSV, services, matrices["compatibility"])
    return {"confidence_csv": str(conf), "compatibility_csv": str(comp)}
