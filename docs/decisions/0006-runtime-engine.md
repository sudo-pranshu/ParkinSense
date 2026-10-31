# ADR-0006 — Pure RuntimeEngine on signal time

**Status:** Accepted · **Date:** 2026-10-31

## Problem

`runtime_v2.py` mixed BLE, FastAPI, file I/O and processing in module globals; it opened (and
truncated) its capture file on import, closed it only on Ctrl-C, read `time.time()` /
`time.monotonic()` inside processing, and could not be replayed or tested without a device
(review P0-1, P1-5, P1-7, P3-18).

## Decision

* `RuntimeEngine.process_packet(bytes) -> PacketResult(rows, analyses)` with no I/O, no globals.
* `SessionRecorder` (context manager) owns files; `app.py` owns BLE/API/reconnect.
* All temporal logic uses signal time from unwrapped device timestamps. `PPGProcessor.analyze(now=)`,
  `StepCounter.update(now=)` and `TremorHMM.update(t)` take it explicitly.
* Every raw sample is recorded from the first sample (v2 dropped the first 4 s of each capture).
* Analysis exceptions are counted, logged once with traceback, exposed in metrics/metadata, and
  escalate after 20 consecutive failures.

## Validation

`test_import_has_no_side_effects`, `test_live_and_replay_are_identical`,
`test_replay_is_deterministic`, `test_analysis_errors_are_surfaced`.
