"""
ocr_batch.py — CLI runner for batch handwritten-note OCR, organized by patient.

Engine : Google Cloud Document AI (image → plain text)
Model  : htr/images/<set>/  →  one patient per set. The patient name is parsed
         from the note's "Patient Name:" line. Each note's OCR text is appended
         as a new submission to that patient's row in the Supabase `patient_raw`
         table (Name + data_1..data_10); a new name inserts a new row. After a
         set is written, its source images are disposed (deleted) unless
         --keep-images is given.

Run from the backend/ directory:
    python -m htr.ocr_batch                                       # every set in htr/images/
    python -m htr.ocr_batch --folder htr/images/trialTest1 --keep-images

Required .env keys:
    GOOGLE_PROJECT_ID, GOOGLE_PROCESSOR_ID, GOOGLE_APPLICATION_CREDENTIALS
    SUPABASE_URL, and SUPABASE_SERVICE_ROLE_KEY (preferred) or SUPABASE_ANON_KEY
"""

import argparse
import sys
from pathlib import Path

# Windows consoles default to cp1252; let stdout/stderr tolerate the box-drawing
# characters and any non-ASCII OCR text we print instead of crashing on them.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(errors="replace")
    except (AttributeError, ValueError):
        pass

# ─── Path bootstrap ───────────────────────────────────────────────────────────
_HTR_DIR     = Path(__file__).resolve().parent   # backend/htr/
_BACKEND_DIR = _HTR_DIR.parent                   # backend/

if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from dotenv import load_dotenv
load_dotenv(_BACKEND_DIR / ".env")

_IMAGES_DIR  = _HTR_DIR / "images"

from app.services.htr_service import process_image_set, SUPPORTED_EXTENSIONS


def _discover_sets(folder_arg: str | None) -> tuple[list[Path], Path | None]:
    """Return (sets, loose_root).

    sets       : list of image-set folders to process (one patient each).
    loose_root : htr/images/ itself when it holds loose image files directly
                 (processed as one extra set, never removed), else None.
    """
    if folder_arg:
        folder = Path(folder_arg)
        if not folder.is_absolute():
            folder = _BACKEND_DIR / folder
        if not folder.is_dir():
            raise FileNotFoundError(f"Set folder not found: {folder}")
        return [folder], None

    if not _IMAGES_DIR.is_dir():
        raise FileNotFoundError(f"Images dir not found: {_IMAGES_DIR}")

    sets = sorted(p for p in _IMAGES_DIR.iterdir() if p.is_dir())
    loose = any(
        p.is_file() and p.suffix.lower() in SUPPORTED_EXTENSIONS
        for p in _IMAGES_DIR.iterdir()
    )
    return sets, (_IMAGES_DIR if loose else None)


def _print_summary(s: dict) -> None:
    if s.get("skipped"):
        print(f"  • {s['set']}/ — skipped ({s['skipped']})")
        return
    if s["display_name"] is None:
        print(f"  • {s['set']}/ — no patient name parsed; nothing written (kept for retry)")
        return
    who = s["display_name"]
    if s["db_error"]:
        print(f"  • {s['set']}/ → patient_raw[{who}]: DB ERROR ({s['db_error'][:80]}) — images kept")
        return
    action = "new row" if s["created"] else "appended"
    cols = ", ".join(c for c in s["columns"] if c) or "-"
    disp = "images disposed" if s["disposed"] else "images kept"
    err = f", {s['errors']} OCR error(s)" if s["errors"] else ""
    print(f"  • {s['set']}/ → patient_raw[{who}]  ({action}: {s['n_written']} submission(s) → {cols}, {disp}{err})")


def main():
    parser = argparse.ArgumentParser(
        description="Batch HTR — handwritten notes → per-patient CSV/TXT via Google Document AI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--folder", "-f",
        help="Process a single image-set folder (default: every set under htr/images/)",
    )
    parser.add_argument(
        "--keep-images", action="store_true",
        help="Do not delete source images after processing (use for repeatable test fixtures)",
    )
    parser.add_argument(
        "--delay", type=float, default=0.5,
        help="Seconds between API calls (default: 0.5)",
    )

    args = parser.parse_args()

    try:
        sets, loose_root = _discover_sets(args.folder)
    except FileNotFoundError as exc:
        print(f"[error] {exc}", file=sys.stderr)
        sys.exit(1)

    if not sets and not loose_root:
        print(
            "[error] No image sets found under htr/images/. "
            "Add one subfolder of images per patient.",
            file=sys.stderr,
        )
        sys.exit(1)

    dispose = not args.keep_images
    n_sets = len(sets) + (1 if loose_root else 0)

    print("\nHTR Batch Processor — OCR → Supabase patient_raw")
    print(f"Engine  : Google Cloud Document AI")
    print(f"Sets    : {n_sets}")
    print(f"Dispose : {'yes' if dispose else 'no (--keep-images)'}\n")

    summaries = []
    for set_dir in sets:
        print(f"── Set: {set_dir.name}/ ──")
        summaries.append(process_image_set(
            set_dir, delay=args.delay, dispose=dispose, remove_set_dir=True,
        ))
    if loose_root:
        print("── Set: (loose images in images/) ──")
        summaries.append(process_image_set(
            loose_root, delay=args.delay, dispose=dispose, remove_set_dir=False,
        ))

    print("\nDone. Profiles updated:")
    for s in summaries:
        _print_summary(s)

    total_errors = sum(s["errors"] for s in summaries)
    if total_errors:
        print(f"\n[warn] {total_errors} OCR error(s) across all sets — "
              f"affected sets were not disposed; see logs above.")


if __name__ == "__main__":
    main()
