"""Confidence & compatibility scoring: patient params vs. service params.

Given one patient's structured params (app.services.patient_params) and one
service's intake params (app.services.service_params), each comparable parameter
is evaluated to:
    1.0  -> patient matches / satisfies this rule
    0.0  -> hard mismatch (e.g. men-only shelter, patient is a woman)
    None -> not applicable / unknown on either side (excluded from the score)

Two scores come out of the same set of evaluations:

  * CONFIDENCE   = plain average of the matched rules (every rule counts equally).
                   "How many of the parameters that we could check actually line up?"

  * COMPATIBILITY = weighted average using PARAM_WEIGHTS (each rule has an
                    importance weight). Eligibility-critical rules (gender, age,
                    sobriety, DV) count for more than nice-to-haves (pets).
                    Weights are intentionally arbitrary/tunable — edit the table.

Both are returned as 0-100 percentages. Rules that evaluate to None are skipped
in BOTH scores, so a patient/service pair with little overlapping info is scored
only on what's known (and `n_evaluated` reports how much that was).
"""

# Importance weights for compatibility (1 = minor, 10 = eligibility-critical).
# Arbitrary by design — this is the "certain weight to each parameter" knob.
PARAM_WEIGHTS = {
    "gender": 10,
    "household": 8,
    "min_age": 9,
    "children_primary": 5,
    "veteran_pref": 4,
    "substance_use": 9,
    "needs_substance_services": 6,
    "mh_diagnosis_required": 6,
    "needs_mental_health_services": 7,
    "domestic_violence": 9,
    "pets": 3,
    "gov_id": 5,
    "low_barrier": 4,
}


def _b(v):
    """True only for an explicit True; None/False stay falsey but distinguishable."""
    return v is True


# ─── Per-rule evaluators ──────────────────────────────────────────────────────
# Each takes (patient, service_params) and returns 1.0 / 0.0 / None.

def _rule_gender(p, s):
    g = p.get("gender")
    if g == "male":
        v = s.get("accepts_men")
        return None if v is None else (1.0 if v else 0.0)
    if g == "female":
        v = s.get("accepts_women")
        return None if v is None else (1.0 if v else 0.0)
    return None


def _rule_household(p, s):
    h = p.get("household")
    if h == "family_with_children":
        v = s.get("accepts_families_with_children")
    elif h == "couple":
        v = s.get("accepts_couples")
    elif h == "single":
        v = s.get("accepts_singles")
    else:
        return None
    return None if v is None else (1.0 if v else 0.0)


def _rule_min_age(p, s):
    age, floor = p.get("age"), s.get("min_age")
    if age is None or floor is None:
        return None
    return 1.0 if age >= floor else 0.0


def _rule_children_primary(p, s):
    if not _b(p.get("is_minor_primary")):
        return None
    v = s.get("children_as_primary_client")
    return None if v is None else (1.0 if v else 0.0)


def _rule_veteran_pref(p, s):
    # A preference, not a gate: reward a match, never penalize a non-veteran.
    if not _b(p.get("veteran")):
        return None
    return 1.0 if _b(s.get("veteran_preference")) else None


def _rule_substance_use(p, s):
    requires_sober = s.get("requires_sobriety")
    accepts_active = s.get("accepts_active_substance_use")
    if _b(p.get("active_substance_use")):
        if _b(requires_sober) or accepts_active is False:
            return 0.0
        if _b(accepts_active) or requires_sober is False:
            return 1.0
        return None
    if _b(p.get("sober")) and _b(requires_sober):
        return 1.0  # sober client satisfies a sobriety requirement
    return None


def _rule_needs_substance_services(p, s):
    if not _b(p.get("needs_substance_services")):
        return None
    v = s.get("substance_use_services")
    return None if v is None else (1.0 if v else 0.0)


def _rule_mh_diagnosis_required(p, s):
    # Only relevant when the service *requires* a diagnosis to enter.
    if not _b(s.get("mental_health_diagnosis_required")):
        return None
    return 1.0 if _b(p.get("mental_health_diagnosis")) else 0.0


def _rule_needs_mental_health_services(p, s):
    if not _b(p.get("needs_mental_health_services")):
        return None
    v = s.get("mental_health_services_available")
    return None if v is None else (1.0 if v else 0.0)


def _rule_domestic_violence(p, s):
    # Reward a DV-focused match; don't punish general shelters (None, not 0).
    if not _b(p.get("fleeing_domestic_violence")):
        return None
    return 1.0 if _b(s.get("domestic_violence_focus")) else None


