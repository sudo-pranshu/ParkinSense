import os

import numpy as np
import pytest

from helpers import packets, run_engine
from parkinsense import config as C
from parkinsense.protocol import packet as P
from parkinsense.runtime import engine as E
from parkinsense.synthetic import signals as S


def test_import_has_no_side_effects(tmp_path, monkeypatch):
    # v2 opened (and truncated) realtime_capture_v2.csv at import (review P0-1)
    monkeypatch.chdir(tmp_path)
    import importlib
    importlib.reload(E)
    E.RuntimeEngine()
    assert os.listdir(tmp_path) == []


def test_rows_schema_and_analysis_markers():
    eng = E.RuntimeEngine()
    rows, analyses = run_engine(eng, S.rest(seconds=12, seed=0))
    assert set(rows[0]) == set(E.CAPTURE_COLUMNS)
    fresh = [r for r in rows if r["is_analysis_row"]]
    assert len(fresh) == len(analyses) == eng.analysis_seq
    seqs = [r["analysis_seq"] for r in fresh]
    assert seqs == list(range(1, len(seqs) + 1))
    # one analysis per 0.5 s hop after the 4 s window fills
    assert abs(len(fresh) - ((12 - 4) / C.ANALYSIS_HOP_SECONDS + 1)) <= 2
    # Issue #1 invariants: sample_count is a unique row index, workload reduced ~52x
    assert len({r["sample_count"] for r in rows}) == len(rows)
    assert len(rows) / len(fresh) > 40


def test_steps_are_per_sample_not_forward_filled():
    eng = E.RuntimeEngine()
    rows, _ = run_engine(eng, S.walking(seconds=30, seed=1))
    inc = [i for i in range(1, len(rows)) if (rows[i]["steps"] or 0) > (rows[i - 1]["steps"] or 0)]
    assert inc and sum(not rows[i]["is_analysis_row"] for i in inc) > 0.8 * len(inc)


def test_bad_packet_rejected_and_counted():
    eng = E.RuntimeEngine()
    r = eng.process_packet(b"\x01" * 50)
    assert r.rejected and eng.bad_packets == 1 and eng.packet_count == 0


def test_gap_resets_windows_and_is_recorded():
    eng = E.RuntimeEngine()
    sig = S.rest(seconds=10, seed=0)
    for d in packets(sig):
        eng.process_packet(d)
    for d in packets(sig, t0_us=1_000_000 + 30_000_000):      # 20 s later
        eng.process_packet(d)
    assert eng.resets == 1 and eng.integrity()["timestamp_gaps"] == 1


def test_sequence_loss_detected_for_v2():
    eng = E.RuntimeEngine()
    sig = S.rest(seconds=3, seed=0)
    ps = list(packets(sig, version=2))
    for i, d in enumerate(ps):
        if i != 5:
            eng.process_packet(d)
    assert eng.seq.lost == 1


def test_timestamp_wrap_is_continuous():
    eng = E.RuntimeEngine()
    sig = S.rest(seconds=8, seed=0)
    rows, _ = run_engine(eng, sig, t0_us=(1 << 32) - 2_000_000)
    t = np.array([r["device_time_us"] for r in rows])
    assert np.all(np.diff(t) > 0) and eng.unwrapper.wraps == 1 and eng.resets == 0


def test_rate_validation_flags_wrong_clock():
    eng = E.RuntimeEngine()
    sig = S.rest(seconds=15, seed=0)
    # device actually sampling 6 % slow: header timestamps spaced 6 % wider
    n = (sig.n // 10) * 10
    for p, start in enumerate(range(0, n, 10)):
        rows = [(sig.ax[i], sig.ay[i], sig.az[i], sig.gx[i], sig.gy[i], sig.gz[i], 1600, 600)
                for i in range(start, start + 10)]
        eng.process_packet(P.encode(rows, int(start * P.SAMPLE_PERIOD_US * 1.06)))
    assert eng.rate_status() == "INVALID"
    assert eng.metrics["tremor_quality"] == "DATA_GAP"


def test_analysis_errors_are_surfaced(monkeypatch):
    eng = E.RuntimeEngine()

    def boom(*a, **k):
        raise ValueError("synthetic failure")
    monkeypatch.setattr(eng.motion, "process", boom)
    with pytest.raises(RuntimeError, match="consecutive analysis failures"):
        run_engine(eng, S.rest(seconds=8, seed=0))
    assert eng.analysis_errors >= E.MAX_CONSECUTIVE_ANALYSIS_ERRORS


def test_ppg_rate_contract():
    eng = E.RuntimeEngine()
    assert eng.ppg.fs == C.PPG_SLOT_RATE_HZ == C.SAMPLE_RATE_HZ
