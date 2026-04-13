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
