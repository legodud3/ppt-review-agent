"""Download and parse PDF presentations from data/sources.json into data/decks/*.json.

Usage:
    python3 data/download.py               # process all PDF sources
    python3 data/download.py <deck_id>     # process one specific deck

HTM-format sources (EDGAR inline XBRL) are skipped — PDF only in v0.1.
"""
import json
import sys
from datetime import date
from pathlib import Path

import pdfplumber
import requests

_ROOT = Path(__file__).parent.parent  # project root (data/download.py → data/ → root)

SOURCES = _ROOT / "data" / "sources.json"
DECKS_DIR = _ROOT / "data" / "decks"
RAW_DIR = _ROOT / "data" / "raw"


def fetch_pdf(url: str, dest: Path) -> bool:
    """Download URL to dest. Returns True on success."""
    try:
        resp = requests.get(url, timeout=60, headers={"User-Agent": "Mozilla/5.0"})
        resp.raise_for_status()
        dest.write_bytes(resp.content)
        if dest.stat().st_size == 0:
            print("  Fetch error: server returned empty body")
            dest.unlink(missing_ok=True)
            return False
        return True
    except Exception as e:
        print(f"  Fetch error: {e}")
        return False


def parse_pdf(pdf_path: Path) -> list[dict]:
    """Extract per-page text. Returns list of {page, title, body}."""
    slides = []
    with pdfplumber.open(pdf_path) as pdf:
        for i, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
            title = lines[0] if lines else ""
            body = "\n".join(lines[1:]) if len(lines) > 1 else ""
            slides.append({"page": i, "title": title, "body": body})
    return slides


def main() -> None:
    DECKS_DIR.mkdir(parents=True, exist_ok=True)
    RAW_DIR.mkdir(parents=True, exist_ok=True)

    sources = json.loads(SOURCES.read_text(encoding="utf-8"))
    deck_id_filter = sys.argv[1] if len(sys.argv) > 1 else None

    for source in sources:
        deck_id = source["deck_id"]

        if deck_id_filter and deck_id != deck_id_filter:
            continue

        if source.get("format") != "pdf":
            print(f"[{deck_id}] Skipping — format is '{source.get('format')}' (PDF only in v0.1)")
            continue

        out_path = DECKS_DIR / f"{deck_id}.json"
        if out_path.exists():
            print(f"[{deck_id}] Already parsed — skipping")
            continue

        print(f"[{deck_id}] Downloading...", end=" ", flush=True)
        raw_path = RAW_DIR / f"{deck_id}.pdf"
        if not fetch_pdf(source["url"], raw_path):
            continue

        print("Parsing...", end=" ", flush=True)
        try:
            slides = parse_pdf(raw_path)
        except Exception as e:
            print(f"Parse error: {e}")
            continue

        deck = {
            "deck_id": deck_id,
            "source_type": source["source_type"],
            "entity": source.get("entity", ""),
            "title": source.get("title", ""),
            "url": source["url"],
            "parsed_date": str(date.today()),
            "slides": slides,
        }
        out_path.write_text(json.dumps(deck, indent=2), encoding="utf-8")
        print(f"Done ({len(slides)} slides → {out_path})")


if __name__ == "__main__":
    main()
