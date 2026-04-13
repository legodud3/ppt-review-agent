# PPT Review Agent v0.1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a ReAct agent that reviews business presentations slide-by-slide (redlines) and holistically (narrative), evaluated by a human rater using a consulting-quality rubric.

**Architecture:** A data pipeline downloads and parses PDFs from `data/sources.json` into structured JSON. An agent ReAct loop reads slides via tools and writes redlines + a narrative. An eval runner orchestrates the loop across all decks and writes output. A score script reads human ratings and computes accuracy. A reflexion flag re-runs the agent with prior feedback as context.

**Tech Stack:** Python 3.11+, `google-genai` (Gemini function calling), `pdfplumber` (PDF text extraction), `tomllib` (built-in, config parsing), `python-dotenv`, `pytest`

---

## File Map

```
ppt-review-agent/
├── config.toml              ← tunable parameters (model, iterations, paths)
├── system_prompt.md         ← rubric — edit this to improve the agent
├── requirements.txt         ← Python dependencies
├── .env.example             ← template showing required env vars
├── agent.py                 ← ReAct loop: reads deck, calls tools, returns review
├── tools.py                 ← Tool implementations: read_slide, write_redline, etc.
├── eval.py                  ← Orchestrates agent across all decks; --reflexion flag
├── score.py                 ← Reads ratings.json, prints accuracy table
├── data/
│   ├── sources.json         ← (exists) 17 curated deck URLs
│   ├── download.py          ← Fetches PDFs, parses to JSON, saves to data/decks/
│   ├── decks/               ← (gitignored) parsed deck JSON files
│   └── raw/                 ← (gitignored) downloaded raw PDFs
└── tests/
    ├── __init__.py
    ├── fixtures/
    │   └── sample_deck.json ← minimal 3-slide deck for unit tests
    ├── test_tools.py        ← unit tests for Tools class
    └── test_agent.py        ← unit tests for token accumulation helper
```

---

## Task 1: Project Scaffold

**Files:**
- Create: `config.toml`
- Create: `system_prompt.md`
- Create: `requirements.txt`
- Create: `.env.example`
- Modify: `.gitignore`
- Create: `tests/__init__.py`
- Create: `tests/fixtures/sample_deck.json`

- [ ] **Step 1: Create config.toml**

```toml
[model]
name = "gemini-3.1-flash-lite-preview"
thinking_level = "none"   # none / minimal / low / medium / high
max_iterations = 30

[eval]
dataset_dir = "data/decks"
runs_dir = "runs"
system_prompt_file = "system_prompt.md"
```

- [ ] **Step 2: Create system_prompt.md**

```markdown
# PPT Review Agent

You are a management consulting expert reviewing business presentations with the rigour of a McKinsey partner.

## Your Task

Review the presentation slide by slide. For each slide, call `write_redline` with a concise comment identifying specific issues. Then call `write_narrative` with a 3–5 sentence deck-level note. Call `finish` when done.

## How to Review

1. Call `read_deck_metadata()` to understand the deck context.
2. For each slide (starting at page 1): call `read_slide(page_num)`, then call `write_redline(page_num, feedback)`.
3. After all slides, call `write_narrative(text)`.
4. Call `finish()`.

Only skip `write_redline` for a slide if it is a cover page, divider, or purely visual with no text to critique.

## Slide-Level Rubric (redlines)

**Action titles:** The slide title must state the conclusion, not label the topic.
- Good: "Revenue grew 12% driven by APAC market share gains"
- Bad: "Revenue performance" → flag as: "Label title — rewrite to state the conclusion, e.g. 'Revenue grew X% driven by Y'"

**So-what clarity:** The key insight must be explicit, ideally in the title or opening line.
- Flag slides where the insight is buried in bullet 4, or implied but never stated.
- Example flag: "So-what is implied but not stated — add an explicit conclusion sentence."

**Pyramid support:** Every point on the slide must directly support the title's claim.
- Flag slides where bullets make a separate argument or are loosely related.
- Example flag: "Bullets 2 and 3 support a different claim than the title — restructure or split."

**Density:** One idea per slide.
- Flag slides making two or three separate points.
- Example flag: "Slide covers both market sizing and competitive dynamics — split into two slides."

**Unsupported assertions:** Any claim requiring data but citing none.
- Flag "significant growth" with no number, "market leading" with no evidence.
- Example flag: "'Significant cost savings' — quantify or remove."

## Deck-Level Rubric (narrative note)

Address all four in your narrative:
1. **Narrative arc** — does the deck follow situation → complication → resolution, or problem → so what → recommendation?
2. **MECE** — do sections cover the issue without overlap or gaps?
3. **Flow** — does each slide set up the next, or are there jarring transitions?
4. **Executive readability** — can a reader follow the argument from titles alone?

## Tone

Be specific and direct. Identify the exact issue and suggest the fix. One sentence per redline is sufficient.
- Weak: "This slide could be improved."
- Strong: "Label title — rewrite as 'Costs fell 18% through procurement consolidation'."
```

