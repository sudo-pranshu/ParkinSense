"""
Performance floors on synthetic ground truth (small N for CI). These guard
against regressions; they are not accuracy claims. Full benchmark:
python -m benchmarks.run_benchmarks
"""
import numpy as np

from helpers import run_engine
from parkinsense.runtime.engine import RuntimeEngine
from parkinsense.synthetic import signals as S


def _fraction_tremor(sig):
    _, an = run_engine(RuntimeEngine(), sig)
    late = [a for a in an if a["signal_time_s"] >= 8]
    return np.mean([a["classification"] == "TREMOR" for a in late])


def test_tremor_sensitivity_floor():
    for scen in ("rest_tremor", "strong_tremor", "subtle_tremor"):
        for seed in (20, 21):
            assert _fraction_tremor(S.SCENARIOS[scen](seconds=20, seed=seed)) >= 0.9, scen


def test_tremor_specificity_floor():
    for scen in ("rest", "voluntary", "walking", "vibration", "non_pd_oscillation"):
        for seed in (20, 21):
            assert _fraction_tremor(S.SCENARIOS[scen](seconds=20, seed=seed)) <= 0.02, scen


def test_hr_error_floor_v2_path():
    p = S.ppg(seconds=40, seed=22)
    ir, red = S.ppg_to_slots(p, path="v2")
    _, an = run_engine(RuntimeEngine(), S.rest(seconds=40, seed=22, micro_rms=0.5), ir=ir, red=red)
    hr = [a["heart_rate"] for a in an if a["signal_time_s"] >= 20 and a["hr_quality_state"] == "VALID"]
    assert hr and abs(np.median(hr) - p.true_hr_bpm) < 2.0


def test_no_steps_during_rest_tremor():
    _, an = run_engine(RuntimeEngine(), S.rest_tremor(seconds=40, seed=23, amp=60))
    assert (an[-1]["steps"] or 0) <= 5
