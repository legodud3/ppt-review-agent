"""Tests for agent.py — OpenRouter/requests implementation."""
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


def _make_response(tool_calls=None, content=None, usage=None):
    message = {"role": "assistant"}
    if tool_calls:
        message["tool_calls"] = tool_calls
        message["content"] = None
    else:
        message["content"] = content or ""
        message["tool_calls"] = None
    return {
        "choices": [{"message": message}],
        "usage": usage or {"prompt_tokens": 10, "completion_tokens": 5, "native_tokens_reasoning": 0},
    }


def _make_tool_call(name: str, args: dict, call_id: str = "call_1"):
    return {
        "id": call_id,
        "type": "function",
        "function": {"name": name, "arguments": json.dumps(args)},
    }


@pytest.fixture()
def sample_deck():
    fixture = Path(__file__).parent / "fixtures" / "sample_deck.json"
    import json as _json
    return _json.loads(fixture.read_text())


@pytest.fixture()
def output_dir(tmp_path):
    return tmp_path / "output"


def test_dispatch_read_deck_metadata(sample_deck, output_dir):
    from agent import _dispatch
    from tools import Tools
    t = Tools(sample_deck, output_dir)
    result = _dispatch(t, "read_deck_metadata", {})
    assert "total_pages" in result


def test_dispatch_unknown_tool(sample_deck, output_dir):
    from agent import _dispatch
    from tools import Tools
    t = Tools(sample_deck, output_dir)
    result = _dispatch(t, "nonexistent_tool", {})
    assert "Unknown tool" in result


def test_tools_list_has_five_entries():
    from agent import TOOLS
    assert len(TOOLS) == 5
    names = {t["function"]["name"] for t in TOOLS}
    assert names == {"read_deck_metadata", "read_slide", "write_redline", "write_narrative", "finish"}


def test_run_calls_finish_and_returns_review(sample_deck, output_dir):
    from agent import run

    responses = [
        _make_response(tool_calls=[_make_tool_call("read_deck_metadata", {}, "c1")]),
        _make_response(tool_calls=[_make_tool_call("read_slide", {"page_num": 1}, "c2")]),
        _make_response(tool_calls=[_make_tool_call("write_redline", {"page_num": 1, "feedback": "Good"}, "c3")]),
        _make_response(tool_calls=[_make_tool_call("write_narrative", {"text": "Overall fine."}, "c4")]),
        _make_response(tool_calls=[_make_tool_call("finish", {}, "c5")]),
    ]

    mock_resp = MagicMock()
    mock_resp.json.side_effect = responses
    mock_resp.raise_for_status.return_value = None

    with patch("agent.requests.post", return_value=mock_resp):
        review, tokens = run(
            deck=sample_deck,
            output_dir=output_dir,
            system_prompt="Review this deck.",
            api_key="test-key",
            model="test/model",
        )

    assert review["narrative"] == "Overall fine."
    assert 1 in review["redlines"]
    assert review["redlines"][1] == "Good"
    assert tokens["input"] > 0
    assert tokens["output"] > 0


def test_run_nudges_on_text_only_response(sample_deck, output_dir):
    from agent import run

    responses = [
        _make_response(content="I will now review the deck."),
        _make_response(tool_calls=[_make_tool_call("read_deck_metadata", {}, "c1")]),
        _make_response(tool_calls=[_make_tool_call("write_narrative", {"text": "Done."}, "c2")]),
        _make_response(tool_calls=[_make_tool_call("finish", {}, "c3")]),
    ]

    mock_resp = MagicMock()
    mock_resp.json.side_effect = responses
    mock_resp.raise_for_status.return_value = None

    with patch("agent.requests.post", return_value=mock_resp):
        review, _ = run(
            deck=sample_deck,
            output_dir=output_dir,
            system_prompt="Review this deck.",
            api_key="test-key",
            model="test/model",
        )

    assert review["narrative"] == "Done."


def test_run_with_reflexion_context(sample_deck, output_dir):
    from agent import run

    responses = [
        _make_response(tool_calls=[_make_tool_call("finish", {}, "c1")]),
    ]
    mock_resp = MagicMock()
    mock_resp.json.side_effect = responses
    mock_resp.raise_for_status.return_value = None

    captured = []

    def capture_post(url, headers, data, timeout):
        captured.append(json.loads(data))
        return mock_resp

    with patch("agent.requests.post", side_effect=capture_post):
        run(
            deck=sample_deck,
            output_dir=output_dir,
            system_prompt="Review.",
            api_key="test-key",
            model="test/model",
            reflexion_context="Prior feedback: slide 1 was wrong.",
        )

    first_user_msg = next(m for m in captured[0]["messages"] if m["role"] == "user")
    assert "Prior feedback" in first_user_msg["content"]


def test_run_raises_on_api_error_body(sample_deck, output_dir):
    """OpenRouter returns HTTP 200 with an error body on rate limits etc."""
    from agent import run
    import pytest

    mock_resp = MagicMock()
    mock_resp.json.return_value = {"error": {"message": "Rate limit exceeded", "code": 429}}
    mock_resp.raise_for_status.return_value = None

    with patch("agent.requests.post", return_value=mock_resp):
        with pytest.raises(RuntimeError, match="OpenRouter error"):
            run(
                deck=sample_deck,
                output_dir=output_dir,
                system_prompt="Review.",
                api_key="test-key",
                model="test/model",
            )
