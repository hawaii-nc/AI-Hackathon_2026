"""
htr_service.py — Batch HTR processing service.
Used by htr/ocr_batch.py (CLI) and future API batch endpoints.
OCR engine: Google Cloud Document AI (plain text output only).
"""

import csv
import re
import time
from datetime import datetime
from pathlib import Path

from app.services.document_ai import process_handwritten_note

SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".tiff", ".tif", ".bmp", ".webp", ".gif", ".pdf"}


# ─── Image collection ─────────────────────────────────────────────────────────

def collect_images(paths: list[str], folder: str | None, base_dir: Path) -> list[Path]:
    """Gather image paths from an explicit list and/or a folder."""
    images: list[Path] = []

    if folder:
        folder_path = Path(folder)
        if not folder_path.is_absolute():
            folder_path = base_dir / folder_path
        if not folder_path.is_dir():
            raise FileNotFoundError(f"Folder not found: {folder_path}")
        for ext in SUPPORTED_EXTENSIONS:
            images.extend(sorted(folder_path.glob(f"*{ext}")))
            images.extend(sorted(folder_path.glob(f"*{ext.upper()}")))
        images = sorted(set(images), key=lambda p: p.name)

    for p in paths:
        path = Path(p)
        if not path.is_absolute():
            path = base_dir / path
        if not path.exists():
            print(f"[warn] File not found, skipping: {p}")
            continue
        if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
            print(f"[warn] Unsupported type, skipping: {p}")
            continue
        images.append(path)

    return images


# ─── Batch processor ──────────────────────────────────────────────────────────

def process_batch(images: list[Path], delay: float = 0.5) -> list[dict]:
    """
    Run Google Document AI OCR on each image.
    Returns list of dicts: {filename, processed_at, transcription, error}.
    """
    results: list[dict] = []

    for i, image_path in enumerate(images, 1):
        print(f"[{i}/{len(images)}] {image_path.name}")

        with open(image_path, "rb") as f:
            image_bytes = f.read()

        error = ""
        transcription = ""
        try:
            transcription = process_handwritten_note(image_bytes, filename=image_path.name)
        except Exception as exc:
            error = str(exc)
            print(f"  [error] {exc}")

        preview = transcription.replace("\n", " ")[:80]
        if preview:
            print(f"  → {preview}{'...' if len(transcription) > 80 else ''}")

        results.append({
            "filename"    : image_path.name,
            "processed_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "transcription": transcription,
            "error"       : error,
        })

        if i < len(images):
            time.sleep(delay)

    return results


# ─── Output folder name ───────────────────────────────────────────────────────

def batch_slug(override: str | None = None) -> str:
    """Return a filesystem-safe output folder name."""
    if override:
        return re.sub(r"[^a-zA-Z0-9_\-]", "_", override).strip("_") or "batch"
    return f"batch_{datetime.now().strftime('%Y%m%d_%H%M%S')}"


# ─── Output writers ───────────────────────────────────────────────────────────

def write_txt(results: list[dict], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("Handwritten Note Transcriptions\n")
        f.write(f"Generated : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"Engine    : Google Cloud Document AI\n")
        f.write("=" * 72 + "\n\n")

        for entry in results:
            f.write(f"FILE : {entry['filename']}\n")
            f.write(f"TIME : {entry['processed_at']}\n")
            f.write("-" * 40 + "\n")
            if entry["error"]:
                f.write(f"[ERROR] {entry['error']}\n")
            else:
                f.write(entry["transcription"] or "[no text detected]")
                f.write("\n")
            f.write("\n" + "=" * 72 + "\n\n")

    print(f"  [txt] → {output_path}")


_CSV_FIELDS = ["filename", "processed_at", "transcription", "error"]


def write_csv(results: list[dict], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=_CSV_FIELDS)
        writer.writeheader()
        for entry in results:
            writer.writerow({
                "filename"     : entry["filename"],
                "processed_at" : entry["processed_at"],
                "transcription": entry["transcription"].replace("\n", " "),
                "error"        : entry["error"],
            })
    print(f"  [csv] → {output_path}")
