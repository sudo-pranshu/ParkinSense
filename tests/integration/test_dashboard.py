"""Dashboard 2.0: runtime live API, LiveFeed client, session store, pages."""

import hashlib
import socket
import threading
import time

import numpy as np
import pandas as pd
import pytest

from helpers import packets

dash = pytest.importorskip("dash")


# --------------------------------------------------------------------------- fixtures
def _record(root, imu, **kw):
    from parkinsense.runtime.engine import RuntimeEngine
    from parkinsense.runtime.recorder import SessionRecorder

    eng = RuntimeEngine()
    with SessionRecorder(eng, root=root, device={"source": "test"}) as rec:
        for d in packets(imu, **kw):
            rec.write_rows(eng.process_packet(d).rows)
    return rec.dir


@pytest.fixture(scope="module")
def recordings(tmp_path_factory):
    from parkinsense.synthetic import signals as S
    root = tmp_path_factory.mktemp("recordings")
    _record(root, S.rest_tremor(seconds=40, seed=1))
    return root


@pytest.fixture
def store(recordings, tmp_path, monkeypatch):
    from parkinsense.visualization import sessions as SS
    monkeypatch.setattr(SS, "RECORDINGS", recordings)
    monkeypatch.setattr(SS, "REPLAYS", tmp_path / "replays")
    return SS


def _free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _feed_live(live, imu, **kw):
    from parkinsense.runtime.engine import RuntimeEngine
    eng = RuntimeEngine()
    live.new_session({"session_id": eng.session_id})
    for d in packets(imu, **kw):
        r = eng.process_packet(d)
        live.on_packet(r.rows, r.analyses)
    return eng


# --------------------------------------------------------------------------- runtime side
def test_live_state_is_incremental_and_bounded():
    from parkinsense.runtime.app import LiveState
    from parkinsense.synthetic import signals as S

    live = LiveState()
    _feed_live(live, S.rest_tremor(seconds=90, seed=2))
    first = live.live(0, 0, max_samples=10_000)
    assert first["last_sample_seq"] > 9000                       # every sample sequenced
    assert len(first["samples"]) <= 10_000                       # capped per response
    assert len(live._samples) == live._samples.maxlen            # bounded buffer (60 s)
    assert first["sample_fields"][:2] == ["seq", "t"]
    assert all(set(a) >= {"live_seq", "tremor_state"} for a in first["analyses"])
    again = live.live(first["last_sample_seq"], first["last_analysis_seq"])
    assert again["samples"] == [] and again["analyses"] == []    # nothing new -> nothing sent


def _serve(app, port):
    import uvicorn
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error"))
    th = threading.Thread(target=server.run, daemon=True)
    th.start()
    for _ in range(100):
        if server.started:
            return server, th
        time.sleep(0.05)
    raise RuntimeError("uvicorn did not start")


def test_livefeed_against_real_api_then_runtime_goes_away():
    pytest.importorskip("uvicorn")
    from parkinsense.runtime.app import LiveState, build_api
    from parkinsense.synthetic import signals as S
    from parkinsense.visualization.datasource import LiveFeed

    live = LiveState()
    _feed_live(live, S.rest_tremor(seconds=20, seed=3))
    port = _free_port()
    server, th = _serve(build_api(live), port)
    try:
        feed = LiveFeed(f"http://127.0.0.1:{port}")
        assert feed.poll_once()
        snap = feed.snapshot()
        assert snap["online"] and len(snap["samples"]) > 1000 and snap["analyses"]
        assert snap["samples"].shape[1] == 10
        n = len(snap["samples"])
        assert feed.poll_once() and len(feed.snapshot()["samples"]) == n   # incremental: no duplicates
        assert np.ptp(feed.snapshot(seconds=5)["samples"][:, 1]) <= 5.01
        assert feed.post("/session/stop")["ok"] is False                   # no control attached
    finally:
        server.should_exit = True
        th.join(5)
    assert not feed.poll_once()
    snap = feed.snapshot()
    assert not snap["online"] and snap["stale"]                           # never presented as live


