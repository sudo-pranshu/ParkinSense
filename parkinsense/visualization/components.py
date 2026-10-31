"""Reusable layout components. Pure functions of their inputs -- no data access."""

from __future__ import annotations

import math

from dash import html

from parkinsense.visualization import quality as Q


def fmt(value, digits=1):
    """Format a number; anything missing renders as an em dash, never as 0."""
    if value is None:
        return None
    try:
        v = float(value)
    except (TypeError, ValueError):
        return str(value)
    if math.isnan(v) or math.isinf(v):
        return None
    if digits == 0:
        return f"{v:,.0f}"
    return f"{v:,.{digits}f}"


def age_text(age_s):
    if age_s is None:
        return "no data yet"
    if age_s < 1.5:
        return "live"
    if age_s < 90:
        return f"{age_s:.0f} s ago"
    if age_s < 5400:
        return f"{age_s / 60:.0f} min ago"
    return f"{age_s / 3600:.1f} h ago"


def badge(state: str | None, text: str | None = None, title: str | None = None):
    if not state:
        return None
    return html.Span(text or Q.label(state), className=f"qbadge {Q.css(state)}", title=title or Q.explain(state))


def metric_card(title, value, unit="", state=None, foot=None, accent=None, digits=1,
                stale=False, always_badge=None, card_id=None):
    """
    A metric card. `state` is the measurement's quality state; a non-VALID state
    (or `stale`) renders the value muted with an explanatory badge, so an
    untrustworthy number never looks like a measurement.
    """
    text = fmt(value, digits) if isinstance(value, (int, float)) or value is None else str(value)
    effective = "STALE" if stale and text is not None else state
    trusted = effective in (None, "VALID")
    cls = "metric-value" + ("" if trusted else " untrusted") + (" empty" if text is None else "")
    badges = [b for b in (badge(effective), badge(always_badge)) if b is not None]
    accent_bar = html.Span(className="metric-accent", style={"background": accent}) if accent else None
    return html.Div(className="card metric", **({"id": card_id} if card_id else {}), children=[
        html.Div(className="metric-head", children=[
            html.Span([accent_bar, title], className="metric-title"),
            html.Div(badges, className="row"),
        ]),
        html.Div(className=cls, children=[text if text is not None else "—",
                                          html.Span(unit, className="metric-unit") if unit and text is not None else None]),
        html.Div(foot, className="metric-foot") if foot else None,
    ])


def status_item(k, v, pill=None):
    return html.Div(className="status-item", children=[
        html.Span(k, className="status-k"),
        html.Span(pill if pill is not None else v, className="status-v"),
    ])


def pill(text, kind="idle"):
    return html.Span(text, className=f"pill pill-{kind}")


def section(title, *children):
    return html.Div([html.Div(title, className="section-title"), *children])


def empty(text):
    return html.Div(text, className="empty-state")


def kv(pairs):
    out = []
    for k, v in pairs:
        out += [html.Div(k, className="k"), html.Div("—" if v is None else str(v), className="v")]
    return html.Div(out, className="kv")


def quality_legend(states=None):
    states = states or [q for q in Q.ORDERED]
    return html.Div(className="legend", children=[
        html.Span(className="legend-item", children=[badge(s), html.Span(Q.explain(s))]) for s in states])
