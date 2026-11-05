# Step detection for a wrist sensor: survey and selection

Selection rule: evidence and licence, not popularity. "(verified)" = read in the primary paper or
repository during this work.

| Method | Idea | Evidence read | Reference-code licence | Decision |
|---|---|---|---|---|
| **ParkinSense v1.1** (production) | HP-filtered \|a\|, adaptive threshold μ+0.7σ over 2 s, hysteresis, 0.30 s refractory, motion-state gate | this work: Clemson/Karas numbers below | project code | **Stays the default** (acceptance criteria not met by the candidate) |
| **Verisense step algorithm** (Rowlands et al., Sensors 2022, PMC9786909) | peak detection (after Gu et al. 2017) plus periodicity, similarity and continuity checks, magnitude threshold | (verified) free-living vs thigh activPAL, 100 Hz wrist | MIT (Shimmer 2020, in the toolbox repo) | The repository's existing `step_counter_periodic.py` follows this design; it was **benchmarked here and is worse than production on all 90 Clemson recordings** (overall bias −37 %) |
| **stepcount** (OxWearables; self-supervised ResNet walking classifier + peak detection) | learned walking detector, 10 s windows | (verified) 10-fold participant-grouped CV on OxWalk (39 adults); Clemson (Shimmer3 15 Hz) used as external set | **Oxford Academic Use Licence** | **Excluded** (licence; also needs PyTorch weights). No code read into this implementation |
| **oak** (Straczkiewicz et al. 2023, JMIR Cancer; arXiv 2207.07443) | CWT walking recognition on \|a\|−1 at 10 Hz, step band 1.4–2.3 Hz, harmonic rule, T = 6 s for smartwatches | (verified) the paper's text gives walking recognition, not wrist step-count errors | BSD-3 (onnela-lab/forest) | Not implemented: it recognises walking and gives cadence, but the paper text read does not report step-count accuracy to compare against |
| scikit-digital-health gait | gait-event detection | not evaluated | MIT | not evaluated |
| Brajdic & Harle, UbiComp 2013 | comparison of step-count methods on phones | cited by the repository; **not re-verified here** | n/a | background only |

## What was built

`parkinsense/activity/step_counter_v2.py` (`GatedStepCounter`, opt-in `RuntimeEngine(step_counter="gated")`),
independent implementation, mathematics in `docs/algorithms/ACTIVITY.md`:

1. \|a\| → causal 4th-order Butterworth band-pass 0.5–3.5 Hz → local maxima above max(0.03 g, 0.5 × RMS) = *candidate* steps.
2. **Walking gate** every 0.5 s over the last 4 s: band RMS ≥ 0.12 g **and** peak normalised autocorrelation over lags
   0.30–1.40 s ≥ 0.65. Autocorrelation instead of interval CV because arm swing makes step intervals/amplitudes alternate.
3. Gate opening credits the candidates of the previous 3 s retroactively (true times kept); gate closes 2 s after the last pass.
4. The runtime's motion/tremor gate still applies.

## Why a gate at all (measured)

Per 0.5 s hop on 30 Clemson recordings (10 participants x 3 conditions): band RMS and autocorrelation separate
walking (≥ 5 reference steps in the preceding 4 s) from non-walking (≤ 1) with, at ρ ≥ 0.65 and RMS ≥ 0.12 g,
sensitivity 0.78 and false-positive rate 0.005 (`benchmarks/results/steps_selection.json` carries the full grid).

## Outcome

See `docs/validation/SLEEP_STEP_VALIDATION.md` and ADR-0012: the candidate is far better on irregular movement
and regular walking, worse on semi-regular walking, and **does not meet the pre-registered acceptance criteria**, so
production remains the default.
