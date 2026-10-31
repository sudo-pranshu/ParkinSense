"""
Deterministic replay of recorded sessions through the *real* runtime.

    python -m parkinsense.replay.replay data/reference/ble_v1_104hz/x.csv --out replays/
    python -m parkinsense.replay.replay a.csv --compare replays/run1 replays/run2

How it stays faithful:
  * rows are re-framed into the original BLE packets (by `packet_count` when
    the capture has it, otherwise consecutive groups of 10) and re-encoded
    with the recorded `packet_version`; `encode` rounds to the nearest count,
    making it the exact inverse of `decode`, so the engine sees the original
    integers;
  * packets go through `RuntimeEngine.process_packet` -- the same code path
    as live BLE. There is no simplified copy of the pipeline;
  * all temporal logic runs on device time, so speed does not affect output.
    `--realtime` only paces delivery for visual inspection.

Supported inputs (auto-detected; docs/validation/REPLAY_AND_DATASETS.md):
  * capture schema v3 (`capture.csv`, this runtime)
  * capture schema v2 (`realtime_capture_v2.csv`, runtime 2.x)
  * BLE v1 raw logs (`timestamp, ax..gz, ir, red, packet_version`; timestamp in us)
  * legacy serial logs (`timestamp, ax..gz`; timestamp in ms, ~23 Hz). These
    are NOT 104 Hz and are only replayable with `--resample` (linear
    interpolation onto a 104 Hz grid; recorded in metadata, and unsuitable
    for any content above the original Nyquist, ~11 Hz).

Historical data is never reinterpreted silently: every replay records the
source file hash, the source pipeline version (if present) and the replay
pipeline version.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from parkinsense import config as C
from parkinsense.protocol import packet as P
from parkinsense.runtime.engine import CAPTURE_COLUMNS, RuntimeEngine
from parkinsense.runtime.recorder import atomic_write_json

IMU = ["ax", "ay", "az", "gx", "gy", "gz"]


@dataclass
class Source:
    kind: str
    frame: pd.DataFrame          # columns: t_us, ax..gz, ir, red, version, packet_id
    meta: dict


def sha256(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load(path, resample: bool = False) -> Source:
    df = pd.read_csv(path, low_memory=False)
    cols = set(df.columns)
    meta = {"source": str(path), "source_sha256": sha256(path), "rows": len(df)}
    if "device_time_us" in cols:
        kind = "capture_v3"
        t = df["device_time_us"].astype("int64")
        pid = df["packet_count"]
    elif "sample_timestamp_us" in cols:
        kind = "capture_v2"
        t = _unwrap32(df["sample_timestamp_us"].astype("int64").to_numpy())
        pid = df["packet_count"]
    elif {"ir", "red"} <= cols and "timestamp" in cols:
        kind = "ble_v1_raw"
        t = _unwrap32(df["timestamp"].astype("int64").to_numpy())
        pid = np.arange(len(df)) // P.BATCH_SIZE
    elif set(IMU) <= cols and "timestamp" in cols:
        kind = "legacy_serial"
        if not resample:
            raise ValueError(f"{path}: legacy serial log (~23 Hz, ms timestamps); use --resample")
        return _resampled(df, meta)
    else:
        raise ValueError(f"{path}: unrecognised capture format")
    for c in ("pipeline_version", "firmware_version"):
        if c in cols:
            meta[f"source_{c}"] = str(df[c].dropna().iloc[0]) if df[c].notna().any() else None
    fr = pd.DataFrame({"t_us": np.asarray(t, dtype="int64"), **{c: df[c].astype(float) for c in IMU},
                       "ir": df["ir"].fillna(0).astype("int64") if "ir" in cols else 0,
                       "red": df["red"].fillna(0).astype("int64") if "red" in cols else 0,
                       "version": df["packet_version"].fillna(1).astype(int) if "packet_version" in cols else 1,
                       "packet_id": np.asarray(pid)})
    meta["kind"] = kind
    return Source(kind, fr, meta)


def _unwrap32(t: np.ndarray) -> np.ndarray:
    d = np.diff(t)
    wraps = np.concatenate([[0], np.cumsum(d < -(1 << 31))])
    return t + wraps * (1 << 32)


def _resampled(df, meta) -> Source:
    t_ms = df["timestamp"].to_numpy(dtype=float)
    t_s = (t_ms - t_ms[0]) / 1000.0
    keep = np.concatenate([[True], np.diff(t_s) > 0])
    t_s = t_s[keep]
    grid = np.arange(0, t_s[-1], 1.0 / C.SAMPLE_RATE_HZ)
    out = {c: np.interp(grid, t_s, df[c].to_numpy(dtype=float)[keep]) for c in IMU}
    n = (len(grid) // P.BATCH_SIZE) * P.BATCH_SIZE
    fr = pd.DataFrame({"t_us": (1_000_000 + grid[:n] * 1e6).astype("int64"),
                       **{c: out[c][:n] for c in IMU}, "ir": 1600, "red": 600,
                       "version": 2, "packet_id": np.arange(n) // P.BATCH_SIZE})
    meta.update({"kind": "legacy_serial_resampled",
                 "original_rate_hz": round(len(t_s) / t_s[-1], 2),
                 "warning": "linearly interpolated to 104 Hz; no information above original Nyquist; "
                            "PPG channels are synthetic no-finger constants; encoded as protocol v2 "
                            "so +-512 dps fits"})
    return Source("legacy_serial_resampled", fr, meta)


def packets(src: Source):
    """Yield (bytes, device_time_s) re-framed into original packets."""
    fr = src.frame
    seq = 0
    for _, g in fr.groupby("packet_id", sort=False):
        rows = g[["ax", "ay", "az", "gx", "gy", "gz", "ir", "red"]].to_numpy()
        ver = int(g["version"].iloc[0])
        t0 = int(g["t_us"].iloc[0])
        for start in range(0, len(rows) - P.BATCH_SIZE + 1, P.BATCH_SIZE):   # partial packets dropped
            chunk = [tuple(r) for r in rows[start:start + P.BATCH_SIZE]]
            yield P.encode(chunk, t0 + start * P.SAMPLE_PERIOD_US, version=ver, seq=seq), \
                (t0 + start * P.SAMPLE_PERIOD_US) / 1e6
            seq += 1


def replay(path, out_dir=None, resample=False, realtime=False, speed=1.0,
           engine_kwargs=None) -> dict:
    src = load(path, resample=resample)
    eng = RuntimeEngine(session_id="replay", **(engine_kwargs or {}))
    rows, analyses = [], []
    t_first = None
    wall0 = time.monotonic()
    for data, t in packets(src):
        if t_first is None:
            t_first = t
        if realtime:
            lag = (t - t_first) / speed - (time.monotonic() - wall0)
            if lag > 0:
                time.sleep(lag)
        res = eng.process_packet(data, host_monotonic=t, host_wall=0.0)
        rows.extend(res.rows)
        analyses.extend(res.analyses)
    summary = {
        "source": src.meta, "replay_pipeline_version": C.PIPELINE_VERSION,
        "capture_schema_version": C.CAPTURE_SCHEMA_VERSION,
        "samples": eng.sample_count, "analyses": eng.analysis_seq,
        "device_rate_hz": eng.device_rate_hz(), "rate_status": eng.rate_status(),
        "integrity": eng.integrity(),
        "outputs": summarize(analyses),
    }
    if out_dir:
        out = Path(out_dir)
        out.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(rows, columns=CAPTURE_COLUMNS).to_csv(out / "capture.csv", index=False)
        atomic_write_json(out / "replay_summary.json", summary)
    return {"summary": summary, "rows": rows, "analyses": analyses}


def summarize(analyses) -> dict:
    if not analyses:
        return {}
    a = pd.DataFrame([{k: v for k, v in m.items() if not isinstance(v, dict)} for m in analyses])
    hr = a.loc[a["hr_quality_state"] == "VALID", "heart_rate"].dropna()
    return {
        "tremor_fraction": float((a["classification"] == "TREMOR").mean()),
        "tremor_rest_fraction": float((a["tremor_type"] == "REST").mean()),
        "median_tremor_frequency_hz": float(a.loc[a["classification"] == "TREMOR", "dominant_frequency"].median())
        if (a["classification"] == "TREMOR").any() else None,
        "motion_state_fraction": a["motion_state"].value_counts(normalize=True).round(4).to_dict(),
        "final_steps": int(a["steps"].dropna().iloc[-1]) if a["steps"].notna().any() else None,
        "valid_hr_fraction": float((a["hr_quality_state"] == "VALID").mean()),
        "median_valid_hr": float(hr.median()) if len(hr) else None,
    }


def compare(a_dir, b_dir) -> dict:
    """Compare two replay outputs analysis-by-analysis (aligned on device time)."""
    A = pd.read_csv(Path(a_dir) / "capture.csv", low_memory=False)
    B = pd.read_csv(Path(b_dir) / "capture.csv", low_memory=False)
    A = A[A["is_analysis_row"] == True].set_index("device_time_us")   # noqa: E712
    B = B[B["is_analysis_row"] == True].set_index("device_time_us")   # noqa: E712
    common = A.index.intersection(B.index)
    A, B = A.loc[common], B.loc[common]
    out = {"analyses_compared": int(len(common)),
           "classification_agreement": float((A["classification"] == B["classification"]).mean())
           if len(common) else None}
    for c in ("dominant_frequency", "heart_rate", "tremor_probability"):
        d = (A[c].astype(float) - B[c].astype(float)).abs().dropna()
        out[f"{c}_max_abs_diff"] = float(d.max()) if len(d) else None
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description="Replay a recording through the ParkinSense runtime")
    ap.add_argument("capture")
    ap.add_argument("--out")
    ap.add_argument("--resample", action="store_true")
    ap.add_argument("--realtime", action="store_true")
    ap.add_argument("--speed", type=float, default=1.0)
    ap.add_argument("--compare", nargs=2, metavar=("RUN_A", "RUN_B"))
    a = ap.parse_args(argv)
    if a.compare:
        print(json.dumps(compare(*a.compare), indent=2))
        return
    r = replay(a.capture, a.out, resample=a.resample, realtime=a.realtime, speed=a.speed)
    print(json.dumps(r["summary"], indent=2, default=str))


if __name__ == "__main__":
    main()
