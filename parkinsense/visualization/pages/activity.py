"""Activity: steps, cadence, walking segments, motion context, uncertain step periods."""

from __future__ import annotations

import numpy as np
from dash import Input, Output, dcc, html

from parkinsense.analytics.biomarkers import activity_summary
from parkinsense.visualization import charts as CH
from parkinsense.visualization import components as K
from parkinsense.visualization import datasource as DS
from parkinsense.visualization import theme as T
from parkinsense.visualization.pages import common
from parkinsense.visualization.pages.tremor import load


def layout():
    g = lambda i, h=260: html.Div(className="card", children=[  # noqa: E731
        dcc.Graph(id=i, config=CH.GRAPH_CONFIG, figure=CH.empty("Select a session", h))])
    return html.Div([
        html.Div(className="page-head", children=[
            html.Div([html.H1("Activity", className="page-title"),
                      html.Div("Wrist step counting (v1 detector). Steps counted outside confirmed walking are "
                               "flagged as uncertain — purposeful arm movement is a known false-positive source.",
                               className="page-sub")]),
            html.Div(className="row", children=[common.session_picker("ac-session"),
                                                html.Button("Reload", id="ac-reload", className="btn")]),
        ]),
        dcc.Loading(html.Div(id="ac-summary"), type="dot", color=T.ACCENT),
        g("ac-steps"),
        html.Div(className="grid g2", style={"marginTop": "14px"}, children=[g("ac-cadence"), g("ac-conf")]),
        html.Div(className="card", style={"marginTop": "14px"}, children=[
            dcc.Graph(id="ac-motion", config=CH.GRAPH_CONFIG, figure=CH.empty("—", 110))]),
    ])


def uncertain_steps(df):
    """Steps added in windows that were not part of a confirmed walking bout."""
    if df.empty or df["steps"].isna().all():
        return 0
    inc = df["steps"].astype(float).diff().fillna(0).clip(lower=0)
    return int(inc[df["walking_state"] != "WALKING"].sum())


def figures(df):
    if df.empty:
        e = CH.empty("No analysis windows", 260)
        return e, e, e, CH.empty("—", 110)
    t = df["t"]
    walking = (df["walking_state"] == "WALKING").to_numpy()
    steps = CH.lines(t, [("cumulative steps", df["steps"].astype(float), T.ACTIVITY)], title="Steps",
                     y_title="steps", uirev="ac-steps")
    CH.shade_intervals(steps, CH.intervals_from_mask(t, walking), T.ACTIVITY, "walking")
    inc = df["steps"].astype(float).diff().fillna(0).clip(lower=0)
    unc = (inc > 0) & (~walking)
    if unc.any():
        steps.add_scatter(x=t[unc], y=df["steps"][unc], mode="markers", name="counted outside walking (uncertain)",
                          marker=dict(color=T.HEART, size=6, symbol="x"))
    cad = CH.lines(t, [("cadence", np.where(walking, df["cadence"].astype(float), np.nan), T.ACTIVITY)],
                   title="Cadence while walking", y_title="steps/min", uirev="ac-cad")
    conf = CH.lines(t, [("walking confidence", df["walking_confidence"].astype(float), T.ACCENT),
                        ("step confidence", df["step_confidence"].astype(float), T.MUTED)],
                    title="Step-detection confidence (heuristic 0–1)", y_title="0–1", uirev="ac-conf")
    motion = CH.state_strip(t, df["motion_state"], T.MOTION, title="Motion context")
    return steps, cad, conf, motion


def summary(df):
    a = activity_summary(df) if not df.empty else {}
    return html.Div(className="grid g4", children=[
        K.metric_card("Steps", a.get("steps"), "", digits=0, accent=T.ACTIVITY, foot="end of data"),
        K.metric_card("Walking time", a.get("walking_minutes"), "min", accent=T.ACTIVITY),
        K.metric_card("Median cadence", a.get("cadence_median_spm"), "spm", digits=0, accent=T.ACTIVITY,
                      foot="while walking"),
        K.metric_card("Uncertain steps", uncertain_steps(df) if not df.empty else None, "", digits=0,
                      state="LOW_CONFIDENCE" if not df.empty and uncertain_steps(df) else None, accent=T.HEART,
                      foot="counted outside confirmed walking"),
    ])


def register(app):
    @app.callback(Output("ac-summary", "children"), Output("ac-steps", "figure"), Output("ac-cadence", "figure"),
                  Output("ac-conf", "figure"), Output("ac-motion", "figure"),
                  Input("ac-session", "value"), Input("ac-reload", "n_clicks"))
    def _load(value, _):
        df, _sess = load(value, DS.feed().snapshot())
        return (summary(df), *figures(df))
