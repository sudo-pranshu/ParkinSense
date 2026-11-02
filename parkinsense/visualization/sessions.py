"""
Read-only access to recorded sessions for the dashboard.

Sources:
  recordings/<session>/capture.csv + metadata.json   (SessionRecorder output)
  replays/<name>/capture.csv + replay_summary.json   (replay output)

Nothing here writes to a session directory. Large captures are loaded with
`usecols` (only the columns a page needs) in chunks, keeping only analysis rows
(1 in 52), so memory is bounded by the number of analysis windows, not by
samples. Results are cached by (path, size, mtime), so a growing live capture
is re-read only when it changed, and finished sessions only once.
"""

from __future__ import annotations

import io
import json
import os
import threading
from collections import OrderedDict
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

from parkinsense import config as C

RECORDINGS = Path(os.environ.get("PARKINSENSE_RECORDINGS", "recordings"))
REPLAYS = Path(os.environ.get("PARKINSENSE_REPLAYS", "replays"))
CHUNK_ROWS = 20_000
CACHE_ENTRIES = 6

ANALYSIS_COLS = [
    "device_time_us", "sample_count", "analysis_seq", "is_analysis_row", "classification", "tremor_state",
    "tremor_probability", "tremor_evidence", "tremor_type", "dominant_frequency",
    "tremor_amplitude_dps", "tremor_power", "tremor_snr_db", "arm_movement_rms_dps", "tremor_quality",
    "motion_state", "motion_rms", "heart_rate", "hr_confidence", "hr_quality_state", "rmssd", "sdnn",
    "pnn50", "spo2", "signal_quality", "sensor_status", "finger_detected", "motion_coupled_hr",
    "ppg_effective_rate_hz", "steps", "cadence", "walking_state", "step_confidence",
    "walking_confidence", "device_rate_hz", "rate_status", "packets_lost", "gap_before_s",
]


@dataclass
class Session:
    id: str
    dir: Path
    kind: str                       # "recording" | "replay"
    capture: Path
    meta: dict = field(default_factory=dict)

    @property
    def label(self):
        m = self.meta
        src = (m.get("device") or {}).get("source") or ("replay" if self.kind == "replay" else "ble")
        return f"{self.id} · {src}"

    def summary_row(self) -> dict:
        m = self.meta
        integ = m.get("integrity") or {}
        meas = m.get("measured") or {}
        pk = integ.get("packets") or 0
        lost = integ.get("packets_lost_seq") or 0
        samples = meas.get("samples")
        return {
            "session": self.id, "kind": self.kind,
            "source": (m.get("device") or {}).get("source", "replay" if self.kind == "replay" else "ble"),
            "started": (m.get("started_utc") or "")[:19].replace("T", " "),
            "duration_min": round(samples / C.SAMPLE_RATE_HZ / 60, 2) if samples else None,
            "status": m.get("status"),
            "firmware": m.get("firmware_version"),
            "pipeline": m.get("pipeline_version") or m.get("replay_pipeline_version"),
            "rate_hz": round(meas["device_rate_hz"], 2) if meas.get("device_rate_hz") else None,
            "rate_status": meas.get("rate_status"),
            "loss_pct": round(100 * lost / (pk + lost), 3) if (pk + lost) else None,
            "gaps": integ.get("timestamp_gaps"),
            "errors": integ.get("analysis_errors"),
            "size_mb": round(self.capture.stat().st_size / 1e6, 1) if self.capture.exists() else None,
        }


def _read_json(p: Path) -> dict:
    try:
        return json.loads(p.read_text())
    except (OSError, ValueError):
        return {}


def list_sessions(recordings: Path = None, replays: Path = None) -> list[Session]:
    recordings = Path(recordings or RECORDINGS)
    replays = Path(replays or REPLAYS)
    out = []
    if recordings.is_dir():
        for d in recordings.iterdir():
            if (d / "capture.csv").exists() and (d / "metadata.json").exists():
                out.append(Session(d.name, d, "recording", d / "capture.csv", _read_json(d / "metadata.json")))
    if replays.is_dir():
        for d in replays.iterdir():
            if (d / "capture.csv").exists():
                rs = _read_json(d / "replay_summary.json")
                meta = {"status": "COMPLETE", "pipeline_version": rs.get("replay_pipeline_version"),
                        "integrity": rs.get("integrity", {}),
                        "measured": {"samples": rs.get("samples"), "device_rate_hz": rs.get("device_rate_hz"),
                                     "rate_status": rs.get("rate_status")},
                        "device": {"source": "replay", "replay_of": (rs.get("source") or {}).get("source")},
                        "started_utc": None, "replay_summary": rs}
                out.append(Session(d.name, d, "replay", d / "capture.csv", meta))
    out.sort(key=lambda s: (s.meta.get("started_utc") or "", s.id), reverse=True)
    return out


def get_session(session_id: str, **kw) -> Session | None:
    return next((s for s in list_sessions(**kw) if s.id == session_id), None)


_cache: "OrderedDict[tuple, pd.DataFrame]" = OrderedDict()
_cache_lock = threading.Lock()


