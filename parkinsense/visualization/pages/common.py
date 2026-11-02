"""Shared page pieces: runtime status bar, simulated-data banner, session selection."""

from __future__ import annotations

import pandas as pd
from dash import dcc, html

from parkinsense.visualization import components as K
from parkinsense.visualization import sessions as SS

LIVE = "__live__"


def status_bar(snap: dict):
    meta = snap["meta"]
    latest = snap["latest"] or {}
    integ = meta.get("integrity") or latest.get("integrity") or {}
    if not snap["online"]:
        conn = K.pill("Runtime offline", "idle")
    elif snap["stale"]:
        conn = K.pill(meta.get("status", "WAITING").title().replace("_", " "), "warn")
    else:
        conn = K.pill("Streaming", "live")
    rate = latest.get("device_rate_hz")
    rate_status = latest.get("rate_status")
    rate_kind = {"OK": "live", "WARN": "warn", "INVALID": "bad"}.get(rate_status, "idle")
    pk = integ.get("packets") or 0
    lost = integ.get("packets_lost_seq") or 0
    loss = f"{100 * lost / (pk + lost):.2f} %" if (pk + lost) else "—"
    items = [
        K.status_item("Runtime", None, conn),
        K.status_item("Source", (meta.get("source") or "—").upper() if snap["online"] else "—"),
        K.status_item("Session", meta.get("session_id") or "—"),
        K.status_item("Recording", "yes" if meta.get("recording") else "no"),
        K.status_item("Last data", K.age_text(snap["data_age_s"])),
        K.status_item("Device rate", None, K.pill(f"{rate:.2f} Hz · {rate_status}" if rate else "—", rate_kind)),
        K.status_item("Packet loss (v2)", loss),
        K.status_item("Gaps · resets", f"{integ.get('timestamp_gaps', '—')} · {integ.get('window_resets', '—')}"),
        K.status_item("Firmware", latest.get("firmware_version") or "—"),
        K.status_item("Pipeline", latest.get("pipeline_version") or "—"),
    ]
    return html.Div(items, className="statusbar")


def banners(snap: dict):
    out = []
    src = (snap["meta"] or {}).get("source")
    if snap["online"] and src in ("simulated", "replay"):
        out.append(html.Div(
            f"{src.upper()} DATA — this stream is {'synthetic' if src == 'simulated' else 'a replayed recording'}, "
            "not a live measurement from the wearable.", className="banner banner-sim"))
    if not snap["online"]:
        m = snap["latest"] or {}
        if m.get("_from_file"):
            out.append(html.Div(f"Runtime API not reachable. Showing the last metrics saved to disk "
                                f"({K.age_text(m.get('_file_age_s'))}) — not live.", className="banner banner-warn"))
        else:
            out.append(html.Div("Runtime not running. Start it with ./start_runtime.sh (or --simulate without "
                                "hardware). Recorded sessions remain available under Sessions.",
                                className="banner banner-info"))
    return out


def session_options():
    opts = [{"label": "Current live session", "value": LIVE}]
    opts += [{"label": s.label, "value": s.id} for s in SS.list_sessions()]
    return opts


def session_picker(id_, value=None, multi=False):
    return dcc.Dropdown(id=id_, options=session_options(), value=value if value is not None else ([] if multi else LIVE),
                        multi=multi, clearable=multi, style={"minWidth": "340px"})


def resolve_session(value, snap=None):
    """Map a picker value to a Session (the live session resolves through the feed's session id)."""
    if value in (None, LIVE):
        sid = (snap or {}).get("meta", {}).get("session_id")
        if not sid:
            return None
        return next((s for s in SS.list_sessions() if s.id.endswith(sid)), None)
    return SS.get_session(value)


def analyses_frame(snap: dict) -> pd.DataFrame:
    """Live analyses buffer as a DataFrame with a relative time column."""
    df = pd.DataFrame(snap["analyses"])
    if df.empty:
        return df
    df["t"] = df["signal_time_s"].astype(float)
    return df
