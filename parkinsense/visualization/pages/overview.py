"""Overview: one-glance state of every implemented biomarker with its quality."""

from __future__ import annotations

from dash import Input, Output, dcc, html

from parkinsense.analytics.biomarkers import tremor_summary
from parkinsense.visualization import charts as CH
from parkinsense.visualization import components as K
from parkinsense.visualization import datasource as DS
from parkinsense.visualization import theme as T
from parkinsense.visualization.pages import common

TITLE = "Overview"


def layout():
    return html.Div([
        html.Div(className="page-head", children=[html.Div([
            html.H1("Overview", className="page-title"),
            html.Div("Current session at a glance. Every value carries its quality state.", className="page-sub")])]),
        html.Div(id="ov-banners"),
        html.Div(id="ov-status"),
        html.Div(className="row", style={"marginBottom": "6px"}, children=[
            html.Button("Start session", id="btn-session-start", className="btn"),
            html.Button("Stop session", id="btn-session-stop", className="btn btn-danger"),
            html.Span(id="ov-ctl-msg", className="muted small"),
        ]),
        html.Div(id="ov-cards"),
        K.section("Recent trends", html.Div(className="grid g2", children=[
            html.Div(className="card", children=[dcc.Graph(id="ov-hr", config=CH.GRAPH_CONFIG,
                                                           figure=CH.empty("Waiting for data", 200))]),
            html.Div(className="card", children=[dcc.Graph(id="ov-p", config=CH.GRAPH_CONFIG,
                                                           figure=CH.empty("Waiting for data", 200))]),
        ])),
        K.section("Quality states", html.Div(K.quality_legend(), className="card")),
        dcc.Interval(id="ov-tick", interval=1000),
    ])


def _num(m, k):
    v = m.get(k)
    return None if v is None or v == "" else v


def body(snap):
    m = snap["latest"] or {}
    stale = snap["stale"]
    hr_q = m.get("hr_quality_state")
    t_q = m.get("tremor_quality")
    df = common.analyses_frame(snap)

    # provisional tremor time over the live buffer (same definition as analytics.tremor_summary)
    burden = None
    burden_q = "INSUFFICIENT_DATA"
    burden_foot = "needs ≥ 2 min of still, valid windows"
    if not df.empty:
        ts = tremor_summary(df, min_valid_minutes=2.0)
        if ts.get("tremor_time_pct") is not None:
            burden, burden_q = ts["tremor_time_pct"], "VALID"
            burden_foot = f"provisional · {ts['still_minutes']:.1f} min still data (last ≤ 10 min)"
        else:
            burden_foot = f"{ts.get('still_minutes', 0):.1f} min still data — needs ≥ 2 min"

    trem_state = m.get("tremor_state")
    trem_text = {"CONFIRMED_TREMOR": "Tremor", "RECOVERY": "Tremor (fading)", "POSSIBLE_TREMOR": "Possible",
                 "NO_TREMOR": "None"}.get(trem_state, None)
    p = m.get("tremor_probability")
    ppg_rate = m.get("ppg_effective_rate_hz")
    hr_foot = "motion-coupled" if m.get("motion_coupled_hr") else (f"PPG {ppg_rate:.0f} Hz" if ppg_rate else None)
    cards_trem = [
        K.metric_card("Tremor status", trem_text, state=t_q, stale=stale, accent=T.TREMOR,
                      foot=[html.Span(f"P(tremor) {p:.2f}" if p is not None else "P(tremor) —"),
                            html.Span(m.get("tremor_type") if m.get("tremor_type") not in (None, "NONE") else "")]),
        K.metric_card("Tremor frequency", _num(m, "dominant_frequency") if m.get("classification") == "TREMOR" else None,
                      "Hz", state=t_q if m.get("classification") == "TREMOR" else None, stale=stale, digits=2,
                      accent=T.TREMOR, foot="peak of summed gyro PSD, 3.5–7.5 Hz"),
        K.metric_card("Tremor amplitude", _num(m, "tremor_amplitude_dps") if m.get("classification") == "TREMOR" else None,
                      "°/s RMS", state=t_q if m.get("classification") == "TREMOR" else None, stale=stale, digits=1,
                      accent=T.TREMOR, foot="gyro power within ±0.625 Hz of the peak"),
        K.metric_card("Tremor time", burden, "%", state=burden_q, accent=T.TREMOR, foot=burden_foot),
    ]
    cards_cardio = [
        K.metric_card("Heart rate", _num(m, "heart_rate"), "bpm", state=hr_q, stale=stale, accent=T.HEART, foot=hr_foot),
        K.metric_card("HRV · RMSSD", _num(m, "rmssd"), "ms", state=hr_q if m.get("rmssd") is not None else
                      ("INSUFFICIENT_DATA" if m else None), stale=stale, accent=T.HEART,
                      foot="10 s window; trend use only"),
        K.metric_card("SpO₂", _num(m, "spo2"), "%", state=None, stale=stale, always_badge="ESTIMATE",
                      accent=T.HEART, foot="research estimate — not a clinical measurement"),
        K.metric_card("Contact · signal", "Finger on" if m.get("finger_detected") else ("No finger" if m else None),
                      state=None if m.get("finger_detected") else ("NO_CONTACT" if m else None), stale=stale,
                      accent=T.HEART, foot=f"SQI {m['signal_quality']:.0f}/100 · {m.get('sensor_status')}"
                      if m.get("signal_quality") is not None else None),
    ]
    cards_act = [
        K.metric_card("Steps", _num(m, "steps"), "", stale=stale, digits=0, accent=T.ACTIVITY,
                      foot="session total"),
        K.metric_card("Cadence", _num(m, "cadence") if m.get("walking_state") == "WALKING" else None, "spm",
                      stale=stale, digits=0, accent=T.ACTIVITY, foot=m.get("walking_state", "").replace("_", " ").lower() or None),
        K.metric_card("Motion context", m.get("motion_state"), stale=stale, accent=T.ACTIVITY,
                      foot=f"arm movement {m['arm_movement_rms_dps']:.1f} °/s RMS" if m.get("arm_movement_rms_dps") is not None else None),
        K.metric_card("Data quality", (m.get("rate_status") or None), state=None, stale=stale, accent=T.ACCENT,
                      foot=[K.badge(t_q, f"tremor: {t_q}") if t_q else None, K.badge(hr_q, f"hr: {hr_q}") if hr_q else None]),
    ]

    cards = [
        K.section("Tremor", html.Div(cards_trem, className="grid g4")),
        K.section("Cardiovascular", html.Div(cards_cardio, className="grid g4")),
        K.section("Activity & data", html.Div(cards_act, className="grid g4")),
        K.section("Signal details (latest window)", details(m)),
    ]
    return common.banners(snap), common.status_bar(snap), cards, \
        _spark(df, "heart_rate", "hr_quality_state", "Heart rate (last 10 min)", "bpm"), _spark_p(df)


