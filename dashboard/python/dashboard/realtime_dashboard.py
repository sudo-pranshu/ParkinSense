import json
import os

import pandas as pd
import plotly.graph_objects as go

from dash import Dash
from dash import dcc
from dash import html
from dash.dependencies import Input
from dash.dependencies import Output


METRICS_FILE = "realtime_metrics.json"
CSV_FILE = "realtime_capture.csv"

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
                "justifyContent": "space-around",
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
            interval=1000,
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
            f"{metrics.get('dominant_frequency',0):.2f} Hz"
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
        )
    ]

    gyro_fig = go.Figure()

    score_fig = go.Figure()

    if os.path.exists(CSV_FILE):

        try:

            df = pd.read_csv(CSV_FILE)

            if len(df) > 1000:

                df = df.tail(1000)

            gyro_fig.add_trace(
                go.Scatter(
                    y=df["gx"],
                    name="GX"
                )
            )

            gyro_fig.add_trace(
                go.Scatter(
                    y=df["gy"],
                    name="GY"
                )
            )

            gyro_fig.add_trace(
                go.Scatter(
                    y=df["gz"],
                    name="GZ"
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
                        }
                    }
                )
            )

        except Exception:

            pass

    gyro_fig.update_layout(

        template="plotly_dark",

        title="Live Gyroscope",

        height=500
    )

    score_fig.update_layout(

        template="plotly_dark",

        height=400
    )

    return cards, gyro_fig, score_fig


def create_card(title, value):

    return html.Div(

        [

            html.H4(title),

            html.H2(str(value))

        ],

        style={

            "backgroundColor": "#222222",

            "padding": "20px",

            "borderRadius": "12px",

            "width": "15%",

            "textAlign": "center"
        }
    )


if __name__ == "__main__":

    app.run(
        debug=True,
        port=8050
    )
