import json
import os

import pandas as pd

from dash import Dash
from dash import dcc
from dash import html
from dash import Input
from dash import Output

import plotly.graph_objects as go


CSV_FILE = "realtime_capture.csv"
METRICS_FILE = "realtime_metrics.json"

app = Dash(__name__)

app.layout = html.Div(

    style={
        "fontFamily": "Arial",
        "padding": "20px"
    },

    children=[

        html.H1(
            "ParkinSense Dashboard"
        ),

        html.H3(
            "Realtime Parkinsonian Tremor Monitoring"
        ),

        dcc.Interval(
            id="interval",
            interval=1000,
            n_intervals=0
        ),

        html.Div(
            id="metrics"
        ),

        dcc.Graph(
            id="gyro_graph"
        )
    ]
)


@app.callback(

    [
        Output(
            "metrics",
            "children"
        ),

        Output(
            "gyro_graph",
            "figure"
        )
    ],

    [
        Input(
            "interval",
            "n_intervals"
        )
    ]
)

def update_dashboard(_):

    metrics = {}

    if os.path.exists(
        METRICS_FILE
    ):

        try:

            with open(
                METRICS_FILE,
                "r"
            ) as f:

                metrics = json.load(f)

        except Exception:

            metrics = {}

    metric_panel = html.Div(

        [

            html.H2(
                metrics.get(
                    "classification",
                    "WAITING..."
                )
            ),

            html.P(
                f"Dominant Frequency: "
                f"{metrics.get('dominant_frequency',0):.2f} Hz"
            ),

            html.P(
                f"Frequency Std Dev: "
                f"{metrics.get('frequency_std',0):.2f}"
            ),

            html.P(
                f"Band Ratio: "
                f"{metrics.get('band_ratio',0):.3f}"
            ),

            html.P(
                f"Tremor Score: "
                f"{metrics.get('tremor_score',0)}"
            ),

            html.P(
                f"Confidence: "
                f"{metrics.get('confidence',0)}%"
            ),

            html.P(
                f"Persistence: "
                f"{metrics.get('persistence',0)}/5"
            ),

            html.P(
                f"Tremor Burden: "
                f"{metrics.get('tremor_burden',0):.1f}%"
            ),

            html.P(
                f"Samples: "
                f"{metrics.get('sample_count',0)}"
            ),

            html.P(
                f"Packets: "
                f"{metrics.get('packet_count',0)}"
            )

        ]
    )

    fig = go.Figure()

    if os.path.exists(
        CSV_FILE
    ):

        try:

            df = pd.read_csv(
                CSV_FILE
            )

            if len(df) > 1000:

                df = df.tail(
                    1000
                )

            fig.add_trace(
                go.Scatter(
                    y=df["gx"],
                    name="gx"
                )
            )

            fig.add_trace(
                go.Scatter(
                    y=df["gy"],
                    name="gy"
                )
            )

            fig.add_trace(
                go.Scatter(
                    y=df["gz"],
                    name="gz"
                )
            )

        except Exception:

            pass

    fig.update_layout(

        title="Live Gyroscope",

        xaxis_title="Samples",

        yaxis_title="deg/s"
    )

    return metric_panel, fig


if __name__ == "__main__":

    app.run(
        debug=True
    )
