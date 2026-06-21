"""Turn a patient's raw image-scanner (OCR) text into structured parameters.

The handwritten-note scanner (Document AI) writes raw transcriptions into the
Supabase `patient_raw` table (Name + data_1..data_10). To score a patient against
a shelter's intake rules we first need those notes as structured fields that line
up with the service parameters in services_parameters.csv.

`extract_patient_params(ocr_text, name)` returns a dict like:
    {
      "name": "Jane Doe",
      "gender": "female",                 # male | female | other | None
      "household": "family_with_children",# single | couple | family_with_children | None
      "age": 34,                          # int | None
      "is_minor_primary": False,          # a child as the primary client
      "veteran": False,
      "active_substance_use": False,
      "sober": None,                      # currently sober / in recovery
      "needs_substance_services": False,
      "mental_health_diagnosis": True,
      "needs_mental_health_services": True,
      "fleeing_domestic_violence": False,
      "has_pets": False,
      "has_government_id": True,
      "high_barrier_needs": True,         # would benefit from low-barrier entry
      "needs": ["housing", "mental_health"],
      "summary": "one factual sentence",
    }

Primary path uses Gemini (gemini-2.5-flash, JSON-only). If Gemini is unavailable
(no key / quota / network / package) it falls back to a transparent keyword
heuristic so scoring still runs — every value it can't determine stays None.
"""

import json
import re

from app.services.referral import client as _gemini_client, _strip_code_fences

# The canonical patient schema. Keys mirror what scoring.py compares against the
# service parameters. Unknown -> None (never guessed).
PATIENT_FIELDS = (
    "gender",
    "household",
    "age",
    "is_minor_primary",
    "veteran",
    "active_substance_use",
    "sober",
    "needs_substance_services",
    "mental_health_diagnosis",
    "needs_mental_health_services",
    "fleeing_domestic_violence",
    "has_pets",
    "has_government_id",
    "high_barrier_needs",
)


def _empty_params(name: str) -> dict:
    base = {f: None for f in PATIENT_FIELDS}
    base["name"] = name or ""
    base["needs"] = []
    base["summary"] = ""
    return base


_PROMPT = (
    "You are a case-worker assistant. Read the intake notes about ONE person and "
    "extract structured facts. Be factual and unbiased: never infer race, religion, "
    "or ethnicity. Only state a field if the notes support it; otherwise use null.\n\n"
    "Return ONLY valid JSON (no prose, no code fences) with exactly these keys:\n"
    '{\n'
    '  "gender": "male" | "female" | "other" | null,\n'
    '  "household": "single" | "couple" | "family_with_children" | null,\n'
    '  "age": integer | null,\n'
    '  "is_minor_primary": boolean | null,            // the client themselves is a minor/child\n'
    '  "veteran": boolean | null,\n'
    '  "active_substance_use": boolean | null,         // currently using\n'
    '  "sober": boolean | null,                        // currently sober / in recovery\n'
    '  "needs_substance_services": boolean | null,\n'
    '  "mental_health_diagnosis": boolean | null,      // has a diagnosed condition\n'
    '  "needs_mental_health_services": boolean | null,\n'
    '  "fleeing_domestic_violence": boolean | null,\n'
    '  "has_pets": boolean | null,\n'
    '  "has_government_id": boolean | null,\n'
    '  "high_barrier_needs": boolean | null,           // complex needs; benefits from low-barrier entry\n'
    '  "needs": [string],                              // any of: housing, mental_health, substance_abuse, medical, food, domestic_violence, employment\n'
    '  "summary": string                               // one short factual sentence\n'
    "}\n\n"
    "Intake notes:\n"
)


def _llm_extract(ocr_text: str, name: str) -> dict:
    """Ask Gemini for the structured params. Raises on API/parse failure."""
    response = _gemini_client.models.generate_content(
        model="gemini-2.5-flash",
        contents=_PROMPT + ocr_text,
    )
    data = json.loads(_strip_code_fences(response.text))
    out = _empty_params(name)
    for k in PATIENT_FIELDS:
        if data.get(k) is not None:
            out[k] = data[k]
    if isinstance(data.get("needs"), list):
        out["needs"] = data["needs"]
    if data.get("summary"):
        out["summary"] = str(data["summary"])
    # Normalize age to int when the model returns a string.
    if out["age"] is not None:
        try:
            out["age"] = int(out["age"])
        except (TypeError, ValueError):
            out["age"] = None
    return out


# ─── Keyword fallback (no Gemini) ─────────────────────────────────────────────
# Transparent, low-confidence heuristics so scoring still produces something when
# the LLM is unavailable. Only sets a field when the text is reasonably explicit.

