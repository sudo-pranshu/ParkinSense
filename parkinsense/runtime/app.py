"""
Live acquisition: packet source -> RuntimeEngine -> SessionRecorder, plus the
HTTP API consumed by the dashboard and the mobile app.

    python -m parkinsense.runtime.app                     # BLE device
    python -m parkinsense.runtime.app --simulate          # synthetic stream (labelled SIMULATED)
    python -m parkinsense.runtime.app --replay FILE.csv   # paced replay of a recording

Every source goes through the identical engine + recorder path. Simulated and
replayed sessions are labelled as such in metadata.json (`device.source`), in
the capture's `firmware_version`, and in every API response (`source`), so they
can never be mistaken for a live measurement.

Lifecycle (review P0-1, P1-7, P2-13, P2-14):
  * a recording directory is created only when a source is streaming;
  * every exit path (normal return, disconnect, Ctrl-C, SIGTERM, exception)
    closes the capture and finalises metadata.json;
  * after a disconnect the app reconnects into a *new* session;
  * POST /session/stop ends the current session cleanly and idles;
    POST /session/start resumes (new session);
  * analysis failures are counted in metrics/metadata, not swallowed.

HTTP API (additive; v2 consumers of /metrics keep working):
  GET  /metrics   latest analysis (+ status)                       [v2 compatible]
  GET  /health    status, integrity, rate status
  GET  /live      incremental samples + analyses since given sequence numbers
  GET  /session   current session, source, recording state
  POST /session/stop, /session/start
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import signal
import threading
import time
from collections import deque
from pathlib import Path

from parkinsense import config as C
from parkinsense.runtime.engine import RuntimeEngine
from parkinsense.runtime.recorder import SessionRecorder, _jsonable_metrics, atomic_write_json

DEVICE_NAME = "ParkinSense"
SERVICE_UUID = "ABCD1234-0000-467A-9538-01F0652C74E0"
CHAR_UUID = "ABCD1234-0001-467A-9538-01F0652C74E0"
FIRMWARE_REV_UUID = "00002a26-0000-1000-8000-00805f9b34fb"   # DIS Firmware Revision String
RECONNECT_DELAY_S = 3.0
METADATA_EVERY_S = 10.0

LIVE_SAMPLE_SECONDS = 60          # raw samples kept in memory for /live (bounded)
LIVE_ANALYSES = 1200              # analyses kept in memory (10 min at a 0.5 s hop)
LIVE_MAX_SAMPLES_PER_RESPONSE = 4000
SAMPLE_FIELDS = ("t", "ax", "ay", "az", "gx", "gy", "gz", "ir", "red")

log = logging.getLogger("parkinsense.app")


class LiveState:
    """
    Thread-safe, bounded store of what the dashboard needs to see live.
    Written by the acquisition loop, read by API threads. Memory is bounded by
    LIVE_SAMPLE_SECONDS and LIVE_ANALYSES regardless of session length.
    """

    def __init__(self, sample_rate: float = C.SAMPLE_RATE_HZ):
        self._lock = threading.Lock()
        self._m: dict = {"status": "WAITING"}
        self.status = "STARTING"
        self.source = "ble"
        self.session: dict = {}
        self.recording = False
        self.last_packet_wall: float | None = None
        self.sample_seq = 0
        self.analysis_seq = 0
        self._samples: deque = deque(maxlen=int(LIVE_SAMPLE_SECONDS * sample_rate))
        self._analyses: deque = deque(maxlen=LIVE_ANALYSES)

    # --- writers -------------------------------------------------------
    def set(self, m: dict):                      # v2-compatible
        with self._lock:
            self._m = m

    def set_status(self, status: str, **session):
        with self._lock:
            self.status = status
            if session:
                self.session.update(session)
            self._m = dict(self._m, status=status)

    def new_session(self, info: dict):
        with self._lock:
            self.session = dict(info)
            self.recording = True
            self._samples.clear()
            self._analyses.clear()
            self._m = {"status": "CONNECTED"}

    def end_session(self, integrity: dict | None):
        with self._lock:
            self.recording = False
            if integrity is not None:
                self.session["integrity"] = integrity

    def on_packet(self, rows: list, analyses: list, capture_path: str | None = None):
        now = time.time()
        with self._lock:
            self.last_packet_wall = now
            for r in rows:
                self.sample_seq += 1
                self._samples.append((self.sample_seq, r["device_time_us"] / 1e6, r["ax"], r["ay"], r["az"],
                                      r["gx"], r["gy"], r["gz"], r["ir"], r["red"]))
            for a in analyses:
                self.analysis_seq += 1
                compact = {k: v for k, v in _jsonable_metrics(a).items() if not isinstance(v, dict)}
                compact["live_seq"] = self.analysis_seq
                self._analyses.append(compact)
            if analyses:
                m = _jsonable_metrics(analyses[-1])
                m["status"] = "STREAMING"
                m["source"] = self.source
                if capture_path:
                    m["capture_path"] = capture_path
                self._m = m
            self.status = "STREAMING"

    # --- readers -------------------------------------------------------
    def get(self) -> dict:
        with self._lock:
            return dict(self._m)

    def session_info(self) -> dict:
        with self._lock:
            age = None if self.last_packet_wall is None else time.time() - self.last_packet_wall
            return {"status": self.status, "source": self.source, "recording": self.recording,
                    "session": dict(self.session), "last_packet_age_s": age,
                    "server_time": time.time()}

    def live(self, since_sample: int = 0, since_analysis: int = 0,
             max_samples: int = LIVE_MAX_SAMPLES_PER_RESPONSE) -> dict:
        with self._lock:
            samples = [s for s in self._samples if s[0] > since_sample]
            if len(samples) > max_samples:
                samples = samples[-max_samples:]
            analyses = [a for a in self._analyses if a["live_seq"] > since_analysis]
            age = None if self.last_packet_wall is None else time.time() - self.last_packet_wall
            return {
                "server_time": time.time(), "status": self.status, "source": self.source,
                "recording": self.recording, "session_id": self.session.get("session_id"),
                "last_packet_age_s": age, "integrity": self._m.get("integrity"),
                "last_sample_seq": self.sample_seq, "last_analysis_seq": self.analysis_seq,
                "sample_fields": ["seq", *SAMPLE_FIELDS],
                "samples": [list(s) for s in samples],
                "analyses": analyses,
            }


class Control:
    """Session start/stop requested from the API thread, consumed by the asyncio loop."""

    def __init__(self, loop: asyncio.AbstractEventLoop, start_enabled: bool = True):
        self.loop = loop
        self.enabled = asyncio.Event()
        self.end_session = asyncio.Event()
        if start_enabled:
            self.enabled.set()

    def request_stop(self):
        self.loop.call_soon_threadsafe(self.enabled.clear)
        self.loop.call_soon_threadsafe(self.end_session.set)

    def request_start(self):
        self.loop.call_soon_threadsafe(self.end_session.clear)
        self.loop.call_soon_threadsafe(self.enabled.set)


def build_api(live: LiveState, control: Control | None = None):
    from fastapi import FastAPI

    app = FastAPI(title="ParkinSense API")

    @app.get("/metrics")
    def metrics():
        return live.get()

    @app.get("/health")
    def health():
        m = live.get()
        return {"status": m.get("status", "OK"), "integrity": m.get("integrity"),
                "rate_status": m.get("rate_status")}

    @app.get("/live")
    def live_data(since_sample: int = 0, since_analysis: int = 0,
                  max_samples: int = LIVE_MAX_SAMPLES_PER_RESPONSE):
        return live.live(since_sample, since_analysis, min(max_samples, LIVE_MAX_SAMPLES_PER_RESPONSE))

    @app.get("/session")
    def session():
        return live.session_info()

    @app.post("/session/stop")
    def session_stop():
        if control is None:
            return {"ok": False, "reason": "session control not available"}
        control.request_stop()
        return {"ok": True}

    @app.post("/session/start")
    def session_start():
        if control is None:
            return {"ok": False, "reason": "session control not available"}
        control.request_start()
        return {"ok": True}

    return app


# ---------------------------------------------------------------------------
# Shared streaming path for every source
# ---------------------------------------------------------------------------

class _Stream:
    """Engine + recorder + live state for one session."""

    def __init__(self, args, live: LiveState, firmware_version: str, device: dict):
        self.args = args
        self.live = live
        self.engine = RuntimeEngine(firmware_version=firmware_version)
        self.rec = SessionRecorder(self.engine, root=args.out, device=device, notes=args.notes)
        self.last_meta = time.monotonic()

    def __enter__(self):
        self.rec.__enter__()
        self.live.new_session({"session_id": self.engine.session_id, "session_dir": str(self.rec.dir),
                               "firmware_version": self.engine.firmware_version,
                               "device": self.rec.device, "started_wall": time.time()})
        log.info("recording to %s (firmware %s, source %s)", self.rec.dir,
                 self.engine.firmware_version, self.live.source)
        return self

    def feed(self, data: bytes):
        res = self.engine.process_packet(bytes(data))
        if res.rows:
            self.rec.write_rows(res.rows)
        capture = str(self.rec.dir / "capture.csv")
        self.live.on_packet(res.rows, res.analyses, capture)
        if res.analyses:
            m = self.live.get()
            atomic_write_json(self.args.metrics_file, m)
        now = time.monotonic()
        if now - self.last_meta >= METADATA_EVERY_S:
            self.rec.write_metadata()
            self.last_meta = now

    def __exit__(self, *exc):
        try:
            return self.rec.__exit__(*exc)
        finally:
            self.live.end_session(self.engine.integrity())


async def _wait_any(*events: asyncio.Event):
    tasks = [asyncio.create_task(e.wait()) for e in events]
    await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
    for t in tasks:
        t.cancel()


async def run_ble_session(args, live: LiveState, stop: asyncio.Event, control: Control) -> None:
    from bleak import BleakClient, BleakScanner

    live.set_status("SCANNING")
    log.info("scanning for %s ...", DEVICE_NAME)
    device = await BleakScanner.find_device_by_filter(
        lambda d, ad: bool(d.name and DEVICE_NAME in d.name), timeout=20.0)
    if device is None:
        log.warning("device not found")
        live.set_status("DEVICE_NOT_FOUND")
        return

    disconnected = asyncio.Event()
    async with BleakClient(device, disconnected_callback=lambda _c: disconnected.set()) as client:
        log.info("connected: %s", device.address)
        live.set_status("CONNECTED")
        fw = args.firmware_version
        if fw == "unknown":
            try:   # Device Information Service, firmware >= 5.0.0
                fw = (await client.read_gatt_char(FIRMWARE_REV_UUID)).decode(errors="replace").strip("\x00 ")
            except Exception:
                log.info("firmware revision not available (pre-5.0 firmware); recording 'unknown'")
        with _Stream(args, live, fw, {"source": "ble", "address": device.address, "name": device.name}) as st:
            await client.start_notify(CHAR_UUID, lambda _s, data: st.feed(data))
            await _wait_any(stop, disconnected, control.end_session)
            if client.is_connected:
                await client.stop_notify(CHAR_UUID)
    live.set_status("DISCONNECTED")


async def run_paced_session(args, live: LiveState, stop: asyncio.Event, control: Control,
                            packets, firmware_version: str, device: dict) -> None:
    """Feed (bytes, device_time_s) packets at their recorded pace (scaled by --speed)."""
    with _Stream(args, live, firmware_version, device) as st:
        t0_dev = None
        t0_wall = time.monotonic()
        for data, t in packets:
            if stop.is_set() or control.end_session.is_set():
                break
            if t0_dev is None:
                t0_dev = t
            lag = (t - t0_dev) / args.speed - (time.monotonic() - t0_wall)
            if lag > 0:
                await asyncio.sleep(lag)
            else:
                await asyncio.sleep(0)
            st.feed(data)
    live.set_status("SOURCE_ENDED" if not stop.is_set() else "STOPPED")


def simulated_packets(seed: int = 0):
    """
    Endless synthetic protocol-v2 stream: 30 s segments cycling rest -> rest
    tremor -> walking -> voluntary, with finger-on PPG. For demos and tests only.
    """
    from parkinsense.protocol.packet import BATCH_SIZE, SAMPLE_PERIOD_US, encode
    from parkinsense.synthetic import signals as S

    order = ["rest", "rest_tremor", "walking", "voluntary"]
    t_us = 1_000_000
    seq = 0
    k = 0
    while True:
        scen = order[k % len(order)]
        imu = S.SCENARIOS[scen](seconds=30, seed=seed + k)
        p = S.ppg(seconds=31, seed=seed + k)
        ir, red = S.ppg_to_slots(p, path="v2")
        n = (imu.n // BATCH_SIZE) * BATCH_SIZE
        for start in range(0, n, BATCH_SIZE):
            rows = [(imu.ax[i], imu.ay[i], imu.az[i], imu.gx[i], imu.gy[i], imu.gz[i],
                     int(ir[i]), int(red[i])) for i in range(start, start + BATCH_SIZE)]
            yield encode(rows, t_us, version=2, seq=seq), t_us / 1e6
            t_us += BATCH_SIZE * SAMPLE_PERIOD_US
            seq += 1
        k += 1


async def main_async(args) -> None:
    live = LiveState()
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    control = Control(loop, start_enabled=not args.start_stopped)
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop.set)
        except (NotImplementedError, RuntimeError):     # Windows
            pass

    if args.simulate:
        live.source = "simulated"
    elif args.replay:
        live.source = "replay"

    if not args.no_api:
        import uvicorn
        api = build_api(live, control)
        threading.Thread(target=lambda: uvicorn.run(api, host=args.host, port=args.port,
                                                    log_level="warning"), daemon=True).start()
        log.info("API on http://%s:%d (/metrics, /live, /session)", args.host, args.port)

    while not stop.is_set():
        if not control.enabled.is_set():
            live.set_status("IDLE")
            log.info("session stopped; waiting for POST /session/start")
            await _wait_any(stop, control.enabled)
            continue
        control.end_session.clear()
        try:
            if args.simulate:
                await run_paced_session(args, live, stop, control, simulated_packets(args.seed),
                                        "simulated", {"source": "simulated",
                                                      "warning": "synthetic data, not a measurement"})
            elif args.replay:
                from parkinsense.replay.replay import load, packets
                src = load(args.replay, resample=args.resample)
                await run_paced_session(args, live, stop, control, packets(src), "replay",
                                        {"source": "replay", "replay_of": str(Path(args.replay).resolve()),
                                         "source_sha256": src.meta["source_sha256"]})
                if not args.loop:
                    control.enabled.clear()
            else:
                await run_ble_session(args, live, stop, control)
        except Exception:
            log.exception("session ended with an error")
            live.set_status("ERROR")
        if stop.is_set() or args.once:
            break
        if control.enabled.is_set():
            await asyncio.sleep(RECONNECT_DELAY_S)
    live.set_status("STOPPED")
    log.info("runtime stopped")


def parse_args(argv=None):
    ap = argparse.ArgumentParser(description="ParkinSense live acquisition")
    src = ap.add_mutually_exclusive_group()
    src.add_argument("--simulate", action="store_true",
                     help="synthetic protocol-v2 stream (labelled SIMULATED everywhere); no hardware needed")
    src.add_argument("--replay", metavar="CAPTURE_CSV",
                     help="stream a recording at its recorded pace into a NEW session (original untouched)")
    ap.add_argument("--resample", action="store_true", help="with --replay: legacy ~23 Hz serial logs")
    ap.add_argument("--loop", action="store_true", help="with --replay: start again when the file ends")
    ap.add_argument("--speed", type=float, default=1.0, help="with --simulate/--replay: pace multiplier")
    ap.add_argument("--seed", type=int, default=0, help="with --simulate")
    ap.add_argument("--firmware-version", default="unknown",
                    help="record the flashed firmware build (firmware >= 5.0 reports it automatically)")
    ap.add_argument("--out", default="recordings")
    ap.add_argument("--metrics-file", default=C.METRICS_FILENAME)
    ap.add_argument("--host", default="0.0.0.0",
                    help="API bind address. Default 0.0.0.0 preserves the v2 behaviour the phone "
                         "app relies on (LAN access); use 127.0.0.1 to keep it local-only.")
    ap.add_argument("--port", type=int, default=C.DEFAULT_API_PORT)
    ap.add_argument("--no-api", action="store_true")
    ap.add_argument("--once", action="store_true", help="exit after the first session ends")
    ap.add_argument("--start-stopped", action="store_true",
                    help="start idle; begin a session with POST /session/start (or the dashboard)")
    ap.add_argument("--notes", default="")
    a = ap.parse_args(argv)
    if a.speed <= 0:
        ap.error("--speed must be > 0")
    return a


def main(argv=None):
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    asyncio.run(main_async(parse_args(argv)))


if __name__ == "__main__":
    main()