def details(m):
    """Secondary per-window values (kept from the 2.x dashboard), as a compact table."""
    def f(k, d=2):
        if m.get(k) is None:
            return None
        v = round(float(m[k]), d)
        return int(v) if d == 0 else v
    left = [("tremor score (window evidence × 100)", f("tremor_score", 0)), ("tremor SNR (dB)", f("tremor_snr_db", 1)),
            ("rest index", f("rest_index")), ("band ratio", f("band_ratio", 3)),
            ("best axis · axis agreement", f"{m['best_axis']} · {m.get('axis_agreement')}" if m.get("best_axis") else None)]
    right = [("distance (stride estimate)", None if m.get("distance_m") is None else f"{m['distance_m'] / 1000:.2f} km"),
             ("active minutes", f("active_minutes", 1)), ("activity type", m.get("activity_type")),
             ("pNN50 · SDNN", f"{m['pnn50']} % · {m.get('sdnn')} ms" if m.get("pnn50") is not None else None),
             ("packets · samples", f"{m.get('packet_count')} · {m.get('sample_count')}" if m.get("packet_count") else None)]
    return html.Div([html.Div(K.kv(left), className="card"), html.Div(K.kv(right), className="card")],
                    className="grid g2")


def _spark(df, col, qcol, title, unit):
    if df.empty or col not in df or df[col].isna().all():
        return CH.empty("No values yet", 200, title)
    return CH.quality_scatter(df["t"], df[col].astype(float), df[qcol].fillna("NONE"), title=title,
                              y_title=unit, height=200, unit=unit, uirev="ov-hr")


def _spark_p(df):
    title = "P(tremor) (last 10 min)"
    if df.empty or "tremor_probability" not in df:
        return CH.empty("No analyses yet", 200, title)
    fig = CH.lines(df["t"], [("P(tremor)", df["tremor_probability"].astype(float), T.TREMOR)],
                   title=title, y_title="probability", height=200, uirev="ov-p")
    fig.add_hline(y=0.8, line=dict(color=T.MUTED, dash="dot", width=1), annotation_text="confirm 0.8",
                  annotation_font=dict(color=T.MUTED, size=10))
    fig.update_yaxes(range=[0, 1.02])
    return fig


def register(app):
    @app.callback(Output("ov-banners", "children"), Output("ov-status", "children"), Output("ov-cards", "children"),
                  Output("ov-hr", "figure"), Output("ov-p", "figure"),
                  Output("btn-session-start", "disabled"), Output("btn-session-stop", "disabled"),
                  Input("ov-tick", "n_intervals"))
    def _update(_):
        snap = DS.feed().snapshot()
        rec = bool(snap["meta"].get("recording"))
        return (*body(snap), (not snap["online"]) or rec, (not snap["online"]) or not rec)

    @app.callback(Output("ov-ctl-msg", "children"), Input("btn-session-start", "n_clicks"),
                  Input("btn-session-stop", "n_clicks"), prevent_initial_call=True)
    def _control(start, stop):
        from dash import ctx
        path = "/session/start" if ctx.triggered_id == "btn-session-start" else "/session/stop"
        r = DS.feed().post(path)
        return "Requested." if r.get("ok") else f"Not possible: {r.get('reason')}"
