"""
Session recording: one directory per session, owned by a context manager.

    recordings/<YYYYmmdd_HHMMSS>_<session_id>/
        capture.csv        per-sample rows, CAPTURE_COLUMNS (schema v3)
        metadata.json      provenance: versions, configuration, measured
                           rates, integrity counters, start/end times
    recordings/latest.json pointer used by the dashboard

Fixes review P0-1 (capture opened at import in "w" mode, closed only on
Ctrl-C) and P2-10 (non-atomic metrics JSON): the file is opened when a
session starts, flushed per packet, and closed on *every* exit path;
JSON files are written to a temp file and `os.replace`d.
"""

from __future__ import annotations

import csv
import json
import os
import platform
import time
from datetime import datetime, timezone
from pathlib import Path

from parkinsense import config as C
from parkinsense.protocol import packet as P
from parkinsense.runtime.engine import CAPTURE_COLUMNS, RuntimeEngine


def atomic_write_json(path, obj) -> None:
    path = Path(path)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w") as f:
        json.dump(obj, f, indent=2, default=str)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def _jsonable_metrics(m: dict) -> dict:
    return {k: v for k, v in m.items() if not k.startswith("_")}


class SessionRecorder:
    def __init__(self, engine: RuntimeEngine, root="recordings", device: dict | None = None,
                 notes: str = ""):
        self.engine = engine
        self.root = Path(root)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.dir = self.root / f"{stamp}_{engine.session_id}"
        self.device = device or {}
        self.notes = notes
        self._f = None
        self._w = None
        self.rows = 0
        self.started_wall = None
        self.started_mono = None

    def __enter__(self):
        self.dir.mkdir(parents=True, exist_ok=False)
        self._f = open(self.dir / "capture.csv", "w", newline="")
        self._w = csv.DictWriter(self._f, fieldnames=CAPTURE_COLUMNS, extrasaction="ignore")
        self._w.writeheader()
        self.started_wall = time.time()
        self.started_mono = time.monotonic()
        self.write_metadata(status="RECORDING")
        atomic_write_json(self.root / "latest.json", {"session_dir": str(self.dir.resolve()),
                                                      "capture": str((self.dir / "capture.csv").resolve()),
                                                      "session_id": self.engine.session_id})
        return self

    def write_rows(self, rows) -> None:
        for r in rows:
            self._w.writerow(r)
        self.rows += len(rows)
        self._f.flush()

    def metadata(self, status: str) -> dict:
        e = self.engine
        return {
            "session_id": e.session_id,
            "status": status,
            "capture_schema_version": C.CAPTURE_SCHEMA_VERSION,
            "pipeline_version": C.PIPELINE_VERSION,
            "tremor_algorithm_version": C.TREMOR_ALGORITHM_VERSION,
            "step_counter_version": C.STEP_COUNTER_VERSION,
            "ppg_version": C.PPG_VERSION,
            "firmware_version": e.firmware_version,
            "protocol_versions_seen": sorted(e.versions),
            "config": {
                "nominal_sample_rate_hz": e.fs, "window_samples": e.window,
                "analysis_hop_samples": e.hop, "ppg_slot_rate_hz": C.PPG_SLOT_RATE_HZ,
                "ppg_window_seconds": C.PPG_WINDOW_SECONDS,
                "tremor_band_hz": C.TREMOR_BAND_HZ, "batch_size": P.BATCH_SIZE,
            },
            "measured": {
                "device_rate_hz": e.device_rate_hz(), "rate_status": e.rate_status(),
                "samples": e.sample_count, "rows_written": self.rows,
                "analyses": e.analysis_seq,
            },
            "integrity": e.integrity(),
            "started_utc": datetime.fromtimestamp(self.started_wall, timezone.utc).isoformat()
            if self.started_wall else None,
            "ended_utc": datetime.now(timezone.utc).isoformat() if status != "RECORDING" else None,
            "duration_host_s": (time.monotonic() - self.started_mono) if self.started_mono else None,
            "device": self.device,
            "host": {"platform": platform.platform(), "python": platform.python_version()},
            "notes": self.notes,
        }

    def write_metadata(self, status="RECORDING") -> None:
        atomic_write_json(self.dir / "metadata.json", self.metadata(status))

    def __exit__(self, exc_type, exc, tb):
        try:
            if self._f:
                self._f.flush()
                os.fsync(self._f.fileno())
                self._f.close()
        finally:
            self.write_metadata(status="COMPLETE" if exc_type is None else f"ABORTED:{exc_type.__name__}")
        return False
