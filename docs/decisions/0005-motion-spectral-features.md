# ADR-0005 — Tremor features on the un-band-passed spectrum; context excludes the tremor band

**Status:** Accepted · **Date:** 2026-10-31 · **Pipeline:** 3.0.0

## Problems (verified against the v2.2 source and measured)
1. `band_ratio` was computed on a 3–8 Hz band-passed signal, i.e. in-band power over
   already-band-limited power — ≈1 for nearly any input.
2. Reported frequency was the unweighted mean of three axes' FFT-bin peaks (0.41 Hz grid),
   while noise-only axes voted in `axis_agreement` (audit P1-8).
3. `MotionContext` used broadband acceleration, so a strong tremor's own acceleration set
   the context to ACTIVE, which then vetoed the tremor (−40 points). Measured: 120–250 deg/s
   rest tremor published as TREMOR in **38 %** of analyses.
4. The 50 Hz notch at fs = 104 Hz was a no-op stage.

## Decision
* One Welch PSD per gyro axis (2 s Hann segments, 50 % overlap, nfft 1024) on the
  mean-removed raw window; axes summed (orientation-independent, as in ParaDigMa).
* Peak in 3.5–7.5 Hz refined by Gaussian interpolation; tremor power = ±0.625 Hz around it;
  amplitude reported in deg/s RMS.
* Arm-movement power measured in the time domain (0.5–3 Hz band-pass, central half of the
  window only — window-edge transients from a strong carrier otherwise leak in).
* Context = max(accel-based state on 0.2–3 Hz linear acceleration, gyro arm-band state).
* Zero-phase filtering kept (audit P1-9 alternative "causal sosfilt" considered): all outputs
  are window-level spectral statistics, so phase is irrelevant; switched to SOS for numerical
  robustness.

## Validation
Synthetic suite (16 seeds × 10 scenarios): strong-tremor detection 38 % → 98 %; frequency
error median 0.11 → 0.08 Hz; band_ratio separates 1 Hz movement (< 0.05) from 5 Hz tremor
(> 0.8) (`tests/unit/test_features_and_detector.py`). Not validated on labelled patient data.

## Consequences
`band_ratio`, `frequency_std`, `axis_agreement` keep their column names but have new, documented
definitions → pipeline 3.0.0; 2.x recordings must be re-processed (replay) to compare.
