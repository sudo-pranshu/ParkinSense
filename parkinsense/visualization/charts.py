"""
Figure builders. Every chart: labelled axes with units, consistent time axis,
tooltips, zoom/pan, PNG export via the mode bar, and an explicit empty state.
`uirevision` keeps the user's zoom across live updates.
"""

from __future__ import annotations

import numpy as np
import plotly.graph_objects as go
import plotly.io as pio

from parkinsense.visualization import theme as T
from parkinsense.visualization.quality import CHART_COLORS

GRAPH_CONFIG = {"displaylogo": False, "scrollZoom": True,
                "modeBarButtonsToRemove": ["lasso2d", "select2d", "autoScale2d"],
                "toImageButtonOptions": {"format": "png", "scale": 2, "filename": "parkinsense"}}

MAX_POINTS = 4000


_AXIS = dict(gridcolor=T.GRID, zerolinecolor=T.GRID, linecolor=T.GRID, tickfont=dict(color=T.MUTED, size=11),
             title=dict(font=dict(color=T.MUTED, size=11)))
# Static styling lives in a registered template: building it once instead of
# update_layout() on every figure makes figure construction ~10x cheaper.
pio.templates["parkinsense"] = go.layout.Template(layout=dict(
    paper_bgcolor=T.PANEL, plot_bgcolor=T.PANEL, font=dict(family=T.FONT, color=T.TEXT, size=12),
    hovermode="x unified",
    legend=dict(orientation="h", yanchor="bottom", y=1.0, xanchor="right", x=1, bgcolor="rgba(0,0,0,0)",
                font=dict(size=11, color=T.MUTED)),
    hoverlabel=dict(bgcolor="#1f2732", bordercolor=T.GRID, font=dict(family=T.FONT, size=12)),
    xaxis=_AXIS, yaxis=_AXIS))


def base(title=None, height=260, x_title=None, y_title=None, uirev="keep", legend=True):
    return go.Figure(layout=dict(
        template="parkinsense", height=height,
        margin=dict(l=56, r=18, t=(56 if legend else 36) if title else 14, b=42),
        # title pinned to the top, legend on its own row just above the plot: they never overlap
        title=dict(text=title, x=0.01, y=1, yref="container", yanchor="top", pad=dict(t=12),
                   font=dict(size=13, color=T.TEXT)) if title else None,
        uirevision=uirev, showlegend=legend,
        xaxis=dict(title=dict(text=x_title)), yaxis=dict(title=dict(text=y_title))))


def empty(message, height=260, title=None):
    fig = base(title=title, height=height, legend=False)
    fig.add_annotation(text=message, showarrow=False, x=0.5, y=0.5, xref="paper", yref="paper",
                       font=dict(color=T.MUTED, size=13))
    fig.update_xaxes(visible=False)
    fig.update_yaxes(visible=False)
    return fig


def decimate(x, *ys, max_points=MAX_POINTS):
    """Min/max-preserving decimation for display only (keeps peaks visible)."""
    x = np.asarray(x)
    n = len(x)
    if n <= max_points:
        return (x, *[np.asarray(y) for y in ys])
    bins = max_points // 2
    edges = np.linspace(0, n, bins + 1).astype(int)
    idx = []
    ref = np.asarray(ys[0], dtype=float)
    for a, b in zip(edges[:-1], edges[1:]):
        if b <= a:
            continue
        seg = ref[a:b]
        if np.all(np.isnan(seg)):
            idx.append(a)
            continue
        i1, i2 = a + int(np.nanargmin(seg)), a + int(np.nanargmax(seg))
        idx.extend(sorted({i1, i2}))
    idx = np.asarray(idx)
    return (x[idx], *[np.asarray(y)[idx] for y in ys])


def lines(x, series, title=None, x_title="time (s)", y_title=None, height=260, uirev="keep"):
    """series: list of (name, y, color)."""
    if len(x) == 0:
        return empty("No data in this range", height, title)
    fig = base(title, height, x_title, y_title, uirev)
    for name, y, color in series:
        xd, yd = decimate(x, y)
        fig.add_trace(go.Scattergl(x=xd, y=yd, name=name, mode="lines", line=dict(width=1.4, color=color)))
    return fig