def _heuristic_extract(ocr_text: str, name: str) -> dict:
    out = _empty_params(name)
    t = (ocr_text or "").lower()

    if re.search(r"\b(male|man|mr\.?|he/him)\b", t) and not re.search(r"\bfemale\b", t):
        out["gender"] = "male"
    elif re.search(r"\b(female|woman|mrs\.?|ms\.?|she/her)\b", t):
        out["gender"] = "female"

    m = re.search(r"\bage\s*[:\-]?\s*(\d{1,3})\b", t) or re.search(r"\b(\d{1,2})\s*(?:yo|y/o|years? old)\b", t)
    if m:
        out["age"] = int(m.group(1))

    if re.search(r"\b(child|children|kids?|family|son|daughter|toddler|infant)\b", t):
        out["household"] = "family_with_children"
    elif re.search(r"\b(couple|spouse|partner|husband|wife|married)\b", t):
        out["household"] = "couple"
    elif re.search(r"\b(single|alone|individual)\b", t):
        out["household"] = "single"

    if re.search(r"\b(veteran|vet|army|navy|marines?|air force|military)\b", t):
        out["veteran"] = True

    # Negation first ("no substance use" must not read as active use).
    if re.search(r"\b(no|denies|without|no history of) (substance|drug|alcohol)", t):
        out["active_substance_use"] = False
    elif re.search(r"\b(sober|in recovery|clean and sober|abstinent)\b", t):
        out["sober"] = True
        out["active_substance_use"] = False
    elif re.search(r"\b(active substance|substance use|active use|substance abuse|addiction|"
                   r"alcoholic|using drugs?|drug use|relapse)\b", t):
        out["active_substance_use"] = True
        out["needs_substance_services"] = True

    if re.search(r"\b(diagnos|ptsd|depression|bipolar|schizophren|anxiety|mental health|psych)\b", t):
        out["mental_health_diagnosis"] = True
        out["needs_mental_health_services"] = True

    if re.search(r"\b(domestic violence|dv\b|abuse|fleeing|assault|restraining order)\b", t):
        out["fleeing_domestic_violence"] = True

    if re.search(r"\b(pet|dog|cat|service animal|emotional support animal)\b", t):
        out["has_pets"] = True

    if re.search(r"\b(no id\b|no government id|lost id|without id|no identification|undocumented)\b", t):
        out["has_government_id"] = False
    elif re.search(r"\b(has id|state id|driver'?s license|identification on file)\b", t):
        out["has_government_id"] = True

    # Complex / low-barrier signals -> would benefit from low-barrier entry.
    if re.search(r"\b(low.?barrier|complex needs|turned away|high needs|multiple barriers|"
                 r"chronically homeless)\b", t):
        out["high_barrier_needs"] = True

    needs = []
    for kw, tag in (
        (r"hous|shelter|homeless", "housing"),
        (r"mental|psych|ptsd|depress", "mental_health"),
        (r"substance|drug|alcohol|addiction", "substance_abuse"),
        (r"medical|health|injur|medication", "medical"),
        (r"food|hungry|meal", "food"),
        (r"domestic violence|\bdv\b|abus", "domestic_violence"),
        (r"job|employ|work", "employment"),
    ):
        if re.search(kw, t):
            needs.append(tag)
    out["needs"] = needs

    first_line = next((ln.strip() for ln in (ocr_text or "").splitlines() if ln.strip()), "")
    out["summary"] = first_line[:200]
    return out


def extract_patient_params(ocr_text: str, name: str = "", use_llm: bool = True) -> dict:
    """Structured patient params from raw OCR text.

    Tries Gemini first (when available and use_llm); on any failure falls back to
    the keyword heuristic. Adds a `param_source` key: "ai" or "heuristic".
    """
    if use_llm and _gemini_client is not None and (ocr_text or "").strip():
        try:
            out = _llm_extract(ocr_text, name)
            out["param_source"] = "ai"
            return out
        except Exception as exc:  # quota / network / parse
            print(f"[warn] Gemini patient extraction unavailable ({type(exc).__name__}); using heuristic.")

    out = _heuristic_extract(ocr_text, name)
    out["param_source"] = "heuristic"
    return out


def combine_patient_submissions(row: dict, data_columns: list[str]) -> str:
    """Join a patient_raw row's data_1..data_N submissions into one text blob."""
    parts = [str(row.get(c)).strip() for c in data_columns if (row.get(c) or "").strip()]
    return "\n\n---\n\n".join(parts)
