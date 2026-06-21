import json

# Import is crash-proof: if the package isn't installed, the module still loads
# and the placeholder path below is used instead of erroring.
try:
    from google import genai
    from google.genai import types as genai_types
except ModuleNotFoundError:
    genai = None
    genai_types = None

from app.core.config import GEMINI_API_KEY

# Hard timeout (milliseconds) on every Gemini request. Without this, a network
# hang (offline / firewall / DNS stall) blocks forever at socket connect and the
# placeholder fallback in draft_referral_email never gets an exception to catch.
# A finite timeout turns the hang into a quick error so the fallback can fire.
_GEMINI_TIMEOUT_MS = 10_000
_http_options = genai_types.HttpOptions(timeout=_GEMINI_TIMEOUT_MS) if genai_types else None

# Only build a real client if the package AND a key are both present. Lets the
# module be imported (and the placeholder used) with no key / no quota / no
# package, so the email flow never hard-fails locally.
client = (
    genai.Client(api_key=GEMINI_API_KEY, http_options=_http_options)
    if (genai and GEMINI_API_KEY)
    else None
)


def generate_referral(client_profile: dict, shelter: dict) -> str:
    """Formal referral letter (used by the /referral route)."""
    response = client.models.generate_content(
        model='gemini-2.5-flash',
        contents=f'You are a professional social worker assistant generating referral letters. Write clearly, professionally, and with zero bias. Do not include race, ethnicity, religion, or any protected characteristics. Focus only on service needs and resource fit. Client needs: {client_profile.get("needs")} Urgency: {client_profile.get("urgency")} Has children: {client_profile.get("has_children")} Veteran: {client_profile.get("veteran")} Referring to: Organization: {shelter.get("name")} Address: {shelter.get("address")}, {shelter.get("city")} Phone: {shelter.get("phone")} Type: {shelter.get("type")} Write a professional referral letter.'
    )
    return response.text


# Default sender identity. Override per-call or wire to the logged-in case
# worker once auth exists.
DEFAULT_SENDER = {
    "name": "Case Management Team",
    "org": "Community Outreach Services",
    "email": "referrals@example.org",
    "phone": "",
}


def _strip_code_fences(text: str) -> str:
    """Remove ```json ... ``` fences if the model wraps its JSON in them."""
    t = (text or "").strip()
    if t.startswith("```"):
        lines = t.splitlines()
        lines = lines[1:]  # drop opening fence (```json or ```)
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]  # drop closing fence
        t = "\n".join(lines).strip()
    return t


def _placeholder_email(client_profile: dict, shelter: dict, sender: dict) -> dict:
    """Placeholder used when the LLM is unavailable (no key / quota / network).

    Intentionally NOT a finished email — it's clearly marked so a case worker
    reviews and completes it before sending. The known facts are listed to make
    that quick.
    """
    needs = client_profile.get("needs")
    if isinstance(needs, list):
        needs = ", ".join(needs)

    def yn(v):
        return "yes" if v else "no"

    org_name = shelter.get("name", "the organization")
    org_desc = " ".join(
        p for p in [shelter.get("type"), "in " + shelter.get("city", "") if shelter.get("city") else ""] if p
    ).strip()

    subject = f"[DRAFT - needs review] Housing referral inquiry - {org_name}"
    body = (
        "[PLACEHOLDER - the AI drafting service was unavailable, so this email "
        "was NOT written by AI. Please review the details below and complete the "
        "message before sending.]\n\n"
        f"To: {org_name}{(' (' + org_desc + ')') if org_desc else ''}\n\n"
        "Referral details on file:\n"
        f"  - Needs: {needs or 'not specified'}\n"
        f"  - Urgency: {client_profile.get('urgency', 'not specified')}\n"
        f"  - Children in household: {yn(client_profile.get('has_children'))}\n"
        f"  - Veteran: {yn(client_profile.get('veteran'))}\n"
        f"  - Summary: {client_profile.get('summary') or 'not specified'}\n\n"
        "[Write the referral message here, then ask whether they currently have "
        "availability and can take this client.]\n\n"
        "Sent by:\n"
        f"{sender.get('name')}\n"
        f"{sender.get('org')}\n"
        f"{sender.get('email')}"
        f"{(chr(10) + sender.get('phone')) if sender.get('phone') else ''}"
    )
    return {"subject": subject, "body": body}


