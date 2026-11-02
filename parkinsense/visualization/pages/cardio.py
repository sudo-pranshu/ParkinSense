"""Cardiovascular: HR / HRV / SQI / contact / motion-artefact periods / SpO2 estimate."""

from __future__ import annotations

from dash import Input, Output, dcc, html

from parkinsense.analytics.biomarkers import heart_summary
from parkinsense.visualization import charts as CH
from parkinsense.visualization import components as K
from parkinsense.visualization import datasource as DS
from parkinsense.visualization import theme as T
from parkinsense.visualization.quality import CHART_COLORS
from parkinsense.visualization.pages import common
from parkinsense.visualization.pages.tremor import load


def layout():
    g = lambda i, h=260: html.Div(className="card", children=[  # noqa: E731
        dcc.Graph(id=i, config=CH.GRAPH_CONFIG, figure=CH.empty("Select a session", h))])
    return html.Div([
        html.Div(className="page-head", children=[
            html.Div([html.H1("Cardiovascular", className="page-title"),
                      html.Div("Finger-PPG heart rate and short-term HRV. Values outside VALID are shown hollow and "
                               "are not measurements.", className="page-sub")]),
            html.Div(className="row", children=[common.session_picker("cv-session"),
                                                html.Button("Reload", id="cv-reload", className="btn")]),
        ]),
        html.Div("SpO₂ shown here is an uncalibrated research estimate (generic ratio-of-ratios curve, no reference "
                 "oximeter validation). It must not be read as a clinical measurement.", className="banner banner-sim"),
        dcc.Loading(html.Div(id="cv-summary"), type="dot", color=T.ACCENT),
        g("cv-hr"),
        html.Div(className="grid g2", style={"marginTop": "14px"}, children=[g("cv-hrv"), g("cv-sqi")]),
        html.Div(className="grid g2", style={"marginTop": "14px"}, children=[g("cv-spo2"), html.Div(className="card", children=[
            html.Div("Inter-beat intervals", className="metric-title"),
            K.empty("Individual RR intervals are computed inside each 10 s analysis but are not part of capture "
                    "schema v3, so they cannot be shown for recorded sessions. HRV summaries (RMSSD, SDNN, pNN50) "
                    "are recorded and plotted."),
        ])]),
    ])


def figures(df):
    if df.empty:
        e = CH.empty("No analysis windows", 260)
        return e, e, e, e
    t = df["t"]
    hr = CH.quality_scatter(t, df["heart_rate"].astype(float), df["hr_quality_state"].fillna("NONE"),
                            title="Heart rate (coloured by quality state)", y_title="bpm", unit="bpm", uirev="cv-hr")
    CH.shade_intervals(hr, CH.intervals_from_mask(t, df["hr_quality_state"] == "MOTION_ARTIFACT"),
                       CHART_COLORS["MOTION_ARTIFACT"], "motion-artefact period", opacity=0.10)
    CH.shade_intervals(hr, CH.intervals_from_mask(t, ~df["finger_detected"].astype(bool)), T.MUTED,
                       "no-contact period", opacity=0.10)
    if df["rmssd"].notna().any():
        hrv = CH.lines(t, [("RMSSD", df["rmssd"].astype(float), T.HEART), ("SDNN", df["sdnn"].astype(float), T.ACCENT)],
                       title="HRV (10 s windows — trend use only)", y_title="ms", uirev="cv-hrv")
    else:
        rate = df["ppg_effective_rate_hz"].dropna()
        why = (f"PPG effective rate {rate.median():.0f} Hz < 25 Hz (firmware ≤ v4): HRV withheld"
               if len(rate) and rate.median() < 25 else "No HRV values (contact / signal quality)")
        hrv = CH.empty(why, 260, "HRV")
    sqi = CH.lines(t, [("SQI", df["signal_quality"].astype(float), T.ACCENT),
                       ("HR confidence ×100", 100 * df["hr_confidence"].astype(float), T.MUTED)],
                   title="PPG signal quality", y_title="0–100", uirev="cv-sqi")
    spo2 = CH.lines(t, [("SpO₂ estimate", df["spo2"].astype(float), "#c9b3ff")],
                    title="SpO₂ — uncalibrated research estimate", y_title="%", uirev="cv-spo2") \
        if df["spo2"].notna().any() else CH.empty("No SpO₂ estimate", 260, "SpO₂ — uncalibrated estimate")
    return hr, hrv, sqi, spo2


def summary(df, sess):
    hs = heart_summary(df) if not df.empty else {}
    q = df["hr_quality_state"].value_counts(normalize=True) if not df.empty else {}
    pct = lambda k: round(100 * float(q.get(k, 0)), 1) if len(q) else None  # noqa: E731
    return html.Div(className="grid g4", children=[
        K.metric_card("Median HR (VALID)", hs.get("hr_median"), "bpm", accent=T.HEART,
                      state="VALID" if hs.get("hr_median") is not None else "INSUFFICIENT_DATA",
                      foot=hs.get("reason") or f"{hs.get('valid_minutes', 0)} valid min"),
        K.metric_card("Median RMSSD", hs.get("rmssd_median"), "ms", accent=T.HEART, foot="from VALID windows"),
        K.metric_card("VALID coverage", pct("VALID"), "%", accent=T.ACCENT, foot="share of analysis windows"),
        K.metric_card("Motion artefact", pct("MOTION_ARTIFACT"), "%", accent=T.ACTIVITY,
                      foot=f"no contact {pct('NO_CONTACT')} %" if len(q) else None),
    ])


def register(app):
    @app.callback(Output("cv-summary", "children"), Output("cv-hr", "figure"), Output("cv-hrv", "figure"),
                  Output("cv-sqi", "figure"), Output("cv-spo2", "figure"),
                  Input("cv-session", "value"), Input("cv-reload", "n_clicks"))
    def _load(value, _):
        df, sess = load(value, DS.feed().snapshot())
        if not df.empty and "finger_detected" in df:
            df = df.assign(finger_detected=df["finger_detected"].astype(str).str.lower().isin(["true", "1"]))
        return (summary(df, sess), *figures(df))
