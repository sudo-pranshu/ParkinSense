"""
Verification harness for Issue #1 (per-sample -> per-hop analysis scheduling).

Drives `runtime_v2.notification_handler` with synthetic BLE packets and
asserts the scheduling contract:

  1. Windowed analysis runs once per ANALYSIS_HOP_SAMPLES, not once per sample.
  2. PPG ingestion still runs once per sample (the rolling buffer *is* the
     PPG waveform, so decimating it would decimate the signal).
  3. StepCounter still receives every sample once a motion state exists.
  4. One capture row is still written per sample after the first analysis,
     so raw-signal recordings keep full temporal resolution for replay.

MotionPipeline is replaced by a counting stub because the real one pulls in
scipy; StepCounter is the real implementation. This isolates the scheduling
change, which is what this issue touched.

Run with:  python3 tests/verify_issue1_scheduling.py
"""

import struct
import sys
import tempfile
import types
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))


# --- Stub third-party modules the runtime imports at module scope ----------

def _install_stub(name, **attrs):
    mod = types.ModuleType(name)
    for key, value in attrs.items():
        setattr(mod, key, value)
    sys.modules.setdefault(name, mod)


class _FakeApp:
    def __init__(self, *a, **kw):
        pass

    def get(self, *a, **kw):
        return lambda fn: fn


_install_stub("fastapi", FastAPI=_FakeApp)
_install_stub("uvicorn", run=lambda *a, **kw: None)
_install_stub("bleak", BleakScanner=object, BleakClient=object)


# --- Counting stub for MotionPipeline -------------------------------------

class CountingPipeline:
    """Records how often each entry point is called."""

    def __init__(self, *a, **kw):
        self.process_calls = 0
        self.ingest_calls = 0

    def ingest_ppg(self, ir, red):
        self.ingest_calls += 1

    def process(self, ax, ay, az, gx, gy, gz, ir=None, red=None):
        self.process_calls += 1
        assert ir is None and red is None, (
            "runtime must not re-ingest PPG through process(); it already "
            "ingested this sample via ingest_ppg()"
        )
        return {
            "result": {
                "tremor": False, "score": 10, "confidence": 50.0,
                "severity": "NONE", "frequency": 5.0, "frequency_std": 0.1,
                "band_ratio": 0.1, "best_axis": "gy", "axis_agreement": 0.9,
                "axis_dominance": 0.4, "rest_index": 0.9,
            },
            # ACTIVE so the real StepCounter's motion gate opens and the
            # synthetic gait signal below can actually register steps --
            # otherwise the step columns stay constant and prove nothing.
            "context": {"state": "ACTIVE", "motion_rms": 0.30},
            "ppg": {
                "heart_rate": None, "signal_quality": 0.0,
                "sensor_status": "NO_FINGER", "finger_detected": False,
                "hr_confidence": 0.0, "spo2": None, "spo2_confidence": 0.0,
                "hr_quality": {}, "hrv": {}, "ir": 1000, "red": 900,
                "timestamp": 0.0,
            },
        }


_pipeline_module = types.ModuleType("dashboard.python.pipelines.motion_pipeline")
_pipeline_module.MotionPipeline = CountingPipeline
sys.modules["dashboard.python.pipelines.motion_pipeline"] = _pipeline_module