def load_analyses(session: Session) -> pd.DataFrame:
    """Analysis rows of a session with a `t` column (seconds from the first sample)."""
    st = session.capture.stat()
    key = (str(session.capture), st.st_size, st.st_mtime_ns)
    with _cache_lock:
        if key in _cache:
            _cache.move_to_end(key)
            return _cache[key]
    header = pd.read_csv(session.capture, nrows=0).columns
    cols = [c for c in ANALYSIS_COLS if c in header]
    t0 = None
    s0 = None
    parts = []
    for chunk in pd.read_csv(session.capture, usecols=cols, chunksize=CHUNK_ROWS, low_memory=False):
        if t0 is None and len(chunk):
            t0 = float(chunk["device_time_us"].iloc[0])
            s0 = int(chunk["sample_count"].iloc[0]) if "sample_count" in chunk else 0
        flag = chunk["is_analysis_row"].astype(str).str.lower().isin(["true", "1"])
        parts.append(chunk[flag])
    df = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame(columns=cols)
    df["t"] = (df["device_time_us"].astype(float) - (t0 or 0.0)) / 1e6
    if "sample_count" in df:
        df["row"] = df["sample_count"].astype(int) - (s0 or 0)
    for c in ("finger_detected", "motion_coupled_hr"):
        if c in df:
            df[c] = df[c].astype(str).str.lower().isin(["true", "1"])
    with _cache_lock:
        _cache[key] = df
        while len(_cache) > CACHE_ENTRIES:
            _cache.popitem(last=False)
    return df


_INDEX_STRIDE = 1024
_index_cache: "OrderedDict[tuple, tuple]" = OrderedDict()


def _line_index(path: Path):
    """(header bytes, byte offset of every 1024th data row). One binary pass, cached per file version."""
    st = path.stat()
    key = (str(path), st.st_size, st.st_mtime_ns)
    with _cache_lock:
        if key in _index_cache:
            return _index_cache[key]
    with open(path, "rb") as f:
        header = f.readline()
        pos = len(header)
        offsets = [pos]                      # row 0
        next_row = 1                         # the next newline found starts this row
        while True:
            block = f.read(1 << 23)
            if not block:
                break
            nl = np.flatnonzero(np.frombuffer(block, dtype=np.uint8) == 10)
            rows = next_row + np.arange(len(nl))
            offsets.extend((pos + nl[rows % _INDEX_STRIDE == 0] + 1).tolist())
            next_row += len(nl)
            pos += len(block)
    out = (header, np.asarray(offsets, dtype=np.int64))
    with _cache_lock:
        _index_cache[key] = out
        while len(_index_cache) > CACHE_ENTRIES:
            _index_cache.popitem(last=False)
    return out


def load_raw_window(session: Session, end_row: int, n: int = C.WINDOW_SAMPLES) -> pd.DataFrame:
    """
    The `n` raw samples ending at data row `end_row` (0-based, = the analysis
    row's `row` column). Rows are located by the recorded sample index, so the
    window is exact even if the stream had gaps. Random access through a
    sparse line index: cost does not depend on where in the file the row is.
    """
    start_row = max(0, int(end_row) - n + 1)
    header, offsets = _line_index(session.capture)
    k = min(start_row // _INDEX_STRIDE, len(offsets) - 1)
    with open(session.capture, "rb") as f:
        f.seek(int(offsets[k]))
        skip = start_row - k * _INDEX_STRIDE
        lines = []
        for i, line in enumerate(f):
            if i >= skip:
                lines.append(line)
                if len(lines) == int(end_row) - start_row + 1:
                    break
    return pd.read_csv(io.BytesIO(header + b"".join(lines)),
                       usecols=["device_time_us", "ax", "ay", "az", "gx", "gy", "gz", "ir", "red"])


def episodes(df: pd.DataFrame, min_s: float = 2.0) -> pd.DataFrame:
    """Contiguous published-tremor periods with summary statistics."""
    if df.empty or "classification" not in df:
        return pd.DataFrame(columns=["start_s", "end_s", "duration_s", "type", "median_hz", "median_amp_dps", "max_p"])
    on = (df["classification"] == "TREMOR").to_numpy()
    t = df["t"].to_numpy()
    rows = []
    i = 0
    while i < len(on):
        if on[i]:
            j = i
            while j + 1 < len(on) and on[j + 1]:
                j += 1
            seg = df.iloc[i:j + 1]
            det = seg[seg.get("tremor_evidence", pd.Series(1.0, index=seg.index)) >= 0.5]
            dur = t[j] - t[i] + C.ANALYSIS_HOP_SECONDS
            if dur >= min_s:
                rows.append({"start_s": round(t[i], 1), "end_s": round(t[j], 1), "duration_s": round(dur, 1),
                             "type": seg["tremor_type"].mode().iat[0] if "tremor_type" in seg and len(seg) else None,
                             "median_hz": round(float(det["dominant_frequency"].median()), 2) if len(det) else None,
                             "median_amp_dps": round(float(det["tremor_amplitude_dps"].median()), 2) if len(det) else None,
                             "max_p": round(float(seg["tremor_probability"].max()), 3)})
            i = j + 1
        else:
            i += 1
    return pd.DataFrame(rows)


def quality_fractions(df: pd.DataFrame) -> dict:
    out = {}
    for col in ("tremor_quality", "hr_quality_state"):
        if col in df and len(df):
            out[col] = df[col].fillna("NONE").value_counts(normalize=True).round(4).to_dict()
    return out


def session_quality_score(df: pd.DataFrame) -> float | None:
    """Share of analysis windows whose tremor measurement is usable (VALID or LOW_CONFIDENCE)."""
    if df.empty or "tremor_quality" not in df:
        return None
    return float(np.mean(df["tremor_quality"].isin(["VALID", "LOW_CONFIDENCE"])))
