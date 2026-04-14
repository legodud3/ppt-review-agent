# PPT Review Agent

An agent that reviews business presentations with the rigour of a McKinsey partner: slide-by-slide redlines plus a deck-level narrative note. Includes a local web UI for running evals, rating output, and scoring.

## Setup

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# edit .env and add your OPENROUTER_API_KEY
```

## Launch the web UI

```bash
python3 server.py
# open http://localhost:8000
```

The UI covers the full workflow: select a model → run the agent → stream progress → rate redlines T/F → score. No CLI needed for the happy path.

## CLI workflow (alternative)

```bash
python3 data/download.py              # download all PDF decks
python3 eval.py                       # review all decks
python3 eval.py --deck <deck_id>      # one deck
python3 eval.py --model <model_id>    # override model
python3 eval.py --reflexion runs/<prior_run_dir>   # reflexion pass after rating
python3 score.py runs/<timestamp>     # score a rated run
```

## Config

- `config.toml` — default model, max iterations, directory paths
- `system_prompt.md` — the review rubric; edit this to tune agent behaviour, no code changes needed
- `.env` — `OPENROUTER_API_KEY`

## Data model

```
data/decks/<deck_id>.json       parsed deck (slides as text)
data/raw/<deck_id>.pdf          source PDF (for the viewer)
runs/<timestamp>/
  summary.json                  run metadata + token usage
  ratings.json                  human T/F ratings per redline
  <deck_id>/
    redlines.json               {"<page>": ["issue 1", "issue 2", ...]}
    narrative.txt               deck-level narrative note
```

---

## Findings & Changelog

### What we built and why

This project started as an experiment: can an LLM agent replicate the kind of structured critique a senior consultant gives on a presentation? The workflow mirrors a real review loop — agent reviews, human rates, agent improves via reflexion.

---

### v0.1 — Initial agent (Gemini)

- Agent reads a parsed deck JSON, calls tools (`read_slide`, `write_redline`, `write_narrative`, `finish`)
- Outputs `redlines.json` (one comment per slide) and `narrative.txt`
- CLI-only: `eval.py` → manual `ratings.json` edit → `score.py`
- Used Google Gemini with extended thinking via `google-genai` SDK

---

### v0.2 — OpenRouter migration + web UI

**Why OpenRouter:** Wanted model flexibility (swap between Gemini, Llama, Nemotron, etc.) without changing code. OpenRouter exposes a unified OpenAI-compatible API. Implemented via `requests` directly (not the openai SDK) as a deliberate choice.

**Default model:** `nvidia/llama-3.1-nemotron-ultra-253b-v1:free` — free tier on OpenRouter, strong reasoning.

**Web UI (`server.py` + `ui/index.html`):**
- FastAPI backend with SSE streaming for live eval progress
- Single-page vanilla JS — no build step, no framework
- PDF viewer (PDF.js) synced to selected slide
- Per-redline T/F rating with auto-save
- Model dropdown populated live from OpenRouter's `/api/v1/models`, free models sorted first
- Reflexion mode: prior rated run injected as context for re-run

**Key technical decisions:**
- SSE via `fetch` + `ReadableStream` (not `EventSource`) because the trigger is a POST
- Atomic file writes (`.tmp` then `rename`) to prevent rating corruption
- Path traversal guard on PDF serving

---

### v0.3 — Multiple redlines per slide

**Problem:** One redline per slide forced the agent to combine unrelated issues into a single comment. A slide with a pyramid problem AND an unsupported assertion got one muddled sentence.

**Change:** `redlines.json` format changed from `{"3": "text"}` to `{"3": ["issue 1", "issue 2"]}`. Agent calls `write_redline` once per distinct issue. Rating keys changed from `"3"` to `"3_0"`, `"3_1"` etc. so each issue is rated independently.

**UI update:** Each issue renders as its own row with its own T/F toggle. Clicking a row jumps the PDF to that slide.

---

### System prompt evolution — what we learned

**Problem 1: Agent only gave title-level feedback.**

The agent defaulted to the easiest mechanical pattern: "Label title — rewrite to 'X drove Y.'" This required no body reading and fit a simple template.

Root cause: "Action titles" appeared first in the rubric. The model treated it as the primary check.

Fix: Reordered the rubric so body criteria come first (unsupported assertions → so-what → pyramid → idea density → content density) and title critique is last (#6), conditional on having already written a body redline. Added explicit negative examples ("a redline that would make sense without reading the body is wrong") and positive examples that reference specific bullet content.

**Problem 2: No cross-slide awareness.**

Agent reviewed each slide in isolation. It had no sense of narrative arc, section structure, or how slides build on each other. Common failure modes:
- Faulting a framework/concept intro slide for lacking evidence (the evidence is in the following slides)
- Faulting directional slides for lacking quantification (premature at the exploration stage)
- Missing transitions and gaps between sections

Root cause: The review loop was read slide N → write redline → read slide N+1. The agent never held the full deck in mind.

Fix: Two-pass review structure.
- Pass 1: read all slides without writing redlines
- Synthesize: map the deck structure, identify section roles, classify framework/intro slides and directional slides
- Pass 2: write redlines with cross-slide awareness; each redline may reference surrounding slides

**Problem 3: Flagging things already on the slide.**

Agent occasionally flagged "unsupported assertion" for a claim that was quantified in the title, a footnote, or a nearby slide.

Fix: Explicit verify step — "before flagging something as missing, confirm it is not stated in the title, subheading, footnote, or a nearby slide."

**Problem 4: Flagging obvious observations.**

Agent flagged things self-evident from the chart type or standard context.

Fix: "Only flag non-obvious structural or argument problems — do not flag things a smart first reader would catch immediately."

---

### Key insight: calibration dataset matters

Initial testing used a final McKinsey client deliverable (USPS deck). After prompt improvements the agent produced only 5 redlines — which turned out to be correct. A polished final deck from a top-tier firm has already been through 8 rounds of partner review. There's not much left to find.

**The real dataset to target is work-in-progress documents.** WIP decks at 60% completion have 15+ real issues. They're also the moment where feedback has the most leverage — before the argument solidifies and before the client sees it.

This reframes the product: it's a pre-send quality gate, not a final-deliverable auditor.

---

### Product direction (exploratory)

The review-and-rate loop is the seed of a more interesting product: an **interactive document review session tool** for independent service providers and SMBs (consultants, agencies, freelancers) who send high-stakes client documents regularly.

Key observations:
- The job to be done is "I'm about to send something to a client and I need it to be tight" — not "review my document type X"
- Gemini in Google Docs rewrites text; this critiques argument structure. Different tool.
- The rubric is the moat: tuned per document type (proposal, brief, scope doc, project plan), improvable via the reflexion loop
- Competitive white space: legal and government RFP review are saturated; creative/consulting ISP market is not served
- MVP scope: upload doc → AI surfaces issues section by section → chat per section → copy suggested rewrites. No file write-back needed for v1.
- The right dataset for this product is WIP documents, not polished final outputs

---

## Architecture

```
agent.py        ReAct loop — reads slides, calls tools, writes output
tools.py        Tool implementations — read_slide, write_redline, write_narrative, finish
eval.py         Batch runner — one or many decks, optional reflexion pass
server.py       FastAPI server — REST API + SSE streaming + static file serving
ui/index.html   Single-page app — runs tab, review tab, modal eval runner
score.py        Standalone scorer for a rated run directory
system_prompt.md  The review rubric — edit to tune behaviour
config.toml     Model, iteration budget, directory paths
```
