import json
import os

import pandas as pd
import plotly.graph_objects as go

from dash import Dash
from dash import dcc
from dash import html
from dash.dependencies import Input
from dash.dependencies import Output

METRICS_FILE = "realtime_metrics_v2.json"
CSV_FILE = "realtime_capture_v2.csv"

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
            id="metric-cards",
            style={
                "display": "flex",
                "justifyContent": "center",
                "gap": "15px",
                "flexWrap": "wrap",
                "marginBottom": "20px"
            }
        ),
        dcc.Graph(
            id="gyro-graph"
        ),
        dcc.Graph(
            id="score-graph"
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
        Output("score-graph", "figure")
    ],
    [
        Input("interval", "n_intervals")
    ]
)
def update_dashboard(_):

    metrics = {}

    if os.path.exists(METRICS_FILE):
        try:
            with open(METRICS_FILE, "r") as f:
                metrics = json.load(f)
        except:
            metrics = {}

    cards = [
        create_card(
            "Status",
            metrics.get(
                "classification",
                "WAITING"
            )
        ),
        create_card(
            "Tremor Score",
            metrics.get(
                "tremor_score",
                0
            )
        ),
        create_card(
            "Frequency",
            f"{metrics.get('dominant_frequency',0)} Hz"
        ),
        create_card(
            "Severity",
            metrics.get(
                "severity",
                "-"
            )
        ),
        create_card(
            "Burden",
            f"{metrics.get('tremor_burden',0):.1f}%"
        ),
        create_card(
            "Confidence",
            f"{metrics.get('confidence',0)}%"
        ),
        create_card(
            "Motion",
            metrics.get(
                "motion_state",
                "-"
            )
        ),
        create_card(
            "IR",
            metrics.get(
                "latest_ir",
                0
            )
        ),
        create_card(
            "RED",
            metrics.get(
                "latest_red",
                0
            )
        ),
        create_card(
            "Finger",
            "YES" if metrics.get("finger_detected", False) else "NO"
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

    gyro_fig = go.Figure()
    score_fig = go.Figure()

    if os.path.exists(CSV_FILE):
        try:
            df = pd.read_csv(CSV_FILE).tail(400)

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

        except Exception:
            pass

    gyro_fig.update_layout(
        template="plotly_dark",
        title="Live Gyroscope",
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

    return cards, gyro_fig, score_fig


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
        debug=True,
        port=8050
    )
