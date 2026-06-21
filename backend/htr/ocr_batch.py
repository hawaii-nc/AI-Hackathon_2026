"""
ocr_batch.py — Batch handwritten note OCR pipeline
Location: backend/htr/ocr_batch.py

Directory layout expected by this script (all paths relative to backend/):
    images/
        <timestamp>/          ← one folder per frontend submission batch
            note1.jpg
            note2.png
    outputs/
        <patient_slug>/       ← created automatically, named from extracted patient name
            handwriting_output.txt
            handwriting_output.csv

Run from backend/ directory:
    python -m htr.ocr_batch --folder images/20260620_143022
    python -m htr.ocr_batch --folder images/20260620_143022 --format csv
    python -m htr.ocr_batch images/20260620_143022/note1.jpg images/20260620_143022/note2.jpg

Or run directly (VSCode Run Button / F5):
    Set working directory to backend/ in launch.json, or pass --root to override.

Primary engine : Anthropic Claude Vision (claude-sonnet-4-6)
Fallback engine: Google Cloud Document AI
                 Requires GOOGLE_PROJECT_ID + GOOGLE_PROCESSOR_ID in .env
                 and Application Default Credentials configured.
"""

import argparse
import base64
import csv
import json
import mimetypes
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path

# ─── Path resolution ──────────────────────────────────────────────────────────
# When run with `python -m htr.ocr_batch` the cwd is backend/.
# When run directly (F5 in VSCode) the cwd may be htr/ — we normalise to backend/.

_THIS_FILE = Path(__file__).resolve()          # backend/htr/ocr_batch.py
_HTR_DIR   = _THIS_FILE.parent                 # backend/htr/
_BACKEND_DIR = _HTR_DIR.parent                 # backend/

# Add backend/ to sys.path so `from app.core.config import ...` works when
# the script is run directly rather than as a module.
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

# Load .env from backend/ (where it lives alongside requirements.txt)
from dotenv import load_dotenv
load_dotenv(_BACKEND_DIR / ".env")

IMAGES_DIR  = _HTR_DIR / "images"
OUTPUTS_DIR = _HTR_DIR / "outputs"

SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".tiff", ".tif", ".bmp", ".webp", ".gif", ".pdf"}
ANTHROPIC_MODEL = "claude-sonnet-4-6"

# ─── Prompts ──────────────────────────────────────────────────────────────────

_SYSTEM_PROMPT = """You are a clinical transcription assistant for social workers serving
unhoused individuals in Hawaii. Transcribe handwritten notes exactly, preserving all
acronyms and medical shorthand. Mark illegible sections as [illegible].
Never add information that is not present in the image."""

_USER_PROMPT = """Transcribe this handwritten note completely and accurately.

Return ONLY a JSON object — no prose before or after it:
{
  "raw_transcription": "<verbatim text exactly as written>",
  "client_name": "<full name if present, else null>",
  "date_of_note": "<date written in note, else null>",
  "presenting_needs": ["<need 1>", "<need 2>"],
  "barriers": ["<barrier 1>"],
  "health_flags": ["<any medical / mental health / SUD mentions>"],
  "veteran_flag": true or false,
  "urgency": "low" | "medium" | "high" | "crisis",
  "location_mentions": ["<any address or location name mentioned>"],
  "action_items": ["<any follow-up tasks written>"],
  "illegible_sections": ["<position or content of illegible text>"],
  "worker_name": "<social worker name or initials if present, else null>"
}"""

# ─── Claude Vision ────────────────────────────────────────────────────────────

def _mime_type(path: Path) -> str:
    mime, _ = mimetypes.guess_type(str(path))
    return mime or "image/jpeg"


def _b64(path: Path) -> str:
    with open(path, "rb") as f:
        return base64.standard_b64encode(f.read()).decode("utf-8")