def _llm_draft(client_profile: dict, shelter: dict, sender: dict) -> dict:
    """Call Gemini to draft the email. Raises on any API/parse failure."""
    needs = client_profile.get("needs")
    if isinstance(needs, list):
        needs = ", ".join(needs)

    prompt = (
        "You are a professional social worker assistant. Draft a concise, warm, "
        "professional email to a housing/shelter organization asking whether they "
        "have availability and can take in a client who needs housing. Describe the "
        "situation factually. Write with zero bias: do NOT mention race, ethnicity, "
        "religion, national origin, or any protected characteristic. Only mention "
        "service-relevant factors (needs, urgency, household composition, veteran "
        "status). End by asking if they can take the client and offering to share "
        "more intake details.\n\n"
        f"Recipient organization: {shelter.get('name')} "
        f"({shelter.get('type')}) in {shelter.get('city')}.\n"
        f"Client needs: {needs}\n"
        f"Urgency: {client_profile.get('urgency')}\n"
        f"Has children: {client_profile.get('has_children')}\n"
        f"Veteran: {client_profile.get('veteran')}\n"
        f"Summary: {client_profile.get('summary', '')}\n\n"
        f"Sender (sign the email as this): {sender.get('name')}, {sender.get('org')}, "
        f"{sender.get('email')}"
        f"{', ' + sender.get('phone') if sender.get('phone') else ''}.\n\n"
        "Return ONLY valid JSON, no extra text, with exactly these keys: "
        '{"subject": "...", "body": "..."}. '
        "The body should be plain text with line breaks (\\n), including a greeting "
        "and a signature."
    )
    response = client.models.generate_content(
        model='gemini-2.5-flash',
        contents=prompt,
    )
    raw = _strip_code_fences(response.text)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {
            "subject": f"Housing referral inquiry - {shelter.get('name', '')}".strip(" -"),
            "body": response.text,
        }


def draft_referral_email(
    client_profile: dict,
    shelter: dict,
    sender: dict | None = None,
    use_llm: bool = True,
) -> dict:
    """Draft an email to a housing home asking if they can take a client.

    Returns: {to_email, to_name, from_email, from_name, subject, body, status}

    `status` is "ai" when Gemini wrote the draft, or "placeholder" when Gemini
    was unavailable (no key, quota, network, or package) — in that case the body
    is a clearly-marked placeholder for a case worker to complete, never an
    AI-quality email that could be sent by mistake.

    Pulls nothing from the network itself — pass dicts you already fetched from
    Supabase (or anywhere). Pass use_llm=False to force the placeholder path.
    """
    sender = {**DEFAULT_SENDER, **(sender or {})}

    draft = None
    status = "placeholder"
    if use_llm and client is not None:
        try:
            draft = _llm_draft(client_profile, shelter, sender)
            status = "ai"
        except Exception as exc:  # quota, network, parse, etc.
            print(f"[warn] Gemini unavailable ({type(exc).__name__}); leaving a placeholder.")
            draft = None

    if draft is None:
        draft = _placeholder_email(client_profile, shelter, sender)

    return {
        "to_email": shelter.get("email"),
        "to_name": shelter.get("name"),
        "from_email": sender.get("email"),
        "from_name": sender.get("name"),
        "subject": draft.get("subject", "").strip(),
        "body": draft.get("body", "").strip(),
        "status": status,
    }


# ─── Score-aware patient referral email ───────────────────────────────────────
# Used when a specific service is *selected*: the email is drafted from the
# patient's scanned/structured info and informed by the confidence/compatibility
# comparison against that service's intake parameters.

def _patient_to_profile(patient: dict) -> dict:
    """Map structured patient params (patient_params schema) -> the client_profile
    shape the drafter already understands, without inventing anything."""
    household = patient.get("household")
    return {
        "needs": patient.get("needs") or [],
        "urgency": "high" if patient.get("high_barrier_needs") else patient.get("urgency"),
        "has_children": household == "family_with_children",
        "veteran": bool(patient.get("veteran")),
        "summary": patient.get("summary") or "",
    }