- [ ] **Step 3: Create requirements.txt**

```
google-genai>=1.0.0
pdfplumber>=0.9.0
python-dotenv>=1.0.0
requests>=2.31.0
pytest>=8.0.0
```

- [ ] **Step 4: Create .env.example**

```
GEMINI_API_KEY=your_key_here
```

- [ ] **Step 5: Update .gitignore**

Add these lines to the existing `.gitignore`:

```
data/decks/
data/raw/
runs/
```

- [ ] **Step 6: Create tests/__init__.py**

Empty file — just `touch tests/__init__.py`.

- [ ] **Step 7: Create tests/fixtures/sample_deck.json**

A deliberately flawed 3-slide deck — label titles, unsupported assertions — so tests can verify the tools return the right structure without needing the model:

```json
{
  "deck_id": "test-deck",
  "source_type": "sec_edgar",
  "entity": "Test Corp",
  "title": "Test Deck",
  "url": "https://example.com/test.pdf",
  "parsed_date": "2026-04-13",
  "slides": [
    {
      "page": 1,
      "title": "Revenue performance",
      "body": "Revenue grew this year\nKey drivers were APAC and EMEA regions"
    },
    {
      "page": 2,
      "title": "Market position",
      "body": "We are market leaders\nSignificant growth ahead\nCompetition remains intense"
    },
    {
      "page": 3,
      "title": "Next steps",
      "body": "Execute plan\nMonitor KPIs\nReport back quarterly"
    }
  ]
}
```

- [ ] **Step 8: Install dependencies**

```bash
pip install -r requirements.txt
```

- [ ] **Step 9: Commit**

```bash
git add config.toml system_prompt.md requirements.txt .env.example .gitignore tests/
git commit -m "feat: project scaffold — config, rubric, deps, test fixtures"
```

---

## Task 2: Data Pipeline

**Files:**
- Create: `data/download.py`

Context: `data/sources.json` already has 17 deck entries. 12 are PDFs, 5 are HTM (EDGAR inline XBRL). HTM parsing is not in scope for v0.1 — skip them. `pdfplumber` opens a PDF and exposes `.pages`, each with `.extract_text()`. We take the first non-empty line as the slide title and the rest as body.

- [ ] **Step 1: Create data/download.py**

```python
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

SOURCES = Path("data/sources.json")
DECKS_DIR = Path("data/decks")
RAW_DIR = Path("data/raw")


def fetch_pdf(url: str, dest: Path) -> bool:
    """Download URL to dest. Returns True on success."""
    try:
        resp = requests.get(url, timeout=60, headers={"User-Agent": "Mozilla/5.0"})
        resp.raise_for_status()
        dest.write_bytes(resp.content)
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
```

- [ ] **Step 2: Run download for one deck to verify**

```bash
python3 data/download.py mckinsey-nhs-productivity-2009
```

Expected output:
```
[mckinsey-nhs-productivity-2009] Downloading... Parsing... Done (N slides → data/decks/mckinsey-nhs-productivity-2009.json)
```

Check the output:
```bash
python3 -c "import json; d=json.load(open('data/decks/mckinsey-nhs-productivity-2009.json')); print(f'{len(d[\"slides\"])} slides, first title: {d[\"slides\"][0][\"title\"]!r}')"
```

- [ ] **Step 3: Run download for all decks**

```bash
python3 data/download.py
```

Expected: processes all PDF sources, skips HTM sources with a message.

- [ ] **Step 4: Commit**

