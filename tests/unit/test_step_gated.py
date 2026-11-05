"""Gated step counter (opt-in): behavioural unit tests on synthetic signals. Accuracy evidence is
benchmarks/steps_bench.py on real labelled recordings, not these."""
import numpy as np
import pytest

from parkinsense import config as C
from parkinsense.activity.step_counter import StepCounter
from parkinsense.activity.step_counter_v2 import GatedStepCounter
from parkinsense.runtime.engine import RuntimeEngine

FS = 104.0


def _run(counter, a, state="ACTIVE"):
    out = None
    for i, row in enumerate(a):
        out = counter.update(row[0], row[1], row[2], state, now=i / FS)
    return out


def walk(seconds=60, cadence_hz=1.8, amp=0.4, seed=0):
    rng = np.random.default_rng(seed)
    t = np.arange(int(seconds * FS)) / FS
    z = 1 + amp * np.sin(2 * np.pi * cadence_hz * t) + 0.6 * amp * np.sin(2 * np.pi * cadence_hz / 2 * t + 1)
    return np.stack([0.2 * amp * np.sin(2 * np.pi * cadence_hz / 2 * t), 0 * t, z], 1) + rng.normal(0, 0.01, (len(t), 3))


def test_counts_regular_walking_within_tolerance():
    c = GatedStepCounter(FS)
    out = _run(c, walk(60))
    assert 0.85 * 108 <= out["steps"] <= 1.1 * 108
    assert out["cadence"] == pytest.approx(108, rel=0.1)


def test_event_times_are_ordered_unique_and_match_total():
    c = GatedStepCounter(FS)
    out = _run(c, walk(40))
    ts = np.array(c.step_event_times)
    assert len(ts) == out["steps"] and np.all(np.diff(ts) >= 0.27)


def test_rest_tremor_band_is_not_counted():
    rng = np.random.default_rng(2)
    t = np.arange(int(60 * FS)) / FS
    a = np.stack([0 * t, 0 * t, 1 + 0.15 * np.sin(2 * np.pi * 5.0 * t)], 1) + rng.normal(0, 0.005, (len(t), 3))
    assert _run(GatedStepCounter(FS), a)["steps"] <= 2


def test_still_signal_counts_nothing():
    a = np.tile([0, 0, 1.0], (int(60 * FS), 1)) + np.random.default_rng(3).normal(0, 0.003, (int(60 * FS), 3))
    assert _run(GatedStepCounter(FS), a)["steps"] == 0


def test_rest_motion_state_blocks_counting():
    assert _run(GatedStepCounter(FS), walk(40), state="REST")["steps"] == 0


def test_irregular_one_off_movements_are_not_a_walk():
    """Three isolated arm movements must not be credited as steps."""
    rng = np.random.default_rng(4)
    a = np.tile([0, 0, 1.0], (int(40 * FS), 1)) + rng.normal(0, 0.005, (int(40 * FS), 3))
    for k in (10, 20, 31):
        a[int(k * FS): int(k * FS) + 20, 2] += 0.5
    assert _run(GatedStepCounter(FS), a)["steps"] <= 3


def test_output_keys_match_production_counter():
    a = walk(5)
    assert set(_run(GatedStepCounter(FS), a)) == set(_run(StepCounter(FS), a, "ACTIVE"))


def test_break_continuity_keeps_totals_and_reset_clears():
    c = GatedStepCounter(FS)
    _run(c, walk(30))
    n = c.steps
    c.break_continuity()
    assert c.steps == n
    c.reset()
    assert c.steps == 0 and len(c.step_event_times) == 0


def test_engine_default_is_unchanged_and_gated_is_opt_in():
    assert isinstance(RuntimeEngine().steps, StepCounter) and RuntimeEngine().step_algorithm == "default"
    assert isinstance(RuntimeEngine(step_counter="gated").steps, GatedStepCounter)
    with pytest.raises(ValueError):
        RuntimeEngine(step_counter="typo")
    assert C.STEP_ALGORITHM_VERSIONS["default"] == "1.1"
