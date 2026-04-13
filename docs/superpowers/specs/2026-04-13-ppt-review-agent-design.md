# PPT Review Agent v0.1 — Design Spec

## Goal

Build an agent that reviews business presentations the way a McKinsey partner would: slide-by-slide redlines plus a deck-level narrative note. Use public corporate filings and government-published consulting deliverables as the dataset. The human reviewer (a McKinsey alum) rates the agent's feedback to create an eval signal.

## Architecture

Four components:

```
data/                  ← downloaded + parsed decks (JSON)
agent.py               ← ReAct loop (adapted from ReAct-practice)
eval.py                ← runs agent across all decks, writes results
score.py               ← aggregates human ratings into accuracy signal
system_prompt.md       ← the rubric (editable without touching code)
config.toml            ← all tunable parameters (model, iterations, etc.)
```

---

## Data Pipeline

### Sources

**Source 1: SEC EDGAR** — investor day presentations, M&A announcement decks, earnings slide decks filed as 8-K exhibits. Auto-discoverable by company ticker + filing type.

**Source 2: Government / multilateral published consulting deliverables** — McKinsey and BCG engagement outputs made public because the client was a government entity, multilateral organisation (World Bank, IMF, UN, ADB), or public institution subject to transparency/procurement rules. Examples: UK gov.uk published reports, World Bank strategy documents, EU Commission published deliverables. Manually curated list of URLs — no auto-discovery.

### Dataset size

Start with 20 decks: 10 per source. Same scale as the AIME project.

### Parsing

```
PDF → pdfplumber → per-page text extraction → structured JSON
```

Output format per deck:

```json
{
  "deck_id": "nvidia-investor-day-2024",
  "source": "sec_edgar",
  "entity": "NVIDIA Corporation",
  "url": "https://...",
  "parsed_date": "2026-04-13",
  "slides": [
    {"page": 1, "title": "...", "body": "..."},
    {"page": 2, "title": "...", "body": "..."}
  ]
}
```

Stored in `data/decks/` as `{deck_id}.json`. Raw PDFs in `data/raw/` (gitignored).

A download script (`data/download.py`) handles fetching, parsing, and saving. Takes a curated `data/sources.json` as input — a list of `{deck_id, source_type, entity, url}` objects.

---

## Agent Design

### ReAct loop

Reuse and adapt the loop from ReAct-practice (`agent.py`). Same `generate_content` + function calling pattern, same iteration budget. Key differences from the AIME agent:

- No Python sandbox — the agent reads structured data and writes structured output
- Tools are read/write for slides, not code execution
- Return type: `{redlines: {1: "...", 2: "..."}, narrative: "..."}` instead of a string answer

### Tools

| Tool | Args | Returns |
|---|---|---|
| `read_slide(page_num)` | int | `{title, body}` for that slide |
| `read_deck_metadata()` | — | `{entity, total_pages, source}` |
| `write_redline(page_num, feedback)` | int, str | confirmation |
| `write_narrative(text)` | str | confirmation |
| `finish()` | — | signals agent is done |

### Agent behaviour

The agent should:
1. Call `read_deck_metadata()` to orient itself
2. Iterate through slides with `read_slide(n)`
3. Write redlines as it goes with `write_redline(n, feedback)`
4. After all slides, write the deck-level note with `write_narrative(text)`
5. Call `finish()`

The rubric in `system_prompt.md` tells the agent what to look for on each slide and at the deck level.

---

## Rubric (system_prompt.md)

The rubric is the system prompt — a markdown file editable without touching code. Starting criteria (human reviewer will extend):

**Slide-level (redlines):**

1. **Action titles** — the slide title should state the conclusion, not the topic. "Revenue grew 12% driven by APAC" is correct. "Revenue performance" is not. Flag label titles.
2. **So-what clarity** — the key insight should be explicit, ideally in the first line or title. Flag slides where the insight is buried in bullet 4 or implied but never stated.
3. **Pyramid support** — the points on the slide should directly support the title's claim. Flag slides where bullets are loosely related or tangential to the title.
4. **Density** — one idea per slide. Flag slides that are trying to make two or three separate points.
5. **Unsupported assertions** — any claim that needs data but has none. Flag "significant growth" with no number, "market leading" with no evidence.

**Deck-level (narrative):**

1. **Narrative arc** — does the deck follow a clear structure: situation → complication → resolution, or problem → so what → recommendation? Flag decks that jump to conclusions without establishing stakes.
2. **MECE** — do the sections cover the issue without overlap? Flag redundant slides or gaps in the argument.
3. **Flow** — does each slide set up the next? Flag jarring transitions or slides that could be reordered without loss.
4. **Executive readability** — could a busy executive read only the titles and get 80% of the story? Test this mentally and flag if not.

---

## Eval Loop

### Running

```bash
python3 eval.py          # runs agent on all decks in data/decks/
```

Output per deck written to `runs/{timestamp}/{deck_id}/`:
- `redlines.json` — `{page_num: feedback_string}`
- `narrative.txt` — deck-level note

### Human rating

After each run, reviewer opens the output and rates:

```
runs/{timestamp}/ratings.json
{
  "nvidia-investor-day-2024": {
    "slide_ratings": {1: true, 2: false, 3: true, ...},
    "notes": "Agent missed the buried so-what on slide 6, got the title critique right"
  },
  ...
}
```

### Scoring

```bash
python3 score.py runs/{timestamp}
```

Outputs per-deck accuracy (% slides correct) and aggregate across all decks. Comparable across runs as the rubric evolves.

---

## Config

All tunable parameters in `config.toml`, committed to git:

```toml
[model]
name = "gemini-3.1-flash-lite-preview"
thinking_level = "none"   # none / minimal / low / medium / high
max_iterations = 50

[eval]
dataset_dir = "data/decks"
runs_dir = "runs"
system_prompt_file = "system_prompt.md"
```

API key stays in `.env`, never committed.

---

## Reflexion loop

Reflexion is included in v0.1 but activates only after the first baseline run is complete and the rubric is stable. Activating it before that is counterproductive — if the rubric changes between runs, the agent is reflecting on feedback generated under different criteria and improvement is unattributable.

**How it works:**

After you rate a run, `eval.py --reflexion` re-runs the agent on each deck it got wrong, passing prior feedback + your slide ratings as additional context:

```
System: <rubric>
User: <deck slides>
User: [Reflexion context] On your previous review of this deck you wrote:
      Slide 3: "Title is a label not an action title"
      Human rating: INCORRECT — the title "Costs reduced 18% through procurement" IS an action title.
      Slide 7: "No so-what stated"
      Human rating: CORRECT
      Use this feedback to improve your review.
```

The agent then produces a revised review. You rate again. Delta in accuracy is the Reflexion signal.

**Sequencing rule:** run baseline first (no reflexion context), rate it, lock the rubric, then run Reflexion. This keeps the two signals clean and comparable.

---

## What is not in v0.1

- Vision / image rendering of slides (v0.2)
- Automatic download from EDGAR — manual URL curation for now
- Multi-agent (generator + verifier)
- Fine-tuning on rated traces
