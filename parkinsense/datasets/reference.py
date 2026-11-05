"""
Labelled reference recordings for algorithm validation (sleep, steps).

A `ReferenceRecording` is the common in-memory form every benchmark uses:
raw tri-axial acceleration in g on its own time base, optional heart rate,
and reference labels with their provenance. Loaders for the public datasets
live here; downloading is `benchmarks/external/fetch.py`. Nothing in this
module modifies source files.

Label kinds
-----------
* step_times_s       -- annotated step (foot-contact) events
* activity           -- per-sample activity code -> walking / not walking
* sleep_epochs       -- 30 s epochs, 1 = sleep, 0 = wake, -1 = unscored

Every recording carries `provenance` (dataset, citation, licence, source,
placement, sampling, any preprocessing applied here), so a benchmark report
can state exactly what it was measured on.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

G = 9.80665


@dataclass
class ReferenceRecording:
    dataset: str
    subject_id: str
    session_id: str
    placement: str
    fs: float                                  # nominal sampling rate of `acc`
    t: np.ndarray                              # seconds, monotonic
    acc: np.ndarray                            # (n, 3), g
    gyro: np.ndarray | None = None             # (n, 3), deg/s
    hr_t: np.ndarray | None = None
    hr: np.ndarray | None = None               # bpm
    step_times_s: np.ndarray | None = None
    walking: np.ndarray | None = None          # per-sample bool (activity label)
    activity: np.ndarray | None = None         # per-sample raw activity code
    sleep_epoch_t: np.ndarray | None = None    # epoch start, s
    sleep_epochs: np.ndarray | None = None     # 1 sleep, 0 wake, -1 unscored
    condition: str = ""
    provenance: dict = field(default_factory=dict)
    aux: dict = field(default_factory=dict)    # other sensors used only to derive references

    @property
    def duration_s(self) -> float:
        return float(self.t[-1] - self.t[0]) if len(self.t) else 0.0


# --------------------------------------------------------------------------- calibration
def autocalibrate(acc: np.ndarray, iters: int = 100) -> tuple[np.ndarray, np.ndarray, float]:
    """
    Affine calibration from quasi-static samples (van Hees et al., J Appl
    Physiol 2014): find per-axis offset o and scale s so that |s * (x - o)| = 1 g
    at rest. Iterative: project each point onto the unit sphere, then solve the
    per-axis linear regression x_cal = s * x + b. Returns (scale, offset_in_g
    after scaling, rms residual in g). Needs points spread over orientations.
    """
    x = np.asarray(acc, float)
    s, b = np.ones(3), np.zeros(3)
    for _ in range(iters):
        y = x * s + b
        target = y / np.linalg.norm(y, axis=1, keepdims=True)
        s_new, b_new = np.empty(3), np.empty(3)
        for k in range(3):
            A = np.c_[x[:, k], np.ones(len(x))]
            s_new[k], b_new[k] = np.linalg.lstsq(A, target[:, k], rcond=None)[0]
        if np.allclose(s_new, s, rtol=1e-9) and np.allclose(b_new, b, atol=1e-9):
            break
        s, b = s_new, b_new
    y = x * s + b
    return s, b, float(np.sqrt(np.mean((np.linalg.norm(y, axis=1) - 1) ** 2)))


def static_points(acc: np.ndarray, fs: float, win_s: float = 1.0, quantile: float = 0.05) -> np.ndarray:
    """Means of the least-variable windows (lowest `quantile` of per-window SD)."""
    n = int(win_s * fs)
    m = len(acc) // n
    if m == 0:
        return np.empty((0, 3))
    w = np.asarray(acc[: m * n], float).reshape(m, n, 3)
    sd = w.std(axis=1).max(axis=1)
    keep = sd <= np.quantile(sd, quantile)
    return w[keep].mean(axis=1)


# --------------------------------------------------------------------------- Walch 2019 (sleep)
WALCH_PROVENANCE = {
    "dataset": "walch2019",
    "title": "Motion and heart rate from a wrist-worn wearable and labeled sleep from polysomnography",
    "citation": "Walch O. (2019) PhysioNet, doi:10.13026/hmhs-py35; Walch O. et al., Sleep 42(12) 2019",
    "licence": "Open Data Commons Attribution License v1.0",
    "placement": "wrist (Apple Watch Series 2/3)",
    "accel": "raw tri-axial, g, ~50 Hz, irregular timestamps",
    "hr": "Apple Watch PPG heart rate, bpm, every ~5 s",
    "labels": "PSG, AASM, 30 s epochs, single RPSGT scorer; 0 wake, 1-4 NREM, 5 REM, -1 unscored",
}


def load_walch(root: Path, subject: str) -> ReferenceRecording:
    """One subject's PSG night. Only data inside the scored PSG window is kept."""
    root = Path(root)
    lab = pd.read_csv(root / "labels" / f"{subject}_labeled_sleep.txt", sep=r"\s+", header=None,
                      names=["t", "stage"])
    acc = pd.read_csv(root / "motion" / f"{subject}_acceleration.txt", sep=r"\s+", header=None,
                      names=["t", "x", "y", "z"])
    hr = pd.read_csv(root / "heart_rate" / f"{subject}_heartrate.txt", sep=",", header=None, names=["t", "hr"])
    t0, t1 = float(lab["t"].iloc[0]), float(lab["t"].iloc[-1]) + 30.0
    acc = acc[(acc["t"] >= t0) & (acc["t"] < t1)].sort_values("t").drop_duplicates("t")
    hr = hr[(hr["t"] >= t0) & (hr["t"] < t1)].sort_values("t")
    stage = lab["stage"].to_numpy()
    sleep = np.where(stage < 0, -1, np.where(stage == 0, 0, 1))
    return ReferenceRecording(
        dataset="walch2019", subject_id=subject, session_id=f"walch_{subject}", placement="wrist",
        fs=50.0, t=acc["t"].to_numpy(float), acc=acc[["x", "y", "z"]].to_numpy(float),
        hr_t=hr["t"].to_numpy(float), hr=hr["hr"].to_numpy(float),
        sleep_epoch_t=lab["t"].to_numpy(float), sleep_epochs=sleep,
        condition="psg_night", provenance=dict(WALCH_PROVENANCE, source_files=[
            f"labels/{subject}_labeled_sleep.txt", f"motion/{subject}_acceleration.txt",
            f"heart_rate/{subject}_heartrate.txt"]))