```bash
git add data/download.py
git commit -m "feat: data pipeline — fetch PDFs, parse with pdfplumber, save JSON"
```

---

## Task 3: Tools

**Files:**
- Create: `tools.py`
- Create: `tests/test_tools.py`

Context: `Tools` holds the deck dict and an output directory. It accumulates redlines in memory and flushes to disk only on `finish()`. `read_slide` uses 1-based page numbering matching the JSON. `write_redline` keys are integers in memory but serialised as strings in JSON (JSON object keys must be strings).

- [ ] **Step 1: Write the failing test**

Create `tests/test_tools.py`:

```python
import json
import pytest
from pathlib import Path
from tools import Tools


@pytest.fixture
def sample_deck():
    fixture = Path("tests/fixtures/sample_deck.json")
    return json.loads(fixture.read_text())


@pytest.fixture
def tools(sample_deck, tmp_path):
    return Tools(sample_deck, tmp_path)


def test_read_deck_metadata(tools, sample_deck):
    meta = tools.read_deck_metadata()
    assert meta["deck_id"] == "test-deck"
    assert meta["entity"] == "Test Corp"
    assert meta["total_pages"] == 3


def test_read_slide_valid(tools):
    slide = tools.read_slide(1)
    assert slide["page"] == 1
    assert slide["title"] == "Revenue performance"
    assert "APAC" in slide["body"]


def test_read_slide_last_page(tools):
    slide = tools.read_slide(3)
    assert slide["page"] == 3
    assert slide["title"] == "Next steps"


def test_read_slide_out_of_range(tools):
    result = tools.read_slide(0)
    assert "error" in result

    result = tools.read_slide(99)
    assert "error" in result


def test_write_redline(tools):
    msg = tools.write_redline(1, "Label title — rewrite to state conclusion")
    assert "1" in msg
    assert tools.redlines[1] == "Label title — rewrite to state conclusion"


def test_write_narrative(tools):
    msg = tools.write_narrative("Deck lacks narrative arc.")
    assert tools.narrative == "Deck lacks narrative arc."


def test_finish_writes_files(tools, tmp_path):
    tools.write_redline(1, "Label title")
    tools.write_redline(2, "Unsupported assertion")
    tools.write_narrative("Poor narrative arc.")
    tools.finish()

    assert tools.is_finished

    redlines_path = tmp_path / "redlines.json"
    narrative_path = tmp_path / "narrative.txt"

    assert redlines_path.exists()
    assert narrative_path.exists()

    redlines = json.loads(redlines_path.read_text())
    assert redlines["1"] == "Label title"
    assert redlines["2"] == "Unsupported assertion"

    assert narrative_path.read_text() == "Poor narrative arc."
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_tools.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'tools'`

- [ ] **Step 3: Create tools.py**

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_tools.py -v
```

Expected: all 9 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add tools.py tests/test_tools.py
git commit -m "feat: tools — read_slide, write_redline, write_narrative, finish"
```

---

## Task 4: Agent

**Files:**
- Create: `agent.py`
- Create: `tests/test_agent.py`

Context: The ReAct loop is identical in structure to `ReAct-practice/agent.py`. Key differences: tools are `read_deck_metadata`, `read_slide`, `write_redline`, `write_narrative`, `finish` instead of `write_file`/`run_python`. The loop breaks when `tools.is_finished` is True (agent called `finish()`). If the model produces text instead of a tool call, nudge it back. Return type is `(review_dict, token_stats)`.

The Gemini SDK uses `types.FunctionDeclaration` to declare tools. `types.Tool` wraps a list of declarations. `types.GenerateContentConfig` holds the system prompt, tools list, and optional thinking config. Responses come back as `response.candidates[0].content.parts` — each part is either a text part or a function call part (`part.function_call` is truthy). Function responses are sent back as `types.Part.from_function_response(name=..., response={"result": ...})`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_agent.py`:

```python
from agent import _accumulate_tokens


def test_accumulate_tokens_adds_counts():
    tokens = {"input": 0, "output": 0, "thinking": 0}

    class FakeUsage:
        prompt_token_count = 100
        candidates_token_count = 50
        thoughts_token_count = 200

    _accumulate_tokens(FakeUsage(), tokens)
    assert tokens["input"] == 100
    assert tokens["output"] == 50
    assert tokens["thinking"] == 200


