# Phase 9 task 1: tremor baseline reproduction (ParaDigMa / Timmermans 2025) — plan and pre-registered criteria

Status: **prepared, not run.** No PD@Home data has been obtained. Nothing below is a result.
Criteria in §4 are fixed here, before any held-out evaluation, and may be changed only by a dated amendment at the end of
this file that states why; a change made after seeing results is reported as such.

## 1. Dataset access (must be confirmed before ingestion)

| Item | Verified | Not verified |
|---|---|---|
| Tremor collection | Radboud Data Repository, "Parkinson@Home – IMU sensor data and video annotations for real-life tremor detection" <https://data.ru.nl/collections/di/dcmn/DSC_pdtremor_t0000359a_966>; author Timmermans; 25 PD (motor fluctuations) + 24 age-matched controls; PD recorded twice (off medication, ~1 h after dose); ≥ 1 h unscripted at home with video; both wrists; accelerometer + gyroscope, 200 Hz; manual video tremor annotation; clinical data | **access level, licence, DOI shown on the page, request procedure** — the public landing page text I could read states none of them |
| Related collection | "Parkinson@Home – IMU sensor data and video annotations for arm swing quantification in free-living gait" <https://data.ru.nl/collections/di/dcmn/DSC_pdhasq_t0000123a_971>: 25 PD + 25 controls, 200 Hz, gait/arm-swing annotations | access and licence not stated; separate dataset, not needed for tremor |
| Paper's data statement | the paper says the training data are publicly available (earlier review) | the Nature page could not be fetched in this session, so the exact data/code availability wording was **not re-read** |
| ParaDigMa | PyPI `paradigma` 1.1.2, Apache-2.0, Python ≥ 3.11; installs in an isolated venv (numpy 2.5, pandas 2.3.3, scikit-learn 1.6.0); `run_paradigma(..., pipelines=['tremor'])`; source <https://github.com/biomarkersParkinson/paradigma> | validated devices per its README: Verily Study Watch, Axivity AX6, Gait-up Physilog 4 — not ours |

**Owner actions (needed; I cannot do them from this environment):**

1. Open both landing pages in a browser (signed in, if the repository asks). Copy the *Access* and *Licence* text
   verbatim into `docs/datasets/DATASET_REGISTER.md` (or send it to me) with the DOI and the date.
2. If the collection is open: download into `data/external/pdathome/` (never committed). If it is restricted, use the
   repository's request mechanism or write to the dataset owner. Do not use any copy obtained another way.
