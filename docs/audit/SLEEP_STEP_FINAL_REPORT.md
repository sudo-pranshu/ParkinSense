# Sleep tracking and step detection — final engineering report

Branch `transform/engineering-overhaul`; `develop` untouched. All accuracy figures come from public wrist datasets of
other devices; **nothing here is validated on ParkinSense hardware.**

## Outcome in one table

| | Before | After |
|---|---|---|
| Sleep | none | Offline accelerometer-only sleep/wake estimate (`parkinsense/sleep`, `parkinsense-sleep`, dashboard page). κ 0.500 vs PSG (leave-one-subject-out, 17 subjects) vs 0.414 for the published van Hees rule; paired Δκ +0.086, 95 % CI +0.047 … +0.127; TST error 14.0 vs 21.3 min. Wake detection still weak (specificity 0.58). |
| Steps, default | production v1.1 | **unchanged, still the default** |
| Steps, candidate | experimental `periodic` counter (worse than production on real data: bias −37 %) | opt-in `gated` counter: held-out MAPE 18.2 % vs 111.1 %, event F1 0.753 vs 0.639 (paired ΔF1 +0.114, CI +0.092 … +0.134), Karas false steps 4.1 vs 52.5 per min — **but fails two pre-registered criteria** (SemiRegular MAPE 20.9 vs 8.2 %; walking-state sensitivity 0.900 vs 0.973), so it was **not** promoted |
| Tests | 84 | 110 (+26: sleep, gated steps, sleep page, parity vectors); no existing test modified |
| Versions | pipeline / firmware / schema / `STEP_COUNTER_VERSION` | + `SLEEP_ALGORITHM_VERSION` 1.0, `SLEEP_EPOCH_SCHEMA_VERSION` 1, `STEP_ALGORITHM_VERSIONS`; recorded in `metadata.json`; capture schema untouched |

## What was delivered

* Research and selection: [sleep](../research/SLEEP_ALGORITHMS.md), [steps](../research/STEP_ALGORITHMS.md),
  [licences](../research/LICENCES_AND_ATTRIBUTION.md).
* Code: `parkinsense/sleep/{features,model,night,api,params}.py`, `activity/step_counter_v2.py`,
  `datasets/reference.py` (dataset loaders with provenance), engine selector and metadata keys.
* Benchmarks (reproducible, subject-independent): `benchmarks/sleep_bench.py`, `steps_bench.py`, `steps_select.py`,
  `external/fetch.py`, [manifest](../../benchmarks/external/MANIFEST.md); raw results in `benchmarks/results/`.
* Validation: [report](../validation/SLEEP_STEP_VALIDATION.md); acceptance rule fixed beforehand
  ([STEP_ACCEPTANCE.md](../algorithms/STEP_ACCEPTANCE.md)).
* Docs: [SLEEP.md](../algorithms/SLEEP.md) (maths), [ACTIVITY.md](../algorithms/ACTIVITY.md) (gated counter maths),
  [architecture](../architecture/SLEEP_STEPS.md), ADRs [0010](../decisions/0010-sleep-subsystem.md) /
  [0011](../decisions/0011-step-algorithm-versioning.md) / [0012](../decisions/0012-gated-step-counter-opt-in.md),
  [hardware limits](../hardware/SLEEP_STEP_HARDWARE_LIMITS.md), [mobile spec](../software/SLEEP_STEP_MOBILE_SPEC.md),
  [adversarial review](SLEEP_STEP_ADVERSARIAL_REVIEW.md).
* Dashboard: Sleep (estimate) page — nightly timeline, per-hour sleep/wake, duration trend across real nights,
  quality panel; every value badged as an estimate; explicit empty states. The existing Activity page already shows step
  trends, walking bouts and cadence.
* Mobile: specification and cross-platform parity vectors only. No mobile code was written or run.

## What is not done or not known

1. **Overnight recording is impossible with the shipped firmware**: it streams only while a finger covers the PPG sensor.
   Not changed here (no firmware edits); documented as a requirement.
2. No ParkinSense hardware data for either algorithm; no Parkinson's-disease data; no MESA / OxWalk / Newcastle results
   (unreachable); 17 of 31 Walch subjects; Clemson is a third-party copy at 15 Hz.
3. The gated step counter is a research candidate, not a better default. Open route: hybrid bout gating and
   hardware trials.
4. `STEP_COUNTER_VERSION = "2.0"` still mislabels the v1.1 default (ADR-0011). Needs your approval to correct.
5. The shipped sleep weights are fitted on all 17 subjects (in-sample for them).
6. Mobile 2.0 (Phase 6) has not been started: it waits on whether an existing Flutter app should be built on.
