# Sleep and step work — adversarial review

Written after the implementation, trying to break each claim. Findings that changed the code are marked **fixed**;
the rest are limits that remain.

## Findings

| # | Challenge | Finding | Status |
|---|---|---|---|
| 1 | "Is the step benchmark fair to production?" The motion gate is held at ACTIVE, which the runtime does not do. | Unfair in one direction: it inflates production's false steps (Irregular, Karas driving) because the runtime's REST gate and tremor guard are absent. It is equally absent for the candidate. The 52 false steps/min and +299 % are *upper-bound* artefacts of the benchmark, stated in the validation report. They still show production has no walking-periodicity check. | Documented |
| 2 | "Production's good SemiRegular MAPE is real?" | Partly cancelling errors: precision 0.75 / recall 0.77. The candidate's F1 there is 0.737 vs 0.761. | Documented |
| 3 | Held-out numbers: was the candidate tuned on the test set? | Selection used a 2-fold participant split and each fold's held-out result uses thresholds picked on the *other* fold. **But the grid was extended once (window 3.2 s variants) after the first held-out result showed the SemiRegular failure.** That is a second look at held-out data; the held-out figures are mildly optimistic. The pre-registered decision (reject) is unaffected because the candidate failed anyway. | Documented |
| 4 | Clemson data provenance. | Not the canonical download; channels were min-max normalised by a third party, and we re-calibrated to g ourselves. Calibration error would affect both counters (both use magnitude, but the adaptive/absolute thresholds are in g: 0.03, 0.12 g, min 0.08 g). Absolute-threshold sensitivity to scale error was **not** tested. | Open |
| 5 | Clemson is 15 Hz up-sampled to 104 Hz. | Band-limited: spectral content above 7.5 Hz absent. Peak detection after a 0.5–3.5 Hz band-pass is robust to this; the production high-pass-only filter keeps more broadband energy that is missing here. Behaviour at true 104 Hz is not measured. | Open |
| 6 | Sleep: does threshold selection leak? | The threshold is chosen by an inner LOSO loop on training subjects only, and `tests/unit/test_sleep.py::test_loso_training_never_sees_the_held_out_subject` asserts that fitting is independent of the held-out subject. The *shipped* weights (fitted on all 17 subjects) are in-sample for them. | Documented |
| 7 | Sleep: is "better than van Hees" real? | κ and TST error, yes with CI excluding 0 over 17 subjects. Balanced accuracy is equal; wake specificity is 0.58. The model buys TST accuracy by calling more sleep. Prevalence 90.5 %. | Documented |
| 8 | Sleep: unequal subject nights. | Walch records include in-bed time before sleep; ParkinSense nights will differ. One subject (13.5 % coverage) excluded and reported. 13 of 31 subjects were not obtainable (mirrors). | Documented |
| 9 | Non-wear rule on a real still night. | `acc_sd < 13 mg for ≥ 60 min` is from the literature (unverified here for this sensor); a very still sleeper on a quiet IMU could be marked non-wear. Synthetic test needed twitches to avoid the flag. Real-sensor noise floor unknown. | Open (hardware) |
| 10 | Memory/time on an 8 h capture. | `analyze_file` originally loaded all 79 columns (≈ 3 M rows). **Fixed:** reads only time + acceleration columns; 32-bit timestamp wrap handled and tested. | Fixed |
| 11 | Unbounded `step_event_times` in a long live session. | **Fixed:** bounded deque (100 000). | Fixed |
| 12 | Silent misconfiguration: `RuntimeEngine(step_counter="typo")` fell back to the default. | **Fixed:** raises `ValueError`. | Fixed |
| 13 | Dashboard Sleep page cost: analysing every long session on each load. | **Fixed:** cached by file stat, trend limited to the 7 most recent qualifying sessions. First load of a long capture still takes seconds. | Fixed / known |
| 14 | Did anything existing change? | Full pre-existing suite and the golden replay regression pass unmodified; `STEP_COUNTER_VERSION` untouched; capture schema untouched. | Verified by test run |
| 15 | Could a chart show fabricated data? | Empty states: no sleep chart for < 1 h or no ≥ 30 min sleep period; trend needs ≥ 2 real nights; tests assert empty states and that every sleep card carries the "uncalibrated estimate" badge. | Tested |
| 16 | Overnight feasibility. | The firmware streams only with a finger on the sensor; overnight recording is impossible as shipped. | Documented, blocks real use |

## Failed experiments (kept for the record)

| Experiment | Result | Evidence |
|---|---|---|
| Existing `periodic` step counter (CV-based bouts) | Worse than production everywhere (bias −37 %, F1 0.387) | `steps_baseline.json` |
| Gated counter, ρ ≤ 0.6 | Irregular false steps return (+52 % at ρ 0.6, RMS 0.08 g) | `steps_grid_a.json` |
| Gated counter, 3.2 s window | No SemiRegular gain; unstable at low thresholds | `steps_grid_c/d.json` |
| Gated counter overall | Fails A2 and A5 → stays opt-in | `steps_selection.json`, `steps_gated_karas.json` |
| HMM smoothing of sleep probabilities | κ 0.50 → 0.47 (tempered) / 0.39 (untempered) | `sleep_walch.json` |
| Heart-rate features for sleep | κ 0.472 → 0.463 | `sleep_walch.json` |
| Random forest + HMM for sleep | κ 0.358 | `sleep_walch.json` |
| van Hees on gravity angle instead of z-angle | no gain (κ 0.407 vs 0.414) | `sleep_walch.json` |
