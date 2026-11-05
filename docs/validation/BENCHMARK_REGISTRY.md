# Algorithm benchmark registry

One row per algorithm/version. A row is only as strong as its evidence class: **synthetic** (generated signals with known
truth), **public data** (other people's devices), **hardware** (ParkinSense device), **clinical**. Nothing here is
hardware or clinical evidence unless that column says so — today none does. Superiority is claimed only between
methods scored on the **same data with the same protocol**; where a row has no comparator it says "no comparator".

Status vocabulary: **production** (default code path), **experimental** (opt-in, failed or has not met its
acceptance rule), **candidate** (planned, not implemented), **provisional** (shipped but thresholds unvalidated on hardware).

## Registry

| Algorithm | Version | Source / reference | Licence | Dataset (evidence class) | Participants | Train / validation / test | Metrics (CI where computed) | HW requirements | Compute cost | Known failure cases | Status | Reproduce |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Tremor: Welch PSD + HMM | 3.0 | ParkinSense (ADR-0005, 0007) | MIT | Synthetic signals (docs/validation/RESULTS.md) | n/a | no training; hand-set thresholds | Sens 0.986, spec 1.000, F1 0.993 vs baseline 2.2.0 0.692/0.983/0.798; no CI computed; **synthetic only** | 104 Hz gyro | see RESULTS.md (cost section) | Onset latency 6.1 s (baseline 1.1 s); real-patient accuracy unknown | **production** | `python -m benchmarks.run_benchmarks` |
| Tremor: MFCC + logistic regression (Timmermans 2025) | paper's | github.com/biomarkersParkinson/paradigma, pdathome_tremor | Apache-2.0 | PD@Home LOSO (public, access unconfirmed) | 24 PD + 24 controls | LOSO | Sens 0.61 (SD 0.20), spec 0.97 (SD 0.05) as published | 50–100 Hz wrist gyro | not measured | Rhythmic non-tremor tasks; paper reports 8 tremor-PD participants | **candidate (Phase 9)** — not implemented, not reproduced | — |
| Sleep/wake: van Hees 2015 z-angle (5°/5 min) | published heuristic | van Hees et al. 2015 | paper; GGIR Apache-2.0 | Walch PSG (public) | 17 | none (rule) / LOSO for comparison | κ 0.414, bal. acc. 0.765, TST MAE 21.3 min, WASO MAE 20.4 min | accelerometer | negligible | Weak wake specificity 0.62 | baseline | `python -m benchmarks.sleep_bench` |
| Sleep/wake: logistic regression, nested-LOSO threshold | 1.0 | ParkinSense | MIT | Walch PSG (public) | 17 | LOSO + nested inner LOSO for threshold | κ **0.500**, bal. acc. 0.767, TST MAE 14.0 min (bias +1.3); paired Δκ +0.086 [+0.047, +0.127] vs van Hees, 14/17 subjects better; \|TST error\| −7.3 min [−13.4, −1.6] | accelerometer | O(1) per 30 s epoch | Wake specificity 0.58; balanced accuracy not better than van Hees (0.767 vs 0.765); 17 healthy subjects, 1 night | **production (offline estimator)** | same |
| Steps: production counter | 1.1 | ParkinSense | MIT | Clemson (public, 15 Hz up-sampled), Karas | 30 / 27 | none | Pooled bias +13.3 %, MAPE 111.1 %, F1 0.639; Karas 52.5 false steps/min | accelerometer | per-sample filters | Irregular gait +299 % | **production** | `python -m benchmarks.steps_bench` |
| Steps: gated counter | 3.0-dev | ParkinSense (ADR-0012) | MIT | Clemson, Karas | 30 / 27 | 2-fold by participant for threshold choice | Held-out MAPE 18.2 %, F1 0.753; paired ΔF1 +0.114 [+0.092, +0.134] vs production; Karas 4.1 false steps/min, walking sensitivity 0.900 | accelerometer | autocorrelation every 0.5 s | **Fails 2 of 7 pre-registered criteria** (SemiRegular MAPE 20.9 vs 8.2; Karas sensitivity 0.900 vs 0.973); grid extended once after held-out result (optimistic) | **experimental, opt-in** | `python -m benchmarks.steps_select` |
| Wear: motion-only removal rule (van Hees 2011 / GGIR: all-axes SD < 13 mg ≥ 60 min) | published rule | GGIR docs; `sleep/night.py` | Apache-2.0 (GGIR) | Walch worn nights (public) | 15 usable of 18 | none (rule) | On worn sleeping wrists, **36.2 %** of the night (mean) lies in still runs ≥ 15 min at 13 mg; 15/15 subjects affected | accelerometer | negligible | Flags worn sleep as non-wear | baseline, **unsafe as sole removal evidence** | `python -m benchmarks.wear_bench --only a` |
| Wear: state machine, `still_acc_sd_g` = 4 mg | 1.0 (not default) | ParkinSense | MIT | Walch worn nights, PPG forced absent | 15 | none; sweep on the evaluated data | Mean time in REMOVED 42.5 %; 12/15 subjects ever REMOVED | accel (+gyro, IR) | 3.1 µs/sample (Python, aarch64 sandbox, 1 h of 104 Hz, 10-sample chunks) | Worn sleepers called removed | rejected threshold | `python -m benchmarks.wear_bench --only b` |
| Wear: state machine, `still_acc_sd_g` = 2 mg | 1.0 (not default) | ParkinSense | MIT | same | 15 | same | Mean time in REMOVED 6.7 %, POSSIBLY_REMOVED 16.0 %; 5/15 ever REMOVED (per-subject up to 31.6 %) | same | same | Same | rejected threshold | same |
| **Wear: state machine, `still_acc_sd_g` = 1 mg (shipped default)** | 1.0 | ParkinSense | MIT | same worn nights (PPG absent) + 27 Karas driving subjects (623 min) | 15 + 27 | **Threshold chosen on the same worn nights it is scored on: optimistic, not held out** | Worn nights: 0 % REMOVED / POSSIBLY_REMOVED, 0/15 subjects; Karas driving: 0 % | accel (+gyro, IR) | 3.1 µs/sample | **Sensitivity to true removal is unmeasured** (no non-wear ground truth exists in public data) and 1 mg is at the Apple Watch noise floor (pooled 1st percentile of epoch SD 0.89 mg), so on this sensor it would almost never flag a table either. LSM6DS3 bench noise unknown | **provisional** | `python -m benchmarks.wear_bench` |

## Reading the wear rows honestly

Moving the threshold from 4 mg to 1 mg removed every false removal in public data, but the same move necessarily lowers
the chance of detecting a real table. The registry therefore records the shipped default as the **fail-safe** choice
(never wrongly suppress a worn night) and marks it provisional until bench recordings (plan W1–W3) give the missing
sensitivity side. This is a selection made on the evaluated data; it is not an independent test.

## Rules for adding a row

1. Fix the acceptance criteria before looking at held-out results (as in `docs/algorithms/STEP_ACCEPTANCE.md`).
2. Subject-independent splits; report per-subject spread and a paired bootstrap CI against the comparator.
3. State the evidence class and any decision that used the test data; mark such results optimistic.
4. Experimental algorithms stay opt-in until every criterion passes.
5. Provide the reproduction command and commit the result JSON under `benchmarks/results/`.
