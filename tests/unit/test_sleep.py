"""Sleep subsystem: unit tests on synthetic edge cases (NOT accuracy evidence - that is benchmarks/sleep_bench.py)."""
import numpy as np
import pytest

from parkinsense import config as C
from parkinsense.sleep import features as F
from parkinsense.sleep import model as M
from parkinsense.sleep import params as P
from parkinsense.sleep.api import analyze

from helpers import NIGHT_FS, synthetic_night as _night  # noqa: E402

FS = NIGHT_FS


def test_epoch_count_and_alignment():
    t, acc = _night(0.5, 0, 0)
    tab = F.epoch_features(t, acc, t0=0.0, fs=FS)
    assert len(tab) == int(len(t) / FS // F.EPOCH_S)
    assert np.all(tab.coverage > 0.99)


def test_still_night_is_sleep_and_wake_ends_are_wake():
    t, acc = _night()
    tab = F.epoch_features(t, acc, t0=0.0, fs=FS)
    state = M.classify(tab, P.ACCEL)["state"]
    mid = state[len(state) // 4: -len(state) // 4]
    assert (mid == 1).mean() > 0.95
    assert (state[:30] == 0).mean() > 0.9
    assert (state[-30:] == 0).mean() > 0.9


def test_night_summary_is_labelled_estimate_and_consistent():
    t, acc = _night()
    rep = analyze(t, acc)
    n = rep["night"]
    assert rep["estimate"] is True and n["estimate"] is True
    assert "polysomnography" in rep["disclaimer"].lower()
    assert n["quality"] == C.Quality.VALID.value
    assert abs(n["tst_min"] - 360) < 30
    assert n["tst_min"] + n["waso_min"] <= n["spt_min"] + 1e-6
    assert 0.9 < n["period_efficiency"] <= 1.0
    assert rep["sleep_algorithm_version"] == C.SLEEP_ALGORITHM_VERSION
    # no invented stages anywhere in the report
    assert not {"rem", "deep", "light", "n1", "n2", "n3", "stage"} & {k.lower() for k in n}


def test_short_recording_is_insufficient_not_a_fabricated_night():
    t, acc = _night(0.4, 0, 0)
    rep = analyze(t, acc)
    assert rep["night"]["quality"] == C.Quality.INSUFFICIENT_DATA.value
    assert "tst_min" not in rep["night"] and rep["epochs"] is None


def test_all_wake_has_no_sleep_period():
    t, acc = _night(0.0, 90, 0)
    n = analyze(t, acc)["night"]
    assert n["quality"] == C.Quality.INSUFFICIENT_DATA.value and "tst_min" not in n


def test_nonwear_flat_signal_is_not_reported_as_sleep():
    n = int(4 * 3600 * FS)
    acc = np.tile([0.0, 0.0, 1.0], (n, 1))          # perfectly constant: sensor on a table
    rep = analyze(np.arange(n) / FS, acc)
    assert rep["night"]["nonwear_min"] > 200
    assert "tst_min" not in rep["night"]
    assert set(rep["epochs"]["state"]) == {-1}


def test_gap_epochs_are_marked_missing():
    t, acc = _night(3, 10, 10)
    keep = ~((t > 3600) & (t < 3600 + 1800))       # 30 min dropout
    rep = analyze(t[keep], acc[keep])
    st = np.array(rep["epochs"]["state"])
    assert (st[(np.array(rep["epochs"]["t_s"]) > 3700) & (np.array(rep["epochs"]["t_s"]) < 5300)] == -1).all()


def test_params_are_consistent_with_feature_list():
    assert len(P.ACCEL["logistic"]["weights"]) == len(P.FEATURES_ACCEL) == len(M.ACCEL_FEATURES)
    assert P.ACCEL["smooth"] is False and 0 < P.ACCEL["threshold"] < 1
    assert P.SLEEP_ALGORITHM_VERSION == C.SLEEP_ALGORITHM_VERSION


def test_loso_training_never_sees_the_held_out_subject():
    """Changing the held-out subject's labels or features must not change the model fitted for it."""
    from benchmarks import sleep_bench as B
    rng = np.random.default_rng(1)

    def subj(k):
        n = 400
        X = rng.normal(size=(n, 6))
        y = (X[:, 0] + 0.3 * rng.normal(size=n) > 0).astype(int)
        tab = type("T", (), {"dg_max": np.ones(n)})()
        return {"subject": k, "X": X, "Xhr": X, "y": y, "tab": tab}

    data = [subj(k) for k in range(5)]
    a = B.fit(data[1:])
    data[0]["y"] = 1 - data[0]["y"]
    data[0]["X"] = data[0]["X"] * 10
    b = B.fit(data[1:])
    assert a["logistic"]["weights"] == b["logistic"]["weights"] and a["threshold"] == b["threshold"]


def test_analyze_file_reads_v3_and_wrapped_v1_captures(tmp_path):
    import pandas as pd

    from parkinsense.sleep.api import analyze_file, read_acceleration
    fs = 20.0
    n = int(2.2 * 3600 * fs)
    rng = np.random.default_rng(5)
    acc = np.tile([0.0, 0.0, 1.0], (n, 1)) + rng.normal(0, 0.004, (n, 3))
    for k in range(0, n - 100, int(150 * fs)):                    # a twitch every 2.5 min
        acc[k:k + 20, 0] += 0.12
    t_us = (np.arange(n) / fs * 1e6).astype("int64") + 5_000_000
    v3 = pd.DataFrame({"device_time_us": t_us, "ax": acc[:, 0], "ay": acc[:, 1], "az": acc[:, 2], "extra": 1.0})
    v3.to_csv(tmp_path / "v3.csv", index=False)
    v1 = pd.DataFrame({"timestamp": t_us % 2 ** 32, "ax": acc[:, 0], "ay": acc[:, 1], "az": acc[:, 2],
                       "ir": 1, "red": 1})                        # 32-bit wrap inside the file (2.2 h > 71 min)
    v1.to_csv(tmp_path / "v1.csv", index=False)
    for name, kind in (("v3.csv", "capture_v3"), ("v1.csv", "ble_v1_raw")):
        t, a, k = read_acceleration(tmp_path / name)
        assert k == kind and np.all(np.diff(t) > 0) and abs(t[-1] - (n - 1) / fs) < 1e-3
    rep = analyze_file(tmp_path / "v1.csv")
    assert rep["source"]["rows"] == n and len(rep["source"]["sha256"]) == 64
    assert rep["night"]["estimate"] is True
    with pytest.raises(ValueError):
        pd.DataFrame({"timestamp": [1, 2], "ax": [0, 0], "ay": [0, 0], "az": [1, 1]}).to_csv(tmp_path / "bad.csv", index=False)
        read_acceleration(tmp_path / "bad.csv")