def test_accumulate_tokens_handles_none():
    tokens = {"input": 10, "output": 5, "thinking": 0}
    _accumulate_tokens(None, tokens)
    assert tokens["input"] == 10
    assert tokens["output"] == 5


def test_accumulate_tokens_handles_missing_attributes():
    tokens = {"input": 0, "output": 0, "thinking": 0}

    class MinimalUsage:
        prompt_token_count = 42

    _accumulate_tokens(MinimalUsage(), tokens)
    assert tokens["input"] == 42
    assert tokens["output"] == 0
    assert tokens["thinking"] == 0
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_agent.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'agent'`

- [ ] **Step 3: Create agent.py**

```python
"""ReAct loop for the PPT review agent.

run(deck, output_dir, system_prompt, api_key) → (review_dict, token_stats)

review_dict = {"redlines": {page_num: feedback}, "narrative": str}
token_stats  = {"input": int, "output": int, "thinking": int}
"""
import tomllib
from pathlib import Path

from dotenv import load_dotenv
from google import genai
from google.genai import types

from tools import Tools

load_dotenv()

with open(Path(__file__).parent / "config.toml", "rb") as _f:
    _config = tomllib.load(_f)

MODEL = _config["model"]["name"]
MAX_ITERATIONS = _config["model"]["max_iterations"]
_THINKING_LEVEL = _config["model"]["thinking_level"]

READ_DECK_METADATA_DECL = types.FunctionDeclaration(
    name="read_deck_metadata",
    description="Get metadata: entity name, deck title, total slide count, source type.",
    parameters={"type": "object", "properties": {}, "required": []},
)

READ_SLIDE_DECL = types.FunctionDeclaration(
    name="read_slide",
    description="Read the title and body text of one slide by page number (1-based).",
    parameters={
        "type": "object",
        "properties": {
            "page_num": {"type": "integer", "description": "Slide number, starting from 1"},
        },
        "required": ["page_num"],
    },
)

WRITE_REDLINE_DECL = types.FunctionDeclaration(
    name="write_redline",
    description="Save a redline comment for a specific slide.",
    parameters={
        "type": "object",
        "properties": {
            "page_num": {"type": "integer", "description": "Slide number"},
            "feedback": {"type": "string", "description": "Redline comment for this slide"},
        },
        "required": ["page_num", "feedback"],
    },
)

WRITE_NARRATIVE_DECL = types.FunctionDeclaration(
    name="write_narrative",
    description="Save the deck-level narrative note (3–5 sentences on overall story quality).",
    parameters={
        "type": "object",
        "properties": {
            "text": {"type": "string", "description": "Deck-level narrative feedback"},
        },
        "required": ["text"],
    },
)

FINISH_DECL = types.FunctionDeclaration(
    name="finish",
    description="Signal that the review is complete. Call after writing all redlines and the narrative.",
    parameters={"type": "object", "properties": {}, "required": []},
)

GEMINI_TOOLS = types.Tool(function_declarations=[
    READ_DECK_METADATA_DECL,
    READ_SLIDE_DECL,
    WRITE_REDLINE_DECL,
    WRITE_NARRATIVE_DECL,
    FINISH_DECL,
])


def _accumulate_tokens(usage, tokens: dict) -> None:
    """Add token counts from a response's usage_metadata into running totals."""
    if usage is None:
        return
    tokens["input"] += getattr(usage, "prompt_token_count", 0) or 0
    tokens["output"] += getattr(usage, "candidates_token_count", 0) or 0
    tokens["thinking"] += getattr(usage, "thoughts_token_count", 0) or 0


