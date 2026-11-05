"""
Public sleep API. Offline only: it never touches the tremor / cardiovascular path.

    from parkinsense.sleep.api import analyze_file
    report = analyze_file("capture.csv")          # or analyze(t_s, acc_g)

Everything returned is an ESTIMATE of sleep/wake from wrist movement (accelerometer
only). It is not polysomnography, not sleep staging, and has not been validated on
ParkinSense hardware. `report["estimate"]` is always True.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

from parkinsense import config as C
from parkinsense.sleep import features as F
from parkinsense.sleep import model as M
from parkinsense.sleep import night as N
from parkinsense.sleep import params as P

DISCLAIMER = ("Movement-derived sleep/wake estimate (accelerometer only). Not polysomnography, no sleep stages, "
              "not clinically validated, not validated on ParkinSense hardware.")


def analyze(t_s, acc_g, t_wall0: float | None = None, hr_t=None, hr=None) -> dict:
    """t_s: seconds (monotonic); acc_g: (n, 3) in g. Returns a JSON-serialisable report."""
    t_s = np.asarray(t_s, float)
    acc_g = np.asarray(acc_g, float)
    meta = {"sleep_algorithm_version": C.SLEEP_ALGORITHM_VERSION,
            "sleep_epoch_schema_version": C.SLEEP_EPOCH_SCHEMA_VERSION,
            "pipeline_version": C.PIPELINE_VERSION, "estimate": True, "disclaimer": DISCLAIMER,
            "model": "logistic regression on movement-context features (accelerometer only)"}
    if len(t_s) < 2 or t_s[-1] - t_s[0] < 3600:
        return {**meta, "night": {"estimate": True, "quality": C.Quality.INSUFFICIENT_DATA.value,
                                  "reason": "recording shorter than 1 h"}, "epochs": None}
    tab = F.epoch_features(t_s, acc_g, t0=float(t_s[0]), hr_t=hr_t, hr=hr)
    out = M.classify(tab, P.ACCEL)
    night = N.summarize(tab, out["state"], t_wall0)
    nw = N.nonwear_mask(tab)
    state = np.where(nw, -1, out["state"])
    return {**meta, "night": night,
            "epochs": {"t_s": tab.t.tolist(), "state": state.astype(int).tolist(),
                       "p_sleep": [None if not np.isfinite(v) else round(float(v), 4) for v in out["p_sleep"]],
                       "coverage": [round(float(v), 3) for v in tab.coverage], "nonwear": nw.astype(int).tolist(),
                       "encoding": "1 sleep, 0 wake, -1 no data / non-wear"}}


def read_acceleration(path):
    """(t_s from the first sample, acc_g (n, 3), format kind). Reads only the needed columns, so an 8 h v3 capture
    (79 columns, ~3 M rows) is not loaded whole."""
    import pandas as pd

    from parkinsense.replay.replay import _unwrap32
    cols = list(pd.read_csv(path, nrows=0).columns)
    if "device_time_us" in cols:
        kind, tcol = "capture_v3", "device_time_us"
    elif "sample_timestamp_us" in cols:
        kind, tcol = "capture_v2", "sample_timestamp_us"
    elif {"ir", "red", "timestamp"} <= set(cols):
        kind, tcol = "ble_v1_raw", "timestamp"
    else:
        raise ValueError(f"{path}: unrecognised or unsupported capture format (legacy serial logs are not supported)")
    df = pd.read_csv(path, usecols=[tcol, "ax", "ay", "az"], dtype={tcol: "int64"})
    t_us = df[tcol].to_numpy(dtype="int64")
    if kind != "capture_v3":
        t_us = _unwrap32(t_us)
    return (t_us - t_us[0]) / 1e6, df[["ax", "ay", "az"]].to_numpy(float), kind


def analyze_file(path, **kw) -> dict:
    import hashlib
    t, acc, kind = read_acceleration(path)
    rep = analyze(t, acc, **kw)
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    rep["source"] = {"path": str(path), "sha256": h.hexdigest(), "kind": kind, "rows": int(len(t))}
    return rep


def main(argv=None):
    ap = argparse.ArgumentParser(description="Offline sleep/wake estimate from a ParkinSense capture (accelerometer).")
    ap.add_argument("capture")
    ap.add_argument("--json", help="write the full report here")
    a = ap.parse_args(argv)
    rep = analyze_file(a.capture)
    if a.json:
        Path(a.json).write_text(json.dumps(rep, indent=1) + "\n")
    n = rep["night"]
    print(DISCLAIMER)
    if "tst_min" not in n:
        print(f"No sleep estimate: {n.get('reason', n.get('quality'))}")
        return 0
    print(f"sleep period {n['spt_min']} min | TST {n['tst_min']} min | WASO {n['waso_min']} min | "
          f"awakenings {n['awakenings']} | quality {n['quality']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
