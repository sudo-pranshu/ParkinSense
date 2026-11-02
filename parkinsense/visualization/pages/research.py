"""Data & research: replay, dataset generation, configuration, benchmark results."""

from __future__ import annotations

import json
import time
from pathlib import Path

from dash import Input, Output, State, dash_table, dcc, html

from parkinsense import config as C
from parkinsense.visualization import components as K
from parkinsense.visualization import jobs as J
from parkinsense.visualization import sessions as SS
from parkinsense.visualization.pages import common
from parkinsense.visualization.pages.tremor import TABLE_STYLE

BENCH_DIR = Path("benchmarks/results")


def layout():
    return html.Div([
        html.Div(className="page-head", children=[html.Div([
            html.H1("Data & research", className="page-title"),
            html.Div("Deterministic replay and dataset generation run the project's CLI tools in a separate process; "
                     "outputs go to new folders and originals are never modified.", className="page-sub")])]),
        html.Div(className="grid g2", children=[
            html.Div(className="card", children=[
                html.Div("Replay a session (offline, deterministic)", className="metric-title"),
                html.Div(style={"height": "8px"}),
                common.session_picker("rs-replay-src", value=None),
                html.Div(className="row", style={"marginTop": "10px"}, children=[
                    html.Button("Run replay", id="rs-replay-go", className="btn btn-primary"),
                    html.Span("→ replays/<session>_<time>/ (appears under Sessions)", className="muted small")]),
            ]),
            html.Div(className="card", children=[
                html.Div("Generate a dataset (one row per analysis window)", className="metric-title"),
                html.Div(style={"height": "8px"}),
                common.session_picker("rs-ds-src", multi=True),
                html.Div(className="row", style={"marginTop": "10px"}, children=[
                    dcc.Input(id="rs-ds-version", type="text", placeholder="version, e.g. 0.1.0", debounce=True),
                    html.Button("Build dataset", id="rs-ds-go", className="btn btn-primary"),
                    html.Span("→ datasets/<version>/", className="muted small")]),
            ]),
        ]),
        K.section("Jobs", html.Div(className="card", children=[html.Div(id="rs-jobs"), html.Div(id="rs-msg", className="muted small")])),
        K.section("Pipeline configuration (read-only)", html.Div(className="card", children=config_view())),
        K.section("Benchmark results (synthetic ground truth)", html.Div(className="card", children=bench_view())),
        dcc.Interval(id="rs-tick", interval=1500),
    ])


def config_view():
    pairs = [("pipeline", C.PIPELINE_VERSION), ("capture schema", C.CAPTURE_SCHEMA_VERSION),
             ("tremor algorithm", C.TREMOR_ALGORITHM_VERSION), ("step counter (config value)", C.STEP_COUNTER_VERSION),
             ("PPG", C.PPG_VERSION), ("nominal rate", f"{C.SAMPLE_RATE_HZ} Hz"),
             ("window / hop", f"{C.WINDOW_SAMPLES} / {C.ANALYSIS_HOP_SAMPLES} samples"),
             ("tremor band", f"{C.TREMOR_BAND_HZ[0]}–{C.TREMOR_BAND_HZ[1]} Hz"),
             ("arm-movement band", f"{C.ARM_MOVEMENT_BAND_HZ[0]}–{C.ARM_MOVEMENT_BAND_HZ[1]} Hz"),
             ("PPG window", f"{C.PPG_WINDOW_SECONDS} s"),
             ("rate warn / invalid", f"{C.RATE_WARN_FRACTION:.0%} / {C.RATE_INVALID_FRACTION:.0%}"),
             ("gap reset", f"> {C.MAX_GAP_BEFORE_RESET_S} s")]
    return [K.kv(pairs), html.Div("Configuration is fixed per pipeline version so recordings stay interpretable. "
                                  "Changing it is a code change with a version bump and an ADR "
                                  "(docs/development/CONTRIBUTING.md). The step-counter value is a known provenance "
                                  "bug (default algorithm is v1.1; see docs/audit/DOCUMENTATION_AUDIT_REPORT.md).",
                                  className="muted small", style={"marginTop": "10px"})]