def run(
    deck: dict,
    output_dir: Path,
    system_prompt: str,
    api_key: str,
    reflexion_context: str | None = None,
) -> tuple[dict, dict]:
    """Run the ReAct review loop for one deck. Returns (review, token_stats).

    Args:
        deck: parsed deck dict from data/decks/*.json
        output_dir: directory to write redlines.json and narrative.txt
        system_prompt: rubric text from system_prompt.md
        api_key: Gemini API key
        reflexion_context: optional prior-run feedback to inject (for --reflexion mode)
    """
    client = genai.Client(api_key=api_key)
    tools = Tools(deck, output_dir)

    thinking_config = None
    if _THINKING_LEVEL and _THINKING_LEVEL != "none":
        thinking_config = types.ThinkingConfig(thinking_level=_THINKING_LEVEL)

    config = types.GenerateContentConfig(
        system_instruction=system_prompt,
        tools=[GEMINI_TOOLS],
        thinking_config=thinking_config,
    )

    initial_parts = [types.Part.from_text(
        text=f"Please review this presentation: {deck['deck_id']} ({deck.get('entity', '')})"
    )]
    if reflexion_context:
        initial_parts.append(types.Part.from_text(text=reflexion_context))

    contents = [types.Content(role="user", parts=initial_parts)]
    tokens = {"input": 0, "output": 0, "thinking": 0}

    for _ in range(MAX_ITERATIONS):
        response = client.models.generate_content(
            model=MODEL,
            contents=contents,
            config=config,
        )
        _accumulate_tokens(response.usage_metadata, tokens)

        if not response.candidates:
            break

        candidate = response.candidates[0]
        fn_calls = [p for p in candidate.content.parts if p.function_call]

        if fn_calls:
            contents.append(candidate.content)
            fn_responses = []
            for part in fn_calls:
                fc = part.function_call
                args = dict(fc.args)
                if fc.name == "read_deck_metadata":
                    result = tools.read_deck_metadata()
                elif fc.name == "read_slide":
                    result = tools.read_slide(int(args["page_num"]))
                elif fc.name == "write_redline":
                    result = tools.write_redline(int(args["page_num"]), args["feedback"])
                elif fc.name == "write_narrative":
                    result = tools.write_narrative(args["text"])
                elif fc.name == "finish":
                    result = tools.finish()
                else:
                    result = f"Unknown tool: {fc.name}"

                fn_responses.append(types.Part.from_function_response(
                    name=fc.name,
                    response={"result": result},
                ))
            contents.append(types.Content(role="user", parts=fn_responses))

            if tools.is_finished:
                break

        else:
            # Model produced text instead of a tool call — nudge it back
            contents.append(candidate.content)
            contents.append(types.Content(role="user", parts=[types.Part.from_text(
                text="Continue the review. Use the available tools to read slides and write feedback."
            )]))

    review = {"redlines": tools.redlines, "narrative": tools.narrative}
    return review, tokens
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_agent.py -v
```

Expected: all 3 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add agent.py tests/test_agent.py
git commit -m "feat: agent — ReAct loop with slide review tools and token tracking"
```

---

## Task 5: Eval Runner

**Files:**
- Create: `eval.py`

Context: Eval reads all `*.json` files from `data/decks/`, runs the agent on each, and writes output to `runs/{timestamp}/{deck_id}/`. It also writes a `ratings_template.json` to the run directory — a pre-filled template the human fills in with `true`/`false` per slide. The `--deck` flag lets you run a single deck for quick testing.

- [ ] **Step 1: Create eval.py**

```python
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
        deck_path = DATASET_DIR / f"{deck_id}.json"
        deck = json.loads(deck_path.read_text(encoding="utf-8"))
        redlines_path = run_dir / deck_id / "redlines.json"
        if redlines_path.exists():
            redlines = json.loads(redlines_path.read_text(encoding="utf-8"))
            slide_ratings = {page: None for page in redlines}
        else:
            slide_ratings = {}
        template[deck_id] = {
            "slide_ratings": slide_ratings,
            "notes": "",
        }
    ratings_path = run_dir / "ratings.json"
    ratings_path.write_text(json.dumps(template, indent=2), encoding="utf-8")
    print(f"\nRatings template written to {ratings_path}")
    print("Fill in each slide rating: true (agent correct) or false (agent wrong), then run:")
    print(f"  python3 score.py {run_dir}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--deck", default=None, help="Review a single deck by deck_id")
    args = parser.parse_args()

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key or api_key == "your_key_here":
        print("Error: set GEMINI_API_KEY in .env", file=sys.stderr)
        sys.exit(1)

    if not SYSTEM_PROMPT_FILE.exists():
        print(f"Error: {SYSTEM_PROMPT_FILE} not found", file=sys.stderr)
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
    run_dir = RUNS_DIR / timestamp
    run_dir.mkdir(parents=True)

    print(f"Run: {run_dir}")
    print(f"Decks: {len(deck_files)}")
    print(f"Model: {agent.MODEL} | thinking: {agent._THINKING_LEVEL} | max_iter: {agent.MAX_ITERATIONS}")
    print()

    summary = []
    reviewed_deck_ids = []

    for deck_file in deck_files:
        deck = json.loads(deck_file.read_text(encoding="utf-8"))
        deck_id = deck["deck_id"]
        output_dir = run_dir / deck_id
        output_dir.mkdir()

        n_slides = len(deck["slides"])
        print(f"[{deck_id}] Reviewing ({n_slides} slides)...", end=" ", flush=True)

        review, tokens = agent.run(deck, output_dir, system_prompt, api_key)
        total_tokens = sum(tokens.values())
        n_redlines = len(review["redlines"])

        print(
            f"→ {n_redlines}/{n_slides} slides redlined  "
            f"({total_tokens:,} tokens: {tokens['input']:,} in / "
            f"{tokens['thinking']:,} think / {tokens['output']:,} out)"
        )

        summary.append({
            "deck_id": deck_id,
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
```

