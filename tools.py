"""Tool implementations for the PPT review agent.

Tools hold deck data and accumulate redlines in memory.
Call finish() to flush redlines.json and narrative.txt to output_dir.
"""
import json
from pathlib import Path


class Tools:
    def __init__(self, deck: dict, output_dir: Path) -> None:
        self.deck = deck
        self.output_dir = output_dir
        self.redlines: dict[int, str] = {}
        self.narrative: str = ""
        self._finished: bool = False

    def read_deck_metadata(self) -> dict:
        """Return deck-level metadata."""
        return {
            "deck_id": self.deck["deck_id"],
            "entity": self.deck.get("entity", ""),
            "title": self.deck.get("title", ""),
            "total_pages": len(self.deck["slides"]),
            "source_type": self.deck.get("source_type", ""),
        }

    def read_slide(self, page_num: int) -> dict:
        """Return title and body text for a slide (1-based page numbering)."""
        slides = self.deck["slides"]
        if page_num < 1 or page_num > len(slides):
            return {"error": f"Page {page_num} out of range (1–{len(slides)})"}
        slide = slides[page_num - 1]
        return {"page": slide["page"], "title": slide["title"], "body": slide["body"]}

    def write_redline(self, page_num: int, feedback: str) -> str:
        """Save a redline comment for a slide."""
        self.redlines[page_num] = feedback
        return f"Redline saved for slide {page_num}."

    def write_narrative(self, text: str) -> str:
        """Save the deck-level narrative note."""
        self.narrative = text
        return "Narrative saved."

    def finish(self) -> str:
        """Flush redlines and narrative to disk and mark review complete."""
        self._finished = True
        redlines_path = self.output_dir / "redlines.json"
        narrative_path = self.output_dir / "narrative.txt"
        redlines_path.write_text(
            json.dumps({str(k): v for k, v in sorted(self.redlines.items())}, indent=2),
            encoding="utf-8",
        )
        narrative_path.write_text(self.narrative, encoding="utf-8")
        return "Review complete. Output saved."

    @property
    def is_finished(self) -> bool:
        return self._finished