def _parse_claude_response(text: str) -> dict:
    text = text.strip()
    # Strip markdown code fences if present
    if text.startswith("```"):
        parts = text.split("```")
        text = parts[1] if len(parts) >= 2 else text
        if text.startswith("json"):
            text = text[4:]
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {
            "raw_transcription": text,
            "_parse_error": "Claude response was not valid JSON; stored as raw transcription.",
        }


def run_claude_ocr(image_path: Path) -> dict:
    try:
        import anthropic
    except ImportError:
        raise RuntimeError("Run: pip install anthropic")

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY not set in .env")

    client = anthropic.Anthropic(api_key=api_key)
    result = _parse_claude_response(
        client.messages.create(
            model=ANTHROPIC_MODEL,
            max_tokens=2048,
            system=_SYSTEM_PROMPT,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": _mime_type(image_path),
                                "data": _b64(image_path),
                            },
                        },
                        {"type": "text", "text": _USER_PROMPT},
                    ],
                }
            ],
        ).content[0].text
    )
    result["_engine"] = "claude_vision"
    return result


# ─── Google Document AI (fallback) ────────────────────────────────────────────

def run_google_docai_ocr(image_path: Path) -> dict:
    try:
        from google.cloud import documentai
    except ImportError:
        raise RuntimeError("Run: pip install google-cloud-documentai")

    project_id  = os.getenv("GOOGLE_PROJECT_ID")
    processor_id = os.getenv("GOOGLE_PROCESSOR_ID")
    location     = os.getenv("GOOGLE_PROCESSOR_LOCATION", "us")

    if not project_id or not processor_id:
        raise RuntimeError("Set GOOGLE_PROJECT_ID and GOOGLE_PROCESSOR_ID in .env")

    with open(image_path, "rb") as f:
        image_bytes = f.read()

    docai = documentai.DocumentProcessorServiceClient(
        client_options={"api_endpoint": f"{location}-documentai.googleapis.com"}
    )
    name = docai.processor_path(project_id, location, processor_id)
    raw_doc = documentai.RawDocument(content=image_bytes, mime_type=_mime_type(image_path))
    result = docai.process_document(
        request=documentai.ProcessRequest(name=name, raw_document=raw_doc)
    )
    return {
        "raw_transcription": result.document.text or "",
        "_engine": "google_document_ai",
    }


# ─── Orchestrator ─────────────────────────────────────────────────────────────

def ocr_image(image_path: Path, use_fallback: bool = False) -> dict:
    if use_fallback:
        print(f"  [docai] {image_path.name}")
        return run_google_docai_ocr(image_path)
    try:
        result = run_claude_ocr(image_path)
        return result
    except Exception as exc:
        print(f"  [warn] Claude failed ({exc}), trying Document AI...")
        try:
            result = run_google_docai_ocr(image_path)
            result["_fallback_reason"] = str(exc)
            return result
        except Exception as fallback_exc:
            return {
                "raw_transcription": "",
                "_engine": "none",
                "_error": f"Claude: {exc} | Google: {fallback_exc}",
            }


# ─── Patient slug ─────────────────────────────────────────────────────────────

def _patient_slug(results: list[dict]) -> str:
    """
    Derive a safe directory name from the most common non-null client_name
    across the batch, or fall back to the current timestamp.
    """
    names = [
        r.get("client_name") for r in results
        if r.get("client_name") and r["client_name"] != "null"
    ]
    if names:
        # Most frequent name wins (handles multi-page notes for same patient)
        name = max(set(names), key=names.count)
        slug = re.sub(r"[^a-zA-Z0-9_\-]", "_", name.strip()).strip("_")
        return slug or "unknown_patient"
    return f"batch_{datetime.now().strftime('%Y%m%d_%H%M%S')}"


# ─── Output writers ───────────────────────────────────────────────────────────

