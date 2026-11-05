"""Sleep dashboard page: honest empty states, ESTIMATE labelling, routing."""
import pytest

pytest.importorskip("dash")
from helpers import synthetic_night  # noqa: E402

from parkinsense.sleep.api import analyze  # noqa: E402
from parkinsense.visualization.pages import sleep as SP  # noqa: E402


def _text(node):
    """All text in a dash component tree."""
    if node is None:
        return ""
    if isinstance(node, (str, int, float)):
        return str(node)
    if isinstance(node, (list, tuple)):
        return " ".join(_text(n) for n in node)
    return _text(getattr(node, "children", None))


def test_page_registered_and_layout_builds():
    from parkinsense.visualization.dashboard import PAGES, create_app
    assert any(p == "/sleep" for p, _, _ in PAGES)
    assert "estimate" in _text(SP.layout()).lower()
    create_app()


def test_empty_states_are_explicit_not_fictional():
    assert "recorded" in _text(SP.summary(None, None)).lower()
    assert len(SP.timeline(None).data) == 0 and SP.timeline(None).layout.annotations[0].text
    assert len(SP.hourly(None).data) == 0
    assert "at least two" in SP.trend([]).layout.annotations[0].text
    short = analyze(*synthetic_night(0.4, 0, 0))
    assert "No sleep estimate" in _text(SP.summary(short, None))
    assert len(SP.timeline(short).data) == 0


def test_full_night_cards_are_badged_as_estimates_and_charts_have_data():
    rep = analyze(*synthetic_night())
    txt = _text(SP.summary(rep, None))
    assert txt.lower().count("uncalibrated estimate") >= 7
    assert len(SP.timeline(rep).data) >= 2
    assert len(SP.hourly(rep).data) == 2
    assert len(SP.trend([("a", rep), ("b", rep)]).data) == 1
