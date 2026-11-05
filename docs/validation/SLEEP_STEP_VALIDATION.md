# Sleep and step validation — public-dataset results

**Every number below comes from other people's wrist devices (Apple Watch, Shimmer3, ActiGraph), not from
ParkinSense hardware. There is no ParkinSense hardware validation of sleep or steps.** Datasets and caveats:
[../../benchmarks/external/MANIFEST.md](../../benchmarks/external/MANIFEST.md). Raw outputs:
`benchmarks/results/{sleep_walch,steps_baseline,steps_grid_*,steps_selection,steps_gated_karas}.json`.
Reproduce: `python -m benchmarks.external.fetch {walch,clemson,karas}` then
`python -m benchmarks.sleep_bench`, `python -m benchmarks.steps_bench`, `python -m benchmarks.steps_select`.

## 1. Sleep/wake vs polysomnography (Walch 2019, 17 subjects, leave-one-subject-out)

Protocol: the held-out night never contributes to training, transition estimation or scaling; the decision
threshold is chosen by a nested inner leave-one-subject-out loop. 13 674 scored 30 s epochs, 90.5 % sleep
(accuracy is inflated by prevalence — read kappa and balanced accuracy). Means over subjects.

| Method | κ | Balanced acc. | Sleep sens. | Wake spec. | TST MAE (bias), min | WASO MAE, min |
|---|---|---|---|---|---|---|
| van Hees 2015 (z-angle, 5°/5 min; published heuristic) | 0.414 | 0.765 | 0.911 | 0.618 | 21.3 (−13.9) | 20.4 |
| van Hees rule on gravity angle | 0.407 | 0.778 | 0.895 | 0.661 | 26.4 (−21.0) | 24.8 |
| Logistic regression, threshold 0.5 | 0.430 | 0.691 | 0.974 | 0.407 | 17.9 (+14.6) | 13.9 |
| **Logistic regression, nested-LOSO threshold (shipped)** | **0.500** | 0.767 | 0.953 | 0.581 | **14.0 (+1.3)** | 17.6 |
| LR + tempered HMM | 0.472 | 0.729 | 0.966 | 0.492 | 14.0 (+8.2) | 16.8 |
| LR + HR + tempered HMM | 0.463 | 0.719 | 0.966 | 0.472 | 14.1 (+8.7) | 16.3 |
| LR + untempered HMM (ablation) | 0.389 | 0.792 | 0.861 | 0.723 | 35.8 (−35.0) | 31.6 |
| Random forest + untempered HMM (reference) | 0.358 | 0.780 | 0.844 | 0.715 | 46.1 (−44.5) | 35.6 |

Paired subject-level bootstrap (10 000 draws) of shipped − van Hees:

| Quantity | mean difference | 95 % CI | subjects improved |
|---|---|---|---|
| κ | +0.086 | [+0.047, +0.127] | 14 / 17 |
| \|TST error\| (min) | −7.3 | [−13.4, −1.6] | — |

What this supports: on these 17 healthy adults the logistic model agrees with PSG better (κ) and estimates
total sleep time better than the published rule, mainly by accepting more sleep. What it does **not**
support: balanced accuracy is the same (0.767 vs 0.765); wake detection stays weak (0.58); the HMM and heart-rate
variants were *worse* and are not shipped. 17 subjects, one night each, healthy, one scorer, one device: the CI is
wide and generalisation to ParkinSense hardware or Parkinson's disease is unknown. The large MESA external test used
by the dataset authors was unreachable, so no external-set result exists.
One of 18 available subjects was excluded for < 50 % accelerometer coverage (reported in the JSON).

## 2. Steps — Clemson (30 participants x 3 conditions, 54 374 annotated foot contacts)

Motion gate held at ACTIVE for every counter (the runtime's gyroscope motion context is not available in these
datasets), so this measures the counters' own detection logic, not the runtime tremor guard. Signals up-sampled
15 → 104 Hz. Event F1 uses one-to-one matching within 0.30 s after removing each recording's median lag.
Bias = (counted − annotated) / annotated, pooled; MAPE = mean per-recording absolute percentage error.