def write_txt(results: list[dict], output_path: Path) -> None:
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("Handwritten Note Transcriptions\n")
        f.write(f"Generated : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write("=" * 72 + "\n\n")

        for entry in results:
            f.write(f"FILE     : {entry['filename']}\n")
            f.write(f"Engine   : {entry.get('_engine', 'unknown')}\n")
            if entry.get("date_of_note"):
                f.write(f"Note Date: {entry['date_of_note']}\n")
            if entry.get("worker_name"):
                f.write(f"Worker   : {entry['worker_name']}\n")
            f.write("-" * 40 + "\n")
            f.write((entry.get("raw_transcription") or entry.get("_error", "[no output]")) + "\n")

            needs    = entry.get("presenting_needs", [])
            barriers = entry.get("barriers", [])
            flags    = entry.get("health_flags", [])
            actions  = entry.get("action_items", [])
            urgency  = entry.get("urgency")

            if any([needs, barriers, flags, actions, urgency]):
                f.write("\n  [Extracted Fields]\n")
                if urgency:
                    f.write(f"  Urgency      : {urgency}\n")
                if needs:
                    f.write(f"  Needs        : {', '.join(needs)}\n")
                if barriers:
                    f.write(f"  Barriers     : {', '.join(barriers)}\n")
                if flags:
                    f.write(f"  Health Flags : {', '.join(flags)}\n")
                if entry.get("veteran_flag"):
                    f.write(f"  Veteran      : Yes\n")
                if actions:
                    f.write(f"  Action Items : {', '.join(actions)}\n")
                if entry.get("illegible_sections"):
                    f.write(f"  Illegible    : {', '.join(entry['illegible_sections'])}\n")

            f.write("\n" + "=" * 72 + "\n\n")

    print(f"  [txt] → {output_path.relative_to(_BACKEND_DIR)}")


_CSV_FIELDS = [
    "filename", "processed_at", "engine",
    "raw_transcription", "client_name", "date_of_note", "worker_name",
    "urgency", "veteran_flag",
    "presenting_needs", "barriers", "health_flags",
    "action_items", "location_mentions", "illegible_sections", "error",
]


def write_csv(results: list[dict], output_path: Path) -> None:
    def join(entry, key):
        val = entry.get(key, [])
        return "; ".join(val) if isinstance(val, list) else (val or "")

    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=_CSV_FIELDS, extrasaction="ignore")
        writer.writeheader()
        for entry in results:
            writer.writerow({
                "filename"          : entry.get("filename", ""),
                "processed_at"      : entry.get("processed_at", ""),
                "engine"            : entry.get("_engine", ""),
                "raw_transcription" : (entry.get("raw_transcription") or "").replace("\n", " "),
                "client_name"       : entry.get("client_name") or "",
                "date_of_note"      : entry.get("date_of_note") or "",
                "worker_name"       : entry.get("worker_name") or "",
                "urgency"           : entry.get("urgency") or "",
                "veteran_flag"      : "Yes" if entry.get("veteran_flag") else "No",
                "presenting_needs"  : join(entry, "presenting_needs"),
                "barriers"          : join(entry, "barriers"),
                "health_flags"      : join(entry, "health_flags"),
                "action_items"      : join(entry, "action_items"),
                "location_mentions" : join(entry, "location_mentions"),
                "illegible_sections": join(entry, "illegible_sections"),
                "error"             : entry.get("_error") or entry.get("_parse_error") or "",
            })

    print(f"  [csv] → {output_path.relative_to(_BACKEND_DIR)}")


# ─── Image collection ─────────────────────────────────────────────────────────

