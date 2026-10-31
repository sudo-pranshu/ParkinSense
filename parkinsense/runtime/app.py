"""
Live acquisition: BLE (bleak) -> RuntimeEngine -> SessionRecorder, plus the
FastAPI `/metrics` endpoint consumed by the mobile app and dashboard.

    python -m parkinsense.runtime.app [--firmware-version X] [--out recordings]

Lifecycle (review P0-1, P1-7, P2-13, P2-14):
  * a recording directory is created only when a device is connected;
  * every exit path (normal return, BLE drop, Ctrl-C, SIGTERM, exception)
    closes the capture and finalises metadata.json;
  * on disconnect the app reconnects into a *new* session (new session_id,
    fresh engine state) instead of splicing across the gap;
  * analysis failures are counted in metrics/metadata, not swallowed.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import signal
import threading
import time

from parkinsense import config as C
from parkinsense.runtime.engine import RuntimeEngine
from parkinsense.runtime.recorder import SessionRecorder, _jsonable_metrics, atomic_write_json

DEVICE_NAME = "ParkinSense"
SERVICE_UUID = "ABCD1234-0000-467A-9538-01F0652C74E0"
CHAR_UUID = "ABCD1234-0001-467A-9538-01F0652C74E0"
RECONNECT_DELAY_S = 3.0
METADATA_EVERY_S = 10.0

log = logging.getLogger("parkinsense.app")


class LiveState:
    """Thread-safe holder for the latest published metrics."""

    def __init__(self):
        self._lock = threading.Lock()
        self._m: dict = {"status": "WAITING"}

    def set(self, m: dict):
        with self._lock:
            self._m = m

    def get(self) -> dict:
        with self._lock:
            return dict(self._m)


def build_api(live: LiveState):
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

    return app


async def run_session(args, live: LiveState, stop: asyncio.Event) -> None:
    from bleak import BleakClient, BleakScanner

    log.info("scanning for %s ...", DEVICE_NAME)
    device = await BleakScanner.find_device_by_filter(
        lambda d, ad: bool(d.name and DEVICE_NAME in d.name), timeout=20.0)
    if device is None:
        log.warning("device not found")
        return

    engine = RuntimeEngine(firmware_version=args.firmware_version)
    disconnected = asyncio.Event()
    with SessionRecorder(engine, root=args.out, device={"address": device.address, "name": device.name},
                         notes=args.notes) as rec:
        log.info("recording to %s", rec.dir)
        last_meta = time.monotonic()

        def on_notify(_sender, data: bytearray):
            nonlocal last_meta
            res = engine.process_packet(bytes(data))
            if res.rows:
                rec.write_rows(res.rows)
            if res.analyses:
                m = _jsonable_metrics(res.analyses[-1])
                m["status"] = "STREAMING"
                m["capture_path"] = str(rec.dir / "capture.csv")
                live.set(m)
                atomic_write_json(args.metrics_file, m)
            now = time.monotonic()
            if now - last_meta >= METADATA_EVERY_S:
                rec.write_metadata()
                last_meta = now

        async with BleakClient(device, disconnected_callback=lambda _c: disconnected.set()) as client:
            log.info("connected: %s", device.address)
            await client.start_notify(CHAR_UUID, on_notify)
            stop_task = asyncio.create_task(stop.wait())
            disc_task = asyncio.create_task(disconnected.wait())
            await asyncio.wait({stop_task, disc_task}, return_when=asyncio.FIRST_COMPLETED)
            for t in (stop_task, disc_task):
                t.cancel()
            if client.is_connected:
                await client.stop_notify(CHAR_UUID)
    live.set({"status": "DISCONNECTED", "integrity": engine.integrity()})


async def main_async(args) -> None:
    live = LiveState()
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop.set)
        except (NotImplementedError, RuntimeError):     # Windows
            pass

    if not args.no_api:
        import uvicorn
        api = build_api(live)
        threading.Thread(target=lambda: uvicorn.run(api, host=args.host, port=args.port,
                                                    log_level="warning"), daemon=True).start()

    while not stop.is_set():
        try:
            await run_session(args, live, stop)
        except Exception:
            log.exception("session ended with an error")
        if stop.is_set() or args.once:
            break
        await asyncio.sleep(RECONNECT_DELAY_S)


def parse_args(argv=None):
    ap = argparse.ArgumentParser(description="ParkinSense live acquisition")
    ap.add_argument("--firmware-version", default="unknown",
                    help="record the flashed firmware build (not yet queryable over BLE)")
    ap.add_argument("--out", default="recordings")
    ap.add_argument("--metrics-file", default=C.METRICS_FILENAME)
    ap.add_argument("--host", default="0.0.0.0",
                    help="API bind address. Default 0.0.0.0 preserves the v2 behaviour the phone "
                         "app relies on (LAN access); use 127.0.0.1 to keep it local-only.")
    ap.add_argument("--port", type=int, default=C.DEFAULT_API_PORT)
    ap.add_argument("--no-api", action="store_true")
    ap.add_argument("--once", action="store_true", help="do not reconnect after a disconnect")
    ap.add_argument("--notes", default="")
    return ap.parse_args(argv)


def main(argv=None):
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    asyncio.run(main_async(parse_args(argv)))


if __name__ == "__main__":
    main()