- [ ] **Step 2: Smoke test against one real deck**

First make sure at least one deck is downloaded:
```bash
python3 data/download.py mckinsey-nhs-productivity-2009
```

Then run eval on just that deck:
```bash
python3 eval.py --deck mckinsey-nhs-productivity-2009
```

Expected output:
```
Run: runs/20260413_XXXXXX
Decks: 1
Model: gemini-3.1-flash-lite-preview | thinking: none | max_iter: 30

[mckinsey-nhs-productivity-2009] Reviewing (N slides)... → M/N slides redlined  (X,XXX tokens: ...)

Ratings template written to runs/20260413_XXXXXX/ratings.json
```

Check the output files exist:
```bash
ls runs/$(ls runs/ | tail -1)/mckinsey-nhs-productivity-2009/
```

Expected: `narrative.txt  redlines.json`

- [ ] **Step 3: Read a few redlines to sanity-check quality**

```bash
python3 -c "
import json
from pathlib import Path
run = sorted(Path('runs').iterdir())[-1]
redlines = json.loads((run / 'mckinsey-nhs-productivity-2009/redlines.json').read_text())
for page, feedback in list(redlines.items())[:5]:
    print(f'Slide {page}: {feedback}')
"
```

- [ ] **Step 4: Commit**

```bash
git add eval.py
git commit -m "feat: eval runner — orchestrates agent across decks, writes ratings template"
```

---

## Task 6: Score

**Files:**
- Create: `score.py`

Context: The human fills in `ratings.json` — changing `null` to `true` (agent was correct) or `false` (agent was wrong) for each slide. `score.py` reads that file and prints a per-deck accuracy table plus an overall total. Identical UX to the AIME `score.py`.

- [ ] **Step 1: Create score.py**

```python
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
        return

    ratings = json.loads(ratings_path.read_text(encoding="utf-8"))

    # Filter out decks with no ratings filled in yet (all None)
    rated = {
        deck_id: r for deck_id, r in ratings.items()
        if any(v is not None for v in r.get("slide_ratings", {}).values())
    }
    if not rated:
        print("No ratings filled in yet. Edit ratings.json: change null → true or false per slide.")
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
```

- [ ] **Step 2: Test with a mock ratings.json**

```bash
python3 -c "
import json
from pathlib import Path
run = sorted(Path('runs').iterdir())[-1]
# Fill in mock ratings for the one deck we ran
ratings = json.loads((run / 'ratings.json').read_text())
for deck_id in ratings:
    for page in ratings[deck_id]['slide_ratings']:
        ratings[deck_id]['slide_ratings'][page] = True   # pretend all correct
    ratings[deck_id]['notes'] = 'mock rating for testing'
(run / 'ratings.json').write_text(json.dumps(ratings, indent=2))
"
python3 score.py runs/$(ls runs/ | tail -1)
```

Expected: table with 100% accuracy (all mocked as correct).

- [ ] **Step 3: Commit**

```bash
git add score.py
git commit -m "feat: score — reads ratings.json, prints per-deck accuracy table"
```

---

## Task 7: Reflexion

**Files:**
- Modify: `eval.py` (add `--reflexion` flag)

