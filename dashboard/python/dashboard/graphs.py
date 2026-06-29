"""
ParkinSense Dashboard V2
Graphs
"""

import plotly.graph_objects as go


def empty_graph():

    fig = go.Figure()

    fig.update_layout(

        template="plotly_dark",

        title="Realtime Tremor Score",

        xaxis_title="Time",

        yaxis_title="Score",

        height=350

    )

    return fig
