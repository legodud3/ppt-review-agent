"""Local web server for PPT Review Agent.

Run:  python server.py
Open: http://localhost:8000
"""
import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import AsyncIterator

import requests as _req
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

load_dotenv()

ROOT = Path(__file__).parent
DATA_RAW = ROOT / "data" / "raw"
DATA_DECKS = ROOT / "data" / "decks"
RUNS_DIR = ROOT / "runs"
UI_DIR = ROOT / "ui"

app = FastAPI(title="PPT Review Agent")

# One eval subprocess at a time
_eval_proc: asyncio.subprocess.Process | None = None


# ── Page / PDF serving ────────────────────────────────────────────────────────

@app.get("/")
def serve_index():
    return FileResponse(UI_DIR / "index.html")


@app.get("/data/raw/{deck_id}.pdf")
def serve_pdf(deck_id: str):
    path = (DATA_RAW / f"{deck_id}.pdf").resolve()
    if not path.is_relative_to(DATA_RAW.resolve()):
        raise HTTPException(400, "Invalid deck_id")
    if not path.exists():
        raise HTTPException(404, f"PDF not found: {deck_id}.pdf — run data/download.py first")
    return FileResponse(path, media_type="application/pdf")


# ── Decks ─────────────────────────────────────────────────────────────────────

@app.get("/api/decks")
def list_decks():
    decks = []
    for f in sorted(DATA_DECKS.glob("*.json")):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            raise HTTPException(500, f"Failed to read file: {exc}") from exc
        decks.append({
            "deck_id": data["deck_id"],
            "entity": data.get("entity", ""),
            "total_pages": len(data.get("slides", [])),
        })
    return decks


# ── Models ────────────────────────────────────────────────────────────────────

@app.get("/api/models")
def list_models():
    api_key = os.environ.get("OPENROUTER_API_KEY", "")
    try:
        resp = _req.get(
            "https://openrouter.ai/api/v1/models",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=10,
        )
        resp.raise_for_status()
        models = resp.json().get("data", [])
    except Exception as exc:
        return {"error": str(exc), "models": []}

    def _sort_key(m):
        pricing = m.get("pricing", {})
        prompt_price = float(pricing.get("prompt", "1") or "1")
        context = m.get("context_length", 0) or 0
        return (prompt_price > 0, -context)

    models.sort(key=_sort_key)
    return {
        "models": [
            {
                "id": m["id"],
                "name": m.get("name", m["id"]),
                "context_length": m.get("context_length"),
                "pricing": m.get("pricing", {}),
            }
            for m in models
        ]
    }


# ── Runs ──────────────────────────────────────────────────────────────────────

def _compute_score(run_dir: Path) -> dict:
    """Compute correct/rated/total from ratings.json."""
    path = run_dir / "ratings.json"
    if not path.exists():
        return {"correct": 0, "rated": 0, "total": 0}
    try:
        ratings = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"correct": 0, "rated": 0, "total": 0}
    correct = rated = total = 0
    for deck_data in ratings.values():
        for v in deck_data.get("slide_ratings", {}).values():
            total += 1
            if v is not None:
                rated += 1
            if v is True:
                correct += 1
    return {"correct": correct, "rated": rated, "total": total}


@app.get("/api/runs")
def list_runs():
    runs = []
    if not RUNS_DIR.exists():
        return runs
    for d in sorted(RUNS_DIR.iterdir(), reverse=True):
        if not d.is_dir():
            continue
        deck_ids = sorted(sub.name for sub in d.iterdir() if sub.is_dir())
        runs.append({
            "run_id": d.name,
            "deck_ids": deck_ids,
            "mode": "reflexion" if d.name.endswith("_reflexion") else "baseline",
            "score": _compute_score(d),
        })
    return runs


@app.get("/api/runs/{run_id}/ratings")
def get_ratings(run_id: str):
    path = RUNS_DIR / run_id / "ratings.json"
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        raise HTTPException(500, f"Failed to read file: {exc}") from exc
    return data


@app.get("/api/runs/{run_id}/{deck_id}/redlines")
def get_redlines(run_id: str, deck_id: str):
    path = RUNS_DIR / run_id / deck_id / "redlines.json"
    if not path.exists():
        raise HTTPException(404, "redlines.json not found")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        raise HTTPException(500, f"Failed to read file: {exc}") from exc
    return data


