"""
test_ocr.py — End-to-end OCR test: generates a sample PNG, runs it through
Google Document AI, and writes output to htr/outputs/test/.

Usage (from backend/):
    python test_ocr.py
"""

from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

from app.services.htr_service import process_batch, write_txt, write_csv

SAMPLE_TEXT = (
    "Client Name: John Doe\n"
    "Date: 2026-06-20\n"
    "Notes: Client needs emergency shelter.\n"
    "Has two children. Veteran status: No.\n"
    "Languages: English, Spanish."
)

OUTPUT_DIR = Path(__file__).parent / "htr" / "outputs" / "test"
IMAGE_PATH = Path(__file__).parent / "htr" / "images" / "test_sample.png"


def create_sample_png() -> Path:
    img = Image.new("RGB", (600, 200), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("arial.ttf", 18)
    except OSError:
        font = ImageFont.load_default()
    draw.multiline_text((20, 20), SAMPLE_TEXT, fill=(0, 0, 0), font=font, spacing=6)
    IMAGE_PATH.parent.mkdir(parents=True, exist_ok=True)
    img.save(IMAGE_PATH)
    print(f"[+] Sample PNG created: {IMAGE_PATH}")
    return IMAGE_PATH


def main():
    image_path = create_sample_png()
    print("[+] Running OCR via Google Document AI...")
    results = process_batch([image_path])

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    write_txt(results, OUTPUT_DIR / "output.txt")
    write_csv(results, OUTPUT_DIR / "output.csv")

    print("\n--- Transcription ---")
    print(results[0]["transcription"] or "[no text detected]")
    if results[0]["error"]:
        print(f"[error] {results[0]['error']}")


if __name__ == "__main__":
    main()
