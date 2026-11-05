"""
Sleep (estimate). Offline analysis of a RECORDED session (accelerometer only). Every number on this
page is an estimate of sleep/wake from wrist movement - not polysomnography, no sleep stages, not
clinically validated and not validated on ParkinSense hardware. A session shorter than 1 h, or one
with no >= 30 min sleep period, shows an explanatory empty state instead of a chart.
"""

from __future__ import annotations

import threading
from collections import OrderedDict

import numpy as np
from dash import Input, Output, dcc, html

from parkinsense import config as C
from parkinsense.sleep import api as SLEEP
from parkinsense.sleep import params as P
from parkinsense.visualization import charts as CH
from parkinsense.visualization import components as K
from parkinsense.visualization import sessions as SS
from parkinsense.visualization import theme as T
from parkinsense.visualization.pages import common

MIN_SESSION_H = 1.0
MAX_TREND_SESSIONS = 7
SLEEP_COLOR, WAKE_COLOR, GAP_COLOR = "#5b9cff", "#e6b450", "#6b7280"
_cache: "OrderedDict[tuple, dict]" = OrderedDict()
_lock = threading.Lock()


def report_for(session) -> dict | None:
    """Cached sleep report for a recorded session (None if it cannot be analysed)."""
    if session is None or not session.capture.exists():
        return None
    st = session.capture.stat()
    key = (str(session.capture), st.st_size, st.st_mtime_ns, C.SLEEP_ALGORITHM_VERSION)
    with _lock:
        if key in _cache:
            _cache.move_to_end(key)
            return _cache[key]
    try:
        rep = SLEEP.analyze_file(session.capture)
    except Exception as e:   # noqa: BLE001 - a malformed capture must not break the page
        rep = {"error": f"{type(e).__name__}: {e}"}
    with _lock:
        _cache[key] = rep
        while len(_cache) > 4:
            _cache.popitem(last=False)
    return rep


def layout():
    g = lambda i, h=260: html.Div(className="card", children=[  # noqa: E731
        dcc.Graph(id=i, config=CH.GRAPH_CONFIG, figure=CH.empty("Select a recorded session", h))])
    return html.Div([
        html.Div(className="page-head", children=[
            html.Div([html.H1("Sleep (estimate)", className="page-title"),
                      html.Div("Sleep/wake estimated from wrist movement. Not polysomnography, no sleep stages, "
                               "not clinically validated, not validated on ParkinSense hardware.",
                               className="page-sub")]),
            html.Div(className="row", children=[common.session_picker("sl-session"),
                                                html.Button("Reload", id="sl-reload", className="btn")]),
        ]),
        html.Div("ESTIMATE — all values on this page are derived estimates, not measurements. Overnight finger-contact "
                 "heart-rate/SpO2 is not available from this analysis (the optical sensor needs finger contact).",
                 className="banner banner-info"),
        dcc.Loading(html.Div(id="sl-summary"), type="dot", color=T.ACCENT),
        g("sl-timeline", 220),
        html.Div(className="grid g2", style={"marginTop": "14px"}, children=[g("sl-hourly"), g("sl-trend")]),
        K.section("Data quality", html.Div(id="sl-quality", className="card")),
    ])


def _minutes(v):
    return None if v is None else float(v)


def summary(rep, session):
    if rep is None:
        return html.Div("Sleep analysis works on recorded sessions. Pick one from the list.", className="card muted")
    if "error" in rep:
        return html.Div(f"This session could not be analysed ({rep['error']}).", className="card muted")
    n = rep["night"]
    if "tst_min" not in n:
        why = n.get("reason") or "no sleep period of at least 30 minutes was found"
        return html.Div(f"No sleep estimate for this session: {why}.", className="card muted")
    q = n.get("quality")
    est = "ESTIMATE"
    return html.Div(className="grid g4", children=[
        K.metric_card("Total sleep time", n["tst_min"] / 60, "h", state=q, always_badge=est, accent=SLEEP_COLOR, digits=2,
                      foot=f"{n['tst_min']:.0f} min inside the sleep period"),
        K.metric_card("Wake after onset", n["waso_min"], "min", state=q, always_badge=est, accent=WAKE_COLOR, digits=0),
        K.metric_card("Sleep period", n["spt_min"] / 60, "h", state=q, always_badge=est, accent=SLEEP_COLOR, digits=2,
                      foot="first sleep onset to final wake"),
        K.metric_card("Period efficiency", 100 * n["period_efficiency"], "%", state=q, always_badge=est, digits=0,
                      foot="sleep / (sleep + wake) inside the period; not time-in-bed efficiency"),
        K.metric_card("Awakenings", n["awakenings"], "", state=q, always_badge=est, digits=0, foot="wake runs >= 1 min"),
        K.metric_card("Fragmentation", n["fragmentation_index_per_h"], "per h", state=q, always_badge=est, digits=1),
        K.metric_card("Movement in sleep", 100 * n["movement_in_sleep_fraction"], "%", state=q, always_badge=est,
                      digits=0, foot="sleep epochs with >5° orientation change"),
        K.metric_card("Data coverage", 100 * n["coverage"], "%", digits=0, foot="analysable share of the recording"),
    ])


