"""
htr_service.py — Batch HTR processing service.
Used by htr/ocr_batch.py (CLI) and future API batch endpoints.
OCR engine: Google Cloud Document AI (plain text output only).

Output model: results are organized by PATIENT and written to the Supabase
`patient_raw` table (no local .csv/.txt). Each image set (a folder under
htr/images/) maps to one patient; the patient name is parsed from the
transcription's "Patient Name:" line. Each note's OCR text is appended as a new
submission to that patient's row (one row per patient; Name + data_1..data_N);
a new name inserts a new row. After a set is written it can be disposed (source
images deleted), so htr/images/ behaves like a self-emptying inbox.
"""

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


# ─── Patient name parsing ─────────────────────────────────────────────────────

# A "Name" field line, optionally prefixed with Patient/Client (e.g. "Patient Name: Jane Doe").
_NAME_LINE_RE = re.compile(r"^\s*(?:patient|client)?\s*name\s*[:\-]\s*(.+)$", re.IGNORECASE)
# Field labels that may run onto the same line when OCR drops the newlines.
_NEXT_FIELD_RE = re.compile(
    r"\b(?:location|address|date|dob|d\.o\.b|age|sex|gender|phone|diagnosis|notes)\b\s*[:\-]",
    re.IGNORECASE,
)


def parse_patient_name(transcription: str) -> str | None:
    """Return the patient name from a transcription's 'Patient Name:' line, or None."""
    if not transcription:
        return None
    for line in transcription.splitlines():
        m = _NAME_LINE_RE.match(line)
        if not m:
            continue
        name = m.group(1)
        # If a following field ran onto the same line (lost newline), cut it off.
        name = _NEXT_FIELD_RE.split(name, maxsplit=1)[0]
        name = name.strip(" \t-:,.;")
        if name:
            return name
    return None


def patient_slug(name: str | None) -> str:
    """Filesystem-safe identity key. 'Lawrence Zheng' -> 'Lawrence_Zheng'.

    Case/spacing-insensitive: any spelling that normalizes to the same slug is
    treated as the same patient (an existing outputs/<slug>/ dir = a match → merge).
    Unnamed sets fall back to '_unidentified'.
    """
    if not name:
        return "_unidentified"
    cleaned = re.sub(r"[^A-Za-z0-9]+", " ", name).strip()
    if not cleaned:
        return "_unidentified"
    return "_".join(word.capitalize() for word in cleaned.split())


def resolve_set_patient(results: list[dict]) -> tuple[str | None, str]:
    """Determine (display_name, slug) for an image set — the first parsed name wins.

    Since one set = one patient, a second, differently-named note is flagged as a
    warning but does not change the routing.
    """
    display_name = None
    for r in results:
        name = parse_patient_name(r.get("transcription", ""))
        if not name:
            continue
        if display_name is None:
            display_name = name
        elif patient_slug(name) != patient_slug(display_name):
            print(f"  [warn] set contains multiple names: '{display_name}' vs '{name}' — using '{display_name}'")
    return display_name, patient_slug(display_name)


# ─── Image disposal ───────────────────────────────────────────────────────────

def dispose_set_images(images: list[Path], set_dir: Path, remove_set_dir: bool = True) -> None:
    """Delete processed source images; optionally remove the now-empty set folder.

    Destructive and irreversible — callers must only invoke this after a
    successful, fully-identified, error-free write.
    """
    deleted = 0
    for img in images:
        try:
            img.unlink()
            deleted += 1
        except OSError as exc:
            print(f"  [warn] could not delete {img.name}: {exc}")

    if remove_set_dir and set_dir.is_dir():
        leftover = [p for p in set_dir.iterdir() if p.name != ".gitkeep"]
        if not leftover:
            try:
                for p in list(set_dir.iterdir()):   # remove a stray .gitkeep
                    p.unlink()
                set_dir.rmdir()
                print(f"  [dispose] deleted {deleted} image(s), removed {set_dir.name}/")
                return
            except OSError as exc:
                print(f"  [warn] could not remove {set_dir}: {exc}")
        else:
            print(f"  [dispose] deleted {deleted} image(s); kept {set_dir.name}/ (other files remain)")
            return
    print(f"  [dispose] deleted {deleted} image(s)")


# ─── Per-patient orchestrator ─────────────────────────────────────────────────

def process_image_set(
    set_dir: Path,
    delay: float = 0.5,
    dispose: bool = True,
    remove_set_dir: bool = True,
) -> dict:
    """Process one image set (folder = one patient) end to end.

    collect → OCR → resolve patient name → write each note's text as a new
    submission to the patient's patient_raw row (insert if new, else append into
    the next empty data_N column) → dispose source images (only when identified,
    OCR- and DB-error-free, and dispose=True).
    Returns a summary dict.
    """
    set_dir = Path(set_dir).resolve()

    summary = {
        "set": set_dir.name, "slug": None, "display_name": None,
        "n_images": 0, "n_written": 0, "created": False, "columns": [],
        "disposed": False, "errors": 0, "db_error": None, "skipped": None,
    }

    images = collect_images([], str(set_dir), base_dir=set_dir)
    if not images:
        summary["skipped"] = "no images"
        return summary

    results = process_batch(images, delay=delay)
    display_name, slug = resolve_set_patient(results)
    summary["slug"] = slug
    summary["display_name"] = display_name
    summary["n_images"] = len(images)
    summary["errors"] = sum(1 for r in results if r["error"])

    if display_name is None:
        print(f"  [skip] no patient name parsed — keeping {set_dir.name}/ for retry (nothing written)")
        return summary

    # Write each successful note transcription as one submission to patient_raw.
    from app.services.supabase_client import upsert_patient_submission
    written: list[dict] = []
    try:
        for r in results:
            if r["error"] or not (r["transcription"] or "").strip():
                continue
            res = upsert_patient_submission(display_name, r["transcription"])
            written.append(res)
            print(f"  [db] {res['action']} {display_name!r} → {res['column']}")
    except Exception as exc:
        summary["db_error"] = str(exc)
        print(f"  [db-error] {exc}")

    summary["n_written"] = len(written)
    summary["created"] = any(w["action"] == "created" for w in written)
    summary["columns"] = [w["column"] for w in written]

    # Dispose only on a fully clean run (identified, no OCR error, DB write ok).
    if dispose and summary["errors"] == 0 and summary["db_error"] is None and written:
        dispose_set_images(images, set_dir, remove_set_dir=remove_set_dir)
        summary["disposed"] = True
    elif dispose and summary["db_error"]:
        print(f"  [skip-dispose] DB write failed — keeping {set_dir.name}/")
    elif dispose and summary["errors"]:
        print(f"  [skip-dispose] {summary['errors']} OCR error(s) — keeping {set_dir.name}/")
    elif dispose and not written:
        print(f"  [skip-dispose] nothing written — keeping {set_dir.name}/")

    return summary
