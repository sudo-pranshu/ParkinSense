# ADR-0010 — Sleep subsystem: offline, accelerometer-only, logistic regression

**Status:** Accepted · **Date:** 2026-11-06

## Context

ParkinSense had no sleep capability. The aim: the best scientifically defensible open-source approach for
wrist acceleration, introduced without touching tremor, cardiovascular or step calculations. Constraints:
no reuse of code whose licence forbids it (Oxford *asleep*, *stepcount*: Academic Use Licence), no sleep stages,
no claim of equivalence to polysomnography, subject-independent validation only.

## Options considered

1. **van Hees 2015 heuristic** (5°/5 min z-angle). No training, published, validated vs PSG; over-calls sleep.
2. **Logistic regression on movement-context features** (the van Hees rule enters as one feature).
3. **+ 2-state HMM** (transition probabilities from PSG), as for tremor (ADR-0007).
4. **+ heart-rate features.**
5. **Random forest / deep learning.** Patterson et al. 2023 found simple models slightly superior on PSG; weights and
   code for the strongest public deep model are licence-restricted.

## Decision

Option 2, accelerometer only, threshold 0.7 chosen by nested leave-one-subject-out on Walch 2019. Offline
(`parkinsense/sleep/`, `parkinsense-sleep`), not wired into `RuntimeEngine`. Night summaries are labelled
`estimate: true`, `INSUFFICIENT_DATA` produces no numbers, `period_efficiency` is named so it is not confused with
clinical sleep efficiency, and no stage labels exist anywhere.

## Evidence (leave-one-subject-out, 17 subjects, public data only)

κ 0.500 vs 0.414 for van Hees (paired Δκ +0.086, 95 % CI +0.047 … +0.127, 14/17 subjects better); TST MAE 14.0
vs 21.3 min. Balanced accuracy equal (0.767 vs 0.765); wake specificity 0.58. Options 3 and 4 lowered κ (0.472, 0.463)
and are disabled; the random forest reached κ 0.358. Details and caveats:
`docs/validation/SLEEP_STEP_VALIDATION.md`.

## Consequences

* Weights are a 7-number vector: identical maths on Android/iOS (`docs/software/SLEEP_STEP_MOBILE_SPEC.md`).
* The shipped weights are fitted on all 17 scored subjects: in-sample for them.
* Overnight use needs a firmware change (finger gate) that is documented, not made.
* No ParkinSense hardware or Parkinson's-disease validation exists; every output says so.
* Re-fit/replace only with a held-out improvement under the same protocol; bump `SLEEP_ALGORITHM_VERSION`.
