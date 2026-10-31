"""
Live Plotly Dash dashboard (http://127.0.0.1:8050).

    python -m parkinsense.visualization.dashboard

Reads the runtime's atomic metrics JSON and the *tail* of the current
session's capture (located through recordings/latest.json or the metrics'
`capture_path`). v2 re-read the entire capture CSV every 100 ms, which grows
by ~100 rows/s and made the dashboard unusable within about an hour.

Quality: every biomarker card shows its quality state; values whose state is
not VALID are shown greyed with the reason instead of as a plain number.
"""

import io
import json
import os

import pandas as pd
import plotly.graph_objects as go

from dash import Dash
from dash import dcc
from dash import html
from dash.dependencies import Input
from dash.dependencies import Output

METRICS_FILE = os.environ.get("PARKINSENSE_METRICS", "realtime_metrics_v2.json")
LATEST_POINTER = os.environ.get("PARKINSENSE_LATEST", "recordings/latest.json")
LEGACY_CSV_FILE = "realtime_capture_v2.csv"
TAIL_BYTES = 2_500_000          # ~70 s of v3 rows; bounded read regardless of file size
_last_good_metrics: dict = {}


def capture_path(metrics):
    p = metrics.get("capture_path")
    if p and os.path.exists(p):
        return p
    try:
        with open(LATEST_POINTER) as f:
            return json.load(f)["capture"]
    except (OSError, ValueError, KeyError):
        return LEGACY_CSV_FILE if os.path.exists(LEGACY_CSV_FILE) else None


def read_tail(path, nbytes=TAIL_BYTES):
    """Header + last `nbytes` of a growing CSV, without reading the whole file."""
    with open(path, "rb") as f:
        header = f.readline()
        size = os.fstat(f.fileno()).st_size
        start = max(len(header), size - nbytes)
        f.seek(start)
        chunk = f.read()
    if start > len(header):
        chunk = chunk.split(b"\n", 1)[-1]         # drop the partial first line
    lines = chunk.rsplit(b"\n", 1)[0] if not chunk.endswith(b"\n") else chunk
    return pd.read_csv(io.BytesIO(header + lines), low_memory=False)


def quality_value(value, state, unit=""):
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return f"-- ({state or 'NO DATA'})"
    if state and state != "VALID":
        return f"{value}{unit} ({state})"
    return f"{value}{unit}"

# How much recent history the trend graphs (gyro, vitals, cadence) show.
# Windowed by actual elapsed time (via the sample_timestamp_us column)
# rather than a fixed row count, so the window stays "last N seconds"
# regardless of the device's actual streaming rate.
HISTORY_SECONDS = 60

app = Dash(__name__)

app.layout = html.Div(
    style={
        "backgroundColor": "#111111",
        "color": "white",
        "padding": "20px",
        "fontFamily": "Arial"
    },
    children=[
        html.H1(
            "ParkinSense Dashboard",
            style={"textAlign": "center"}
        ),
        html.Div(
            id="metric-cards"
        ),
        dcc.Graph(
            id="gyro-graph"
        ),
        dcc.Graph(
            id="score-graph"
        ),
        dcc.Graph(
            id="vitals-graph"
        ),
        dcc.Graph(
            id="cadence-graph"
        ),
        dcc.Interval(
            id="interval",
            interval=100,
            n_intervals=0
        )
    ]
)

