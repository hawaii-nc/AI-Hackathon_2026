"""One-off: score the demo subject 'Marcus' against every service and emit the
per-service compatibility + the matched/mismatched rule detail, so the frontend
console can be driven by real CSV data instead of fictional orgs. Offline only.
"""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from app.services import service_params, scoring

# Subject derived from the console intake text:
# "Marcus, 52. Army veteran, two tours. Lost his apartment three weeks ago after
#  a relapse - drinking heavily again. Has PTSD, hasn't had meds in months.
#  Sleeping near the train depot. Four shelters already turned him away."
marcus = {
    "name": "Marcus",
    "gender": "male",
    "household": "single",
    "age": 52,
    "is_minor_primary": False,
    "veteran": True,
    "active_substance_use": True,
    "sober": False,
    "needs_substance_services": True,
    "mental_health_diagnosis": True,        # PTSD diagnosis
    "needs_mental_health_services": True,
    "fleeing_domestic_violence": False,
    "has_pets": False,
    "has_government_id": None,               # unknown
    "high_barrier_needs": True,             # turned away 4x -> needs low-barrier
}

services = service_params.load_service_params()
out = []
for s in services:
    r = scoring.score_patient_service(marcus, s)
    out.append({
        "name": s["name"],
        "compatibility": r["compatibility"],
        "confidence": r["confidence"],
        "n_evaluated": r["n_evaluated"],
        "detail": r["detail"],
    })

out.sort(key=lambda x: x["compatibility"], reverse=True)
print(json.dumps(out, indent=2))
