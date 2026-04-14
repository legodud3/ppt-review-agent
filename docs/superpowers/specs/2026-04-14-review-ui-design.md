# PPT Review Agent — Full Web Workflow Design Spec

## Goal

Replace the CLI-only workflow with a local web app covering the full loop: upload/select a PDF deck → run the agent → stream progress → rate redlines → see score. Simultaneously migrate the agent from `google-genai` to OpenRouter via `requests`.

## Architecture

Two deliverables:

1. **OpenRouter migration** — `agent.py` rewritten to use `requests` against `https://openrouter.ai/api/v1/chat/completions`. Standard OpenAI function-calling format (tools array + tool_calls response). No new dependency beyond `requests` (already in stdlib-adjacent use).

2. **Web app** — `server.py` (FastAPI) + `ui/index.html` (vanilla JS, single file, no build step). `python server.py` launches everything; user opens `http://localhost:8000`.

**Tech Stack:** Python 3.12+, FastAPI, uvicorn, requests, PDF.js (CDN, embedded in HTML), vanilla JS (no React/Vue/bundler).

---

## Part 1: OpenRouter Migration

### `agent.py`

**Remove:** all `google.genai` / `types.*` imports and classes.

**Add:**

```python
import json
import os
import requests

OPENROUTER_BASE = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_HEADERS = {
    "Authorization": f"Bearer {os.environ['OPENROUTER_API_KEY']}",
    "HTTP-Referer": "http://localhost:8000",
    "X-OpenRouter-Title": "PPT Review Agent",
    "Content-Type": "application/json",
}
```

**Tool declarations** — replace Gemini `FunctionDeclaration` objects with OpenAI-format dicts:

```python
TOOLS = [
    {"type": "function", "function": {
        "name": "read_deck_metadata",
        "description": "Get metadata: entity name, deck title, total slide count, source type.",
        "parameters": {"type": "object", "properties": {}, "required": []}
    }},
    {"type": "function", "function": {
        "name": "read_slide",
        "description": "Read the title and body text of one slide by page number (1-based).",
        "parameters": {"type": "object", "properties": {
            "page_num": {"type": "integer", "description": "Slide number, starting from 1"}
        }, "required": ["page_num"]}
    }},
    {"type": "function", "function": {
        "name": "write_redline",
        "description": "Save a redline comment for a specific slide.",
        "parameters": {"type": "object", "properties": {
            "page_num": {"type": "integer", "description": "Slide number"},
            "feedback": {"type": "string", "description": "Redline comment for this slide"}
        }, "required": ["page_num", "feedback"]}
    }},
    {"type": "function", "function": {
        "name": "write_narrative",
        "description": "Save the deck-level narrative note (3–5 sentences on overall story quality).",
        "parameters": {"type": "object", "properties": {
            "text": {"type": "string", "description": "Deck-level narrative feedback"}
        }, "required": ["text"]}
    }},
    {"type": "function", "function": {
        "name": "finish",
        "description": "Signal that the review is complete. Call after writing all redlines and the narrative.",
        "parameters": {"type": "object", "properties": {}, "required": []}
    }},
]
```

**`run()` signature** — unchanged externally:

```python
def run(
    deck: dict,
    output_dir: Path,
    system_prompt: str,
    api_key: str,
    model: str,
    reflexion_context: str | None = None,
) -> tuple[dict, dict]:
```

Note: `model` is now a required argument (no longer read from config.toml in agent.py — eval.py passes it in).

**Conversation format** — plain dicts replacing `types.Content`:

```python
messages = [
    {"role": "system", "content": system_prompt},
    {"role": "user", "content": f"Please review: {deck['deck_id']} ({deck.get('entity', '')})"}
]
if reflexion_context:
    messages[-1]["content"] += f"\n\n{reflexion_context}"
```

**ReAct loop** — one `requests.post()` per iteration:

```python
resp = requests.post(
    OPENROUTER_BASE,
    headers={**OPENROUTER_HEADERS, "Authorization": f"Bearer {api_key}"},
    data=json.dumps({"model": model, "messages": messages, "tools": TOOLS, "tool_choice": "auto"}),
    timeout=120,
)
resp.raise_for_status()
data = resp.json()
message = data["choices"][0]["message"]
```

**Tool call handling:**

```python
if message.get("tool_calls"):
    messages.append(message)  # append assistant message with tool_calls
    for tc in message["tool_calls"]:
        name = tc["function"]["name"]
        args = json.loads(tc["function"]["arguments"])
        result = _dispatch(tools, name, args)
        messages.append({
            "role": "tool",
            "tool_call_id": tc["id"],
            "content": str(result),
        })
    if tools.is_finished:
        break
else:
    # text-only response — nudge back to tools
    messages.append(message)
    messages.append({"role": "user", "content": "Continue the review. Use the available tools."})
```

**Token accumulation:**

```python
usage = data.get("usage", {})
tokens["input"] += usage.get("prompt_tokens", 0)
tokens["output"] += usage.get("completion_tokens", 0)
# OpenRouter returns native_tokens_prompt / native_tokens_completion for reasoning models
tokens["thinking"] += usage.get("native_tokens_reasoning", 0)
```

### `config.toml`

Remove `thinking_level`. Add `default_model`. Remove `name` (model now passed at runtime).

```toml
[model]
default_model = "nvidia/llama-3.1-nemotron-ultra-253b-v1:free"
max_iterations = 150

[eval]
dataset_dir = "data/decks"
runs_dir = "runs"
system_prompt_file = "system_prompt.md"
```

### `eval.py`

- Replace `GEMINI_API_KEY` → `OPENROUTER_API_KEY`
- Accept `--model MODEL` CLI flag (default: `config.toml` `default_model`)
- Pass `model=args.model` to `agent.run()`
- Remove reference to `agent._THINKING_LEVEL`