def bench_view():
    files = {"baseline 2.2.0": BENCH_DIR / "baseline_legacy.json", "current 3.0.0": BENCH_DIR / "current.json"}
    data = {k: json.loads(p.read_text()) for k, p in files.items() if p.exists()}
    if not data:
        return K.empty("No benchmark results found in benchmarks/results/.")

    def g(d, *path):
        for p in path:
            d = (d or {}).get(p)
        return None if d is None else (round(d, 3) if isinstance(d, float) else d)
    metrics = [("tremor sensitivity", ("tremor", "analysis_level", "sensitivity")),
               ("tremor specificity", ("tremor", "analysis_level", "specificity")),
               ("tremor frequency error, median (Hz)", ("tremor", "frequency_abs_error_hz", "median")),
               ("onset latency, median (s)", ("latency", "onset_latency_s_median")),
               ("rest HR MAE, v2 path (bpm)", ("ppg_v2_path", "rest_hr_mae_bpm")),
               ("RMSSD MAE, v2 path (ms)", ("ppg_v2_path", "rest_rmssd_mae_ms")),
               ("walking count error (%)", ("steps", "walking_count_error_pct", "mean")),
               ("false steps/min, rest tremor", ("steps", "false_steps_per_minute", "rest_tremor"))]
    rows = [{"metric": name, **{k: g(d, *path) for k, d in data.items()}} for name, path in metrics]
    return [dash_table.DataTable(data=rows, columns=[{"name": c, "id": c} for c in rows[0]], **TABLE_STYLE),
            html.Div("Synthetic signals only — not clinical accuracy. See docs/validation/RESULTS.md.",
                     className="muted small", style={"marginTop": "8px"})]


def jobs_view():
    js = J.all_jobs()
    if not js:
        return K.empty("No jobs started in this dashboard session.")
    out = []
    for j in js[:6]:
        kind = {"RUNNING": "warn", "DONE": "live", "FAILED": "bad"}[j.status]
        out.append(html.Div(style={"marginBottom": "10px"}, children=[
            html.Div(className="row", children=[K.pill(j.status, kind), html.Span(f"{j.kind} · {j.id} · "
                     f"{time.strftime('%H:%M:%S', time.localtime(j.started))}", className="small muted")]),
            html.Pre("\n".join(list(j.log)[-12:]) or "(no output yet)", className="log")]))
    return out


def register(app):
    @app.callback(Output("rs-msg", "children"), Input("rs-replay-go", "n_clicks"), Input("rs-ds-go", "n_clicks"),
                  State("rs-replay-src", "value"), State("rs-ds-src", "value"), State("rs-ds-version", "value"),
                  prevent_initial_call=True)
    def _start(a, b, src, ds_src, version):
        from dash import ctx
        stamp = time.strftime("%Y%m%d_%H%M%S")
        if ctx.triggered_id == "rs-replay-go":
            sess = SS.get_session(src) if src and src != common.LIVE else None
            if sess is None:
                return "Choose a recorded session to replay."
            j = J.replay(str(sess.capture), str(SS.REPLAYS / f"{sess.id}_{stamp}"))
            return f"Replay job {j.id} started."
        sessions = [SS.get_session(v) for v in (ds_src or []) if v != common.LIVE]
        sessions = [s for s in sessions if s is not None]
        if not sessions:
            return "Choose one or more recorded sessions."
        if not version:
            return "Enter a dataset version."
        out = Path("datasets") / version.strip()
        if out.exists():
            return f"{out} already exists — choose a new version (datasets are never overwritten)."
        j = J.dataset([str(s.capture) for s in sessions], str(out), version.strip())
        return f"Dataset job {j.id} started."

    @app.callback(Output("rs-jobs", "children"), Input("rs-tick", "n_intervals"))
    def _jobs(_):
        return jobs_view()
