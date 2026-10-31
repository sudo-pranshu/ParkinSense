"""
Verification harness for the PPGProcessor half of Issue #1.

Decimating analysis to a slower hop breaks any temporal threshold expressed
as a *call count*. PPGProcessor previously converted its second-denominated
constants into sample counts via `fs`, which silently assumed analysis runs
once per sample. Those thresholds are now measured as elapsed monotonic
time. This harness asserts:

  1. `ingest()` buffers a sample without running analysis.
  2. `analyze()` runs analysis without buffering a sample.
  3. `process()` still equals ingest + analyze (backward compatibility).
  4. Finger-presence hysteresis honours FINGER_ON/OFF_HYSTERESIS_SECONDS as
     wall-clock seconds, and is invariant to how often `analyze()` is called
     -- the property that was broken before.
  5. The returned "ir"/"red" fields echo the last ingested pair regardless
     of which entry point produced the reading.

`algorithms` is stubbed because it pulls in scipy; this issue changed no DSP,
only the state machine's time base and the ingest/analyze split.

Run with:  python3 tests/verify_issue1_ppg_timebase.py
"""

import sys
import types
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

# --- Controllable clock ----------------------------------------------------

class FakeClock:
    def __init__(self):
        self.now = 1000.0

    def monotonic(self):
        return self.now

    def time(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


CLOCK = FakeClock()

# --- Stub the scipy-backed algorithms module -------------------------------

FINGER_RAW = {"detected": False}

_algos = types.ModuleType("dashboard.python.ppg.algorithms")
_algos.assess_finger_presence = lambda ir, fs: {
    "detected": FINGER_RAW["detected"], "confidence": 0.9, "reason": "stub",
}
_algos.compute_signal_quality = lambda ir, fs: {"score": 80.0, "motion_score": 1.0}
_algos.classify_sensor_status = lambda ir, sqi_score=None: "GOOD"
_algos.estimate_heart_rate = lambda ir, fs, debug=False: {
    "heart_rate": 70.0, "rr_intervals_ms": [850.0] * 5, "confidence": 0.9,
    "peak_quality": 0.9, "rhythm_quality": 0.9,
}
_algos.compute_hrv_metrics = lambda rr: {
    "rmssd": 20.0, "sdnn": 30.0, "mean_rr": 850.0, "pnn50": 5.0, "n_intervals": len(rr),
}
_algos.estimate_spo2 = lambda ir, red, fs: {"spo2": 98.0, "confidence": 0.8}
sys.modules["dashboard.python.ppg.algorithms"] = _algos

import dashboard.python.ppg.ppg_processor as pp  # noqa: E402

pp.time = CLOCK  # inject the controllable clock


def main():
    failures = []

    # --- 1 & 2: ingest and analyze are genuinely separate -----------------
    proc = pp.PPGProcessor(sample_rate=50, window_seconds=10)
    proc.ingest(1234, 5678)
    if len(proc._ir_buffer) != 1 or len(proc._red_buffer) != 1:
        failures.append("ingest() did not buffer the sample")

    before = len(proc._ir_buffer)
    reading = proc.analyze()
    if len(proc._ir_buffer) != before:
        failures.append("analyze() must not append to the buffer")

    # --- 5: raw echo survives the split -----------------------------------
    if reading["ir"] != 1234 or reading["red"] != 5678:
        failures.append(
            f"analyze() echoed ir/red as {reading['ir']}/{reading['red']}, "
            "expected the last ingested pair 1234/5678"
        )

    # --- 3: process() is still ingest + analyze ---------------------------
    proc2 = pp.PPGProcessor(sample_rate=50, window_seconds=10)
    proc2.process(1111, 2222)
    if len(proc2._ir_buffer) != 1:
        failures.append("process() no longer ingests")
    r2 = proc2.analyze()
    if r2["ir"] != 1111:
        failures.append("process() did not record the last ingested sample")

    # --- 4: hysteresis is time-based, not call-count based ----------------
    # Same 3 seconds of held "finger on", once sampled densely (per-sample
    # analysis) and once sparsely (per-hop analysis). Both must confirm.
    def run_hysteresis(analyses_per_second):
        CLOCK.now = 1000.0
        FINGER_RAW["detected"] = False
        p = pp.PPGProcessor(sample_rate=50, window_seconds=10)
        for _ in range(200):
            p.ingest(50_000, 40_000)

        # Settle in the "off" state.
        p.analyze()

        FINGER_RAW["detected"] = True
        confirm_delay = None
        step = 1.0 / analyses_per_second
        for i in range(int(3 * analyses_per_second)):
            CLOCK.advance(step)
            p.analyze()
            if p._finger_confirmed and confirm_delay is None:
                confirm_delay = (i + 1) * step
        return confirm_delay

    dense = run_hysteresis(analyses_per_second=104)   # old behaviour
    sparse = run_hysteresis(analyses_per_second=1)    # new hop rate

    expected = pp.FINGER_ON_HYSTERESIS_SECONDS
    print(f"FINGER_ON_HYSTERESIS_SECONDS      : {expected}")
    print(f"confirm delay @ 104 analyses/s    : {dense}")
    print(f"confirm delay @ 1 analysis/s      : {sparse}")

    if dense is None or abs(dense - expected) > 0.05:
        failures.append(
            f"dense-analysis confirm delay {dense} s != {expected} s"
        )
    if sparse is None or abs(sparse - expected) > 1.01:
        failures.append(
            f"sparse-analysis confirm delay {sparse} s not within one hop "
            f"of {expected} s -- hysteresis is still call-rate dependent"
        )

    # The whole point: the delay must be set by the clock, not the call rate.
    if dense is not None and sparse is not None and abs(dense - sparse) > 1.01:
        failures.append(
            f"confirm delay changed from {dense} s to {sparse} s when the "
            "analysis rate changed -- threshold is not time-based"
        )

    print("-" * 46)
    if failures:
        for f in failures:
            print(f"FAIL: {f}")
        return 1
    print("PASS: ingest/analyze split and time-based hysteresis verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