### `requirements.txt`

Remove `google-genai`. Ensure `fastapi`, `uvicorn[standard]`, `requests` are present.

---

## Part 2: Web App

### File Structure

```
server.py          # FastAPI app, all endpoints
ui/
  index.html       # Single-page app, vanilla JS + PDF.js via CDN
```

### `server.py` — Endpoints

#### Static / page serving
- `GET /` → serve `ui/index.html`
- `GET /data/raw/{deck_id}.pdf` → serve `data/raw/{deck_id}.pdf` as `application/pdf`

#### Data endpoints
- `GET /api/decks` → list `data/decks/*.json`, return `[{deck_id, entity, total_pages}]`
- `GET /api/models` → proxy `GET https://openrouter.ai/api/v1/models`, return filtered list of `{id, name, description, pricing}` sorted free-first then by context window desc
- `GET /api/runs` → list `runs/*/` dirs, return `[{run_id, timestamp, deck_ids, mode, score_pct}]` (score_pct from ratings.json if present, else null)
- `GET /api/runs/{run_id}/ratings` → read `runs/{run_id}/ratings.json` (return `{}` if missing)
- `GET /api/runs/{run_id}/{deck_id}/redlines` → read `runs/{run_id}/{deck_id}/redlines.json`
- `GET /api/runs/{run_id}/{deck_id}/narrative` → read `runs/{run_id}/{deck_id}/narrative.txt`

#### Write endpoints
- `POST /api/runs/{run_id}/ratings` — body: `{deck_id, slide, value}` where value is `true | false | null`. Reads ratings.json, updates one entry, writes back. Returns `{score_pct, rated, total}`.
- `POST /api/runs/{run_id}/notes` — body: `{deck_id, notes}`. Updates `ratings.json` notes field for that deck.

#### Eval runner
- `POST /api/eval/start` — body: `{deck_id?: string, model: string, reflexion_run_id?: string}`. Launches `eval.py` as asyncio subprocess, streams stdout line-by-line as SSE events (`data: <line>\n\n`). Returns `text/event-stream`. Sends `data: __DONE__\n\n` on completion.

#### Score
- `GET /api/runs/{run_id}/score` — compute score across all decks: `{per_deck: [{deck_id, rated, total, correct_pct}], overall: {rated, total, correct_pct}}`.

### `ui/index.html` — Views

Single HTML file, ~400 lines. Tab-based navigation, no page reloads.

**Tab 1: Runs**
- Header: "PPT Review Agent" + "New Run" button (opens modal)
- Table: run_id | decks | mode | score | date | [Review] button
- Clicking [Review] switches to Tab 2 with that run pre-selected

**New Run Modal:**
- Deck selector: multi-select or "All decks" checkbox
- Model dropdown: populated from `GET /api/models`, grouped free/paid
- Reflexion toggle: checkbox "Use reflexion from prior run" → shows prior run selector
- [Run] button → calls `POST /api/eval/start`, switches to log view
- Log view: scrolling `<pre>` box streaming SSE output; shows "Done!" + [Go to Review] when `__DONE__` received

**Tab 2: Review** (wireframe v3 layout)
- Top bar: Run dropdown | Deck dropdown | "X/Y rated · Z%" | [Run eval.py] button (opens New Run modal)
- Left 50%: PDF viewer — PDF.js `<canvas>`, prev/next page buttons, page counter; clicking a redline row in the middle panel jumps to that slide's page
- Middle 30%: Redlines + Ratings — scrollable list, each row: `[Sl#] [T] [F] · redline text · [badge]`. T/F buttons call `POST /api/runs/{run_id}/ratings` immediately, update score display. Unrated rows are visually distinct (no active button). Selected row highlighted.
- Right 20%: Deck Notes textarea (blur → `POST /api/runs/{run_id}/notes`) + Score box (live updates on each T/F click)
- Bottom bar: "auto-saves on T/F click · notes saved on blur" | [Save & Score] button (forces score refresh)

**PDF.js integration:**
- Load via CDN: `https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.min.js`
- PDF fetched from `/data/raw/{deck_id}.pdf`
- Page sync: when redline row clicked, call `pdfDoc.getPage(slideNum)` and render to canvas

---

## Data Flow

```
[New Run modal] → POST /api/eval/start
  → subprocess: python eval.py --deck X --model Y
    → agent.py → requests.post(openrouter) × N iterations
    → writes runs/{run_id}/{deck_id}/redlines.json + narrative.txt
    → writes runs/{run_id}/ratings.json (template with nulls)
  → SSE stream of stdout back to browser log view

[Review tab] → GET /api/runs/{run_id}/{deck_id}/redlines
           → GET /api/runs/{run_id}/ratings
           → GET /data/raw/{deck_id}.pdf  (PDF.js renders it)

[T/F click] → POST /api/runs/{run_id}/ratings
           → server updates ratings.json, returns new score
           → UI updates score box

[Notes blur] → POST /api/runs/{run_id}/notes
            → server updates ratings.json notes field
```

---

## Error Handling

- `POST /api/eval/start` while eval is already running: return 409 with message "Eval already running"
- Missing PDF: `GET /data/raw/{deck_id}.pdf` returns 404; UI shows "PDF not found — download it first"
- OpenRouter API error during model fetch: return cached list from prior fetch, or empty list with error message
- ratings.json missing (run in progress or never scored): GET returns empty object; POST creates it

---

## Out of Scope (v0.1 web)

- User authentication
- Multiple concurrent eval runs
- Uploading new PDFs via the browser (user runs `data/download.py` manually)
- Editing or re-running individual slides
- Exporting ratings as CSV
