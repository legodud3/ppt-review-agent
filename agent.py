"""ReAct loop for the PPT review agent — OpenRouter backend.

run(deck, output_dir, system_prompt, api_key, model, reflexion_context=None) → (review_dict, token_stats)

review_dict = {"redlines": {page_num: feedback}, "narrative": str}
token_stats  = {"input": int, "output": int, "thinking": int}
"""
import json
import sys
import tomllib
from pathlib import Path

import requests
from dotenv import load_dotenv

from tools import Tools

load_dotenv()

with open(Path(__file__).parent / "config.toml", "rb") as _f:
    _config = tomllib.load(_f)

MAX_ITERATIONS = _config["model"]["max_iterations"]
DEFAULT_MODEL = _config["model"].get("default_model", "nvidia/llama-3.1-nemotron-ultra-253b-v1:free")

OPENROUTER_BASE = "https://openrouter.ai/api/v1/chat/completions"
_SITE_URL = "http://localhost:8000"
_SITE_TITLE = "PPT Review Agent"

TOOLS = [
    {"type": "function", "function": {
        "name": "read_deck_metadata",
        "description": "Get metadata: entity name, deck title, total slide count, source type.",
        "parameters": {"type": "object", "properties": {}, "required": []},
    }},
    {"type": "function", "function": {
        "name": "read_slide",
        "description": "Read the title and body text of one slide by page number (1-based).",
        "parameters": {
            "type": "object",
            "properties": {
                "page_num": {"type": "integer", "description": "Slide number, starting from 1"},
            },
            "required": ["page_num"],
        },
    }},
    {"type": "function", "function": {
        "name": "write_redline",
        "description": "Save a redline comment for a specific slide.",
        "parameters": {
            "type": "object",
            "properties": {
                "page_num": {"type": "integer", "description": "Slide number"},
                "feedback": {"type": "string", "description": "Redline comment for this slide"},
            },
            "required": ["page_num", "feedback"],
        },
    }},
    {"type": "function", "function": {
        "name": "write_narrative",
        "description": "Save the deck-level narrative note (3-5 sentences on overall story quality).",
        "parameters": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "Deck-level narrative feedback"},
            },
            "required": ["text"],
        },
    }},
    {"type": "function", "function": {
        "name": "finish",
        "description": "Signal that the review is complete. Call after writing all redlines and the narrative.",
        "parameters": {"type": "object", "properties": {}, "required": []},
    }},
]


def _dispatch(tools: Tools, name: str, args: dict) -> str:
    """Route a tool call name+args to the Tools instance. Returns result string."""
    if name == "read_deck_metadata":
        return tools.read_deck_metadata()
    elif name == "read_slide":
        return tools.read_slide(int(args["page_num"]))
    elif name == "write_redline":
        return tools.write_redline(int(args["page_num"]), args["feedback"])
    elif name == "write_narrative":
        return tools.write_narrative(args["text"])
    elif name == "finish":
        return tools.finish()
    else:
        return f"Unknown tool: {name}"


def run(
    deck: dict,
    output_dir: Path,
    system_prompt: str,
    api_key: str,
    model: str = DEFAULT_MODEL,
    reflexion_context: str | None = None,
) -> tuple[dict, dict]:
    """Run the ReAct review loop for one deck. Returns (review, token_stats).

    Args:
        deck: parsed deck dict from data/decks/*.json
        output_dir: directory to write redlines.json and narrative.txt
        system_prompt: rubric text from system_prompt.md
        api_key: OpenRouter API key
        model: OpenRouter model ID (e.g. 'nvidia/llama-3.1-nemotron-ultra-253b-v1:free')
        reflexion_context: optional prior-run feedback (for --reflexion mode)
    """
    tools_obj = Tools(deck, output_dir)
    headers = {
        "Authorization": f"Bearer {api_key}",
        "HTTP-Referer": _SITE_URL,
        "X-OpenRouter-Title": _SITE_TITLE,
        "Content-Type": "application/json",
    }

    initial_content = (
        f"Please review this presentation: {deck['deck_id']} ({deck.get('entity', '')})"
    )
    if reflexion_context:
        initial_content += f"\n\n{reflexion_context}"

    messages: list[dict] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": initial_content},
    ]
    tokens = {"input": 0, "output": 0, "thinking": 0}

    for _ in range(MAX_ITERATIONS):
        resp = requests.post(
            OPENROUTER_BASE,
            headers=headers,
            data=json.dumps({
                "model": model,
                "messages": messages,
                "tools": TOOLS,
                "tool_choice": "auto",
            }),
            timeout=120,
        )
        resp.raise_for_status()
        data = resp.json()

        if "error" in data:
            raise RuntimeError(f"OpenRouter error: {data['error'].get('message', data['error'])}")
        choices = data.get("choices")
        if not choices:
            raise RuntimeError(f"Unexpected API response (no choices): {data}")
        message = choices[0]["message"]

        usage = data.get("usage", {})
        tokens["input"] += usage.get("prompt_tokens", 0) or 0
        tokens["output"] += usage.get("completion_tokens", 0) or 0
        tokens["thinking"] += usage.get("native_tokens_reasoning", 0) or 0

        if message.get("tool_calls"):
            messages.append(message)
            for tc in message["tool_calls"]:
                name = tc["function"]["name"]
                try:
                    args = json.loads(tc["function"]["arguments"])
                except json.JSONDecodeError:
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc["id"],
                        "content": "Error: could not parse tool arguments as JSON. Please retry with valid JSON.",
                    })
                    continue
                result = _dispatch(tools_obj, name, args)
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": str(result),
                })
            if tools_obj.is_finished:
                break
        else:
            # Model produced text instead of a tool call — nudge it back
            messages.append(message)
            messages.append({"role": "user", "content": (
                "Continue the review. Use the available tools to read slides and write feedback."
            )})

    if not tools_obj.is_finished:
        print(f"  Warning: agent hit MAX_ITERATIONS ({MAX_ITERATIONS}) without calling finish()", file=sys.stderr)

    review = {"redlines": tools_obj.redlines, "narrative": tools_obj.narrative}
    return review, tokens