| Counter | Condition | Bias % | MAPE % | Precision | Recall | F1 |
|---|---|---|---|---|---|---|
| **production v1.1** | Regular | −21.9 | 21.7 | 0.982 | 0.769 | 0.859 |
| | SemiRegular | +2.9 | 8.2 | 0.751 | 0.774 | 0.761 |
| | Irregular | +299.3 | 303.4 | 0.187 | 0.731 | 0.297 |
| | all | +13.3 | 111.1 | 0.640 | 0.758 | 0.639 |
| periodic (experimental, existing) | all | −37.2 | 41.3 | 0.506 | 0.330 | 0.387 |
| **gated 3.0-dev, held-out (2-fold by participant)** | Regular | −7.4 | 7.4 | — | — | 0.952 |
| | SemiRegular | −18.5 | 20.9 | — | — | 0.737 |
| | Irregular | +10.2 | 26.3 | — | — | 0.569 |
| | all | −9.7 | 18.2 | — | — | 0.753 |
| gated, shipped constants, all participants (in-sample choice) | all | −12.1 | 17.9 | 0.798 | 0.708 | 0.742 |

The threshold grid was extended once (3.2 s-window variants) after the first held-out result, so the held-out figures are mildly optimistic.
Paired participant bootstrap, held-out gated − production: event F1 **+0.114** (95 % CI +0.092 … +0.134); MAPE
−92.9 points (CI −102.0 … −84.5).

## 3. Steps — Karas (27 subjects, 641 min of labelled driving/clapping)

| Counter | False steps / min (driving, clapping) | Walking-state sensitivity | Walking-state specificity | Steps / walking min |
|---|---|---|---|---|
| production v1.1 | 52.5 | 0.973 | 0.506 | 93.5 |
| periodic | 2.4 | 0.509 | 0.983 | 73.0 |
| gated 3.0-dev | 4.1 | 0.900 | 0.966 | 105.1 |

Karas has no step annotations, so this is false-step and walking-state evidence, not count accuracy. "Steps /
walking min" includes stair walking labels and is not an accuracy figure. The motion gate is held ACTIVE here; in the
runtime it is not constant, so the 52 false steps/min of production probably overstate what the full pipeline
would count during driving. That was not measured: the gyroscope motion context needed to run the full pipeline is
absent from these datasets.

## 4. Acceptance decision (criteria fixed beforehand in [STEP_ACCEPTANCE.md](../algorithms/STEP_ACCEPTANCE.md))

| # | Criterion | Result |
|---|---|---|
| A1 | Overall pooled bias and MAPE lower than production | **Pass** (held-out \|bias\| 9.7 vs 13.3 %, MAPE 18.2 vs 111.1 %) |
| A2 | No condition worse by > 2 pts MAPE | **Fail** — SemiRegular 20.9 vs 8.2 |
| A3 | F1 higher, paired CI excludes 0 | **Pass** (+0.114, CI +0.092 … +0.134) |
| A4 | Karas false steps not higher | **Pass** (4.1 vs 52.5 per min) |
| A5 | Karas sensitivity within 2 pts, specificity not lower | **Fail** — sensitivity 0.900 vs 0.973 |
| A6 | Existing behaviour unchanged | **Pass** — default engine, golden replay and all pre-existing tests unchanged |
| A7 | Honest reporting | this document |

**Decision: production v1.1 stays the default; the gated counter is opt-in.** Two criteria failed. Part of
production's good SemiRegular count error is cancelling mistakes (precision 0.75, recall 0.77), which is why its F1
there (0.761) is close to the candidate's (0.737) despite the 12-point MAPE gap; the candidate misses short walking
bouts (recall 0.70) that its autocorrelation gate cannot yet confirm.

## 5. Not measured

ParkinSense hardware accuracy for either algorithm; walking-bout durations against a reference; cadence error
against a reference; sleep in Parkinson's disease; overnight finger-contact PPG; free-living step counts. The Clemson
15 Hz data cannot test 104 Hz behaviour; the Karas ankle sensors were not used.