def quality_scatter(x, y, states, title=None, y_title=None, height=260, unit="", uirev="keep", connect=True,
                    custom=None):
    """Value over time; VALID points solid, every other state hollow and coloured by state."""
    x, y, states = np.asarray(x), np.asarray(y, dtype=float), np.asarray(states, dtype=object)
    custom = None if custom is None else np.asarray(custom)
    ok = ~np.isnan(y)
    if not ok.any():
        return empty("No values in this range", height, title)
    fig = base(title, height, "time (s)", y_title, uirev)
    if connect:
        valid = states == "VALID"
        yv = np.where(valid & ok, y, np.nan)
        fig.add_trace(go.Scattergl(x=x, y=yv, mode="lines", name="VALID", line=dict(color=CHART_COLORS["VALID"], width=1.6),
                                   hovertemplate=f"%{{y:.1f}} {unit} · VALID<extra></extra>"))
    for s in sorted(set(states[ok])):
        m = ok & (states == s)
        if s == "VALID" and connect:
            continue
        fig.add_trace(go.Scattergl(
            x=x[m], y=y[m], mode="markers", name=s.replace("_", " ").title(),
            marker=dict(size=5 if s == "VALID" else 6, color=CHART_COLORS.get(s, T.MUTED),
                        symbol="circle" if s == "VALID" else "circle-open"),
            customdata=None if custom is None else custom[m],
            hovertemplate=f"%{{y:.1f}} {unit} · {s}<extra></extra>"))
    return fig


def shade_intervals(fig, intervals, color, label=None, opacity=0.13):
    """
    Shade (t0, t1) intervals as ONE filled trace on a hidden 0-1 overlay axis
    (plotly shapes cost ~1 ms each to build; a 1-hour session can have
    hundreds of intervals). The label becomes the legend entry.
    """
    if not intervals:
        return fig
    xs, ys = [], []
    for a, b in intervals:
        xs += [a, a, b, b, None]
        ys += [0, 1, 1, 0, None]
    fig.add_trace(go.Scatter(x=xs, y=ys, yaxis="y9", fill="toself", mode="none", fillcolor=color, opacity=opacity,
                             name=label or "", showlegend=bool(label), hoverinfo="skip"))
    fig.update_layout(yaxis9=dict(overlaying="y", range=[0, 1], visible=False, fixedrange=True))
    return fig


def state_strip(t, states, colors, title=None, height=90):
    """Categorical timeline (e.g. motion state)."""
    t = np.asarray(t)
    if len(t) == 0:
        return empty("No data", height, title)
    fig = base(title, height, None, None, legend=True)
    for s, c in colors.items():
        m = np.asarray(states) == s
        if m.any():
            fig.add_trace(go.Scattergl(x=t[m], y=[s] * int(m.sum()), mode="markers", name=s,
                                       marker=dict(color=c, size=6, symbol="square")))
    fig.update_yaxes(showgrid=False, categoryorder="array", categoryarray=list(colors))
    fig.update_layout(margin=dict(l=90, r=18, t=26 if title else 8, b=26))
    return fig


def intervals_from_mask(t, mask, min_len_s=0.0, merge_gap_s=1.0):
    """
    True runs of `mask` over sorted times `t` -> [(t0, t1)]. Each sample covers
    ±half its spacing (a single flagged window is still visible), and runs
    separated by less than `merge_gap_s` are merged so a flickering state does
    not produce hundreds of shapes.
    """
    t = np.asarray(t, dtype=float)
    m = np.asarray(mask, dtype=bool)
    if len(t) == 0 or not m.any():
        return []
    half = float(np.median(np.diff(t))) / 2 if len(t) > 1 else 0.25
    d = np.diff(np.concatenate([[0], m.astype(np.int8), [0]]))
    starts, ends = np.flatnonzero(d == 1), np.flatnonzero(d == -1) - 1
    out = []
    for a, b in zip(t[starts] - half, t[ends] + half):
        if out and a - out[-1][1] < merge_gap_s:
            out[-1] = (out[-1][0], b)
        else:
            out.append((a, b))
    return [(a, b) for a, b in out if b - a >= min_len_s]
    start = None
    for i in range(len(t)):
        if m[i] and start is None:
            start = t[i]
        if (not m[i] or i == len(t) - 1) and start is not None:
            end = t[i] if m[i] else t[i - 1]
            if end - start >= min_len_s:
                out.append((start, end))
            start = None
    return out
