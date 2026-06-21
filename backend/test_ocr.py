"""
test_ocr.py — End-to-end OCR test for the per-patient → Supabase pipeline.

Generates a sample note PNG inside an image set, runs it through
process_image_set with the Supabase writer STUBBED (no DB needed, nothing
written remotely), and verifies the parsed patient name is routed to an
upsert_patient_submission call.

Usage (from backend/):
    python test_ocr.py
"""

import sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

# Tolerate non-ASCII console output (cp1252 default on Windows).
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(errors="replace")
    except (AttributeError, ValueError):
        pass

import app.services.supabase_client as sbc
from app.services import htr_service

SAMPLE_TEXT = (
    "Patient Name: John Doe\n"
    "Date: 2026-06-20\n"
    "Notes: Client needs emergency shelter.\n"
    "Has two children. Veteran status: No.\n"
    "Languages: English, Spanish."
)

_HTR_DIR   = Path(__file__).parent / "htr"
SET_DIR    = _HTR_DIR / "images" / "_test_john_doe"
IMAGE_PATH = SET_DIR / "sample_note.png"


def create_sample_png() -> Path:
    img = Image.new("RGB", (600, 200), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("arial.ttf", 18)
    except OSError:
        font = ImageFont.load_default()
    draw.multiline_text((20, 20), SAMPLE_TEXT, fill=(0, 0, 0), font=font, spacing=6)
    SET_DIR.mkdir(parents=True, exist_ok=True)
    img.save(IMAGE_PATH)
    print(f"[+] Sample PNG created: {IMAGE_PATH}")
    return IMAGE_PATH


def main():
    create_sample_png()

    # Stub the DB writer so the test needs no Supabase and writes nothing remote.
    # process_image_set imports upsert_patient_submission lazily from this module,
    # so patching the module attribute is enough.
    calls = []
    def fake_upsert(name, ocr_text):
        calls.append({"name": name, "text": ocr_text})
        return {
            "action": "created" if len(calls) == 1 else "appended",
            "name": name,
            "column": f"data_{len(calls)}",
        }
    sbc.upsert_patient_submission = fake_upsert

    print("[+] Running pipeline (real OCR, stubbed DB, disposal off)...")
    summary = htr_service.process_image_set(SET_DIR, dispose=False)

    print("\n--- Summary ---")
    print(summary)
    print("DB calls:", calls)

    assert summary["display_name"] == "John Doe", f"expected John Doe, got {summary['display_name']!r}"
    assert calls and calls[0]["name"] == "John Doe", "DB upsert not called with parsed name"
    assert summary["n_written"] == 1, f"expected 1 submission, got {summary['n_written']}"
    print("\n[ok] John Doe routed to patient_raw upsert (data_1) — stubbed, no real DB write.")


if __name__ == "__main__":
    main()
