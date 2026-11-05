# Sleep algorithms for a wrist accelerometer: survey and selection

Scope: estimate sleep/wake and night summaries from ParkinSense wrist acceleration (104 Hz, ±
range per firmware). Selection rule: **evidence and licence, not popularity**. Items marked
(verified) were read from the primary paper or repository during this work; everything else is
stated as "not verified".

## What the evidence says

| Method | Input | Evidence read | Licence of reference code | Decision |
|---|---|---|---|---|
| **van Hees 2015** (PLoS ONE 10(11):e0142533): z-angle, sustained inactivity = no change > 5° for ≥ 5 min | raw acc, 5 s | (verified) vs PSG, n = 28 clinic patients (Newcastle): ~83 % accuracy, overestimates sleep by ~31 min at 5°/5 min | GGIR, Apache-2.0 | **Implemented independently as the published-heuristic baseline** (`vanhees_sleep`) |
| **HDCZA** (van Hees 2018, Sci Rep, doi 10.1038/s41598-018-31266-z): sleep-period window from 5 min rolling median of z-angle change, threshold = 15 x 10th percentile, blocks > 30 min, gaps < 60 min merged | raw acc | (verified) Newcastle left wrist: SPT accuracy 87 %, onset error 30.8 min, wake error 47.1 min (mean absolute) | GGIR, Apache-2.0 | **Sleep-period merge rule (60 min gap, ≥ 30 min) adopted in spirit**; ParkinSense does not use the guider percentile (no daily context offline) |
| **Walch 2019** (Sleep 42(12)): activity counts + HR + clock proxy; LR/kNN/RF/MLP | Apple Watch acc + HR | (verified) n = 31, PSG; at 93 % sleep sensitivity wake-correct 0.47–0.60, κ 0.36–0.45; external test on MESA | MIT (`ojwalch/sleep_classifiers`); data ODC-By | **Dataset used for validation.** Code not copied |
| **Sundararajan 2021** (Sci Rep 2021, doi 10.1038/s41598-020-79217-x): 36 features (ENMO, z-angle, LIDS) + random forest, nested CV, 158 participants | raw acc | (verified) subject-independent | code on Zenodo (licence not checked) | RF family tested in our benchmark on our features (it lost, see below); features not copied |
| **Patterson 2023** (npj Digit Med 2023, doi 10.1038/s41746-023-00802-1): 8 algorithms vs PSG, Newcastle | counts / raw acc | (verified) "simple regression-based and heuristic algorithms slightly superior" to ML/DL; van Hees best sensitivity (83.6 %) and F1 | MIT (ActiGraph repo) | Supports a simple model; no code used |
| Cole–Kripke, Sadeh, Oakley, Sazonov | ActiGraph counts | (verified as compared in Patterson 2023) | n/a | Need proprietary-style activity counts; not used |
| **asleep** (Oxford, deep learning) | raw acc | not verified (performance not read) | **Oxford Academic Use Licence** | **Excluded**: licence forbids reuse here; no code read into this implementation |
| MESA / NSRR-trained models | n/a | n/a | n/a | MESA unreachable from the build environment |

## What was built

`parkinsense/sleep/` (algorithm 1.0, documented with equations in `docs/algorithms/SLEEP.md`):

1. 30 s epochs from 5 s sub-epochs; orientation features after van Hees (z-angle change) and an
   orientation-free gravity-angle change, ENMO, per-axis SD for non-wear.
2. Six movement-context features per epoch (log gravity-angle change, local movement density,
   context ENMO, still-bout length, log time since / until the nearest movement).
3. L2-regularised logistic regression (Newton / IRLS), decision threshold chosen by an *inner*
   leave-one-subject-out loop.
4. Night summary: HDCZA-style sleep-period merge, TST, WASO, period efficiency, awakenings,
   fragmentation, non-wear.

## Experiments that did not help (kept out of production)

All figures leave-one-subject-out on Walch 2019, 17 subjects (see `docs/validation/SLEEP_STEP_VALIDATION.md`).

* **Two-state HMM smoothing** of the classifier output: κ 0.50 → 0.47 (tempered) or 0.39 (untempered). Untempered
  smoothing doubles the TST error (35.8 min vs 14.0). Not shipped.
* **Heart-rate features** (relative HR, local HR SD): κ 0.463 vs 0.472 without. Not shipped; also unavailable overnight
  on ParkinSense (the optical sensor needs finger contact, `docs/hardware/SLEEP_STEP_HARDWARE_LIMITS.md`).
* **Random forest + HMM** (scikit-learn, reference): κ 0.358, worse than the published heuristic. Not shipped.

## Limits that apply to every claim

Movement-based sleep/wake is an *estimate*. It systematically over-calls sleep in quiet wakefulness
(wake specificity 0.58 here, as in the literature). It is not polysomnography, produces no sleep
stages (none are computed or displayed), and has not been validated on ParkinSense hardware or in
Parkinson's disease.
