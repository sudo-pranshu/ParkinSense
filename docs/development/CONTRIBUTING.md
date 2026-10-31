# Contributing and extending ParkinSense

## Workflow

1. Branch from `develop` (or from `transform/engineering-overhaul` until it is merged).
2. `pip install -e ".[live,dashboard,dev]"`; run `pytest` before and after your change.
3. For algorithm changes, run the benchmark on both the old and the new code
   ([testing](../testing/TESTING.md#benchmarks-reproducing-the-beforeafter-numbers)) and put the
   comparison in the PR.
4. Open a PR; CI must pass (lint, tests on 3.10/3.12, firmware host tests).

Other branches in the repository (`main`, `feature/*`, `lakshya`, `spo2_test`) predate this
structure and are not covered by this documentation.

## Rules that keep the system honest

1. **Signal time only.** Processing code never calls `time.time()` / `time.monotonic()`; take
   `now` / `t` from the caller. Otherwise replay stops being deterministic.
2. **No I/O in processing.** Files belong to `runtime/recorder.py`, BLE and HTTP to `runtime/app.py`.
3. **Quality before value.** A new output gets a quality state (`config.Quality`) and must be
   `None` or flagged when it cannot be trusted.
4. **Append-only schema.** New capture columns go at the end of `V3_COLUMNS` (or a future `V4_`
   list) and bump `CAPTURE_SCHEMA_VERSION`. Never rename or reorder.
5. **Versioned wire format.** New packet meaning = new `version` byte + new decoder branch;
   keep all old decoders.
6. **Version bumps** — see the table in [replay and datasets](../datasets/REPLAY_AND_DATASETS.md#4-provenance-and-versioning).
   Record the reason in an ADR (`docs/decisions/NNNN-title.md`, see the [ADR index](../decisions/README.md)).
7. **Acceptance.** Replace an algorithm only if it is at least as good on the synthetic suite
   **and** does not regress on the real recordings (golden tests). Keep the losing variant only if
   it is useful for research, marked experimental (example: `step_counter_periodic.py`).
8. **Claims.** No accuracy, clinical or power claim in code comments, docs or the README without
   the data behind it.

## Adding a new window-level biomarker (example)

1. Compute it in a stateless function (e.g. in `motion/features.py`) from the window arrays.
2. If it needs temporal state, give that state its own class with `update(value, t)` and `reset()`.
3. Add it to `MotionPipeline.process` result, to `RuntimeEngine._metrics`, to `ANALYSIS_COLUMNS`
   and to the end of `V3_COLUMNS`; bump versions.
4. Unit test with a synthetic signal whose ground truth you control; add a performance floor in
   `tests/synthetic` if relevant; regenerate the golden file and explain the diff.
5. Document the definition in [biomarkers](../biomarkers/BIOMARKERS.md) with its status.

## Adding a new sensor stream

Requires a new protocol version (firmware `packet.h` + `protocol/packet.py` decoder branch +
spec update + host tests), a new per-sample consumer in `RuntimeEngine.process_packet`, and new
capture columns. Write an ADR first.

## Coding conventions

Python ≥ 3.10, type hints on public functions, docstrings that state units and assumptions,
constants named and justified next to their use, no bare `except`. Firmware: logic that can be
tested on the host goes in headers without Arduino dependencies (`packet.h`).

## Commit messages

`area: imperative summary` (e.g. `ppg: withhold HRV below 25 Hz effective rate`), body explaining
why and how it was validated.

## Roadmap (prioritised)

1. Flash firmware 5.0.0 and run H0–H6.
2. HR/HRV against a chest-strap ECG (H7).
3. Labelled tremor data (PD@Home) and LOSO evaluation; ParaDigMa as an external comparator.
4. Decide the finger-gated streaming policy (blocks tremor-only and overnight monitoring).
5. Reduce arm-movement false steps with labelled walking data.
6. Measure power (H5).
7. Bring the mobile app into version control and align it with the v3 metrics and quality states.
8. Fix the `STEP_COUNTER_VERSION` provenance value (see [audit](../audit/DOCUMENTATION_AUDIT_REPORT.md)).