def walch_subjects(root: Path) -> list[str]:
    return sorted(p.name.split("_")[0] for p in (Path(root) / "motion").glob("*_acceleration.txt"))


# --------------------------------------------------------------------------- Clemson (steps)
CLEMSON_PROVENANCE = {
    "dataset": "clemson_pedometer",
    "citation": "Mattfeld R., Jesch E., Hoover A. A new dataset for evaluating pedometer performance. "
                "IEEE BIBM 2017, doi:10.1109/BIBM.2017.8217769",
    "licence": "per upstream Pedometer Evaluation Project terms (cecas.clemson.edu/~ahoover/pedometer); "
               "not redistributed here",
    "source": "prepared copy github.com/ChaddBrenner/mattfeld_research_data (timelines aligned, channels "
              "min-max normalised over all participants)",
    "placement": "wrist (Shimmer3, Sensor01), 15 Hz",
    "labels": "annotated left/right foot contacts ('l','r'); 'ledge'/'redge' kept separately",
    "preprocessing_here": "per-channel affine re-calibration to g (autocalibrate on the least-variable "
                          "1 s windows pooled over all 90 files); gyroscope unused (scale unrecoverable)",
}
CLEMSON_KINDS = ("Regular", "SemiRegular", "Irregular")


def clemson_calibration(root: Path) -> dict:
    """Affine map from the normalised wrist channels back to g, cached next to the data."""
    root = Path(root)
    cache = root / "wrist_calibration.json"
    if cache.exists():
        return json.loads(cache.read_text())
    pts = []
    for f in sorted(root.glob("P*_*.csv")):
        d = pd.read_csv(f, usecols=["Sensor01_Accel_X", "Sensor01_Accel_Y", "Sensor01_Accel_Z"])
        pts.append(static_points(d.to_numpy(float), 15.0, quantile=0.10))
    pts = np.concatenate(pts)
    # normalised units: start from a unit-sphere guess so the iteration is well conditioned
    centre = (pts.max(0) + pts.min(0)) / 2
    half = (pts.max(0) - pts.min(0)) / 2
    s, b, rms = autocalibrate((pts - centre) / half)
    cal = {"centre": centre.tolist(), "half": half.tolist(), "scale": s.tolist(), "offset": b.tolist(),
           "rms_residual_g": rms, "static_points": len(pts)}
    cache.write_text(json.dumps(cal, indent=2))
    return cal


