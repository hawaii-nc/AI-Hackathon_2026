"""
ocr_batch.py — CLI runner for batch handwritten note OCR.
Engine: Google Cloud Document AI (image → plain text).
Output: .txt and/or .csv in htr/outputs/<name>/

Run from backend/ directory:
    python -m htr.ocr_batch --folder htr/images
    python -m htr.ocr_batch --folder htr/images/20260620_143022 --format csv
    python -m htr.ocr_batch htr/images/20260620_143022/note1.jpg

Required .env keys:
    GOOGLE_PROJECT_ID
    GOOGLE_PROCESSOR_ID
    GOOGLE_APPLICATION_CREDENTIALS
"""

import argparse
import sys
from pathlib import Path

# ─── Path bootstrap ───────────────────────────────────────────────────────────
_HTR_DIR     = Path(__file__).resolve().parent   # backend/htr/
_BACKEND_DIR = _HTR_DIR.parent                   # backend/

if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from dotenv import load_dotenv
load_dotenv(_BACKEND_DIR / ".env")

_IMAGES_DIR  = _HTR_DIR / "images"
_OUTPUTS_DIR = _HTR_DIR / "outputs"

from app.services.htr_service import (
    collect_images,
    process_batch,
    batch_slug,
    write_txt,
    write_csv,
)


def main():
    parser = argparse.ArgumentParser(
        description="Batch HTR — handwritten note images → .txt / .csv via Google Document AI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "images", nargs="*",
        help="Image paths (relative to backend/ or absolute)",
    )
    parser.add_argument(
        "--folder", "-f",
        help="Process all images in this folder. Example: htr/images/20260620_143022",
    )
    parser.add_argument(
        "--format", choices=["txt", "csv", "both"], default="both",
        help="Output format (default: both)",
    )
    parser.add_argument(
        "--name", "-n",
        help="Output subfolder name inside htr/outputs/ (default: batch_<timestamp>)",
    )
    parser.add_argument(
        "--delay", type=float, default=0.5,
        help="Seconds between API calls (default: 0.5)",
    )

    args = parser.parse_args()

    if not args.images and not args.folder:
        parser.print_help()
        sys.exit(1)

    images = collect_images(args.images, args.folder, base_dir=_BACKEND_DIR)

    if not images:
        print("[error] No supported image files found.", file=sys.stderr)
        sys.exit(1)

    print(f"\nHTR Batch Processor")
    print(f"Engine  : Google Cloud Document AI")
    print(f"Images  : {len(images)}")
    print(f"Format  : {args.format}\n")

    results = process_batch(images, delay=args.delay)

    slug = batch_slug(override=args.name)
    out_dir = _OUTPUTS_DIR / slug
    print(f"\nWriting output → htr/outputs/{slug}/")

    base = out_dir / "handwriting_output"
    if args.format in ("txt", "both"):
        write_txt(results, base.with_suffix(".txt"))
    if args.format in ("csv", "both"):
        write_csv(results, base.with_suffix(".csv"))

    print(f"\nDone. {len(results)} image(s) processed.")
    errors = [r for r in results if r["error"]]
    if errors:
        print(f"[warn] {len(errors)} error(s):")
        for r in errors:
            print(f"  {r['filename']}: {r['error']}")


if __name__ == "__main__":
    main()
