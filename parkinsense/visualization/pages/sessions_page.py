"""Session history: browse, inspect metadata/integrity, export, compare."""

from __future__ import annotations

import json

from dash import Input, Output, State, dash_table, dcc, html

from parkinsense.analytics.biomarkers import session_report
from parkinsense.visualization import components as K
from parkinsense.visualization import sessions as SS
from parkinsense.visualization.pages.tremor import TABLE_STYLE

COLUMNS = ["session", "source", "started", "duration_min", "status", "firmware", "pipeline", "rate_hz",
           "rate_status", "loss_pct", "gaps", "errors", "size_mb", "kind"]


def layout():
    return html.Div([
        html.Div(className="page-head", children=[
            html.Div([html.H1("Sessions", className="page-title"),
                      html.Div("Recordings (recordings/) and replay outputs (replays/). Read-only: nothing here "
                               "modifies a recording.", className="page-sub")]),
            html.Button("Refresh", id="ss-refresh", className="btn"),
        ]),
        html.Div(className="card", children=[html.Div(id="ss-table")]),
        html.Div(className="grid g2", style={"marginTop": "14px"}, children=[
            html.Div(className="card", children=[html.Div(id="ss-detail", children=K.empty("Select a session row."))]),
            html.Div(className="card", children=[
                html.Div("Export", className="metric-title"),
                html.Div(className="row", style={"margin": "10px 0"}, children=[
                    html.Button("Raw capture (CSV)", id="ss-dl-csv", className="btn"),
                    html.Button("Metadata (JSON)", id="ss-dl-meta", className="btn"),
                    html.Button("Session summary (JSON)", id="ss-dl-sum", className="btn btn-primary"),
                ]),
                html.Div("The summary contains metadata, integrity, quality fractions and the analytics "
                         "session_report. Exports are copies; originals are never modified.", className="muted small"),
                dcc.Download(id="ss-download"),
            ]),
        ]),
        dcc.Store(id="ss-selected"),
    ])


def table():
    rows = [s.summary_row() for s in SS.list_sessions()]
    if not rows:
        return K.empty("No recordings yet. Start the runtime (./start_runtime.sh, or --simulate) to create one.")
    return dash_table.DataTable(id="ss-dt", data=rows, columns=[{"name": c, "id": c} for c in COLUMNS],
                                row_selectable="single", filter_action="native", **TABLE_STYLE)


def summary_json(sess):
    df = SS.load_analyses(sess)
    return {"session": sess.id, "kind": sess.kind, "metadata": sess.meta,
            "quality_fractions": SS.quality_fractions(df), "usable_tremor_fraction": SS.session_quality_score(df),
            "episodes": SS.episodes(df).to_dict("records"), "report": session_report(df)}


def detail(sess):
    m = sess.meta
    integ = m.get("integrity") or {}
    meas = m.get("measured") or {}
    return [html.Div(f"Session {sess.id}", className="metric-title"),
            html.Div(style={"height": "8px"}),
            K.kv([("status", m.get("status")), ("source", (m.get("device") or {}).get("source")),
                  ("firmware", m.get("firmware_version")), ("pipeline", m.get("pipeline_version")),
                  ("schema", m.get("capture_schema_version")), ("protocols", m.get("protocol_versions_seen")),
                  ("samples", meas.get("samples")), ("analyses", meas.get("analyses")),
                  ("device rate", meas.get("device_rate_hz")), ("rate status", meas.get("rate_status")),
                  ("packets", integ.get("packets")), ("lost (seq)", integ.get("packets_lost_seq")),
                  ("gaps", integ.get("timestamp_gaps")), ("wraps", integ.get("timestamp_wraps")),
                  ("window resets", integ.get("window_resets")), ("analysis errors", integ.get("analysis_errors")),
                  ("started (UTC)", m.get("started_utc")), ("ended (UTC)", m.get("ended_utc")),
                  ("directory", str(sess.dir))]),
            html.Details([html.Summary("Full metadata JSON", className="muted small"),
                          html.Pre(json.dumps(m, indent=2, default=str), className="log")])]


def register(app):
    @app.callback(Output("ss-table", "children"), Input("ss-refresh", "n_clicks"))
    def _table(_):
        return table()

    @app.callback(Output("ss-selected", "data"), Output("ss-detail", "children"),
                  Input("ss-dt", "selected_rows"), State("ss-dt", "derived_virtual_data"), prevent_initial_call=True)
    def _select(sel, data):
        if not sel or not data:
            return None, K.empty("Select a session row.")
        sid = data[sel[0]]["session"]
        sess = SS.get_session(sid)
        return sid, detail(sess) if sess else K.empty("Session not found.")

    @app.callback(Output("ss-download", "data"), Input("ss-dl-csv", "n_clicks"), Input("ss-dl-meta", "n_clicks"),
                  Input("ss-dl-sum", "n_clicks"), State("ss-selected", "data"), prevent_initial_call=True)
    def _download(a, b, c, sid):
        from dash import ctx
        sess = SS.get_session(sid) if sid else None
        if sess is None:
            return None
        if ctx.triggered_id == "ss-dl-csv":
            return dcc.send_file(str(sess.capture), filename=f"{sess.id}_capture.csv")
        if ctx.triggered_id == "ss-dl-meta":
            return dict(content=json.dumps(sess.meta, indent=2, default=str), filename=f"{sess.id}_metadata.json")
        return dict(content=json.dumps(summary_json(sess), indent=2, default=str), filename=f"{sess.id}_summary.json")
