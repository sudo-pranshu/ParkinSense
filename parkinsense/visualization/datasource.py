"""
Live data access for the dashboard.

The dashboard never imports the runtime engine and never touches the
acquisition process. It reads:

  1. the runtime HTTP API (`/live`, `/session`) -- primary, incremental;
  2. the atomic metrics JSON file -- fallback when the API is unreachable,
     always shown as STALE (never as live).

`LiveFeed` polls `/live` on a background thread with a short timeout and keeps
bounded client-side buffers, so Dash callbacks only take an in-memory snapshot:
no network or disk I/O happens on the UI path, and memory does not grow with
session length.
"""

from __future__ import annotations

import json
import os
import threading
import time
import urllib.error
import urllib.request
from collections import deque

import numpy as np

DEFAULT_API = os.environ.get("PARKINSENSE_API", "http://127.0.0.1:8000")
METRICS_FILE = os.environ.get("PARKINSENSE_METRICS", "realtime_metrics_v2.json")
POLL_INTERVAL_S = 0.4
HTTP_TIMEOUT_S = 1.0
STALE_AFTER_S = 3.0
BUFFER_SECONDS = 30
BUFFER_ANALYSES = 1200        # 10 min at the 0.5 s hop
NOMINAL_FS = 104.0


class LiveFeed:
    def __init__(self, api: str = DEFAULT_API, poll_s: float = POLL_INTERVAL_S):
        self.api = api.rstrip("/")
        self.poll_s = poll_s
        self._lock = threading.Lock()
        self._samples = deque(maxlen=int(BUFFER_SECONDS * NOMINAL_FS))
        self._analyses = deque(maxlen=BUFFER_ANALYSES)
        self._since_sample = 0
        self._since_analysis = 0
        self.session_id = None
        self.meta: dict = {}
        self.online = False
        self.last_ok = None
        self.last_error = None
        self.polls = 0
        self._thread = None
        self._stop = threading.Event()

    # ------------------------------------------------------------------
    def start(self):
        if self._thread and self._thread.is_alive():
            return self
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="parkinsense-livefeed", daemon=True)
        self._thread.start()
        return self

    def stop(self):
        self._stop.set()

    def _get(self, path):
        with urllib.request.urlopen(self.api + path, timeout=HTTP_TIMEOUT_S) as r:
            return json.load(r)

    def post(self, path) -> dict:
        req = urllib.request.Request(self.api + path, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT_S) as r:
                return json.load(r)
        except (urllib.error.URLError, OSError, ValueError) as e:
            return {"ok": False, "reason": f"runtime not reachable ({e})"}

    def poll_once(self):
        try:
            d = self._get(f"/live?since_sample={self._since_sample}&since_analysis={self._since_analysis}")
        except (urllib.error.URLError, OSError, ValueError) as e:
            with self._lock:
                self.online = False
                self.last_error = str(e)
            return False
        with self._lock:
            # runtime restarted or a new session began: sequence went backwards or id changed
            if (d.get("session_id") != self.session_id) or d["last_sample_seq"] < self._since_sample:
                self._samples.clear()
                self._analyses.clear()
                self.session_id = d.get("session_id")
                if d["last_sample_seq"] < self._since_sample:
                    self._since_sample = self._since_analysis = 0
            for s in d["samples"]:
                self._samples.append(s)
            self._analyses.extend(d["analyses"])
            self._since_sample = d["last_sample_seq"]
            self._since_analysis = d["last_analysis_seq"]
            self.meta = {k: d.get(k) for k in ("status", "source", "recording", "session_id", "last_packet_age_s",
                                               "server_time", "integrity")}
            self.online = True
            self.last_ok = time.time()
            self.polls += 1
        return True

    def _run(self):
        while not self._stop.is_set():
            ok = self.poll_once()
            self._stop.wait(self.poll_s if ok else max(self.poll_s, 1.0))

    # ------------------------------------------------------------------
    def snapshot(self, seconds: float | None = None) -> dict:
        """Copy of the buffers (optionally the last `seconds` of samples)."""
        with self._lock:
            samples = list(self._samples)
            analyses = list(self._analyses)
            meta = dict(self.meta)
            online, last_ok = self.online, self.last_ok
        arr = np.asarray(samples, dtype=float) if samples else np.empty((0, 10))
        if seconds and len(arr):
            arr = arr[arr[:, 1] >= arr[-1, 1] - seconds]
        age = meta.get("last_packet_age_s")
        if online and last_ok is not None and age is not None:
            age = age + (time.time() - last_ok)
        stale = (not online) or age is None or age > STALE_AFTER_S
        return {"samples": arr, "analyses": analyses, "meta": meta, "online": online,
                "data_age_s": age, "stale": stale,
                "latest": analyses[-1] if analyses else (fallback_metrics() if not online else {})}


def fallback_metrics(path: str | None = None) -> dict:
    """Last metrics written to disk by the runtime (for display as STALE only)."""
    path = path or METRICS_FILE
    try:
        with open(path) as f:
            m = json.load(f)
        m["_from_file"] = True
        m["_file_age_s"] = time.time() - os.path.getmtime(path)
        return m
    except (OSError, ValueError):
        return {}


def read_tail(path, nbytes=2_500_000):
    """Header + last `nbytes` of a growing CSV, without reading the whole file."""
    import io

    import pandas as pd
    with open(path, "rb") as f:
        header = f.readline()
        size = os.fstat(f.fileno()).st_size
        start = max(len(header), size - nbytes)
        f.seek(start)
        chunk = f.read()
    if start > len(header):
        chunk = chunk.split(b"\n", 1)[-1]
    if not chunk.endswith(b"\n"):
        chunk = chunk.rsplit(b"\n", 1)[0]
    return pd.read_csv(io.BytesIO(header + chunk), low_memory=False)


_FEED: LiveFeed | None = None
_FEED_LOCK = threading.Lock()


def feed() -> LiveFeed:
    """Process-wide LiveFeed (started on first use)."""
    global _FEED
    with _FEED_LOCK:
        if _FEED is None:
            _FEED = LiveFeed().start()
        return _FEED


def set_feed(f: LiveFeed):
    """Inject a feed (tests, custom API URL)."""
    global _FEED
    with _FEED_LOCK:
        _FEED = f
