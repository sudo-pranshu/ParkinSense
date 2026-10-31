import numpy as np
import pandas as pd
import pytest

from parkinsense.activity.step_counter import StepCounter
from parkinsense.analytics.baseline import DayRecord, PersonalBaseline
from parkinsense.datasets import splits
from parkinsense.synthetic import signals as S


def _count(sig, state="ACTIVE"):
    c = StepCounter(sample_rate=104)
    for i in range(sig.n):
        r = c.update(sig.ax[i], sig.ay[i], sig.az[i], state, now=i / 104)
    return r


def test_walking_count_within_25pct():
    for seed in (0, 1, 2):
        s = S.walking(seconds=60, seed=seed)
        assert abs(_count(s)["steps"] - s.true_steps) / s.true_steps < 0.25


def test_rest_gate_counts_nothing():
    assert _count(S.walking(seconds=30, seed=0), state="REST")["steps"] == 0


def test_walking_state_key_present():
    assert _count(S.walking(seconds=20, seed=0))["walking_state"] in ("WALKING", "NOT_WALKING")


def _windows(n_subj=4, per=20):
    return pd.DataFrame({"subject_id": np.repeat([f"s{i}" for i in range(n_subj)], per),
                         "recording_id": np.repeat([f"r{i}" for i in range(n_subj)], per),
                         "window_start_s": np.tile(np.arange(per) * 0.5, n_subj)})


def test_group_split_has_no_leakage():
    tr, te = splits.group_split(_windows(), 0.25)
    splits.assert_no_leakage(tr, te)
    assert len(tr) and len(te)


def test_leakage_is_detected():
    df = _windows()
    with pytest.raises(AssertionError):
        splits.assert_no_leakage(df.iloc[:30], df.iloc[25:])


def test_temporal_split_guard_gap():
    df = _windows(1, 200)
    tr, te = splits.temporal_split(df, 0.25)
    assert te["window_start_s"].min() - (tr["window_start_s"].max() + 4.0) >= 4.0 - 1e-9


def test_baseline_needs_min_days_and_rejects_provenance_change():
    b = PersonalBaseline("tremor_time_pct")
    prov = {"pipeline_version": "3.0.0", "firmware_version": "5.0.0", "rate_status": "OK"}
    for d in range(6):
        assert b.add_day(DayRecord(f"d{d}", 10.0 + d % 2, True, prov))["status"] == "BUILDING_BASELINE"
    b.add_day(DayRecord("d6", 10.5, True, prov))
    assert b.add_day(DayRecord("d7", 30.0, True, prov))["status"] == "DEVIATION"
    moved = dict(prov, firmware_version="6.0.0")
    assert b.add_day(DayRecord("d8", 10.0, True, moved))["status"] == "NOT_COMPARABLE"
    assert b.add_day(DayRecord("d9", None, False, prov))["status"] == "INSUFFICIENT_DATA"
