"""Run the confidence/compatibility scoring end-to-end locally (no Supabase needed).

    python score_patients_local.py                 # mock patients + heuristic params
    python score_patients_local.py --llm           # use Gemini to extract params
    python score_patients_local.py --email "THE SHELTER"   # also draft an email
                                                            # for that selected service
What it does (all offline-safe):
  1. Builds a few mock patients from raw OCR-style note text.
  2. Extracts structured patient params (heuristic by default; --llm for Gemini).
  3. Loads service params from services_parameters.csv.
  4. Computes the confidence + compatibility matrices (patients x services).
  5. Writes confidence_scores.csv and compatibility_scores.csv in the backend.
  6. Prints each patient's top matches.
  7. With --email NAME, drafts a referral email for that service and saves a
     preview to backend/outbox/ (nothing is sent).

The scores live as CSVs in the backend; nothing is written to a database.
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.services.patient_params import extract_patient_params
from app.services import scoring, score_store, score_service

# Mock OCR text shaped like what the image scanner writes into patient_raw.
MOCK_NOTES = {
    "Jane Doe": (
        "Patient Name: Jane Doe\nAge: 34\nSex: Female\n"
        "Notes: Single mother with two young children, fled a domestic violence "
        "situation last week. Currently staying in her car. Needs emergency housing "
        "and help with food. Has a state ID. No substance use. Reports anxiety."
    ),
    "Robert King": (
        "Patient Name: Robert King\nAge: 52\nSex: Male\n"
        "Notes: Army veteran, single, experiencing homelessness for 6 months. "
        "History of alcohol use, currently in recovery and sober for 90 days. "
        "Diagnosed with PTSD, wants mental health support. Has a service dog."
    ),
    "Maria Santos": (
        "Patient Name: Maria Santos\nAge: 19\nSex: Female\n"
        "Notes: Young single woman, active substance use, no government ID. "
        "Complex needs, has been turned away from several programs. Needs a "
        "low-barrier place that can take her tonight."
    ),
}


def _bar(pct: float, width: int = 20) -> str:
    filled = int(round((pct / 100.0) * width))
    return "#" * filled + "-" * (width - filled)


def main():
    parser = argparse.ArgumentParser(description="Local confidence/compatibility scoring.")
    parser.add_argument("--llm", action="store_true", help="Use Gemini to extract patient params.")
    parser.add_argument("--email", metavar="SERVICE", help="Draft an email for this selected service.")
    parser.add_argument("--patient", metavar="NAME", default="Jane Doe",
                        help="Which mock patient the --email draft is for (default: Jane Doe).")
    parser.add_argument("--top", type=int, default=3, help="How many top matches to print per patient.")
    args = parser.parse_args()

    use_llm = args.llm
    print(f"Extracting patient params ({'Gemini' if use_llm else 'heuristic'})...")
    patients = [extract_patient_params(txt, name=name, use_llm=use_llm)
                for name, txt in MOCK_NOTES.items()]
    for p in patients:
        print(f"  - {p['name']:<14} source={p.get('param_source')}  "
              f"gender={p.get('gender')} household={p.get('household')} "
              f"age={p.get('age')} veteran={p.get('veteran')} "
              f"active_use={p.get('active_substance_use')}")

    services = score_service.load_services()
    print(f"\nLoaded {len(services)} services from services_parameters.csv")

    matrices = scoring.build_matrices(patients, services)

    store = score_store.save_matrices(matrices)
    print("\nWrote:")
    print(f"  confidence    -> {store['confidence_csv']}")
    print(f"  compatibility -> {store['compatibility_csv']}")

    print("\nTop matches per patient (compatibility | confidence):")
    for p in patients:
        ranked = scoring.score_patient_all_services(p, services)
        print(f"\n  {p['name']}:")
        for r in ranked[:args.top]:
            print(f"    {r['compatibility']:5.1f}% [{_bar(r['compatibility'])}]  "
                  f"conf {r['confidence']:5.1f}%  n={r['n_evaluated']:>2}  {r['service']}")

    if args.email:
        from app.services.referral import draft_patient_referral_email
        from app.services.email_service import send_email

        patient = next((p for p in patients if p["name"].lower() == args.patient.lower()), patients[0])
        service = score_service.find_service(services, args.email)
        if service is None:
            print(f"\n[error] service not found in CSV: {args.email!r}")
            return
        scores = score_service.score_one(patient, service)
        shelter = {
            "name": service["name"], "type": "shelter", "city": "",
            "email": "intake@example.org",  # demo placeholder recipient
        }
        sender = {
            "name": "Jordan Rivera", "org": "Community Outreach Services",
            "email": "jordan.rivera@example.org", "phone": "(808) 555-0199",
        }
        print(f"\nDrafting email: {patient['name']} -> {service['name']} "
              f"(confidence {scores['confidence']}%, compatibility {scores['compatibility']}%)")
        email = draft_patient_referral_email(patient, shelter, scores=scores, sender=sender, use_llm=use_llm)
        print(f"[info] draft status: {email['status']}")
        send_email(
            to_email=email["to_email"], subject=email["subject"], body=email["body"],
            from_email=email["from_email"], from_name=email["from_name"],
            to_name=email["to_name"], backend="console", open_preview=False,
        )


if __name__ == "__main__":
    main()
