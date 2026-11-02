"""
Dashboard performance on a long recording.

    python -m benchmarks.dashboard_bench [--minutes 60] [--legacy path/to/old_dashboard.py] [--out FILE]

1. Records a long synthetic session (protocol v2, PPG v2 path) with the real
   RuntimeEngine + SessionRecorder, feeding the runtime's LiveState as it goes.
2. Live path: cost of one incremental /live poll (in-process, no HTTP) and of
   the Overview and Live-monitoring callbacks; size of every live buffer.
3. History path: cold and cached load of the full session, and figure
   construction for the tremor, cardiovascular and activity pages.
4. Optionally the 1 s update of a previous dashboard module (`--legacy`,
   e.g. `git show <rev>:parkinsense/visualization/dashboard.py > old.py`) and
   a full re-read of the capture (`--full-reread`, the original approach).

Timings are wall-clock medians on this machine; compare runs on one machine only.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import resource
import statistics
import sys
import tempfile
import time
from pathlib import Path


def _median_ms(fn, n=7):
    out = []
    for _ in range(n):
        t = time.perf_counter()
        fn()
        out.append(1000 * (time.perf_counter() - t))
    return round(statistics.median(out), 2)


def _rss_mb():
    r = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return round(r / (1024 * 1024 if sys.platform == "darwin" else 1024), 1)


def record(root: Path, minutes: float, live):
    from parkinsense.runtime.app import simulated_packets
    from parkinsense.runtime.engine import RuntimeEngine
    from parkinsense.runtime.recorder import SessionRecorder, _jsonable_metrics

    eng = RuntimeEngine(firmware_version="simulated")
    end_s = minutes * 60
    t0 = time.perf_counter()
    with SessionRecorder(eng, root=root, device={"source": "simulated"}) as rec:
        live.new_session({"session_id": eng.session_id})
        for data, t in simulated_packets(seed=7):
            r = eng.process_packet(data)
            rec.write_rows(r.rows)
            live.on_packet(r.rows, r.analyses, str(rec.dir / "capture.csv"))
            if t - 1.0 >= end_s:
                break
    metrics = _jsonable_metrics(eng.metrics)
    metrics["capture_path"] = str(rec.dir / "capture.csv")
    return rec.dir, metrics, time.perf_counter() - t0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--minutes", type=float, default=60)
    ap.add_argument("--legacy", help="path to a previous dashboard.py to time for comparison")
    ap.add_argument("--full-reread", action="store_true",
                    help="also time a full pd.read_csv of the capture (what the original develop dashboard did per tick)")
    ap.add_argument("--out")
    a = ap.parse_args(argv)

    from parkinsense.runtime.app import LiveState
    from parkinsense.visualization import datasource as DS
    from parkinsense.visualization import sessions as SS
    from parkinsense.visualization.pages import activity, cardio, common, live, overview, tremor

    res = {"minutes": a.minutes}
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        state = LiveState()
        sdir, metrics, gen_s = record(tmp / "recordings", a.minutes, state)
        cap = sdir / "capture.csv"
        res["recording"] = {"capture_mb": round(cap.stat().st_size / 1e6, 1), "generate_s": round(gen_s, 1)}

        # ---- live path --------------------------------------------------
        feed = DS.LiveFeed("in-process")
        feed._get = lambda path: state.live(*[int(kv.split("=")[1]) for kv in path.split("?")[1].split("&")])
        res["live"] = {"first_poll_ms": _median_ms(feed.poll_once, 1)}
        from parkinsense.runtime.app import simulated_packets
        from parkinsense.runtime.engine import RuntimeEngine
        eng = RuntimeEngine()
        gen = simulated_packets(seed=99)

        def push():  # ~0.4 s of new data (16 packets × 26 samples), as between two polls
            for _ in range(16):
                r = eng.process_packet(next(gen)[0])
                state.on_packet(r.rows, r.analyses)
        polls = []
        for _ in range(30):
            push()
            t = time.perf_counter()
            feed.poll_once()
            polls.append(1000 * (time.perf_counter() - t))
        res["live"]["incremental_poll_ms"] = round(statistics.median(polls[5:]), 2)

        def ov():
            snap = feed.snapshot()
            overview.body(snap)
            common.status_bar(snap)
        res["live"]["overview_callback_ms"] = _median_ms(ov)
        res["live"]["live_page_callback_ms"] = _median_ms(lambda: live.figures(feed.snapshot()))
        res["live"]["buffers"] = {"runtime_samples": len(state._samples), "runtime_samples_max": state._samples.maxlen,
                                  "runtime_analyses": len(state._analyses),
                                  "runtime_analyses_max": state._analyses.maxlen,
                                  "client_samples_max": feed._samples.maxlen,
                                  "client_analyses_max": feed._analyses.maxlen}

        # ---- history path -----------------------------------------------
        sess = SS.Session(sdir.name, sdir, "recording", cap, {})
        t = time.perf_counter()
        df = SS.load_analyses(sess)
        res["history"] = {"analysis_windows": len(df), "load_cold_ms": round(1000 * (time.perf_counter() - t), 1),
                          "load_cached_ms": _median_ms(lambda: SS.load_analyses(sess))}
        res["history"]["tremor_figures_ms"] = _median_ms(lambda: tremor.figures(df), 3)
        res["history"]["cardio_figures_ms"] = _median_ms(lambda: cardio.figures(df), 3)
        res["history"]["activity_figures_ms"] = _median_ms(lambda: activity.figures(df), 3)
        res["history"]["psd_click_ms"] = _median_ms(lambda: tremor.psd_figure(sess, int(df["row"].iloc[len(df) // 2])), 3)

        res["peak_rss_mb_new_paths"] = _rss_mb()     # before the legacy / full-read measurements below

        # ---- legacy dashboard -------------------------------------------
        if a.legacy:
            mf = tmp / "metrics.json"
            mf.write_text(json.dumps(metrics, default=str))
            spec = importlib.util.spec_from_file_location("legacy_dashboard", a.legacy)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            mod.METRICS_FILE = str(mf)
            res["legacy_update_ms"] = _median_ms(lambda: mod.update_dashboard(1))

        if a.full_reread:
            import pandas as pd
            res["full_csv_reread_ms"] = _median_ms(lambda: pd.read_csv(cap, low_memory=False).tail(300), 3)

        res["peak_rss_mb_total"] = _rss_mb()

    text = json.dumps(res, indent=2)
    print(text)
    if a.out:
        Path(a.out).write_text(text + "\n")


if __name__ == "__main__":
    main()
