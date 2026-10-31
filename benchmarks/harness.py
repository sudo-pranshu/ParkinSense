"""
Benchmark harness: drive a runtime implementation with encoded BLE packets.

Two adapters share one interface so baseline and current code see byte-for-
byte identical input:

* ``LegacyRuntimeAdapter`` -- the pre-transformation runtime (``runtime_v2``)
  loaded from a git worktree of the baseline commit. Its module clocks are
  patched to signal time so accelerated feeding does not distort its
  time-based hysteresis (fairness to the baseline).
* ``CurrentRuntimeAdapter`` -- ``parkinsense.runtime.engine.RuntimeEngine``.

Each adapter exposes ``feed(packet_bytes, t_s)`` and collects one dict per
analysis in ``analyses`` with normalised keys.
"""

from __future__ import annotations

import contextlib
import importlib
import io
import os
import sys
import tempfile
import time as _time

import numpy as np

from parkinsense.protocol.packet import BATCH_SIZE, SAMPLE_PERIOD_US, encode


def packets_from_arrays(imu, ir, red, version=1, t0_us=1_000_000):
    """Yield (bytes, t_seconds) for a synthetic ImuSignal plus PPG slot arrays."""
    n = (imu.n // BATCH_SIZE) * BATCH_SIZE
    for p, start in enumerate(range(0, n, BATCH_SIZE)):
        rows = [(imu.ax[i], imu.ay[i], imu.az[i], imu.gx[i], imu.gy[i], imu.gz[i],
                 int(ir[i]), int(red[i])) for i in range(start, start + BATCH_SIZE)]
        ts = t0_us + start * SAMPLE_PERIOD_US
        yield encode(rows, ts, version=version, seq=p), (start + BATCH_SIZE) * SAMPLE_PERIOD_US / 1e6


class _FakeClock:
    def __init__(self):
        self.t = 1000.0

    def time(self):
        return 1.7e9 + self.t

    def monotonic(self):
        return self.t

    def perf_counter(self):
        return _time.perf_counter()

    def sleep(self, *_):
        pass


def _norm(m: dict, t: float, latency_s: float) -> dict:
    return {
        "t": t,
        "tremor": m.get("classification") == "TREMOR",
        "tremor_state": m.get("tremor_state"),
        "tremor_score": m.get("tremor_score"),
        "frequency": m.get("dominant_frequency"),
        "motion_state": m.get("motion_state"),
        "heart_rate": m.get("heart_rate"),
        "hr_confidence": (m.get("hr_quality") or {}).get("overall_confidence", m.get("hr_confidence")),
        "rmssd": m.get("rmssd"),
        "steps": m.get("steps"),
        "cadence": m.get("cadence"),
        "finger": m.get("finger_detected"),
        "latency_s": latency_s,
        "raw": m,
    }


class LegacyRuntimeAdapter:
    """Baseline runtime_v2 from a worktree. One instance == one fresh session."""

    def __init__(self, worktree: str):
        self.clock = _FakeClock()
        self.analyses: list[dict] = []
        self._tmp = tempfile.mkdtemp(prefix="legacy_rt_")
        for k in [m for m in list(sys.modules) if m.startswith("dashboard")]:
            del sys.modules[k]
        if worktree not in sys.path:
            sys.path.insert(0, worktree)
        cwd = os.getcwd()
        os.chdir(self._tmp)
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                rt = importlib.import_module("dashboard.python.runtime.runtime_v2")
        finally:
            os.chdir(cwd)
        self.rt = rt
        for name in ("dashboard.python.runtime.runtime_v2",
                     "dashboard.python.ppg.ppg_processor",
                     "dashboard.python.activity.step_counter"):
            sys.modules[name].time = self.clock
        rt.start_time = self.clock.time()
        self._t = 0.0


        def capture(metrics):
            self.analyses.append(_norm(metrics, self._t, self._last_lat))
        rt._print_status = capture
        self._last_lat = 0.0
        sys.path.remove(worktree)

    def feed(self, data: bytes, t_s: float):
        self._t = t_s
        self.clock.t = 1000.0 + t_s
        cwd = os.getcwd()
        os.chdir(self._tmp)
        try:
            t0 = _time.perf_counter()
            with contextlib.redirect_stdout(io.StringIO()):
                self.rt.notification_handler(None, data)
            self._last_lat = _time.perf_counter() - t0
            if self.analyses and self.analyses[-1]["t"] == t_s:
                self.analyses[-1]["latency_s"] = self._last_lat
        finally:
            os.chdir(cwd)

    def close(self):
        with contextlib.suppress(Exception):
            self.rt.csv_file.close()


class CurrentRuntimeAdapter:
    def __init__(self, **engine_kwargs):
        from parkinsense.runtime.engine import RuntimeEngine
        self.engine = RuntimeEngine(**engine_kwargs)
        self.analyses: list[dict] = []

    def feed(self, data: bytes, t_s: float):
        t0 = _time.perf_counter()
        out = self.engine.process_packet(data, host_monotonic=1000.0 + t_s)
        lat = _time.perf_counter() - t0
        for m in out.analyses:
            self.analyses.append(_norm(m, t_s, lat))

    def close(self):
        pass


def run(adapter, imu, ir=None, red=None, version=1):
    if ir is None:
        ir = np.full(imu.n, 1600)
        red = np.full(imu.n, 600)
    for data, t in packets_from_arrays(imu, ir, red, version=version):
        adapter.feed(data, t)
    adapter.close()
    return adapter.analyses
