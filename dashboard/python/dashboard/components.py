"""
ParkinSense Dashboard V2
Components
"""

import dash_bootstrap_components as dbc
from dash import html


def status_badge(status):

    color = "success"

    if status == "TREMOR":
        color = "danger"

    return dbc.Badge(
        status,
        color=color,
        className="fs-6"
    )


def info_card(title, value):

    return dbc.Card(

        dbc.CardBody(

            [

                html.H6(
                    title,
                    className="text-center"
                ),

                html.H3(
                    value,
                    className="text-center"
                )

            ]

        ),

        className="shadow-sm"

    )
