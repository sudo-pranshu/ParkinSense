# Step detection: acceptance criteria (pre-registered)

Written **before** any candidate was evaluated. A candidate replaces the production
counter (`activity/step_counter.py`, v1.1) as the default only if it meets every
criterion below on `benchmarks/steps_bench.py` over all 90 Clemson recordings
(30 participants x Regular / SemiRegular / Irregular) and all Karas subjects.
Otherwise production stays the default and the candidate remains opt-in.

Selection of any tunable constant is allowed only inside a leave-one-participant-out
loop; the reported numbers are from held-out participants.

| # | Criterion | Rule |
|---|---|---|
| A1 | Overall count error | Pooled absolute bias and MAPE (all 90 recordings) both lower than production |
| A2 | No condition regression | MAPE in each of Regular, SemiRegular, Irregular not worse than production by more than 2 percentage points |
| A3 | Event accuracy | Mean event F1 higher than production, with the paired participant-bootstrap 95 % CI of the difference excluding 0 |
| A4 | False steps | Karas false steps per non-walking minute not higher than production |
| A5 | Walking bouts | Karas walking-state sensitivity not lower than production by more than 2 points; specificity not lower |
| A6 | Existing behaviour | All existing tests pass unmodified; `default` stays the engine default; replay of `data/reference` recordings with the default counter is byte-identical |
| A7 | Honesty | Report includes per-condition numbers, the failures, and the statement that results are public-dataset (wrist, Shimmer3 / ActiGraph) and **not** ParkinSense hardware validation |

Ground-truth limits that apply to every number: Clemson step references are foot
contacts annotated on video, wrist sensor at 15 Hz resampled to 104 Hz; Karas has
activity labels only (no step events), so it supports false-step and bout-state
metrics, not count accuracy. The motion gate is held at ACTIVE in the benchmark, so the
runtime tremor guard is not exercised.
