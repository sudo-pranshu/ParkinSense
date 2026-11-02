# Testing and benchmarking

## Quick reference

| Command | What it runs | Expected (this branch, laptop) |
|---|---|---|
| `./check.sh` | everything CI runs (lint, pytest, benchmark smoke, firmware host tests, doc links) | `✔ all checks passed`, ~1 min |
| `pytest` | all non-hardware tests | `84 passed, 1 deselected` in ~50 s |
| `pytest tests/unit` | unit tests | 36 passed, ~6 s |
| `pytest -m hardware` | hardware placeholder | skipped unless `PARKINSENSE_DEVICE` is set |
| `flake8 parkinsense tests benchmarks --select=E9,F63,F7,F82,F401,F811,F841` | lint (errors only) | `0` |
| `g++ … firmware/tests/test_packet.cpp` (see [firmware](../firmware/FIRMWARE.md#tests-that-run-without-hardware)) | firmware packing/scheduler logic | `firmware packet tests: OK` |
| `python -m benchmarks.run_benchmarks --impl current --out benchmarks/results/current.json` | full synthetic benchmark | ~4 min; numbers in [results](../validation/RESULTS.md) |
| `python -m benchmarks.dashboard_bench --minutes 60` | dashboard live/history paths on a 1-hour recording | ~5 min; [report](../audit/DASHBOARD_2_REPORT.md) |

CI ([`.github/workflows/python-app.yml`](../../.github/workflows/python-app.yml)) runs lint +
`pytest` on Python 3.10 and 3.12, a benchmark smoke run (`--only cost`), and the firmware host
tests + sketch type-check, on pushes to `develop`, `main`, `transform/**` and on pull requests.

## Test categories

| Directory | Purpose | Files |
|---|---|---|
| `tests/unit` | one module in isolation | `test_protocol.py` (wire layout, round-trip, unwrap, sequence, gaps) · `test_features_and_detector.py` (frequency/amplitude accuracy, band ratio, out-of-band rejection, context) · `test_temporal.py` (HMM confirm/release, hop invariance, no lock-up) · `test_ppg.py` (HR accuracy, determinism, HRV gating, motion coupling, enum keys, reset) · `test_activity_and_splits.py` (steps, splits, leakage, baseline) |
| `tests/integration` | modules together through `RuntimeEngine` | `test_engine.py` (no import side effects, schema, analysis markers, Issue #1 invariants, per-sample steps, bad packets, gaps, loss, wrap, rate validation, error surfacing, strict JSON) · `test_replay_and_recording.py` (recorder lifecycle, **live == replay**, determinism, dataset builder) · `test_dashboard.py` (live API incremental + bounded, LiveFeed against a real server incl. runtime loss and session reset, session store read-only, every page, figures with/without data, no zeros for missing values) · `test_launchers.py` (every script's help and usage errors, missing environment, port conflict, duplicate runtime, start → health → Ctrl+C → metadata COMPLETE) |
| `tests/regression` | golden outputs on the real recordings in `data/reference/` | `test_reference_recordings.py`, `golden.json`, `make_golden.py` |
| `tests/synthetic` | performance floors on ground-truth signals (small N, CI-sized) | `test_performance_floor.py` |
| `tests/hardware` | marked `hardware`, skipped by default | placeholder pointing to the manual procedure |

Shared helpers: `tests/helpers.py` (`packets()` encodes a synthetic signal into BLE packets;
`run_engine()` feeds them through a `RuntimeEngine`).

## Golden regression

`tests/regression/golden.json` stores the replay summary outputs of six real recordings
(one BLE v1 capture at 104 Hz and five ~23 Hz serial logs replayed with `--resample`), produced
by pipeline 3.0.0. A change that moves them fails the test. If the change is intentional:

```bash
python -m tests.regression.make_golden      # rewrites golden.json
git diff tests/regression/golden.json        # explain every changed value in the PR
```

`test_known_facts_about_reference_data` adds invariants that must hold regardless of
regeneration (stationary recording has no tremor and is ≥ 95 % REST; walking recording ≥ 60 steps;
the BLE v1 recording has no tremor).

## Synthetic ground truth

[`parkinsense/synthetic/signals.py`](../../parkinsense/synthetic/signals.py), seeded and
deterministic. Gyro in deg/s, accel in g, at 104 Hz.

| Scenario | Model | Ground truth |
|---|---|---|
| `rest` | 0.1–2 Hz postural micro-motion (~1 deg/s), sensor noise 0.35 deg/s, slow bias wander | no tremor, 0 steps |
| `rest_tremor` | 4–6.5 Hz carrier, peak 8–120 deg/s (log-uniform), slow FM ±0.15 Hz and AM 25 %, dominant axis 85 % | frequency, amplitude |
| `subtle_tremor` / `strong_tremor` | same, 3–8 / 120–240 deg/s | 〃 |
| `voluntary` | band-limited 0.2–3 Hz rotations, 25–140 deg/s RMS | no tremor |
| `walking` | shoulder pendulum r = 0.6 m at stride frequency (cadence/120), centripetal + tangential + heel-strike specific force rotated into a randomly oriented sensor frame | step count = cadence × duration |
| `walking_with_tremor`, `action_tremor` | sums of the above | tremor + movement |
| `vibration` | 12–25 Hz, 4 deg/s, 0.06 g | no tremor |
| `non_pd_oscillation` | 8.5–11 Hz, 15–40 deg/s | not PD-band tremor |
| `ppg` | two-Gaussian pulse (systolic + diastolic) on an RR series with RSA and white variability; 0.25 Hz baseline wander; optional periodic motion artefact | beat times, RR, HR, RMSSD, SDNN, ratio R |
| `ppg_to_slots(path="v1"/"v2")` | reproduces what each firmware delivers per 104 Hz slot | — |

For the non-walking scenarios, the accelerometer signal is gravity rotated by the integrated gyro
plus the tangential acceleration of a 7 cm lever arm (`WRIST_LEVER_M`) and 0.003 g noise. An
early walking model lacked
the centripetal term and made the legacy step counter look 82 % wrong; it was corrected before
any decision ([ADR-0009](../decisions/0009-step-counter-acceptance.md)) — a reminder that
synthetic results are only as good as the model.

## Benchmarks: reproducing the before/after numbers

The harness ([`benchmarks/harness.py`](../../benchmarks/harness.py)) feeds byte-identical
packets to either runtime. The baseline is the repository as found (commit `cc7b9df`):

```bash
git worktree add ../ps-baseline cc7b9df
python -m benchmarks.run_benchmarks --impl legacy --worktree ../ps-baseline \
       --out benchmarks/results/baseline_legacy.json
python -m benchmarks.run_benchmarks --impl current --out benchmarks/results/current.json
python -m benchmarks.run_benchmarks --impl current --only tremor latency --out /tmp/t.json
```

Fairness: the baseline's `time` module is patched to a signal-time clock so accelerated
feeding does not distort its wall-clock hysteresis. Suites: `tremor` (16 seeds × 30 s × 10
scenarios; first 8 s excluded), `latency` (rest 20 s → tremor 30 s → rest 30 s, 8 seeds),
`steps` (16 × 60 s walking; false steps in 4 non-walking scenarios), `ppg_v1_path` /
`ppg_v2_path` (10 × 60 s rest, 6 × 60 s with a 1.8 Hz motion artefact), `cost`.
Committed results: `benchmarks/results/{baseline_legacy,current}.json`.

## What is verified and what is not

| Verified automatically | Not verified |
|---|---|
| protocol encode/decode, both versions | firmware 5.0.0 on hardware (H0–H11) |
| runtime invariants, integrity tracking, recording, replay equivalence | BLE app lifecycle with a real device |
| algorithm behaviour on synthetic ground truth | accuracy on people (any population) |
| golden outputs on six real, unlabelled recordings | HR/HRV vs ECG, SpO₂ vs oximeter |
| firmware packing logic on the host | power consumption |
| dashboard callback | dashboard visuals under long live sessions |

Manual hardware procedure: [HARDWARE_TEST_PROCEDURE.md](../validation/HARDWARE_TEST_PROCEDURE.md).
