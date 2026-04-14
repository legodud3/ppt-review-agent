import json
import pytest
from pathlib import Path
from tools import Tools


@pytest.fixture
def sample_deck():
    fixture = Path(__file__).parent / "fixtures" / "sample_deck.json"
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
    msg = tools.write_redline(1, "Pyramid broken — bullets don't support title claim")
    assert "1" in msg
    assert tools.redlines[1] == ["Pyramid broken — bullets don't support title claim"]


def test_write_redline_multiple_per_slide(tools):
    """Multiple write_redline calls on the same slide append to a list."""
    tools.write_redline(1, "Unsupported assertion — quantify the claim")
    tools.write_redline(1, "So-what missing — add conclusion sentence")
    assert len(tools.redlines[1]) == 2
    assert tools.redlines[1][0] == "Unsupported assertion — quantify the claim"
    assert tools.redlines[1][1] == "So-what missing — add conclusion sentence"


def test_write_redline_out_of_range(tools):
    msg = tools.write_redline(0, "should not save")
    assert "Error" in msg
    assert 0 not in tools.redlines

    msg = tools.write_redline(99, "should not save")
    assert "Error" in msg
    assert 99 not in tools.redlines


def test_write_narrative(tools):
    msg = tools.write_narrative("Deck lacks narrative arc.")
    assert msg == "Narrative saved."
    assert tools.narrative == "Deck lacks narrative arc."


def test_finish_idempotent(tools):
    tools.write_redline(1, "Pyramid broken")
    tools.write_narrative("Poor arc.")
    tools.finish()
    msg = tools.finish()
    assert msg == "Review already complete."


def test_finish_writes_files(tools, tmp_path):
    tools.write_redline(1, "Pyramid broken")
    tools.write_redline(1, "So-what missing")
    tools.write_redline(2, "Unsupported assertion")
    tools.write_narrative("Poor narrative arc.")
    tools.finish()

    assert tools.is_finished

    redlines_path = tmp_path / "redlines.json"
    narrative_path = tmp_path / "narrative.txt"

    assert redlines_path.exists()
    assert narrative_path.exists()

    redlines = json.loads(redlines_path.read_text())
    assert redlines["1"] == ["Pyramid broken", "So-what missing"]
    assert redlines["2"] == ["Unsupported assertion"]

    assert narrative_path.read_text() == "Poor narrative arc."
