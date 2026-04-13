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