@app.callback(
    [
        Output("metric-cards", "children"),
        Output("gyro-graph", "figure"),
        Output("score-graph", "figure"),
        Output("vitals-graph", "figure"),
        Output("cadence-graph", "figure")
    ],
    [
        Input("interval", "n_intervals")
    ]
)
def update_dashboard(_):

    global _last_good_metrics
    metrics = _last_good_metrics
    try:
        with open(METRICS_FILE, "r") as f:
            metrics = json.load(f)
        _last_good_metrics = metrics
    except FileNotFoundError:
        metrics = {}
    except (OSError, json.JSONDecodeError):
        pass                      # keep the previous frame rather than blanking (review P2-10)

    # ----------------------------------------------------------------
    # Cards, grouped into three sections for readability. Grouping is
    # purely presentational -- it doesn't change what's in metrics.json,
    # it just organizes the same fields so related metrics sit together
    # (Parkinson's signal, activity, vitals) instead of one long strip.
    # ----------------------------------------------------------------

    parkinsons_cards = [
        create_card(
            "Status",
            metrics.get("classification", "WAITING")
        ),
        create_card(
            "Tremor Score",
            metrics.get("tremor_score", 0)
        ),
        create_card(
            "Frequency",
            f"{metrics.get('dominant_frequency',0)} Hz"
        ),
        create_card(
            "Amplitude",
            f"{metrics.get('tremor_amplitude_dps', 0)} °/s"
        ),
        create_card(
            "Tremor State",
            metrics.get("tremor_state", "-")
        ),
        create_card(
            "P(tremor)",
            f"{100 * (metrics.get('tremor_probability') or 0):.0f}%"
        ),
        create_card(
            "Data Quality",
            f"{metrics.get('tremor_quality', '-')} / rate {metrics.get('rate_status', '-')}"
        ),
        create_card(
            "Motion",
            metrics.get("motion_state", "-")
        ),
        create_card(
            "Rest Index",
            f"{metrics.get('rest_index',0):.2f}"
        ),
        create_card(
            "Best Axis",
            metrics.get("best_axis", "-")
        ),
        create_card(
            "Band Ratio",
            f"{metrics.get('band_ratio',0)}"
        )
    ]

    activity_cards = [
        create_card(
            "Steps",
            metrics.get("steps", 0)
        ),
        create_card(
            "Cadence",
            f"{metrics.get('cadence',0)} spm"
        ),
        create_card(
            "Distance",
            f"{metrics.get('distance_m',0) / 1000.0:.2f} km"
        ),
        # walking_state is the canonical field written by the runtime
        # (and the same one used in the CSV) -- the dashboard mirrors
        # it here rather than keeping a second "walking" boolean in
        # sync, so there's exactly one source of truth for this value.
        create_card(
            "Walking",
            "YES" if metrics.get("walking_state", "IDLE") == "WALKING" else "NO"
        ),
        create_card(
            "Active Minutes",
            metrics.get("active_minutes", 0)
        )
    ]

    vitals_cards = [
        create_card(
            "Heart Rate",
            quality_value(metrics.get("heart_rate"), metrics.get("hr_quality_state"), " BPM")
        ),
        create_card(
            "SpO₂",
            quality_value(metrics.get("spo2"), "UNCALIBRATED ESTIMATE", " %")
        ),
        create_card(
            "Finger",
            "YES" if metrics.get("finger_detected", False) else "NO"
        )
    ]

    cards = [
        create_section("Parkinson's", parkinsons_cards),
        create_section("Activity", activity_cards),
        create_section("Vitals", vitals_cards)
    ]

    gyro_fig = go.Figure()
    score_fig = go.Figure()
    vitals_fig = go.Figure()
    cadence_fig = go.Figure()

    cap = capture_path(metrics)
    if cap and os.path.exists(cap):
        try:
            df_full = read_tail(cap)

            # Restrict trend graphs to the last HISTORY_SECONDS of actual
            # elapsed time (using the on-device sample timestamp), rather
            # than a fixed row count -- a fixed row count would represent
            # a different time span depending on the streaming rate, but
            # "last 60 seconds" should mean the same thing regardless.
            if (
                "sample_timestamp_us" in df_full.columns
                and len(df_full) > 0
            ):
                latest_us = df_full["sample_timestamp_us"].iloc[-1]
                window_us = HISTORY_SECONDS * 1_000_000
                df = df_full[
                    df_full["sample_timestamp_us"] >= latest_us - window_us
                ]
            else:
                df = df_full.tail(400)

            gyro_fig.add_trace(
                go.Scatter(
                    y=df["gx"],
                    name="GX",
                    mode="lines",
                    line=dict(width=2),
                    line_shape="linear"
                )
            )

            gyro_fig.add_trace(
                go.Scatter(
                    y=df["gy"],
                    name="GY",
                    mode="lines",
                    line=dict(width=2),
                    line_shape="linear"
                )
            )

            gyro_fig.add_trace(
                go.Scatter(
                    y=df["gz"],
                    name="GZ",
                    mode="lines",
                    line=dict(width=2),
                    line_shape="linear"
                )
            )

            score_fig.add_trace(
                go.Indicator(
                    mode="gauge+number",
                    value=metrics.get(
                        "tremor_score",
                        0
                    ),
                    title={
                        "text":
                        "Tremor Score"
                    },
                    gauge={
                        "axis": {
                            "range":
                            [0, 100]
                        },
                        "bar": {"color": "orange"},
                        "steps": [
                            {"range": [0, 30],  "color": "green"},
                            {"range": [30, 60], "color": "yellow"},
                            {"range": [60, 80], "color": "orange"},
                            {"range": [80, 100],"color": "red"}
                        ]
                    }
                )
            )

            vitals_fig.add_trace(
                go.Scatter(
                    y=df["heart_rate"],
                    name="Heart Rate (BPM)",
                    mode="lines",
                    line=dict(width=2, color="#ff4444"),
                    line_shape="linear"
                )
            )

            vitals_fig.add_trace(
                go.Scatter(
                    y=df["spo2"],
                    name="SpO₂ (%)",
                    mode="lines",
                    line=dict(width=2, color="#00cc66"),
                    line_shape="linear",
                    yaxis="y2"
                )
            )

            cadence_fig.add_trace(
                go.Scatter(
                    y=df["cadence"],
                    name="Cadence (spm)",
                    mode="lines",
                    line=dict(width=2, color="#3399ff"),
                    line_shape="linear",
                    fill="tozeroy"
                )
            )

        except (OSError, ValueError, KeyError, pd.errors.ParserError) as e:
            print(f"dashboard: could not read capture tail: {e}")

    gyro_fig.update_layout(
        template="plotly_dark",
        title=f"Live Gyroscope (last {HISTORY_SECONDS}s)",
        height=500,
        margin=dict(l=20, r=20, t=40, b=20),
        showlegend=True,
        xaxis_title="Samples",
        yaxis_title="Angular Velocity",
        uirevision=True,
        transition={"duration": 80}
    )

    score_fig.update_layout(
        template="plotly_dark",
        height=400
    )

    vitals_fig.update_layout(
        template="plotly_dark",
        title=f"Heart Rate & SpO₂ (last {HISTORY_SECONDS}s)",
        height=350,
        margin=dict(l=20, r=20, t=40, b=20),
        showlegend=True,
        xaxis_title="Samples",
        yaxis=dict(title="Heart Rate (BPM)"),
        yaxis2=dict(
            title="SpO₂ (%)",
            overlaying="y",
            side="right",
            range=[80, 100]
        ),
        uirevision=True,
        transition={"duration": 80}
    )

    cadence_fig.update_layout(
        template="plotly_dark",
        title=f"Cadence Trend (last {HISTORY_SECONDS}s)",
        height=350,
        margin=dict(l=20, r=20, t=40, b=20),
        showlegend=True,
        xaxis_title="Samples",
        yaxis_title="Steps / Minute",
        uirevision=True,
        transition={"duration": 80}
    )

    return cards, gyro_fig, score_fig, vitals_fig, cadence_fig


