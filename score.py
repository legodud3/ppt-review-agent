"""Score a completed eval run using human ratings.

Usage:
    python3 score.py runs/<timestamp>

ratings.json format:
{
  "deck_id": {
    "slide_ratings": {"1": true, "2": false, "3": true},
    "notes": "free-form notes"
  }
}
"""
import json
import sys
from pathlib import Path


def score_run(run_dir: Path) -> None:
    ratings_path = run_dir / "ratings.json"
    if not ratings_path.exists():
        print(f"Error: {ratings_path} not found.")
        print(f"Fill in ratings.json in {run_dir} first.")
        sys.exit(1)

    ratings = json.loads(ratings_path.read_text(encoding="utf-8"))

    # Filter out decks with no ratings filled in yet (all None)
    rated = {
        deck_id: r for deck_id, r in ratings.items()
        if any(v is not None for v in r.get("slide_ratings", {}).values())
    }
    if not rated:
        print("No ratings filled in yet.")
        return

    print(f"Run: {run_dir}")
    print(f"{'Deck':<50} {'Correct':>8} {'Total':>6} {'%':>6}")
    print("-" * 75)

    total_correct = 0
    total_slides = 0

    for deck_id, rating in rated.items():
        slide_ratings = {k: v for k, v in rating.get("slide_ratings", {}).items() if v is not None}
        correct = sum(1 for v in slide_ratings.values() if v)
        total = len(slide_ratings)
        pct = (correct / total * 100) if total else 0.0
        print(f"{deck_id:<50} {correct:>8} {total:>6} {pct:>5.1f}%")
        if rating.get("notes"):
            print(f"  Notes: {rating['notes']}")
        total_correct += correct
        total_slides += total

    print("-" * 75)
    overall = (total_correct / total_slides * 100) if total_slides else 0.0
    print(f"{'TOTAL':<50} {total_correct:>8} {total_slides:>6} {overall:>5.1f}%")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 score.py runs/<timestamp>")
        sys.exit(1)
    score_run(Path(sys.argv[1]))
