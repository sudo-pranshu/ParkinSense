"""Live monitoring: raw IMU/PPG waveforms, live tremor/HR outputs, acquisition health."""

from __future__ import annotations

import numpy as np
from dash import Input, Output, dcc, html

from parkinsense.visualization import charts as CH
from parkinsense.visualization import components as K
from parkinsense.visualization import datasource as DS
from parkinsense.visualization import theme as T
from parkinsense.visualization.pages import common

WAVE_SECONDS = 10
TREND_SECONDS = 120


def layout():
    g = lambda i, h=240: html.Div(className="card", children=[  # noqa: E731
        dcc.Graph(id=i, config=CH.GRAPH_CONFIG, figure=CH.empty("Waiting for data", h))])
    return html.Div([
        html.Div(className="page-head", children=[html.Div([
            html.H1("Live monitoring", className="page-title"),
            html.Div(f"Raw signals (last {WAVE_SECONDS} s) and live analysis outputs (last {TREND_SECONDS // 60} min). "
                     "Time axis = device signal time.", className="page-sub")])]),
        html.Div(id="lv-banners"),
        html.Div(id="lv-status"),
        html.Div(className="grid g2", children=[g("lv-acc"), g("lv-gyro")]),
        html.Div(className="grid g2", style={"marginTop": "14px"}, children=[g("lv-ppg"), g("lv-trem")]),
        html.Div(className="grid g2", style={"marginTop": "14px"}, children=[g("lv-hr"), g("lv-rate")]),
        html.Div(className="card", style={"marginTop": "14px"}, children=[
            dcc.Graph(id="lv-motion", config=CH.GRAPH_CONFIG, figure=CH.empty("Waiting for data", 110))]),
        dcc.Interval(id="lv-tick", interval=500),
    ])


def _detrend(x, fs=104.0, win_s=0.75):
    """Display-only baseline removal for the PPG trace (moving mean)."""
    n = max(3, int(win_s * fs))
    if len(x) < n:
        return x - np.mean(x) if len(x) else x
    pad = np.pad(np.asarray(x, float), (n // 2, n - 1 - n // 2), mode="edge")
    base = np.convolve(pad, np.ones(n) / n, mode="valid")
    return x - base


def figures(snap):
    s = snap["samples"]
    df = common.analyses_frame(snap)
    if len(s):
        s = s[s[:, 1] >= s[-1, 1] - WAVE_SECONDS]
        t = s[:, 1]
        acc = CH.lines(t, [("ax", s[:, 2], T.AXES["x"]), ("ay", s[:, 3], T.AXES["y"]), ("az", s[:, 4], T.AXES["z"])],
                       title="Accelerometer", y_title="g", uirev="lv-acc")
        gyr = CH.lines(t, [("gx", s[:, 5], T.AXES["x"]), ("gy", s[:, 6], T.AXES["y"]), ("gz", s[:, 7], T.AXES["z"])],
                       title="Gyroscope", y_title="°/s", uirev="lv-gyro")
        ir = s[:, 8]
        if np.nanmax(ir) < 5000:
            ppg = CH.empty("No PPG contact (IR below finger level)", 240, "PPG (IR)")
        else:
            ppg = CH.lines(t, [("IR (baseline removed)", _detrend(ir), T.HEART)], title="PPG waveform (IR)",
                           y_title="ADC counts (detrended for display)", uirev="lv-ppg")
    else:
        acc = CH.empty("No samples received", 240, "Accelerometer")
        gyr = CH.empty("No samples received", 240, "Gyroscope")
        ppg = CH.empty("No samples received", 240, "PPG (IR)")

    if not df.empty:
        d = df[df["t"] >= df["t"].iloc[-1] - TREND_SECONDS]
        trem = CH.base("Tremor: frequency (detected windows) and P(tremor)", 240, "time (s)", "Hz", "lv-trem")
        det = d[(d["tremor_evidence"].astype(float) >= 0.5)]
        trem.add_scatter(x=det["t"], y=det["dominant_frequency"], mode="markers", name="peak frequency",
                         marker=dict(color=T.TREMOR, size=6))
        trem.add_scatter(x=d["t"], y=d["tremor_probability"], mode="lines", name="P(tremor)", yaxis="y2",
                         line=dict(color=T.MUTED, width=1.4))
        trem.update_layout(yaxis=dict(range=[3, 8]),
                           yaxis2=dict(overlaying="y", side="right", range=[0, 1.02], tickvals=[0, 0.5, 1],
                                       title="P(tremor)", showgrid=False, tickfont=dict(color=T.MUTED, size=11)))
        hr = CH.quality_scatter(d["t"], d["heart_rate"].astype(float), d["hr_quality_state"].fillna("NONE"),
                                title="Heart rate", y_title="bpm", unit="bpm", uirev="lv-hr") \
            if d["heart_rate"].notna().any() else CH.empty("No heart rate yet (contact / signal quality)", 240, "Heart rate")
        rate = CH.lines(d["t"], [("measured device rate", d["device_rate_hz"].astype(float), T.ACCENT)],
                        title="Measured sample rate", y_title="Hz", uirev="lv-rate") \
            if d["device_rate_hz"].notna().any() else CH.empty("Rate not measured yet", 240, "Measured sample rate")
        if d["device_rate_hz"].notna().any():
            for y, lab in ((104 * 0.98, "−2 %"), (104 * 1.02, "+2 %")):
                rate.add_hline(y=y, line=dict(color=T.MUTED, dash="dot", width=1), annotation_text=lab,
                               annotation_font=dict(color=T.MUTED, size=10))
        motion = CH.state_strip(d["t"], d["motion_state"], T.MOTION, title="Motion context")
    else:
        trem = CH.empty("No analyses yet (first after 4 s of data)", 240, "Tremor")
        hr = CH.empty("No analyses yet", 240, "Heart rate")
        rate = CH.empty("No analyses yet", 240, "Measured sample rate")
        motion = CH.empty("No analyses yet", 110, "Motion context")
    return acc, gyr, ppg, trem, hr, rate, motion


def register(app):
    @app.callback(Output("lv-banners", "children"), Output("lv-status", "children"),
                  Output("lv-acc", "figure"), Output("lv-gyro", "figure"), Output("lv-ppg", "figure"),
                  Output("lv-trem", "figure"), Output("lv-hr", "figure"), Output("lv-rate", "figure"),
                  Output("lv-motion", "figure"), Input("lv-tick", "n_intervals"))
    def _update(_):
        snap = DS.feed().snapshot(seconds=WAVE_SECONDS)
        status = common.status_bar(snap)
        if snap["stale"] and snap["online"]:
            status = [status, html.Div(f"No new data for {K.age_text(snap['data_age_s'])} — waveforms are frozen, "
                                       "not live.", className="banner banner-warn")]
        return (common.banners(snap), status, *figures(snap))
