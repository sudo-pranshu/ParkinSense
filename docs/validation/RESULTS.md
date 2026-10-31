# Validation results — baseline (pipeline 2.2.0) vs current (3.0.0)

**Read this first.** Every number below comes from *synthetic signals with known ground truth*
(`parkinsense/synthetic/signals.py`) or from the handful of unlabelled real recordings in
`data/reference/`. None is evidence of clinical accuracy. No patient with Parkinson's disease
has been recorded with this system.

Method: `benchmarks/run_benchmarks.py`. Baseline = the repository as found (commit `cc7b9df`,
including the uncommitted Issue #1 work), loaded from a git worktree. Both runtimes receive
byte-identical BLE packets; the baseline's clocks are patched to signal time so accelerated
feeding does not penalise its time-based logic. 16 seeds × 30 s per tremor scenario; first 8 s of
each segment excluded. Raw output: `benchmarks/results/{baseline_legacy,current}.json`.

## Tremor

| Metric | Baseline 2.2.0 | Current 3.0.0 |
|---|---|---|
| Sensitivity (analysis-level, rest + strong tremor) | 0.692 | **0.986** |
| Specificity (rest, voluntary, walking, vibration, 8.5–11 Hz) | 0.983 | **1.000** |
| F1 | 0.798 | **0.993** |
| Strong tremor 120–250 deg/s detected | 38 % | **97 %** |
| 8.5–11 Hz oscillation called PD tremor | 8.6 % | **0 %** |
| Subtle tremor 3–8 deg/s detected | 100 % | 100 % |
| Tremor during movement (action) / during walking | 49 % / 60 % | 100 % / 100 % (labelled `ACTION`) |
| Frequency error, median / p90 | 0.090 / 0.219 Hz | **0.024 / 0.096 Hz** |
| Onset latency (median) | **1.1 s** | 6.1 s |
| Offset latency (median) | **4.0 s** | 8.1 s |

The latency regression is deliberate (ADR-0007): the published state now requires ~1.4
independent windows of evidence.

## Steps

| Metric | Baseline | Current |
|---|---|---|
| Walking count error, mean (synthetic) | −9.7 % | −9.7 % (same algorithm) |
| False steps/min during rest tremor | 23.3 | **0.3** |
| False steps/min during purposeful arm movement | 46.3 | 48.8 (unchanged limitation) |
| Real `walking_60s` (≈86 expected) | 75 (counter alone) | 69 (through full runtime) |

A rewrite was tried and rejected on the real recording (ADR-0009).

## PPG (rest, 10 seeds × 60 s; motion, 6 seeds with 1.8 Hz artefact)

| Metric | Baseline, v1 fw | Current, v1 fw | Baseline, v2 fw | Current, v2 fw |
|---|---|---|---|---|
| HR MAE at rest (BPM) | 16.1 | **0.29** | 17.8 | **0.37** |
| RMSSD MAE (ms) | 195 | withheld (10 Hz PPG) | 91.6 | **6.7** |
| HR confidence, rest (median) | 0.44 | 0.59 | 0.49 | 0.73 |
| HR confidence, motion artefact (median) | 0.63 | **0.14** | 0.84 | **0.17** |
| HR MAE under motion artefact (BPM) | 29.5 | 27.7 (flagged) | 27.9 | 28.0 (flagged) |

"v1 fw" reproduces the legacy firmware's 10 Hz decimated PPG; "v2 fw" the new firmware's
~100 Hz PPG (not yet verified on hardware).

## Cost (laptop CPU, Python 3.13)

| | Baseline | Current |
|---|---|---|
| Real-time factor (full runtime incl. PPG) | 26.9× | 26.4× |
| Analysis packet latency, median / p95 | 17.4 / 19.8 ms | 17.8 / 21.5 ms |

## Real recordings (unlabelled; golden outputs in `tests/regression/golden.json`)

| Recording | Notes | Current output |
|---|---|---|
| `stationary_60s` (23 Hz, resampled) | wrist at rest | REST 100 %, no tremor, 0 steps |
| `walking_60s` (23 Hz, resampled) | walking, ~1.35 Hz cadence | ACTIVE 100 %, 69 steps |
| `normal_motion_60s` | everyday arm movement | no tremor; **90 false steps** |
| `simulated_tremor_30s` | wrist shaken at 8–9 Hz | no PD-band tremor (correct for 3.5–7.5 Hz); **83 false steps** |
| `vibration_reference_30s` | vibration | no tremor, 3 steps |
| `parkinsense_20260630_123551` (BLE v1, 87 s) | finger mostly off | rate 104.01 Hz OK, no tremor, HR VALID 10 % of windows |
| local finger-on v2 capture (not committed — personal data) | healthy wearer | a 5 s, 6.4–6.8 Hz, 7–11 deg/s oscillation flagged by both versions; cannot be labelled without ground truth |

## What would establish real accuracy

1. Tremor: PD@Home labelled data (Radboud) or a recorded cohort with video annotation;
   leave-one-subject-out evaluation via `datasets/splits.py`.
2. HR/HRV: simultaneous chest-strap ECG (procedure H7); PPG-DaLiA for motion.
3. SpO₂: reference finger oximeter across a desaturation range — otherwise it stays an estimate.
4. Steps: video- or foot-pod-counted walking and non-walking sessions.