def test_livefeed_resets_on_new_session():
    from parkinsense.runtime.app import LiveState
    from parkinsense.synthetic import signals as S
    from parkinsense.visualization.datasource import LiveFeed

    live = LiveState()
    _feed_live(live, S.rest_tremor(seconds=10, seed=4))
    feed = LiveFeed("http://unused")
    feed._get = lambda path: live.live(*[int(x.split("=")[1]) for x in path.split("?")[1].split("&")])
    feed.poll_once()
    old = feed.session_id
    _feed_live(live, S.rest_tremor(seconds=5, seed=5))
    feed.poll_once()
    assert feed.session_id != old
    assert len(feed.snapshot()["samples"]) <= 5 * 104 + 26


# --------------------------------------------------------------------------- session store
def test_session_store_reads_without_modifying(store, recordings):
    sessions = store.list_sessions()
    assert len(sessions) == 1
    s = sessions[0]
    digest = hashlib.sha256(s.capture.read_bytes()).hexdigest()
    row = s.summary_row()
    assert row["source"] == "test" and row["status"] == "COMPLETE" and row["duration_min"] > 0.5
    df = store.load_analyses(s)
    assert len(df) > 50 and df["t"].is_monotonic_increasing
    assert store.load_analyses(s) is df                                    # cached
    eps = store.episodes(df)
    assert len(eps) >= 1 and (eps["type"] == "REST").all()
    q = store.quality_fractions(df)
    assert all(abs(sum(v.values()) - 1) < 1e-3 for v in q.values())
    raw = store.load_raw_window(s, int(df["row"].iloc[-1]))
    assert len(raw) == 416
    assert hashlib.sha256(s.capture.read_bytes()).hexdigest() == digest   # original untouched


# --------------------------------------------------------------------------- pages
def test_all_pages_build_and_route(store):
    from parkinsense.visualization import dashboard as D
    app = D.create_app(None)
    assert app.layout is not None
    for _, _, mod in D.PAGES:
        assert mod.layout() is not None


def test_page_figures_with_data_and_without(store):
    from parkinsense.visualization.pages import activity, cardio, tremor
    s = store.list_sessions()[0]
    df = store.load_analyses(s)
    for figs in (tremor.figures(df), cardio.figures(df), activity.figures(df)):
        assert all(f.data or f.layout.annotations for f in figs)
    empty = df.iloc[0:0]
    for figs in (tremor.figures(empty), cardio.figures(empty), activity.figures(empty)):
        assert all(len(f.data) == 0 for f in figs)
    psd = tremor.psd_figure(s, int(df["row"].iloc[-1]))
    assert psd.data


def test_live_and_overview_render_offline_without_zeros(tmp_path, monkeypatch):
    from parkinsense.visualization import datasource as DS
    from parkinsense.visualization.pages import live, overview
    monkeypatch.setattr(DS, "METRICS_FILE", str(tmp_path / "missing.json"))
    feed = DS.LiveFeed("http://127.0.0.1:9")      # nothing listens there
    feed.poll_once()
    snap = feed.snapshot()
    assert not snap["online"] and snap["stale"] and snap["latest"] == {}
    figs = live.figures(snap)
    assert all(len(f.data) == 0 for f in figs if hasattr(f, "data"))
    html = str(overview.body(snap))
    assert "—" in html                               # missing shown as a dash, not as 0


def test_components_never_turn_missing_into_zero():
    from parkinsense.visualization import components as K
    assert K.fmt(None) is None and K.fmt(float("nan")) is None and K.fmt(0.0) == "0.0"
    card = str(K.metric_card("HR", None, "bpm"))
    assert "—" in card and "0.0" not in card
    assert "LOW" in str(K.metric_card("HR", 70, "bpm", state="LOW_CONFIDENCE")).upper()


def test_charts_decimate_preserves_extremes():
    from parkinsense.visualization import charts as CH
    x = np.arange(100_000, dtype=float)
    y = np.sin(x / 50)
    y[12_345] = 9.0
    xd, yd = CH.decimate(x, y, max_points=2000)
    assert len(xd) <= 4100 and yd.max() == 9.0


def test_read_tail_compat(store):
    from parkinsense.visualization import dashboard as D
    s = store.list_sessions()[0]
    tail = D.read_tail(str(s.capture), nbytes=20_000)
    assert isinstance(tail, pd.DataFrame) and "is_analysis_row" in tail.columns