def _fit_lines(scores: dict | None) -> tuple[list[str], list[str]]:
    """Split a score breakdown into aligned vs. concern bullet labels."""
    aligned, concerns = [], []
    for d in (scores or {}).get("detail", []):
        (aligned if d["value"] >= 1.0 else concerns).append(d["label"])
    return aligned, concerns


def _llm_draft_patient(patient: dict, shelter: dict, sender: dict, scores: dict | None) -> dict:
    """Gemini draft that cross-references patient facts and the parameter match."""
    profile = _patient_to_profile(patient)
    needs = ", ".join(profile["needs"]) if profile["needs"] else "not specified"
    aligned, concerns = _fit_lines(scores)

    fit_block = ""
    if scores:
        fit_block = (
            f"Internal fit (do NOT quote the numbers in the email): "
            f"confidence {scores.get('confidence')}%, compatibility "
            f"{scores.get('compatibility')}%.\n"
            f"Aligned intake factors to reference naturally: "
            f"{', '.join(aligned) if aligned else 'none'}.\n"
            f"Possible concerns to acknowledge or ask about: "
            f"{', '.join(concerns) if concerns else 'none'}.\n"
        )

    prompt = (
        "You are a professional social worker assistant. Draft a concise, warm, "
        "professional email to a housing/shelter organization asking whether they "
        "have availability for a client. Use ONLY the facts given. Write with zero "
        "bias: never mention race, ethnicity, religion, national origin, or any "
        "protected characteristic. Reference the intake factors that make this place "
        "a fit (e.g. accepts families, offers mental-health services) in plain prose, "
        "but do NOT print any scores or numbers. If there are concerns, ask about them "
        "politely. End by asking if they can take the client and offering full intake "
        "details.\n\n"
        f"Recipient organization: {shelter.get('name')} "
        f"({shelter.get('type', 'shelter')}) in {shelter.get('city', '')}.\n"
        f"Client needs: {needs}\n"
        f"Urgency: {profile.get('urgency') or 'not specified'}\n"
        f"Has children: {profile.get('has_children')}\n"
        f"Veteran: {profile.get('veteran')}\n"
        f"Summary: {profile.get('summary')}\n"
        f"{fit_block}\n"
        f"Sender (sign the email as this): {sender.get('name')}, {sender.get('org')}, "
        f"{sender.get('email')}"
        f"{', ' + sender.get('phone') if sender.get('phone') else ''}.\n\n"
        "Return ONLY valid JSON, no extra text, with exactly these keys: "
        '{"subject": "...", "body": "..."}. '
        "The body should be plain text with line breaks (\\n), greeting and signature."
    )
    response = client.models.generate_content(model="gemini-2.5-flash", contents=prompt)
    raw = _strip_code_fences(response.text)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {
            "subject": f"Housing referral inquiry - {shelter.get('name', '')}".strip(" -"),
            "body": response.text,
        }


def draft_patient_referral_email(
    patient: dict,
    shelter: dict,
    scores: dict | None = None,
    sender: dict | None = None,
    use_llm: bool = True,
) -> dict:
    """Draft a referral email for a SELECTED service, informed by the patient's
    scanned info and the confidence/compatibility comparison.

    `patient` is the structured params from patient_params.extract_patient_params.
    `shelter` carries at least name/email/type/city (merge of shelters row +
    services_parameters). `scores` is the score_patient_service() result for this
    pair (optional — its matched factors steer the wording). Returns the same
    shape as draft_referral_email plus a `scores` echo.
    """
    sender = {**DEFAULT_SENDER, **(sender or {})}
    draft, status = None, "placeholder"

    if use_llm and client is not None:
        try:
            draft = _llm_draft_patient(patient, shelter, sender, scores)
            status = "ai"
        except Exception as exc:
            print(f"[warn] Gemini unavailable ({type(exc).__name__}); leaving a placeholder.")
            draft = None

    if draft is None:
        draft = _placeholder_email(_patient_to_profile(patient), shelter, sender)

    return {
        "to_email": shelter.get("email"),
        "to_name": shelter.get("name"),
        "from_email": sender.get("email"),
        "from_name": sender.get("name"),
        "subject": draft.get("subject", "").strip(),
        "body": draft.get("body", "").strip(),
        "status": status,
        "scores": (
            {"confidence": scores.get("confidence"), "compatibility": scores.get("compatibility")}
            if scores else None
        ),
    }