def collect_images(paths: list[str], folder: str | None) -> list[Path]:
    images: list[Path] = []

    if folder:
        # Allow relative paths from backend/ OR absolute
        folder_path = Path(folder)
        if not folder_path.is_absolute():
            # Try relative to htr/ first (e.g. "images/batch"), then backend/
            if (_HTR_DIR / folder_path).is_dir():
                folder_path = _HTR_DIR / folder_path
            else:
                folder_path = _BACKEND_DIR / folder_path
        if not folder_path.is_dir():
            print(f"[error] Folder not found: {folder_path}", file=sys.stderr)
            sys.exit(1)
        for ext in SUPPORTED_EXTENSIONS:
            images.extend(sorted(folder_path.glob(f"*{ext}")))
            images.extend(sorted(folder_path.glob(f"*{ext.upper()}")))
        images = sorted(set(images), key=lambda p: p.name)

    for p in paths:
        path = Path(p)
        if not path.is_absolute():
            if (_HTR_DIR / path).exists():
                path = _HTR_DIR / path
            else:
                path = _BACKEND_DIR / path
        if not path.exists():
            print(f"[warn] File not found, skipping: {p}")
            continue
        if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
            print(f"[warn] Unsupported type, skipping: {p}")
            continue
        images.append(path)

    return images


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Batch HTR — handwritten note images → .txt / .csv",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "images", nargs="*",
        help="Image paths to process (relative to backend/ or absolute)"
    )
    parser.add_argument(
        "--folder", "-f",
        help="Process all images in this folder (relative to backend/ or absolute). "
             "Example: images/20260620_143022"
    )
    parser.add_argument(
        "--format", choices=["txt", "csv", "both"], default="both",
        help="Output format (default: both)"
    )
    parser.add_argument(
        "--patient", "-p",
        help="Override patient name for output directory (default: auto-detected from notes)"
    )
    parser.add_argument(
        "--fallback", action="store_true",
        help="Skip Claude, use Google Document AI directly"
    )
    parser.add_argument(
        "--delay", type=float, default=0.5,
        help="Seconds between API calls to avoid rate limits (default: 0.5)"
    )

    args = parser.parse_args()

    if not args.images and not args.folder:
        parser.print_help()
        sys.exit(1)

    images = collect_images(args.images, args.folder)

    if not images:
        print("[error] No supported image files found.", file=sys.stderr)
        sys.exit(1)

    engine_label = "Google Document AI" if args.fallback else f"Claude Vision ({ANTHROPIC_MODEL}) + DocAI fallback"
    print(f"\nHTR Batch Processor")
    print(f"Backend : {_BACKEND_DIR}")
    print(f"Engine  : {engine_label}")
    print(f"Images  : {len(images)}")
    print(f"Format  : {args.format}\n")

    # ── Process images ──────────────────────────────────────────────────────
    results: list[dict] = []
    for i, image_path in enumerate(images, 1):
        print(f"[{i}/{len(images)}] {image_path.name}")
        result = ocr_image(image_path, use_fallback=args.fallback)
        result["filename"]     = image_path.name
        result["processed_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        preview = (result.get("raw_transcription") or "").replace("\n", " ")[:80]
        print(f"  → {preview}{'...' if len(result.get('raw_transcription','')) > 80 else ''}")

        if result.get("urgency") in ("high", "crisis"):
            print(f"  ⚠  URGENCY: {result['urgency'].upper()}")

        results.append(result)
        if i < len(images):
            time.sleep(args.delay)

    # ── Determine output directory ──────────────────────────────────────────
    patient_slug = args.patient if args.patient else _patient_slug(results)
    # Sanitize any user-supplied override the same way
    patient_slug = re.sub(r"[^a-zA-Z0-9_\-]", "_", patient_slug).strip("_") or "unknown_patient"

    out_dir = OUTPUTS_DIR / patient_slug
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"\nWriting output → outputs/{patient_slug}/")

    base = out_dir / "handwriting_output"
    if args.format in ("txt", "both"):
        write_txt(results, base.with_suffix(".txt"))
    if args.format in ("csv", "both"):
        write_csv(results, base.with_suffix(".csv"))

    print(f"\nDone. {len(results)} image(s) processed.")
    errors = [r for r in results if r.get("_error")]
    if errors:
        print(f"[warn] {len(errors)} error(s):")
        for r in errors:
            print(f"  {r['filename']}: {r['_error']}")


if __name__ == "__main__":
    main()