def load_clemson(root: Path, participant: int, kind: str, cal: dict | None = None) -> ReferenceRecording:
    root = Path(root)
    cal = cal or clemson_calibration(root)
    d = pd.read_csv(root / f"P{participant:03d}_{kind}.csv",
                    usecols=["Sensor01_Date", "Sensor01_Accel_X", "Sensor01_Accel_Y", "Sensor01_Accel_Z",
                             "Sensor01_Step_type"]).dropna(subset=["Sensor01_Date", "Sensor01_Accel_X"])
    # a few rows carry spreadsheet-mangled times ("24:00.0"): parse strictly, then
    # interpolate those from their neighbours (the stream is uniformly sampled)
    ts = pd.to_datetime(d["Sensor01_Date"], format="%Y-%m-%d %H:%M:%S.%f", errors="coerce")
    if ts.notna().mean() > 0.5:
        t = (ts - ts.min()).dt.total_seconds().interpolate(limit_direction="both").to_numpy()
        timebase = "source timestamps (unparseable rows interpolated)"
    else:                                   # whole column mangled (P008_SemiRegular)
        t = np.arange(len(d)) / 15.0
        timebase = "nominal 15 Hz (source timestamps unparseable)"
    t = t - t[0]
    raw = d[["Sensor01_Accel_X", "Sensor01_Accel_Y", "Sensor01_Accel_Z"]].to_numpy(float)
    acc = ((raw - np.array(cal["centre"])) / np.array(cal["half"])) * np.array(cal["scale"]) + np.array(cal["offset"])
    st = d["Sensor01_Step_type"].astype(str).to_numpy()
    steps = t[np.isin(st, ["l", "r"])]
    return ReferenceRecording(
        dataset="clemson_pedometer", subject_id=f"P{participant:03d}", session_id=f"P{participant:03d}_{kind}",
        placement="wrist", fs=15.0, t=t, acc=acc, step_times_s=steps, condition=kind,
        provenance=dict(CLEMSON_PROVENANCE, file=f"P{participant:03d}_{kind}.csv", timebase=timebase,
                        edge_events=int(np.isin(st, ["ledge", "redge"]).sum()), calibration=cal))


# --------------------------------------------------------------------------- Karas 2021 (walking / not)
KARAS_PROVENANCE = {
    "dataset": "karas2021_walk_climb_drive",
    "citation": "Karas M. et al. (2021) Labeled raw accelerometry data captured during walking, stair "
                "climbing and driving. PhysioNet, doi:10.13026/51h0-a262",
    "licence": "Open Data Commons Open Database License v1.0",
    "placement": "left wrist (ActiGraph GT3X+), 100 Hz (ankle/hip sensors exist in the dataset but are not used)",
    "labels": "activity per sample: 1 walking, 2 stairs down, 3 stairs up, 4 driving, 77 clapping, 99 non-study. No step annotations: used here only for walking-state sensitivity and for false steps during labelled driving/clapping",
}


def load_karas(root: Path, subject: str) -> ReferenceRecording:
    root = Path(root)
    d = pd.read_csv(root / "raw_accelerometry_data" / f"{subject}.csv")
    act = d["activity"].to_numpy(int)
    rec = ReferenceRecording(
        dataset="karas2021_walk_climb_drive", subject_id=subject, session_id=f"karas_{subject}",
        placement="left_wrist", fs=100.0, t=d["time_s"].to_numpy(float),
        acc=d[["lw_x", "lw_y", "lw_z"]].to_numpy(float), walking=np.isin(act, [1, 2, 3]), activity=act,
        condition="walk_climb_drive", provenance=dict(KARAS_PROVENANCE, file=f"{subject}.csv"))
    rec.aux["ankles"] = {"la": d[["la_x", "la_y", "la_z"]].to_numpy(np.float32),
                                "ra": d[["ra_x", "ra_y", "ra_z"]].to_numpy(np.float32)}
    return rec


def karas_subjects(root: Path) -> list[str]:
    return sorted(p.stem for p in (Path(root) / "raw_accelerometry_data").glob("*.csv"))
