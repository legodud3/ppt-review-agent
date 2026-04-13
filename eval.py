"""Run the PPT review agent on all parsed decks and write output.

Usage:
    python3 eval.py                     # review all decks
    python3 eval.py --deck <deck_id>    # review one deck (for testing)
"""
import argparse
import json
import os
import sys
import tomllib
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

import agent

load_dotenv()

with open("config.toml", "rb") as _f:
    _config = tomllib.load(_f)

DATASET_DIR = Path(_config["eval"]["dataset_dir"])
RUNS_DIR = Path(_config["eval"]["runs_dir"])
SYSTEM_PROMPT_FILE = Path(_config["eval"]["system_prompt_file"])


def build_ratings_template(deck_ids: list[str], run_dir: Path) -> None:
    """Write a ratings_template.json the human fills in after reviewing output."""
    template = {}
    for deck_id in deck_ids:
        redlines_path = run_dir / deck_id / "redlines.json"
        if redlines_path.exists():
            redlines = json.loads(redlines_path.read_text(encoding="utf-8"))
            slide_ratings = {page: None for page in redlines}
        else:
            slide_ratings = {}
        entry: dict = {"slide_ratings": slide_ratings, "notes": ""}
        if not slide_ratings:
            entry["warning"] = "redlines.json not found — agent may not have called finish()"
        template[deck_id] = entry
    ratings_path = run_dir / "ratings.json"
    ratings_path.write_text(json.dumps(template, indent=2), encoding="utf-8")
    print(f"\nRatings template written to {ratings_path}")
    print("Fill in each slide rating: true (agent correct) or false (agent wrong), then run:")
    print(f"  python3 score.py {run_dir}")


def build_reflexion_context(deck_id: str, prior_run_dir: Path) -> str | None:
    """Build reflexion context string from prior redlines + human ratings.
    Returns None if no prior data or all slides were correct.
    """
    ratings_path = prior_run_dir / "ratings.json"
    redlines_path = prior_run_dir / deck_id / "redlines.json"

    if not ratings_path.exists() or not redlines_path.exists():
        return None

    ratings = json.loads(ratings_path.read_text(encoding="utf-8"))
    redlines = json.loads(redlines_path.read_text(encoding="utf-8"))
    deck_ratings = ratings.get(deck_id, {}).get("slide_ratings", {})

    lines = [
        "[Reflexion context] On your previous review of this deck you wrote the following. "
        "Human ratings are shown — use them to improve your review:\n"
    ]
    has_incorrect = False
    for page_str, feedback in sorted(redlines.items(), key=lambda x: int(x[0])):
        verdict = deck_ratings.get(page_str)
        if verdict is True:
            label = "CORRECT"
        elif verdict is False:
            label = "INCORRECT"
            has_incorrect = True
        else:
            label = "UNRATED"
        lines.append(f"  Slide {page_str}: \"{feedback}\" → Human rating: {label}")

    notes = ratings.get(deck_id, {}).get("notes", "")
    if notes:
        lines.append(f"\nReviewer notes: {notes}")

    lines.append("\nFocus especially on the slides rated INCORRECT. Revise your approach for those.")

    if not has_incorrect:
        return None  # No INCORRECT slides — no reflexion needed

    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--deck", default=None, help="Review a single deck by deck_id")
    parser.add_argument(
        "--reflexion",
        default=None,
        metavar="PRIOR_RUN_DIR",
        help="Re-run with reflexion context from a prior rated run (e.g. runs/20260413_120000)",
    )
    args = parser.parse_args()

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key or api_key == "your_key_here":
        print("Error: set GEMINI_API_KEY in .env", file=sys.stderr)
        sys.exit(1)

    if not SYSTEM_PROMPT_FILE.exists():
        print(f"Error: {SYSTEM_PROMPT_FILE} not found", file=sys.stderr)
        sys.exit(1)

    prior_run_dir = Path(args.reflexion) if args.reflexion else None
    if prior_run_dir and not prior_run_dir.exists():
        print(f"Error: prior run dir {prior_run_dir} not found", file=sys.stderr)
        sys.exit(1)

    if args.deck:
        deck_files = [DATASET_DIR / f"{args.deck}.json"]
        if not deck_files[0].exists():
            print(f"Error: {deck_files[0]} not found", file=sys.stderr)
            sys.exit(1)
    else:
        deck_files = sorted(DATASET_DIR.glob("*.json"))

    if not deck_files:
        print(f"Error: no deck JSON files in {DATASET_DIR} — run data/download.py first", file=sys.stderr)
        sys.exit(1)

    system_prompt = SYSTEM_PROMPT_FILE.read_text(encoding="utf-8")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    suffix = "_reflexion" if prior_run_dir else ""
    run_dir = RUNS_DIR / f"{timestamp}{suffix}"
    run_dir.mkdir(parents=True)

    print(f"Run: {run_dir}")
    print(f"Decks: {len(deck_files)}")
    print(f"Model: {agent.MODEL} | thinking: {agent._THINKING_LEVEL} | max_iter: {agent.MAX_ITERATIONS}")
    if prior_run_dir:
        print(f"Reflexion: {prior_run_dir}")
    print()

    summary = []
    reviewed_deck_ids = []

    for deck_file in deck_files:
        deck = json.loads(deck_file.read_text(encoding="utf-8"))
        deck_id = deck["deck_id"]
        output_dir = run_dir / deck_id
        n_slides = len(deck["slides"])

        reflexion_context = None
        if prior_run_dir:
            reflexion_context = build_reflexion_context(deck_id, prior_run_dir)
            if reflexion_context is None:
                print(f"[{deck_id}] No INCORRECT slides in prior run — skipping reflexion")
                continue

        mode = "reflexion" if reflexion_context else "baseline"
        print(f"[{deck_id}] Reviewing ({n_slides} slides, {mode})...", end=" ", flush=True)

        try:
            review, tokens = agent.run(deck, output_dir, system_prompt, api_key, reflexion_context)
        except Exception as exc:
            print(f"ERROR: {exc}")
            summary.append({"deck_id": deck_id, "mode": mode, "error": str(exc)})
            reviewed_deck_ids.append(deck_id)
            continue

        total_tokens = sum(tokens.values())
        n_redlines = len(review["redlines"])

        print(
            f"→ {n_redlines}/{n_slides} slides redlined  "
            f"({total_tokens:,} tokens: {tokens['input']:,} in / "
            f"{tokens['thinking']:,} think / {tokens['output']:,} out)"
        )

        summary.append({
            "deck_id": deck_id,
            "mode": mode,
            "slides": n_slides,
            "redlines": n_redlines,
            "has_narrative": bool(review["narrative"]),
            "tokens_input": tokens["input"],
            "tokens_thinking": tokens["thinking"],
            "tokens_output": tokens["output"],
            "tokens_total": total_tokens,
        })
        reviewed_deck_ids.append(deck_id)

    summary_path = run_dir / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    build_ratings_template(reviewed_deck_ids, run_dir)


if __name__ == "__main__":
    main()
