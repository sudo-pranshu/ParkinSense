"""
ParkinSense Dashboard V2
Layout
"""

from dash import html
from dash import dcc

import dash_bootstrap_components as dbc


def metric_card(title, value_id):

    return dbc.Card(

        dbc.CardBody(

            [

                html.H6(
                    title,
                    className="text-center"
                ),

                html.H3(

                    id=value_id,

                    children="--",

                    className="text-center"

                )

            ]

        ),

        className="shadow-sm"

    )


def create_layout():

    return dbc.Container(

        [

            html.Br(),

            html.H1(

                "ParkinSense V2",

                className="text-center"

            ),

            html.Hr(),

            dbc.Row(

                [

                    dbc.Col(
                        metric_card(
                            "Status",
                            "status"
                        )
                    ),

                    dbc.Col(
                        metric_card(
                            "Score",
                            "score"
                        )
                    ),

                    dbc.Col(
                        metric_card(
                            "Confidence",
                            "confidence"
                        )
                    )

                ]

            ),

            html.Br(),

            dbc.Row(

                [

                    dbc.Col(
                        metric_card(
                            "Frequency",
                            "frequency"
                        )
                    ),

                    dbc.Col(
                        metric_card(
                            "Severity",
                            "severity"
                        )
                    ),

                    dbc.Col(
                        metric_card(
                            "Motion",
                            "motion"
                        )
                    )

                ]

            ),

            html.Br(),

            dbc.Row(

                [

                    dbc.Col(
                        metric_card(
                            "Best Axis",
                            "axis"
                        )
                    ),

                    dbc.Col(
                        metric_card(
                            "Packets",
                            "packets"
                        )
                    ),

                    dbc.Col(
                        metric_card(
                            "Sampling Rate",
                            "sampling"
                        )
                    )

                ]

            ),

            html.Br(),

            dcc.Graph(
                id="score_graph"
            ),

            dcc.Interval(

                id="timer",

                interval=500,

                n_intervals=0

            )

        ],

        fluid=True

    )
