"""Build the JS dataset the console needs: each real service joined with its
live coords/island/type and scored against the subject 'Marcus', plus the
1-3 most *unique* parameters that actually match him (rarity x weight)."""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from app.services import service_params, scoring

marcus = {
    "name": "Marcus", "gender": "male", "household": "single", "age": 52,
    "is_minor_primary": False, "veteran": True, "active_substance_use": True,
    "sober": False, "needs_substance_services": True, "mental_health_diagnosis": True,
    "needs_mental_health_services": True, "fleeing_domestic_violence": False,
    "has_pets": False, "has_government_id": None, "high_barrier_needs": True,
}

# human phrasing for a matched (good) / hard-mismatch (bad) rule
POS = {
    "gender": "Accepts men", "household": "Accepts single adults",
    "min_age": "Adult intake (18+)", "veteran_pref": "Veteran preference",
    "substance_use": "Accepts active substance use",
    "needs_substance_services": "Substance-use program",
    "mh_diagnosis_required": "Meets diagnosis requirement",
    "needs_mental_health_services": "Mental-health services",
    "domestic_violence": "Domestic-violence focus", "pets": "Pets welcome",
    "gov_id": "ID already on file", "low_barrier": "Low-barrier entry",
}
NEG = {
    "gender": "Does not accept men", "household": "No single adults",
    "min_age": "Under age minimum",
    "substance_use": "Requires sobriety",
    "needs_substance_services": "No substance-use program",
    "mh_diagnosis_required": "Diagnosis required",
    "needs_mental_health_services": "No mental-health services",
    "pets": "No pets", "gov_id": "Government ID required",
}
# rules everyone shares -> not "unique"
COMMON = {"gender", "household", "min_age"}

services = service_params.load_service_params()
scored = {s["name"]: scoring.score_patient_service(marcus, s) for s in services}

# rarity of each matched rule across ALL services (rarer match == more unique)
match_freq = {}
for r in scored.values():
    for d in r["detail"]:
        if d["value"] == 1.0:
            match_freq[d["rule"]] = match_freq.get(d["rule"], 0) + 1

def chips_for(name):
    r = scored[name]
    good = [d for d in r["detail"] if d["value"] == 1.0]
    bad = [d for d in r["detail"] if d["value"] == 0.0]
    # rank good by uniqueness (rarity) then importance(weight); de-prioritise common
    def rank(d):
        rare = 1.0 / match_freq.get(d["rule"], 1)
        common_pen = 0 if d["rule"] in COMMON else 1
        return (common_pen, rare, d["weight"])
    good.sort(key=rank, reverse=True)
    chips = [{"k": "good", "t": POS.get(d["rule"], d["label"])} for d in good[:3]]
    if len(chips) < 3:  # backfill with common matches if too few distinctive
        for d in good[3:]:
            if len(chips) >= 3: break
    # surface at most one hard eligibility fail as a warning
    bad.sort(key=lambda d: d["weight"], reverse=True)
    warns = [{"k": "bad", "t": NEG.get(d["rule"], d["label"])} for d in bad[:2]]
    return chips, warns

rows = []
for s in services:
    name = s["name"]
    r = scored[name]
    chips, warns = chips_for(name)
    rows.append({
        "name": name, "compat": r["compatibility"], "conf": r["confidence"],
        "n": r["n_evaluated"], "chips": chips, "warns": warns,
    })

rows.sort(key=lambda x: x["compat"], reverse=True)
print(f"{'SERVICE':46s} {'COMP':>5s} {'CONF':>5s} {'N':>2s}  TOP-UNIQUE-MATCHES / WARN")
for x in rows:
    cstr = ", ".join(c["t"] for c in x["chips"])
    wstr = ", ".join('!'+w["t"] for w in x["warns"])
    print(f"{x['name'][:46]:46s} {x['compat']:5.1f} {x['conf']:5.1f} {x['n']:2d}  {cstr}  {wstr}")