Context: Reflexion re-runs the agent on decks where the prior run had at least one incorrect slide rating. It builds a context string from the prior redlines + the human's slide-level verdicts, then passes it to `agent.run()` via the `reflexion_context` argument (already wired in from Task 4). Output goes to a new timestamped run directory with `_reflexion` suffix. Compare accuracy before and after with `score.py`.

- [ ] **Step 1: Add --reflexion flag to eval.py**

Replace the `main()` function in `eval.py` with:

```python
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
        return None  # All correct — no reflexion needed

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
        output_dir.mkdir()

        reflexion_context = None
        if prior_run_dir:
            reflexion_context = build_reflexion_context(deck_id, prior_run_dir)
            if reflexion_context is None:
                print(f"[{deck_id}] All slides correct in prior run — skipping reflexion")
                continue

        n_slides = len(deck["slides"])
        mode = "reflexion" if reflexion_context else "baseline"
        print(f"[{deck_id}] Reviewing ({n_slides} slides, {mode})...", end=" ", flush=True)

        review, tokens = agent.run(deck, output_dir, system_prompt, api_key, reflexion_context)
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
```

- [ ] **Step 2: Run tests to verify nothing broke**

```bash
pytest tests/ -v
```

Expected: all tests PASS.

- [ ] **Step 3: Smoke test reflexion flag**

First ensure the prior run has a filled-in `ratings.json` (from Task 6 Step 2). Then:

```bash
PRIOR_RUN=$(ls runs/ | grep -v reflexion | tail -1)
python3 eval.py --deck mckinsey-nhs-productivity-2009 --reflexion runs/$PRIOR_RUN
```

Expected: run directory named `runs/20260413_XXXXXX_reflexion/`, reflexion context logged.

- [ ] **Step 4: Commit**

```bash
git add eval.py
git commit -m "feat: reflexion — re-run agent with prior ratings as context (--reflexion flag)"
```

---

## Task 8: Final wiring and README

**Files:**
- Create: `README.md`

- [ ] **Step 1: Create README.md**

```markdown
# PPT Review Agent v0.1

An agent that reviews business presentations the way a McKinsey partner would: slide-by-slide redlines plus a deck-level narrative note.

## Setup

```bash
pip install -r requirements.txt
cp .env.example .env
# edit .env and add your GEMINI_API_KEY
```

## Download dataset

```bash
python3 data/download.py          # all PDF decks
python3 data/download.py <id>     # one specific deck
```

## Run

```bash
python3 eval.py                           # review all decks
python3 eval.py --deck <deck_id>          # one deck (for testing)
python3 eval.py --reflexion runs/<prior>  # reflexion run after rating a baseline
```

## Rate the output

Open `runs/<timestamp>/ratings.json`. For each slide the agent commented on, change `null` to `true` (agent feedback was correct) or `false` (it was wrong). Add free-form notes per deck.

## Score

```bash
python3 score.py runs/<timestamp>
```

## Config

Edit `config.toml` to change model, thinking level, or iteration budget.
Edit `system_prompt.md` to improve the rubric — no code changes needed.

## Workflow

```
data/download.py → eval.py → rate ratings.json → score.py
                           ↑                           ↓
                    eval.py --reflexion ←──────────────┘
```
```

- [ ] **Step 2: Run the full test suite one final time**

```bash
pytest tests/ -v
```

Expected: all tests PASS.

- [ ] **Step 3: Commit and push**

```bash
git add README.md
git commit -m "feat: README — setup, workflow, usage"
git push origin master
```

---

## Self-Review

**Spec coverage check:**
- Data pipeline (download.py) → Task 2 ✓
- Tools (read_slide, write_redline, etc.) → Task 3 ✓
- Agent ReAct loop → Task 4 ✓
- Eval runner → Task 5 ✓
- Score → Task 6 ✓
- Reflexion → Task 7 ✓
- config.toml → Task 1 ✓
- system_prompt.md / rubric → Task 1 ✓
- ratings.json template → Task 5 ✓

**Placeholder scan:** None found — all steps have complete code.

**Type consistency:**
- `Tools.redlines` → `dict[int, str]` throughout (int keys in memory, str keys in JSON)
- `agent.run()` → `(dict, dict)` throughout
- `reflexion_context: str | None` consistent between agent.py signature and eval.py call
