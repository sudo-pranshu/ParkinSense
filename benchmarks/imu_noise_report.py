"""
Per-epoch IMU stillness statistics of ParkinSense captures, for hardware tests W1 (table) and W2 (worn still).

    python -m benchmarks.imu_noise_report capture.csv [more.csv ...] --label W1-surface-A [--out w1_a.json]
    python -m benchmarks.imu_noise_report w2.csv --label W2-seated --table-json w1_a.json w1_b.json w1_c.json

Reports the distribution of 1 s epoch max-axis accelerometer SD (mg) and gyro SD (dps), the sample rate, gaps and fault
flags. With --table-json it also gives the W2/W1 margin: worn 1st-percentile SD divided by the largest table 99th
percentile (plan criterion: >= 2). It reports numbers; it does not declare a test passed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np

from benchmarks.wear_bench import epoch_sd_max
from parkinsense.wear.api import read_capture
from parkinsense.wear import WearConfig

QS = (0.01, 0.05, 0.25, 0.5, 0.75, 0.95, 0.99)


def _q(x):
    return {f"p{int(q * 100):02d}": round(float(v), 4) for q, v in zip(QS, np.quantile(x, QS))}


def report(paths, label):
    parts, sha = [], []
    for p in paths:
        d = read_capture(p)
        h = hashlib.sha256(Path(p).read_bytes()).hexdigest()
        sha.append({"path": str(p), "sha256": h, "rows": int(len(d["t"])), "kind": d["kind"]})
        parts.append(d)
    acc_sd, gyro_sd, dur, gaps, imu_fault, rate = [], [], 0.0, 0, 0, []
    for d in parts:
        t = d["t"]
        ok = d["imu_ok"]
        imu_fault += int((~ok).sum())
        t, acc, gyro = t[ok], d["acc"][ok], d["gyro"][ok]
        if len(t) < 100:
            continue
        dt = np.diff(t)
        rate.append(1.0 / float(np.median(dt)))
        gaps += int((dt > 5.0).sum())
        dur += float(t[-1] - t[0])
        acc_sd.append(epoch_sd_max(t, acc)[1] * 1000.0)       # g -> mg
        gyro_sd.append(epoch_sd_max(t, gyro)[1])              # dps
    if not acc_sd:
        raise SystemExit("no usable IMU samples")
    a, g = np.concatenate(acc_sd), np.concatenate(gyro_sd)
    thr_mg = WearConfig().still_acc_sd_g * 1000.0
    return {"label": label, "sources": sha, "duration_s": round(dur, 1), "epochs": int(len(a)),
            "median_rate_hz": round(float(np.median(rate)), 2), "gaps_ge_5s": gaps, "imu_fault_samples": imu_fault,
            "acc_sd_mg": _q(a), "gyro_sd_dps": _q(g),
            "default_still_threshold_mg": thr_mg,
            "table_p99_below_half_threshold": bool(np.quantile(a, 0.99) < thr_mg / 2)}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("captures", nargs="+")
    ap.add_argument("--label", required=True)
    ap.add_argument("--out")
    ap.add_argument("--table-json", nargs="*", default=[], help="W1 reports (all three surfaces) for the W2 margin")
    a = ap.parse_args(argv)
    rep = report(a.captures, a.label)
    if a.table_json:
        p99 = max(json.loads(Path(p).read_text())["acc_sd_mg"]["p99"] for p in a.table_json)
        rep["margin_worn_p01_over_table_p99"] = round(rep["acc_sd_mg"]["p01"] / p99, 3)
        rep["table_p99_max_mg"] = p99
    text = json.dumps(rep, indent=1)
    print(text)
    if a.out:
        Path(a.out).write_text(text + "\n")


if __name__ == "__main__":
    main()