def timeline(rep):
    if not rep or "error" in rep or not rep.get("epochs"):
        return CH.empty("No epochs: the recording is shorter than 1 h", 220, "Sleep/wake timeline (estimate)")
    e = rep["epochs"]
    t = np.asarray(e["t_s"], float) / 3600
    st = np.asarray(e["state"])
    p = np.array([np.nan if v is None else v for v in e["p_sleep"]])
    fig = CH.base("Sleep/wake timeline (estimate)", 220, "time since recording start (h)", "P(sleep)", "sl-tl")
    for val, name, col in ((1, "sleep", SLEEP_COLOR), (0, "wake", WAKE_COLOR), (-1, "no data / non-wear", GAP_COLOR)):
        m = st == val
        if m.any():
            fig.add_scatter(x=t[m], y=np.where(m, np.nan_to_num(p, nan=0.0), np.nan)[m], mode="markers", name=name,
                            marker=dict(color=col, size=5, symbol="square"),
                            hovertemplate="%{x:.2f} h · " + name + "<extra></extra>")
    fig.update_yaxes(range=[-0.05, 1.05])
    fig.add_hline(y=P.ACCEL["threshold"], line_dash="dot", line_color=T.MUTED,
                  annotation_text="sleep if P ≥ threshold", annotation_position="bottom right")
    n = rep["night"]
    if "onset_s" in n:
        fig.add_vrect(x0=n["onset_s"] / 3600, x1=n["wake_s"] / 3600, fillcolor=SLEEP_COLOR, opacity=0.07, line_width=0,
                      annotation_text="sleep period", annotation_position="top left")
    return fig


def hourly(rep):
    if not rep or "error" in rep or not rep.get("epochs"):
        return CH.empty("No data", 260, "Sleep per hour (estimate)")
    e = rep["epochs"]
    t, st = np.asarray(e["t_s"], float), np.asarray(e["state"])
    h = (t // 3600).astype(int)
    hours = sorted(set(h))
    sl = [float(np.sum((h == k) & (st == 1)) * C_EPOCH / 60) for k in hours]
    wk = [float(np.sum((h == k) & (st == 0)) * C_EPOCH / 60) for k in hours]
    fig = CH.base("Sleep per hour of recording (estimate)", 260, "hour of recording", "minutes", "sl-hr")
    fig.add_bar(x=hours, y=sl, name="sleep", marker_color=SLEEP_COLOR)
    fig.add_bar(x=hours, y=wk, name="wake", marker_color=WAKE_COLOR)
    fig.update_layout(barmode="stack")
    return fig


C_EPOCH = 30.0


def trend(reports):
    rows = [(lab, r["night"]) for lab, r in reports if r and "night" in r and "tst_min" in r["night"]]
    if len(rows) < 2:
        return CH.empty("A duration trend needs at least two recorded nights with a sleep estimate", 260,
                        "Sleep duration across sessions (estimate)")
    fig = CH.base("Sleep duration across sessions (estimate)", 260, "session", "hours", "sl-trend", legend=True)
    fig.add_scatter(x=[r[0] for r in rows], y=[r[1]["tst_min"] / 60 for r in rows], mode="lines+markers",
                    name="total sleep time", line=dict(color=SLEEP_COLOR))
    return fig


def quality_card(rep):
    if not rep or "error" in rep:
        return "No quality information for this selection."
    n = rep["night"]
    items = [("Recording", f"{n.get('recording_min', 0) / 60:.1f} h"), ("Analysed", f"{n.get('analysed_min', 0) / 60:.1f} h"),
             ("Non-wear / flat signal", f"{n.get('nonwear_min', 0):.0f} min"),
             ("Gaps inside sleep period", f"{n.get('gap_in_spt_min', 0):.0f} min" if "gap_in_spt_min" in n else "—"),
             ("Quality state", n.get("quality", "—")),
             ("Algorithm", f"sleep {rep['sleep_algorithm_version']} · pipeline {rep['pipeline_version']}")]
    return html.Div(className="grid g3", children=[K.status_item(k, v) for k, v in items])


def register(app):
    @app.callback(Output("sl-summary", "children"), Output("sl-timeline", "figure"), Output("sl-hourly", "figure"),
                  Output("sl-trend", "figure"), Output("sl-quality", "children"),
                  Input("sl-session", "value"), Input("sl-reload", "n_clicks"))
    def _load(value, _):
        sess = common.resolve_session(value, None) if value not in (None, common.LIVE) else None
        rep = report_for(sess)
        long_enough = [s for s in SS.list_sessions() if s.kind == "recording" and
                       (s.meta.get("measured") or {}).get("samples", 0) >= MIN_SESSION_H * 3600 * C.SAMPLE_RATE_HZ]
        # trend over the most recent nights only (each analysis reads a whole capture); oldest first for the x axis
        others = [(s.id, report_for(s)) for s in long_enough[:MAX_TREND_SESSIONS]][::-1]
        return summary(rep, sess), timeline(rep), hourly(rep), trend(others), quality_card(rep)
