"""
ParkinSense dashboard (Plotly Dash).

    python -m parkinsense.visualization.dashboard [--port 8050] [--api http://127.0.0.1:8000]
    ./start_dashboard.sh

A pure consumer: it reads the runtime's HTTP API (live data) and the session
folders on disk (history). It never imports the runtime engine, never writes to
a recording, and can be started, stopped or restarted at any time without
affecting acquisition. Architecture: docs/software/DASHBOARD_AND_API.md.
"""

from __future__ import annotations

import argparse
import logging
import os

from dash import Dash, Input, Output, dcc, html

from parkinsense import config as C
from parkinsense.visualization import datasource as DS
from parkinsense.visualization.datasource import read_tail  # noqa: F401  (public helper, kept for compatibility)
from parkinsense.visualization.pages import activity, cardio, live, overview, research, sessions_page, tremor

PAGES = [
    ("/", "Overview", overview),
    ("/live", "Live monitoring", live),
    ("/tremor", "Tremor analytics", tremor),
    ("/cardio", "Cardiovascular", cardio),
    ("/activity", "Activity", activity),
    ("/sessions", "Sessions", sessions_page),
    ("/research", "Data & research", research),
]


def sidebar():
    return html.Nav(className="sidebar", children=[
        html.Div(className="brand", children=[
            html.Div(className="brand-mark"),
            html.Div([html.Div("ParkinSense", className="brand-name"),
                      html.Div(f"pipeline {C.PIPELINE_VERSION}", className="brand-sub")])]),
        *[dcc.Link([html.Span(className="nav-dot"), name], href=path, id=f"nav-{mod.__name__.split('.')[-1]}",
                   className="nav-link") for path, name, mod in PAGES],
        html.Div(className="sidebar-foot", children=[
            "Research use only. Not a medical device.", html.Br(),
            "Values marked other than VALID are not measurements."]),
    ])


def create_app(api: str | None = None) -> Dash:
    if api:
        DS.set_feed(DS.LiveFeed(api).start())
    app = Dash(__name__, title="ParkinSense", update_title=None, suppress_callback_exceptions=True,
               assets_folder=os.path.join(os.path.dirname(__file__), "assets"))
    app.layout = html.Div(className="shell", children=[
        dcc.Location(id="url"),
        sidebar(),
        html.Main(id="page", className="main"),
    ])

    @app.callback(Output("page", "children"), *[Output(f"nav-{m.__name__.split('.')[-1]}", "className") for _, _, m in PAGES],
                  Input("url", "pathname"))
    def _route(path):
        match = next((m for p, _, m in PAGES if p == path), overview)
        classes = ["nav-link active" if m is match else "nav-link" for _, _, m in PAGES]
        return (match.layout(), *classes)

    for _, _, mod in PAGES:
        mod.register(app)
    return app


def main(argv=None):
    ap = argparse.ArgumentParser(description="ParkinSense dashboard")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=C.DEFAULT_DASHBOARD_PORT)
    ap.add_argument("--api", default=DS.DEFAULT_API, help="runtime API base URL")
    a = ap.parse_args(argv)
    logging.getLogger("werkzeug").setLevel(logging.WARNING)
    app = create_app(a.api)
    print(f"ParkinSense dashboard on http://{a.host}:{a.port}  (runtime API: {a.api})", flush=True)
    app.run(host=a.host, port=a.port, debug=False)


if __name__ == "__main__":
    main()
