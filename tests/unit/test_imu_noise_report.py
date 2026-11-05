import json

import numpy as np
import pandas as pd

from benchmarks.imu_noise_report import main, report


def _csv(path, sd_g, fs=104, seconds=120, seed=0):
    rng = np.random.default_rng(seed)
    n = fs * seconds
    t = (np.arange(n) * 1e6 / fs).astype("int64")
    acc = rng.normal(0, sd_g, (n, 3)) + np.array([0, 0, 1.0])
    df = pd.DataFrame({"device_time_us": t, "ax": acc[:, 0], "ay": acc[:, 1], "az": acc[:, 2],
                       "gx": rng.normal(0, 0.1, n), "gy": rng.normal(0, 0.1, n), "gz": rng.normal(0, 0.1, n),
                       "ir": 1500, "flags": 0})
    df.to_csv(path, index=False)


def test_report_recovers_known_noise(tmp_path):
    p = tmp_path / "a.csv"
    _csv(p, 0.0003)
    r = report([p], "t")
    assert abs(r["median_rate_hz"] - 104) < 0.5 and r["gaps_ge_5s"] == 0
    assert 0.25 < r["acc_sd_mg"]["p50"] < 0.35
    assert r["table_p99_below_half_threshold"] is True
    assert 0.05 < r["gyro_sd_dps"]["p50"] < 0.15


def test_noisy_table_is_flagged_and_margin_computed(tmp_path):
    table, worn = tmp_path / "t.csv", tmp_path / "w.csv"
    _csv(table, 0.0003)
    _csv(worn, 0.003, seed=1)
    out = tmp_path / "t.json"
    main([str(table), "--label", "W1-A", "--out", str(out)])
    assert json.loads(out.read_text())["label"] == "W1-A"
    wout = tmp_path / "w.json"
    main([str(worn), "--label", "W2", "--table-json", str(out), "--out", str(wout)])
    w = json.loads(wout.read_text())
    assert w["margin_worn_p01_over_table_p99"] > 2
    assert w["table_p99_below_half_threshold"] is False
