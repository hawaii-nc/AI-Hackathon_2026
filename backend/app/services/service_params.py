"""Load the per-shelter intake parameters from services_parameters.csv.

The CSV (backend/services_parameters.csv) has one row per service/shelter and a
fixed set of columns describing who each place can take: gender, household type,
age floor, sobriety rules, mental-health/substance services, etc.

Each cell is normalized to a tri-state / number:
  * "yes" / "y" / "true" / "1"  -> True
  * "no"  / "n" / "false" / "0" -> False
  * ""    (blank)               -> None   (unknown / no stated constraint)
  * a number column             -> int    (min_age, max_stay_days)

`load_service_params()` returns a list of dicts shaped like:
    {"name": "THE SHELTER", "params": {"accepts_men": False, "min_age": 18, ...}}

This is the SERVICE side of the confidence/compatibility comparison. The patient
side comes from app.services.patient_params.
"""

import csv
from pathlib import Path

# backend/  (two parents up: services -> app -> backend)
_BACKEND_DIR = Path(__file__).resolve().parents[2]
DEFAULT_CSV = _BACKEND_DIR / "services_parameters.csv"

NAME_FIELD = "name"
# Columns that hold integers rather than yes/no.
NUMERIC_FIELDS = {"min_age", "max_stay_days"}

_TRUE = {"yes", "y", "true", "t", "1"}
_FALSE = {"no", "n", "false", "f", "0"}


def _coerce(field: str, raw: str):
    """Turn one CSV cell into True / False / int / None."""
    val = (raw or "").strip()
    if val == "":
        return None
    if field in NUMERIC_FIELDS:
        try:
            return int(float(val))
        except ValueError:
            return None
    low = val.lower()
    if low in _TRUE:
        return True
    if low in _FALSE:
        return False
    return None


def load_service_params(csv_path: str | Path | None = None) -> list[dict]:
    """Read the services CSV into [{name, params}], skipping unnamed rows."""
    path = Path(csv_path) if csv_path else DEFAULT_CSV
    if not path.exists():
        raise FileNotFoundError(f"services parameters CSV not found: {path}")

    services: list[dict] = []
    with path.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        param_fields = [c for c in (reader.fieldnames or []) if c and c != NAME_FIELD]
        for row in reader:
            name = (row.get(NAME_FIELD) or "").strip()
            if not name:
                continue
            params = {field: _coerce(field, row.get(field, "")) for field in param_fields}
            services.append({"name": name, "params": params})
    return services


def service_param_fields(csv_path: str | Path | None = None) -> list[str]:
    """The parameter column names (everything except the name column)."""
    path = Path(csv_path) if csv_path else DEFAULT_CSV
    with path.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        return [c for c in (reader.fieldnames or []) if c and c != NAME_FIELD]
