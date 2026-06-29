"""
ParkinSense Dashboard V2.5

Designed to support the full platform roadmap without redesign:
  Phase 4  — IMU / tremor (current)
  Phase 5  — HR / SpO2 (MAX30102)
  Phase 6  — Bradykinesia
  Phase 7  — Steps / Calories / Sleep / Recovery
  Phase 8  — ML inference
"""

import json
import os

import dash_bootstrap_components as dbc
import pandas as pd
import plotly.graph_objects as go
from dash import Dash, Input, Output
from pathlib import Path

from dashboard.python.dashboard.layout import create_layout
from dashboard.python.dashboard.graphs import empty_graph

# ---------------------------------------------------------------------------
# Paths — resolved from file location so the dashboard runs from any cwd
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parents[3]

METRICS  = PROJECT_ROOT / "realtime_metrics_v2.json"
CSV_FILE = PROJECT_ROOT / "realtime_capture_v2.csv"

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = Dash(
    __name__,
    external_stylesheets=[dbc.themes.DARKLY]
)

app.title = "ParkinSense V2"

app.layout = create_layout()

# ---------------------------------------------------------------------------
# Callback
# ---------------------------------------------------------------------------

@app.callback(

    Output("status",     "children"),
    Output("score",      "children"),
    Output("confidence", "children"),
    Output("frequency",  "children"),
    Output("severity",   "children"),
    Output("motion",     "children"),
    Output("axis",       "children"),
    Output("packets",    "children"),
    Output("sampling",   "children"),
    Output("score_graph", "figure"),

    Input("timer", "n_intervals"),

)
def update(_):

    # --- Gyroscope graph (built first so we can return it on early exit) ---

    fig = empty_graph()

    if CSV_FILE.exists():
        try:
            df  = pd.read_csv(CSV_FILE).tail(300)
            fig = go.Figure()

            fig.add_trace(go.Scatter(y=df["gx"], mode="lines", name="GX", line=dict(width=2)))
            fig.add_trace(go.Scatter(y=df["gy"], mode="lines", name="GY", line=dict(width=2)))
            fig.add_trace(go.Scatter(y=df["gz"], mode="lines", name="GZ", line=dict(width=2)))

            fig.update_layout(
                template="plotly_dark",
                title="Live Gyroscope",
                height=400,
                margin=dict(l=20, r=20, t=40, b=20),
            )
        except Exception:
            fig = empty_graph()

    # --- Metrics ---

    if not METRICS.exists():
        return ("--", "--", "--", "--", "--", "--", "--", "--", "--", fig)

    try:
        with open(METRICS) as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return ("--", "--", "--", "--", "--", "--", "--", "--", "--", fig)

    # Status badge
    classification = data.get("classification", "")
    status = (
        "🟢 NO TREMOR"
        if classification == "NO TREMOR"
        else "🔴 TREMOR"
    )

    return (
        status,
        f"{data.get('tremor_score', 0)}/100",
        f"{data.get('confidence', 0):.1f}%",
        f"{data.get('dominant_frequency', 0):.2f} Hz",
        data.get("severity", "--"),
        data.get("motion_state", "--"),
        data.get("best_axis", "--"),
        f"{data.get('packet_count', '--')} Packets",
        f"{data.get('sampling_rate', 0):.1f} Hz",
        fig,
    )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    app.run(debug=True)
