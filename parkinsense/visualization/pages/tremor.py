"""
Tremor analytics for the live buffer or any recorded session: time course,
detected episodes, the frequency-domain view of any analysis window, and
cross-session comparison. All values are the pipeline's own outputs; the
spectrum view calls the pipeline's own `motion.features.gyro_spectrum` on the
recorded raw window (it does not re-implement it).
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from dash import Input, Output, State, dash_table, dcc, html

from parkinsense import config as C
from parkinsense.analytics.biomarkers import tremor_summary
from parkinsense.motion.features import TREMOR_PEAK_HALF_WIDTH_HZ, gyro_spectrum
from parkinsense.visualization import charts as CH
from parkinsense.visualization import components as K
from parkinsense.visualization import datasource as DS
from parkinsense.visualization import sessions as SS
from parkinsense.visualization import theme as T
from parkinsense.visualization.pages import common

TABLE_STYLE = dict(
    style_header={"backgroundColor": T.PANEL, "color": T.MUTED, "fontWeight": 600, "border": f"1px solid {T.GRID}"},
    style_cell={"backgroundColor": T.BG, "color": T.TEXT, "border": f"1px solid {T.GRID}", "fontSize": 12,
                "padding": "6px 8px", "textAlign": "left"},
    style_table={"overflowX": "auto"}, page_size=10, sort_action="native")


def layout():
    return html.Div([
        html.Div(className="page-head", children=[
            html.Div([html.H1("Tremor analytics", className="page-title"),
                      html.Div("Rest-tremor detection, frequency, amplitude and power over a session. "
                               "No clinical severity is computed.", className="page-sub")]),
            html.Div(className="row", children=[common.session_picker("tr-session"),
                                                html.Button("Reload", id="tr-reload", className="btn")]),
        ]),
        dcc.Loading(html.Div(id="tr-summary"), type="dot", color=T.ACCENT),
        html.Div(className="card", children=[dcc.Graph(id="tr-p", config=CH.GRAPH_CONFIG, figure=CH.empty("Select a session", 260))]),
        html.Div(className="grid g2", style={"marginTop": "14px"}, children=[
            html.Div(className="card", children=[dcc.Graph(id="tr-freq", config=CH.GRAPH_CONFIG, figure=CH.empty("—", 260))]),
            html.Div(className="card", children=[dcc.Graph(id="tr-amp", config=CH.GRAPH_CONFIG, figure=CH.empty("—", 260))]),
        ]),
        html.Div(className="grid g2", style={"marginTop": "14px"}, children=[
            html.Div(className="card", children=[dcc.Graph(id="tr-power", config=CH.GRAPH_CONFIG, figure=CH.empty("—", 260))]),
            html.Div(className="card", children=[
                html.Div("Click a point in the frequency chart to inspect that 4 s window's spectrum.",
                         className="muted small"),
                dcc.Graph(id="tr-psd", config=CH.GRAPH_CONFIG, figure=CH.empty("No window selected", 240))]),
        ]),
        html.Div(className="card", style={"marginTop": "14px"}, children=[
            dcc.Graph(id="tr-motion", config=CH.GRAPH_CONFIG, figure=CH.empty("—", 110))]),
        K.section("Detected episodes", html.Div(id="tr-episodes", className="card")),
        K.section("Compare sessions", html.Div(className="card", children=[
            common.session_picker("tr-compare", multi=True),
            html.Div(id="tr-compare-out", style={"marginTop": "12px"}),
        ])),
    ])


def load(value, snap):
    if value in (None, common.LIVE):
        return common.analyses_frame(snap), None
    sess = SS.get_session(value)
    if sess is None:
        return pd.DataFrame(), None
    return SS.load_analyses(sess), sess


def summary_cards(df, sess):
    ts = tremor_summary(df) if not df.empty else {}
    ep = SS.episodes(df)
    src = "live buffer (≤ 10 min)" if sess is None else f"session {sess.id}"
    q = SS.session_quality_score(df)
    return html.Div(className="grid g4", children=[
        K.metric_card("Tremor time", ts.get("tremor_time_pct"), "%",
                      state="VALID" if ts.get("tremor_time_pct") is not None else "INSUFFICIENT_DATA",
                      accent=T.TREMOR, foot=ts.get("reason") or f"{ts.get('still_minutes', 0):.1f} min still data · {src}"),
        K.metric_card("Median frequency", ts.get("tremor_frequency_hz_median"), "Hz", digits=2, accent=T.TREMOR,
                      foot="detected windows (evidence ≥ 0.5)"),
        K.metric_card("Tremor power (median)", ts.get("tremor_power_median"), "log₁₀(°²/s²+1)", digits=3,
                      accent=T.TREMOR, foot=ts.get("tremor_power_note") or "reported when tremor time ≥ 3.5 %"),
        K.metric_card("Episodes · usable windows", f"{len(ep)} · {q * 100:.0f} %" if q is not None else None,
                      accent=T.ACCENT, foot="episodes ≥ 2 s; usable = tremor quality VALID/LOW_CONFIDENCE"),
    ])


def figures(df):
    if df.empty:
        e = CH.empty("No analysis windows", 260)
        return e, e, e, e, CH.empty("—", 110)
    t = df["t"]
    on = (df["classification"] == "TREMOR").to_numpy()
    p = CH.lines(t, [("P(tremor)", df["tremor_probability"].astype(float), T.TREMOR),
                     ("window evidence", df["tremor_evidence"].astype(float), T.MUTED)],
                 title="Tremor probability (HMM posterior) and per-window evidence", y_title="0–1", uirev="tr-p")
    CH.shade_intervals(p, CH.intervals_from_mask(t, on), T.TREMOR, "published TREMOR")
    p.add_hline(y=0.8, line=dict(color=T.MUTED, dash="dot", width=1))
    det = df[df["tremor_evidence"].astype(float) >= 0.5]
    freq = CH.quality_scatter(det["t"], det["dominant_frequency"].astype(float), det["tremor_quality"].fillna("NONE"),
                              title="Peak frequency (detected windows)", y_title="Hz", unit="Hz", uirev="tr-f", connect=False,
                              custom=det["row"] if "row" in det else None)
    if not det.empty:
        freq.update_yaxes(range=[C.TREMOR_BAND_HZ[0] - 0.2, C.TREMOR_BAND_HZ[1] + 0.2])
    amp = CH.quality_scatter(det["t"], det["tremor_amplitude_dps"].astype(float), det["tremor_quality"].fillna("NONE"),
                             title="Tremor amplitude (detected windows)", y_title="°/s RMS", unit="°/s", uirev="tr-a",
                             connect=False)
    power = CH.lines(t, [("log₁₀(tremor power + 1)", np.log10(df["tremor_power"].astype(float).clip(lower=0) + 1), T.TREMOR),
                         ("arm movement (°/s RMS)", df["arm_movement_rms_dps"].astype(float), T.ACTIVITY)],
                     title="Tremor-band power vs purposeful arm movement", y_title="value", uirev="tr-pw")
    motion = CH.state_strip(t, df["motion_state"], T.MOTION, title="Motion context (REST / LOW MOTION = still windows)")
    return p, freq, amp, power, motion


def psd_figure(sess, row, snap=None):
    if sess is not None and row is not None:
        raw = SS.load_raw_window(sess, int(row))
        g = raw[["gx", "gy", "gz"]].to_numpy().T
        label = f"window ending at row {int(row)} of {sess.id}"
    elif snap is not None and len(snap["samples"]) >= C.WINDOW_SAMPLES:
        g = snap["samples"][-C.WINDOW_SAMPLES:, 5:8].T
        label = "latest live 4 s window"
    else:
        return CH.empty("No window selected", 240)
    f, P = gyro_spectrum(g, C.SAMPLE_RATE_HZ)
    S = P.sum(axis=0)
    m = f <= 15
    fig = CH.base(f"Gyro PSD (sum of axes) — {label}", 240, "frequency (Hz)", "(°/s)²/Hz", uirev=f"psd-{label}")
    fig.add_trace(go.Scatter(x=f[m], y=S[m], mode="lines", name="Σ axes", line=dict(color=T.TREMOR, width=1.6)))
    for k, name in enumerate(("gx", "gy", "gz")):
        fig.add_trace(go.Scatter(x=f[m], y=P[k][m], mode="lines", name=name, line=dict(width=1, color=list(T.AXES.values())[k]),
                                 opacity=0.6))
    fig.add_vrect(x0=C.TREMOR_BAND_HZ[0], x1=C.TREMOR_BAND_HZ[1], fillcolor=T.TREMOR, opacity=0.08, line_width=0,
                  annotation_text="tremor band", annotation_font=dict(color=T.MUTED, size=10))
    band = (f >= C.TREMOR_BAND_HZ[0]) & (f <= C.TREMOR_BAND_HZ[1])
    fpk = f[band][np.argmax(S[band])]
    fig.add_vrect(x0=fpk - TREMOR_PEAK_HALF_WIDTH_HZ, x1=fpk + TREMOR_PEAK_HALF_WIDTH_HZ, fillcolor=T.TREMOR,
                  opacity=0.12, line_width=0)
    fig.update_yaxes(type="log")
    return fig


def compare(values):
    if not values:
        return K.empty("Pick two or more sessions to compare.")
    rows, freqs = [], []
    for v in values:
        sess = SS.get_session(v)
        if sess is None:
            continue
        df = SS.load_analyses(sess)
        ts = tremor_summary(df)
        rows.append({"session": sess.id, "still_min": ts.get("still_minutes"), "tremor_time_%": ts.get("tremor_time_pct"),
                     "median_Hz": ts.get("tremor_frequency_hz_median"), "power_median": ts.get("tremor_power_median"),
                     "episodes": len(SS.episodes(df)), "usable_%": round(100 * (SS.session_quality_score(df) or 0), 1),
                     "note": ts.get("reason", "")})
        det = df[df["tremor_evidence"].astype(float) >= 0.5]
        freqs.append((sess.id, det["dominant_frequency"].astype(float)))
    fig = CH.base("Detected-window frequency by session", 260, None, "Hz", "tr-cmp", legend=False)
    for sid, fr in freqs:
        fig.add_trace(go.Box(y=fr, name=sid, marker_color=T.TREMOR, boxpoints=False))
    return [dash_table.DataTable(data=rows, columns=[{"name": k, "id": k} for k in (rows[0] if rows else {})], **TABLE_STYLE),
            dcc.Graph(figure=fig, config=CH.GRAPH_CONFIG)]


def register(app):
    @app.callback(Output("tr-summary", "children"), Output("tr-p", "figure"), Output("tr-freq", "figure"),
                  Output("tr-amp", "figure"), Output("tr-power", "figure"), Output("tr-motion", "figure"),
                  Output("tr-episodes", "children"),
                  Input("tr-session", "value"), Input("tr-reload", "n_clicks"))
    def _load(value, _):
        snap = DS.feed().snapshot()
        df, sess = load(value, snap)
        ep = SS.episodes(df)
        table = dash_table.DataTable(data=ep.to_dict("records"), columns=[{"name": c, "id": c} for c in ep.columns],
                                     **TABLE_STYLE) if len(ep) else K.empty("No tremor episodes ≥ 2 s in this data.")
        return (summary_cards(df, sess), *figures(df), table)

    @app.callback(Output("tr-psd", "figure"), Input("tr-freq", "clickData"), State("tr-session", "value"),
                  prevent_initial_call=True)
    def _psd(click, value):
        snap = DS.feed().snapshot()
        if value in (None, common.LIVE):
            return psd_figure(None, None, snap)
        sess = SS.get_session(value)
        row = None
        if click and click.get("points"):
            row = click["points"][0].get("customdata")
        return psd_figure(sess, row)

    @app.callback(Output("tr-compare-out", "children"), Input("tr-compare", "value"))
    def _cmp(values):
        return compare(values)