3. Suggested request text (edit freely):
   > I am an engineering student building an open-source research wearable for Parkinson's monitoring (ParkinSense,
   > MIT-licensed). I would like access to Parkinson@Home – IMU sensor data and video annotations for real-life tremor
   > detection, to reproduce the ParaDigMa tremor classifier (Timmermans et al., npj Parkinson's Disease 2025) and
   > benchmark my own algorithm under participant-independent evaluation. I will comply with the data-use conditions,
   > keep the data out of public repositories, and cite the dataset. Please let me know the conditions and procedure.
4. Return: licence text, any data-use agreement, and the file layout (or the files).

If access is refused or restricted beyond what is acceptable, the tremor benchmark is **blocked** and is reported as such;
it is not replaced by a dataset that does not label tremor.

## 2. What ParaDigMa does (read from the installed 1.1.2 source, not from the paper)

| Stage | Setting (`TremorConfig`) |
|---|---|
| Input | gyroscope |
| Windows | 4 s, step 4 s (non-overlapping) |
| Spectrum | Hann window; PSD from 3 s segments, 80 % overlap, resolution 0.25 Hz; peak search 1–25 Hz; rest-tremor band 3–7 Hz; "below tremor" band 0.5–3 Hz |
| MFCC | 12 coefficients from 15 filters over 0–25 Hz |
| Classifier | pickled package `tremor_detection_clf_package.pkl` (model, scaler, threshold) shipped with the wheel; prediction = probability ≥ stored threshold |
| Movement gate | window rejected when below-tremor power > `movement_threshold` = 50 |
| Aggregation | tremor power: mode (binned), median, 90th percentile |

Comparison notes that must stay attached to any number:

* The shipped classifier was presumably trained on PD@Home; applying it to PD@Home is **not an independent test**
  (to be verified from the package metadata and paper). The reproduction therefore **retrains** with ParaDigMa's own
  feature code and model type under LOSO (§3 B1).
* The pickle is third-party code in executable form: load it only inside the isolated venv, never in the ParkinSense
  environment, and treat results from it as "shipped model".
* PD@Home is 200 Hz and both wrists; ParkinSense is 104 Hz, one wrist, other sensor placement and noise. Evaluating
  ParkinSense v3 on PD@Home needs decimation to ≈104 Hz; that is a **resampled** result, labelled as such.

## 3. Procedure

1. Ingestion with SHA-256 manifest (originals untouched), participant IDs kept; record exclusions with reasons.
2. **B1 – baseline reproduction.** Leave-one-participant-out retraining of the ParaDigMa feature + logistic-regression
   pipeline; threshold chosen on training folds only for 95 % specificity (the paper's operating point, to be confirmed).
   Also run the shipped classifier and mark it "not independent".
3. **ParkinSense tremor v3 as shipped** (no tuning) through the same windows/labels. Evaluated once, on all
   participants. This is a clean test of v3 because its thresholds were hand-set and not fitted to PD@Home; after this
   evaluation PD@Home has influenced development and is disclosed as such.
4. Any modified or learned candidate (classical DSP variant, MFCC+LR in the ParkinSense runtime, activity-aware gate):
   **nested LOSO** — all tuning inside the training folds, outer fold touched once.
5. Report per-participant tables and participant-clustered bootstrap CIs (§4).

Why nested LOSO instead of a locked hold-out: the paper reports 8 tremor-PD participants. A locked 20 % test set would
contain about 2 of them, which cannot support a CI. This is a limitation, stated up front. A truly independent test
needs PPP (request-gated) or ParkinSense hardware recordings from labelled tremor, neither available now.

## 4. Pre-registered metrics and acceptance criteria

Unit: 4 s window; window label from the dataset's video annotation using the dataset documentation's own rule
(confirm after access; no rule is invented here). Controls contribute specificity and false-positive minutes only.

Metrics, each per participant and summarised as mean ± SD with a 95 % participant-clustered bootstrap CI (2 000
resamples, seed fixed in the manifest): sensitivity, specificity, F1, false-positive minutes per hour (controls and
PD non-tremor time), onset latency (annotated tremor onset to first positive window; segments ≥ 8 s), walking-window
specificity (if walking is annotated), tremor-time fraction vs annotated fraction (Spearman, Bland–Altman).
Frequency error is **not** evaluable on PD@Home (video annotation has no frequency reference); it stays a bench test
(H8, shaker). Cost: ms per window on the sandbox and on the target class of host, recorded.

| ID | Criterion (fixed now) | If not met |
|---|---|---|
| B1 | Reproduction: LOSO mean sensitivity within ±0.05 of 0.61 and mean specificity within ±0.02 of 0.97 (published), under the paper's metric definitions | report "not reproduced", list differences (exclusions, labels, window rule), and use **our reproduced numbers**, not the published ones, as the baseline |
| C1 | Any statement that a ParkinSense method is better than the baseline: paired participant-clustered bootstrap 95 % CI of (method − baseline) sensitivity has lower bound > 0, **and** lower bound of the specificity difference ≥ −0.02, **and** false-positive minutes/hour in controls not higher | report "no demonstrated difference"; keep the stronger baseline as candidate |
| C2 | Promotion of anything to production or default: C1, plus no regression in `python -m benchmarks.run_benchmarks` and golden replay, works through `RuntimeEngine` at 104 Hz with capture schema, metadata provenance and replay determinism intact, walking-window specificity not lower than baseline, cost recorded | stays opt-in / research-only |
| C3 | Matched comparison | compare at a common specificity only if both methods give a continuous score; v3 is a state machine, so otherwise each method is compared at its own fixed operating point and the report says it is not matched |

No production default is changed to raise an aggregate number. No claim of clinical or hardware validity follows from
PD@Home results.

## 5. Commands (to be created when data exists; none run yet)

```bash
# isolated baseline environment, outside the ParkinSense venv
python3.12 -m venv ~/pdm-venv && ~/pdm-venv/bin/pip install paradigma==1.1.2
# ingestion + manifest, LOSO runner, report: added under benchmarks/ and parkinsense/datasets/ only after §1 is settled
```

## Amendments

(none)