def main():
    # runtime_v2 opens its capture CSV at import time, relative to cwd.
    workdir = tempfile.mkdtemp(prefix="parkinsense_verify_")
    import os
    os.chdir(workdir)

    import dashboard.python.runtime.runtime_v2 as rt

    hop = rt.ANALYSIS_HOP_SAMPLES
    window = rt.WINDOW_SIZE
    batch = rt.BATCH_SIZE

    # Count StepCounter calls without replacing its behaviour.
    #
    # `now` is injected from the runtime's own sample counter so the harness
    # simulates real-time arrival at SAMPLE_RATE_HZ. Without this the whole
    # capture is fed in a few milliseconds of wall clock and StepCounter's
    # refractory period (correctly) rejects every candidate -- an artifact of
    # replaying faster than real time, not a defect in the detector.
    step_calls = {"n": 0}
    real_update = rt.step_counter.update

    def counting_update(ax, ay, az, motion_state, now=None, **kw):
        step_calls["n"] += 1
        simulated_now = rt.state.sample_count / rt.SAMPLE_RATE_HZ
        return real_update(ax, ay, az, motion_state, now=simulated_now, **kw)

    rt.step_counter.update = counting_update

    # Count capture rows. `_csv.writer` has read-only attributes, so wrap
    # the whole object rather than patching the method.
    rows = {"n": 0}

    captured = []

    class CountingWriter:
        def __init__(self, inner):
            self._inner = inner

        def writerow(self, row):
            rows["n"] += 1
            captured.append(list(row))
            return self._inner.writerow(row)

    rt.writer = CountingWriter(rt.writer)

    # Record which sample indices an analysis ran on, so step-column
    # freshness can be asserted independently of the hop and the gait rate.
    analysis_at = set()
    _real_process = rt.pipeline.process

    def recording_process(*a, **kw):
        analysis_at.add(rt.state.sample_count)
        return _real_process(*a, **kw)

    rt.pipeline.process = recording_process

    # --- Drive synthetic packets ------------------------------------------
    # az carries a 2 Hz, 0.5 g oscillation on top of 1 g gravity: a crude
    # but sufficient stand-in for gait, so the real StepCounter produces
    # steps at roughly 120 spm and the step columns actually vary.
    import math

    n_packets = 400
    gait_hz = 2.0
    n = 0
    for p in range(n_packets):
        payload = struct.pack(rt.HEADER_FORMAT, 1, 0, 0, p * batch * rt.SAMPLE_PERIOD_US)
        for s in range(batch):
            t = n / rt.SAMPLE_RATE_HZ
            az_g = 1.0 + 0.5 * math.sin(2 * math.pi * gait_hz * t)
            payload += struct.pack(
                rt.SAMPLE_FORMAT,
                100, 200, int(az_g * rt.ACCEL_COUNTS_PER_G),
                10, 20, 30,         # gx, gy, gz counts
                50_000, 40_000,     # ir, red
            )
            n += 1
        rt.notification_handler(None, payload)

    total_samples = n_packets * batch
    pipe = rt.pipeline

    print(f"samples fed            : {total_samples}")
    print(f"window size            : {window}")
    print(f"analysis hop           : {hop} samples "
          f"({rt.ANALYSIS_HOP_SECONDS:.2f} s)")
    print("-" * 46)
    print(f"pipeline.process calls : {pipe.process_calls}")
    print(f"pipeline.ingest calls  : {pipe.ingest_calls}")
    print(f"StepCounter.update     : {step_calls['n']}")
    print(f"capture rows written   : {rows['n']}")
    print("-" * 46)

    failures = []

    # 1. Analysis is decimated to the hop.
    analysable = total_samples - window + 1
    expected_analyses = 1 + (analysable - 1) // hop
    if pipe.process_calls != expected_analyses:
        failures.append(
            f"analysis count {pipe.process_calls} != expected {expected_analyses}"
        )
    if pipe.process_calls >= analysable:
        failures.append("analysis is still running per-sample")

    # 2. PPG ingestion is NOT decimated.
    if pipe.ingest_calls != total_samples:
        failures.append(
            f"PPG ingested {pipe.ingest_calls} of {total_samples} samples "
            "-- ingestion must stay per-sample"
        )

    # 3. StepCounter sees every sample once a motion state exists.
    #    It is skipped only for samples before the first analysis, plus one
    #    priming call on the first analysis itself.
    expected_steps = total_samples - window + 1
    if step_calls["n"] != expected_steps:
        failures.append(
            f"StepCounter called {step_calls['n']} times, expected {expected_steps}"
        )

    # 4. Raw capture keeps full sample-rate resolution.
    expected_rows = total_samples - window + 1
    if rows["n"] != expected_rows:
        failures.append(
            f"capture rows {rows['n']} != expected {expected_rows} "
            "-- raw signal resolution was lost"
        )

    # 5. Column time bases. Columns that describe a *sample* must advance
    #    every row; columns that describe a *window* may forward-fill.
    #    Sampling a per-sample quantity at the analysis rate would quantise
    #    it to the hop, which is a silent loss of recorded resolution.
    header = rt.CAPTURE_COLUMNS
    idx = {name: i for i, name in enumerate(header)}

    def distinct(col):
        return len({row[idx[col]] for row in captured})

    # sample_count advances once per sample, so it must be unique per row
    # (it is the natural row index for offline analysis).
    if distinct("sample_count") != rows["n"]:
        failures.append(
            f"column 'sample_count' has {distinct('sample_count')} distinct "
            f"values across {rows['n']} rows -- it is not unique per row and "
            "cannot serve as a row index"
        )

    # packet_count legitimately changes only once per BLE packet, so the
    # discriminator is whether it tracks packets or the (much slower)
    # analysis rate.
    pkt_distinct = distinct("packet_count")
    if pkt_distinct <= pipe.process_calls:
        failures.append(
            f"column 'packet_count' changed only {pkt_distinct} times, at or "
            f"below the analysis rate ({pipe.process_calls}) -- it is being "
            "forward-filled instead of taken from the current packet"
        )
    print(f"distinct packet_count values: {pkt_distinct} "
          f"(expected ~{rows['n'] // batch})")

    # Step columns come from a per-sample streaming detector. If they were
    # sampled at the analysis rate instead, step *timing* would be quantised
    # to the hop -- silently destroying the resolution gait and cadence
    # analysis depend on.
    #
    # Comparing "distinct step values" against "number of analyses" does NOT
    # discriminate: at a 0.5 s hop and ~2 steps/s the two rates coincide.
    # The hop-independent test is whether the step column ever advances on a
    # row where no analysis ran -- that is only possible if it is written
    # per sample.
    final_steps = captured[-1][idx["steps"]]
    step_changes = [
        captured[i][idx["sample_count"]]
        for i in range(1, len(captured))
        if captured[i][idx["steps"]] != captured[i - 1][idx["steps"]]
    ]
    changes_off_analysis = [s for s in step_changes if s not in analysis_at]

    print(f"step increments             : {len(step_changes)} "
          f"(final count: {final_steps}, analyses: {pipe.process_calls})")
    print(f"  ...on non-analysis rows   : {len(changes_off_analysis)}")

    if final_steps in (None, 0):
        failures.append(
            "synthetic gait produced no steps -- the step-resolution check "
            "cannot discriminate; fix the stimulus before trusting this test"
        )
    elif not changes_off_analysis:
        failures.append(
            f"all {len(step_changes)} step increments landed on analysis rows "
            "-- the step column is being sampled at the analysis rate instead "
            "of written per sample"
        )

    # Windowed columns are expected to forward-fill: far fewer distinct
    # values than rows, bounded by the number of analyses.
    tremor_distinct = distinct("tremor_score")
    if tremor_distinct > pipe.process_calls:
        failures.append(
            f"windowed column 'tremor_score' changed {tremor_distinct} times "
            f"but only {pipe.process_calls} analyses ran"
        )

    print(f"distinct sample_count values: {distinct('sample_count')} "
          f"(rows: {rows['n']})")
    print(f"distinct tremor_score values: {tremor_distinct} "
          f"(analyses: {pipe.process_calls})")

    reduction = analysable / pipe.process_calls
    print(f"analysis workload reduction: {reduction:.1f}x")
    print("-" * 46)

    if failures:
        for f in failures:
            print(f"FAIL: {f}")
        return 1

    print("PASS: all scheduling invariants hold")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
