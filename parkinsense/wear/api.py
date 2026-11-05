"""
Offline wear analysis of a recorded capture.

    parkinsense-wear recordings/<session>/capture.csv [--set still_acc_sd_g=0.001 ...] [--out wear.json]

Reads capture_v3 / capture_v2 / ble_v1_raw files (same detection as the sleep API). The packet `flags` column, when
present, marks IMU_FAULT / PPG_FAULT packets so faulted data is not read as stillness or as lost contact. The result is
an INFERENCE from motion and optical level; it is not a measurement of wear (docs/architecture/WEAR_AWARE_ACQUISITION.md).
"""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
from pathlib import Path

import numpy as np

from parkinsense.protocol.packet import PacketFlags
from parkinsense.wear import WearConfig, analyze_arrays


def read_capture(path):
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
        raise ValueError(f"{path}: unrecognised capture format")
    use = [tcol, "ax", "ay", "az", "gx", "gy", "gz", "ir"] + (["flags"] if "flags" in cols else [])
    df = pd.read_csv(path, usecols=use, dtype={tcol: "int64"})
    t_us = df[tcol].to_numpy("int64")
    if kind != "capture_v3":
        t_us = _unwrap32(t_us)
    flags = df["flags"].fillna(0).to_numpy("int64") if "flags" in df else np.zeros(len(df), "int64")
    return {"t": (t_us - t_us[0]) / 1e6, "acc": df[["ax", "ay", "az"]].to_numpy(float),
            "gyro": df[["gx", "gy", "gz"]].to_numpy(float), "ir": df["ir"].to_numpy(float),
            "imu_ok": (flags & int(PacketFlags.IMU_FAULT)) == 0, "ppg_ok": (flags & int(PacketFlags.PPG_FAULT)) == 0,
            "kind": kind}


def analyze_file(path, config: WearConfig | None = None) -> dict:
    d = read_capture(path)
    m = analyze_arrays(d["t"], d["acc"], d["gyro"], d["ir"], d["imu_ok"], d["ppg_ok"], config=config, keep_epochs=False)
    rep = m.summary()
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    rep["source"] = {"path": str(path), "sha256": h.hexdigest(), "kind": d["kind"], "rows": int(len(d["t"]))}
    return rep


def main(argv=None):
    ap = argparse.ArgumentParser(description="Infer wear state from a ParkinSense capture (offline).")
    ap.add_argument("capture")
    ap.add_argument("--set", action="append", default=[], metavar="KEY=VALUE", help="override a WearConfig field")
    ap.add_argument("--out")
    a = ap.parse_args(argv)
    fields = {f.name: f for f in dataclasses.fields(WearConfig)}
    kw = {}
    for item in a.set:
        k, v = item.split("=", 1)
        if k not in fields:
            ap.error(f"unknown WearConfig field {k!r}; choose from {sorted(fields)}")
        kw[k] = float(v)
    rep = analyze_file(a.capture, WearConfig(**kw))
    text = json.dumps(rep, indent=1)
    print(text if not a.out else json.dumps({k: rep[k] for k in ("final_state", "time_in_state_s", "transition_count")}, indent=1))
    if a.out:
        Path(a.out).write_text(text + "\n")


if __name__ == "__main__":
    main()
