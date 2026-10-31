"""
Dataset builder: recordings -> validated, versioned, window-level dataset.

    python -m parkinsense.datasets.builder recordings/*/capture.csv \
        --labels labels.csv --out datasets/v1 --version 1.0.0

Stages
  1. ingest      every recording via replay.load (all capture formats);
  2. validate    timestamp monotonicity, gaps / missing samples, duplicate
                 rows, packet-version mix, measured rate, clipping fraction;
  3. reprocess   through the *current* RuntimeEngine (replay) so every
                 window is computed by one pipeline version -- historical
                 per-window values are never silently mixed with new ones;
  4. windows     ONE row per analysis (`is_analysis_row`), never per sample:
                 per-sample rows carry forward-filled window values and would
                 multiply every label ~52x (review P0-2);
  5. labels      optional interval labels (session_id/recording, start_s,
                 end_s, label, subject_id) assigned by window overlap;
  6. metadata    dataset.json: version, pipeline/schema versions, source
                 hashes, per-recording QC, label distribution, split policy.

Per-sample data stays in the source recordings; the dataset references them
by hash. Splitting is in `splits.py`.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from parkinsense import config as C
from parkinsense.protocol import packet as P
from parkinsense.replay import replay as R
from parkinsense.runtime.recorder import atomic_write_json

WINDOW_FEATURES = [
    "analysis_seq", "device_time_us", "tremor_probability", "tremor_evidence", "classification",
    "tremor_state", "tremor_type", "dominant_frequency", "tremor_amplitude_dps", "tremor_power",
    "tremor_snr_db", "band_ratio", "frequency_std", "axis_agreement", "axis_dominance", "best_axis",
    "arm_movement_rms_dps", "motion_state", "motion_rms", "tremor_quality",
    "heart_rate", "hr_confidence", "hr_quality_state", "signal_quality", "finger_detected",
    "rmssd", "sdnn", "spo2", "ppg_effective_rate_hz", "steps", "cadence",
]
MAX_CLIPPED_FRACTION = 0.01
MAX_MISSING_FRACTION = 0.05


def validate(src: R.Source) -> dict:
    f = src.frame
    t = f["t_us"].to_numpy()
    d = np.diff(t)
    period = P.SAMPLE_PERIOD_US
    dup = int(f.duplicated(subset=["t_us", "ax", "ay", "az", "gx", "gy", "gz"]).sum())
    backwards = int((d < 0).sum())
    gaps = d > 1.5 * period
    missing = int(np.sum(np.round(d[gaps] / period) - 1)) if gaps.any() else 0
    span_s = (t[-1] - t[0]) / 1e6 if len(t) > 1 else 0.0
    rate = (len(t) - 1) / span_s if span_s > 0 else None
    clip = float((f[["gx", "gy", "gz"]].abs().to_numpy() >= 249.0).any(axis=1).mean()) \
        if (f["version"] == 1).all() else 0.0
    qc = {
        "samples": int(len(f)), "duration_s": round(span_s, 3), "rate_hz": rate,
        "duplicates": dup, "backward_steps": backwards, "gaps": int(gaps.sum()),
        "missing_samples_est": missing,
        "missing_fraction": missing / max(len(f) + missing, 1),
        "packet_versions": sorted(map(int, f["version"].unique())),
        "v1_possible_gyro_clip_fraction": clip,
    }
    problems = []
    if backwards:
        problems.append("non-monotonic timestamps")
    if qc["missing_fraction"] > MAX_MISSING_FRACTION:
        problems.append(f"missing {qc['missing_fraction']:.1%} of samples")
    if rate and abs(rate - C.SAMPLE_RATE_HZ) / C.SAMPLE_RATE_HZ > C.RATE_INVALID_FRACTION:
        problems.append(f"rate {rate:.2f} Hz off nominal")
    if clip > MAX_CLIPPED_FRACTION:
        problems.append(f"{clip:.1%} samples at v1 gyro full scale (possible wrap)")
    if len(qc["packet_versions"]) > 1:
        problems.append("mixed packet versions")
    qc["problems"] = problems
    qc["accepted"] = not problems
    return qc


def windows_for(path, recording_id: str, subject_id: str | None, resample=False) -> tuple[pd.DataFrame, dict]:
    src = R.load(path, resample=resample)
    qc = validate(src)
    out = R.replay(path, resample=resample)
    rows = [r for r in out["rows"] if r["is_analysis_row"]]
    w = pd.DataFrame(rows)
    if w.empty:
        return w, {**qc, "windows": 0}
    w = w[[c for c in WINDOW_FEATURES if c in w.columns]].copy()
    w["window_end_s"] = (w["device_time_us"] - w["device_time_us"].iloc[0]) / 1e6 + C.WINDOW_SECONDS
    w["window_start_s"] = w["window_end_s"] - C.WINDOW_SECONDS
    w.insert(0, "recording_id", recording_id)
    w.insert(1, "subject_id", subject_id or recording_id)
    w["source_sha256"] = src.meta["source_sha256"]
    w["pipeline_version"] = C.PIPELINE_VERSION
    return w, {**qc, "windows": int(len(w)), "source": src.meta}


def apply_labels(w: pd.DataFrame, labels: pd.DataFrame, min_overlap=0.5) -> pd.DataFrame:
    """labels: recording_id, start_s, end_s, label[, subject_id]. A window gets a
    label when >= min_overlap of it lies inside the labelled interval."""
    w = w.copy()
    w["label"] = None
    for lab in labels.itertuples():
        m = w["recording_id"] == lab.recording_id
        ov = (np.minimum(w["window_end_s"], lab.end_s) - np.maximum(w["window_start_s"], lab.start_s)).clip(lower=0)
        hit = m & (ov / C.WINDOW_SECONDS >= min_overlap)
        w.loc[hit, "label"] = lab.label
        if hasattr(lab, "subject_id") and isinstance(lab.subject_id, str):
            w.loc[m, "subject_id"] = lab.subject_id
    return w


def build(paths, out_dir, version, labels_csv=None, subject_map=None, resample=False,
          include_rejected=False) -> dict:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    frames, recs = [], {}
    for p in paths:
        rid = Path(p).parent.name if Path(p).name == "capture.csv" else Path(p).stem
        sid = (subject_map or {}).get(rid)
        w, qc = windows_for(p, rid, sid, resample=resample)
        recs[rid] = qc
        if qc.get("accepted") or include_rejected:
            frames.append(w)
    data = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    if labels_csv and not data.empty:
        data = apply_labels(data, pd.read_csv(labels_csv))
    data.to_csv(out / "windows.csv", index=False)
    meta = {
        "dataset_version": version, "pipeline_version": C.PIPELINE_VERSION,
        "capture_schema_version": C.CAPTURE_SCHEMA_VERSION,
        "unit": "one row per analysis window (4 s window, 0.5 s hop -> consecutive rows overlap 87.5%)",
        "recordings": recs,
        "windows": int(len(data)),
        "label_counts": data["label"].value_counts(dropna=False).to_dict() if "label" in data else {},
        "split_policy": "use parkinsense.datasets.splits.group_split (subject-level); never split windows at random",
        "synthetic": False,
    }
    atomic_write_json(out / "dataset.json", meta)
    return meta


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("captures", nargs="+")
    ap.add_argument("--out", required=True)
    ap.add_argument("--version", required=True)
    ap.add_argument("--labels")
    ap.add_argument("--subjects", help="JSON {recording_id: subject_id}")
    ap.add_argument("--resample", action="store_true")
    ap.add_argument("--include-rejected", action="store_true")
    a = ap.parse_args(argv)
    sm = json.loads(Path(a.subjects).read_text()) if a.subjects else None
    print(json.dumps(build(a.captures, a.out, a.version, a.labels, sm, a.resample, a.include_rejected),
                     indent=2, default=str))


if __name__ == "__main__":
    main()