def _rule_pets(p, s):
    if not _b(p.get("has_pets")):
        return None
    v = s.get("accepts_pets")
    return None if v is None else (1.0 if v else 0.0)


def _rule_gov_id(p, s):
    # Only a factor when the service requires a government ID.
    if not _b(s.get("requires_government_id")):
        return None
    return 1.0 if _b(p.get("has_government_id")) else 0.0


def _rule_low_barrier(p, s):
    if not _b(p.get("high_barrier_needs")):
        return None
    return 1.0 if _b(s.get("low_barrier_entry")) else None


# Ordered (rule_key, human_label, evaluator). rule_key matches PARAM_WEIGHTS.
RULES = [
    ("gender", "Gender eligibility", _rule_gender),
    ("household", "Household type", _rule_household),
    ("min_age", "Minimum age", _rule_min_age),
    ("children_primary", "Child as primary client", _rule_children_primary),
    ("veteran_pref", "Veteran preference", _rule_veteran_pref),
    ("substance_use", "Sobriety / active use", _rule_substance_use),
    ("needs_substance_services", "Substance-use services", _rule_needs_substance_services),
    ("mh_diagnosis_required", "MH diagnosis requirement", _rule_mh_diagnosis_required),
    ("needs_mental_health_services", "Mental-health services", _rule_needs_mental_health_services),
    ("domestic_violence", "Domestic-violence focus", _rule_domestic_violence),
    ("pets", "Pets accepted", _rule_pets),
    ("gov_id", "Government ID requirement", _rule_gov_id),
    ("low_barrier", "Low-barrier entry", _rule_low_barrier),
]


def score_patient_service(patient: dict, service: dict) -> dict:
    """Score one patient against one service.

    `service` is a dict like {"name": ..., "params": {...}} from
    service_params.load_service_params(). Returns:
        {
          "service": name,
          "confidence": float (0-100),       # unweighted
          "compatibility": float (0-100),    # weighted by PARAM_WEIGHTS
          "n_evaluated": int,                # rules that applied
          "detail": [{rule, label, value, weight}, ...],  # per-rule breakdown
        }
    """
    sp = service.get("params", service)
    detail = []
    matched_sum = 0.0           # sum of values (for confidence)
    n = 0                       # count of applicable rules
    w_match_sum = 0.0           # sum of weight*value (for compatibility)
    w_sum = 0.0                 # sum of applicable weights

    for key, label, fn in RULES:
        v = fn(patient, sp)
        if v is None:
            continue
        w = PARAM_WEIGHTS.get(key, 1)
        matched_sum += v
        n += 1
        w_match_sum += w * v
        w_sum += w
        detail.append({"rule": key, "label": label, "value": v, "weight": w})

    confidence = round((matched_sum / n) * 100, 1) if n else 0.0
    compatibility = round((w_match_sum / w_sum) * 100, 1) if w_sum else 0.0
    return {
        "service": service.get("name"),
        "confidence": confidence,
        "compatibility": compatibility,
        "n_evaluated": n,
        "detail": detail,
    }


def score_patient_all_services(patient: dict, services: list[dict]) -> list[dict]:
    """Score one patient against every service, sorted best-compatibility first."""
    scored = [score_patient_service(patient, s) for s in services]
    scored.sort(key=lambda r: (r["compatibility"], r["confidence"]), reverse=True)
    return scored


def build_matrices(patients: list[dict], services: list[dict]) -> dict:
    """Full patient x service matrices for both scores.

    Returns:
        {
          "services": [service names in column order],
          "patients": [patient names in row order],
          "confidence":   {patient_name: {service_name: score}},
          "compatibility":{patient_name: {service_name: score}},
        }
    Row/column layout = patients down the rows, services across the columns,
    exactly how the confidence/compatibility tables are stored.
    """
    service_names = [s["name"] for s in services]
    confidence: dict[str, dict] = {}
    compatibility: dict[str, dict] = {}
    for p in patients:
        pname = p.get("name") or "(unnamed)"
        conf_row, comp_row = {}, {}
        for s in services:
            r = score_patient_service(p, s)
            conf_row[s["name"]] = r["confidence"]
            comp_row[s["name"]] = r["compatibility"]
        confidence[pname] = conf_row
        compatibility[pname] = comp_row
    return {
        "services": service_names,
        "patients": [p.get("name") or "(unnamed)" for p in patients],
        "confidence": confidence,
        "compatibility": compatibility,
    }