@app.get("/api/runs/{run_id}/{deck_id}/narrative")
def get_narrative(run_id: str, deck_id: str):
    path = RUNS_DIR / run_id / deck_id / "narrative.txt"
    if not path.exists():
        return {"narrative": ""}
    return {"narrative": path.read_text(encoding="utf-8")}


# ── Rating writes ─────────────────────────────────────────────────────────────

class RatingUpdate(BaseModel):
    deck_id: str
    slide: str        # page number as string key, e.g. "3"
    value: bool | None  # true=correct, false=wrong, None=unrate


class NotesUpdate(BaseModel):
    deck_id: str
    notes: str


@app.post("/api/runs/{run_id}/ratings")
def save_rating(run_id: str, body: RatingUpdate):
    path = RUNS_DIR / run_id / "ratings.json"
    if not path.exists():
        raise HTTPException(404, "ratings.json not found — run eval first")
    try:
        ratings = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        raise HTTPException(500, f"Failed to read ratings.json: {exc}") from exc
    deck_data = ratings.setdefault(body.deck_id, {"slide_ratings": {}, "notes": ""})
    deck_data["slide_ratings"][body.slide] = body.value
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(ratings, indent=2), encoding="utf-8")
    tmp.replace(path)
    return _compute_score(RUNS_DIR / run_id)


@app.post("/api/runs/{run_id}/notes")
def save_notes(run_id: str, body: NotesUpdate):
    path = RUNS_DIR / run_id / "ratings.json"
    if not path.exists():
        raise HTTPException(404, "ratings.json not found — run eval first")
    try:
        ratings = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        raise HTTPException(500, f"Failed to read ratings.json: {exc}") from exc
    deck_data = ratings.setdefault(body.deck_id, {"slide_ratings": {}, "notes": ""})
    deck_data["notes"] = body.notes
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(ratings, indent=2), encoding="utf-8")
    tmp.replace(path)
    return {"ok": True}


# ── Score ─────────────────────────────────────────────────────────────────────

@app.get("/api/runs/{run_id}/score")
def get_score(run_id: str):
    path = RUNS_DIR / run_id / "ratings.json"
    if not path.exists():
        raise HTTPException(404, "ratings.json not found")
    try:
        ratings = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        raise HTTPException(500, f"Failed to read file: {exc}") from exc
    per_deck = []
    t_correct = t_rated = t_total = 0
    for deck_id, deck_data in ratings.items():
        slide_ratings = deck_data.get("slide_ratings", {})
        correct = sum(1 for v in slide_ratings.values() if v is True)
        rated = sum(1 for v in slide_ratings.values() if v is not None)
        total = len(slide_ratings)
        per_deck.append({
            "deck_id": deck_id,
            "correct": correct,
            "rated": rated,
            "total": total,
            "correct_pct": round(correct / rated * 100, 1) if rated else None,
        })
        t_correct += correct
        t_rated += rated
        t_total += total
    return {
        "per_deck": per_deck,
        "overall": {
            "correct": t_correct,
            "rated": t_rated,
            "total": t_total,
            "correct_pct": round(t_correct / t_rated * 100, 1) if t_rated else None,
        },
    }


# ── Eval runner (SSE) ─────────────────────────────────────────────────────────

class EvalRequest(BaseModel):
    deck_id: str | None = None
    model: str
    reflexion_run_id: str | None = None


@app.post("/api/eval/start")
async def start_eval(body: EvalRequest):
    global _eval_proc
    if _eval_proc is not None and _eval_proc.returncode is None:
        raise HTTPException(409, "Eval already running — wait for it to finish")

    cmd = [sys.executable, str(ROOT / "eval.py"), "--model", body.model]
    if body.deck_id:
        cmd += ["--deck", body.deck_id]
    if body.reflexion_run_id:
        cmd += ["--reflexion", str(RUNS_DIR / body.reflexion_run_id)]

    async def _stream() -> AsyncIterator[str]:
        global _eval_proc
        _eval_proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            cwd=str(ROOT),
        )
        assert _eval_proc.stdout is not None
        async for raw in _eval_proc.stdout:
            line = raw.decode(errors="replace").rstrip()
            yield f"data: {line}\n\n"
        await _eval_proc.wait()
        yield "data: __DONE__\n\n"

    return StreamingResponse(_stream(), media_type="text/event-stream")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
