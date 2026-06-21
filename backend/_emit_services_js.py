"""Emit a JS literal (window.KOKUA_SERVICES) the console can embed: every real
service joined with live coords/island/city/address/phone/type, scored against
the subject, with the 1-3 most unique matching params + notable warnings."""
import json, os, re, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from app.services import service_params, scoring

marcus = {
    "name": "Marcus", "gender": "male", "household": "single", "age": 52,
    "is_minor_primary": False, "veteran": True, "active_substance_use": True,
    "sober": False, "needs_substance_services": True, "mental_health_diagnosis": True,
    "needs_mental_health_services": True, "fleeing_domestic_violence": False,
    "has_pets": False, "has_government_id": None, "high_barrier_needs": True,
}

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
    "min_age": "Under age minimum", "substance_use": "Requires sobriety",
    "needs_substance_services": "No substance-use program",
    "mh_diagnosis_required": "Diagnosis required",
    "needs_mental_health_services": "No mental-health services",
    "pets": "No pets", "gov_id": "Government ID required",
}
COMMON = {"gender", "household", "min_age"}

TYPE_LABEL = {
    "emergency_shelter": "Emergency shelter", "family_shelter": "Family shelter",
    "shelter": "Shelter", "shelter_navigation": "Shelter navigation",
    "shelter_mental_health": "Shelter + mental-health services",
    "day_services_access_point": "Day services & access point",
    "services_access_point": "Services access point",
    "resource_center_access_point": "Resource center", "admin_intake": "Intake office",
    "services_by_referral": "Services by referral",
    "shelter_rental_assistance": "Shelter + rental assistance",
    "temporary_safe_zone": "Temporary safe zone",
    "mobile_day_services": "Mobile day services",
    "women_dv_services": "Women's & DV services", "dv_services": "Domestic-violence services",
    "government_housing_office": "Government housing office",
}
# services chips shown in the detail modal, derived from CSV params
def derived_services(p):
    out = []
    def add(c, t):
        if c: out.append(t)
    add(p.get("substance_use_services"), "Substance-use treatment")
    add(p.get("mental_health_services_available"), "Mental-health services")
    add(p.get("veteran_preference"), "Veteran navigation")
    add(p.get("domestic_violence_focus"), "Domestic-violence support")
    add(p.get("accepts_pets"), "Pet-friendly intake")
    add(p.get("low_barrier_entry"), "Low-barrier entry")
    add(p.get("housing_first_model"), "Housing-first model")
    if not out:
        out = ["Emergency shelter", "Case management", "Meals & basic needs"]
    return out[:6]

def website(name):
    slug = re.sub(r"[^a-z0-9]+", "", name.lower())[:24]
    return slug + ".org"

shelters = {s["name"]: s for s in json.load(open("shelters_dump.json", encoding="utf-8"))}
services = service_params.load_service_params()
scored = {s["name"]: scoring.score_patient_service(marcus, s) for s in services}

match_freq = {}
for r in scored.values():
    for d in r["detail"]:
        if d["value"] == 1.0:
            match_freq[d["rule"]] = match_freq.get(d["rule"], 0) + 1

def chips_for(name):
    r = scored[name]
    good = [d for d in r["detail"] if d["value"] == 1.0]
    bad = [d for d in r["detail"] if d["value"] == 0.0]
    def rank(d):
        rare = 1.0 / match_freq.get(d["rule"], 1)
        common_pen = 0 if d["rule"] in COMMON else 1
        return (common_pen, rare, d["weight"])
    good.sort(key=rank, reverse=True)
    chips = [{"k": "good", "t": POS.get(d["rule"], d["label"])} for d in good[:3]]
    bad.sort(key=lambda d: d["weight"], reverse=True)
    chips += [{"k": "bad", "t": NEG.get(d["rule"], d["label"])} for d in bad[:2]]
    return chips[:3] if len([c for c in chips if c["k"]=="good"]) >= 3 else chips

def key_for(name):
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")

rows = []
for s in services:
    name = s["name"]
    sh = shelters.get(name, {})
    r = scored[name]
    p = s["params"]
    rows.append({
        "key": key_for(name), "name": name,
        "island": sh.get("island", ""), "city": sh.get("city", ""),
        "address": sh.get("address", ""), "phone": sh.get("phone", ""),
        "type": sh.get("type", ""), "typeLabel": TYPE_LABEL.get(sh.get("type", ""), "Community service"),
        "lat": sh.get("latitude"), "lng": sh.get("longitude"),
        "score": r["compatibility"], "conf": r["confidence"], "n": r["n_evaluated"],
        "chips": chips_for(name),
        "services": derived_services(p),
        "website": website(name),
    })

rows.sort(key=lambda x: x["score"], reverse=True)
js = "window.KOKUA_SERVICES = " + json.dumps(rows, ensure_ascii=False) + ";\n"
open("console_services.js.txt", "w", encoding="utf-8").write(js)
print("wrote console_services.js.txt  (", len(rows), "services )")
print("Oahu in-window count:", sum(1 for r in rows if r["island"] == "Oahu"))