def create_section(title, cards):
    """Group a set of related metric cards under a section header."""
    return html.Div(
        [
            html.H3(
                title,
                style={
                    "textAlign": "center",
                    "color": "#aaaaaa",
                    "marginBottom": "10px",
                    "marginTop": "10px",
                    "fontWeight": "normal",
                    "textTransform": "uppercase",
                    "letterSpacing": "1px"
                }
            ),
            html.Div(
                cards,
                style={
                    "display": "flex",
                    "justifyContent": "center",
                    "gap": "15px",
                    "flexWrap": "wrap",
                    "marginBottom": "20px"
                }
            )
        ]
    )


def create_card(title, value):
    status_color = "#ffffff"
    status = str(value).upper()

    if status == "TREMOR":
        status_color = "#ff4444"
    elif status == "NO TREMOR":
        status_color = "#00cc66"
    elif status == "YES":
        status_color = "#00cc66"
    elif status == "NO":
        status_color = "#ff4444"
    elif status == "WAITING":
        status_color = "#aaaaaa"

    return html.Div(
        [
            html.H4(title),
            html.H2(
                str(value),
                style={
                    "color": status_color,
                    "fontSize": "28px",
                    "overflowWrap": "break-word",
                    "wordBreak": "break-word",
                    "whiteSpace": "normal"
                }
            )
        ],
        style={
            "backgroundColor": "#222222",
            "padding": "20px",
            "borderRadius": "12px",
            "width": "180px",
            "minHeight": "135px",
            "display": "flex",
            "flexDirection": "column",
            "justifyContent": "center",
            "alignItems": "center",
            "textAlign": "center"
        }
    )

if __name__ == "__main__":
    app.run(
        debug=False,
        port=8050
    )
