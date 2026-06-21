"""Run the referral-email flow locally — no AWS, no keys required.

Examples (run from the backend/ folder):

    # Draft + preview using built-in mock data (works with ZERO setup):
    python test_referral_local.py

    # Use the SMTP backend instead of the console preview
    # (start a catcher first:  python -m aiosmtpd -n -l localhost:1025):
    python test_referral_local.py --smtp

    # Pull the real client + shelter from Supabase by id (needs .env):
    python test_referral_local.py --client-id <uuid> --shelter-id <uuid>

What you get with no flags:
  * The email is drafted (via Gemini if GEMINI_API_KEY is set and reachable,
    otherwise a clearly-marked placeholder for a human to complete).
  * It's saved to backend/outbox/ as .html + .eml and opened in your browser.
  * Nothing is sent anywhere.
"""

import argparse
import os
import sys

# Make `from app...` imports work no matter where this is run from.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.services.referral import draft_referral_email
from app.services.email_service import send_email

# ---- Mock rows, shaped like what Supabase would return ---------------------
MOCK_CLIENT = {
    "id": "mock-client-001",
    "needs": ["housing", "mental_health", "food"],
    "urgency": "high",
    "has_children": True,
    "veteran": False,
    "languages": ["English"],
    "summary": (
        "Single parent with two young children, recently lost housing after a "
        "job loss. Currently staying in a vehicle and needs short-term shelter "
        "plus help connecting to food and mental health support."
    ),
}

MOCK_SHELTER = {
    "id": "mock-shelter-042",
    "name": "Aloha Family Shelter",
    "type": "family shelter",
    "address": "1234 Kapiolani Blvd",
    "city": "Honolulu",
    "island": "Oahu",
    "phone": "(808) 555-0142",
    "email": "intake@alohafamilyshelter.example.org",
}

MOCK_SENDER = {
    "name": "Jordan Rivera",
    "org": "Community Outreach Services",
    "email": "jordan.rivera@example.org",
    "phone": "(808) 555-0199",
}


def main():
    parser = argparse.ArgumentParser(description="Test the referral email flow locally.")
    parser.add_argument("--client-id", help="Pull this client from Supabase instead of using mock data.")
    parser.add_argument("--shelter-id", help="Pull this shelter from Supabase instead of using mock data.")
    parser.add_argument("--smtp", action="store_true", help="Send via SMTP backend instead of console preview.")
    parser.add_argument("--no-open", action="store_true", help="Don't auto-open the HTML preview in the browser.")
    parser.add_argument("--placeholder", "--template", dest="placeholder", action="store_true",
                        help="Skip Gemini and leave a placeholder draft (no API call / quota).")
    args = parser.parse_args()

    # Resolve client + shelter (Supabase if ids given, otherwise mock).
    client_profile = MOCK_CLIENT
    shelter = MOCK_SHELTER
    if args.client_id or args.shelter_id:
        from app.services.supabase_client import get_client_by_id, get_shelter_by_id
        if args.client_id:
            print(f"Fetching client {args.client_id} from Supabase...")
            client_profile = get_client_by_id(args.client_id)
        if args.shelter_id:
            print(f"Fetching shelter {args.shelter_id} from Supabase...")
            shelter = get_shelter_by_id(args.shelter_id)

    use_llm = not args.placeholder
    if args.placeholder:
        print("[info] --placeholder set - skipping Gemini, leaving a placeholder draft.\n")
    elif not os.getenv("GEMINI_API_KEY"):
        print("[info] No GEMINI_API_KEY found - will leave a placeholder draft.\n")

    print("Drafting referral email...")
    email = draft_referral_email(client_profile, shelter, sender=MOCK_SENDER, use_llm=use_llm)
    print(f"[info] draft status: {email['status']}\n")

    backend = "smtp" if args.smtp else "console"
    send_email(
        to_email=email["to_email"],
        subject=email["subject"],
        body=email["body"],
        from_email=email["from_email"],
        from_name=email["from_name"],
        to_name=email["to_name"],
        backend=backend,
        open_preview=not args.no_open,
    )


if __name__ == "__main__":
    main()
