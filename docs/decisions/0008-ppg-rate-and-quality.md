# ADR-0008 — PPG at the true slot rate, owned state, explicit quality

**Status:** Accepted · **Date:** 2026-10-31

## Problems (verified, measured on synthetic ground truth)
* `PPGProcessor()` defaulted to fs = 50 Hz while samples arrive at 104 Hz (audit P0-2) →
  every interval wrong by 2.08×. Measured HR error 16–18 BPM; RMSSD error 92–195 ms.
* Motion state never passed, and the key spelling (`LOW_MOTION` vs `LOW MOTION`) would have
  missed anyway (audit P1-5). Measured: HR confidence *higher* during motion (0.63–0.84) than
  at rest (0.44–0.49).
* SpO₂ lock/rate-limit added the whole 10 s buffer duration per call → 20× too fast at a 0.5 s
  hop (new finding N-1). SpO₂ state was a module global never reset by `reset()`.

## Decision
fs = slot rate (104 Hz); signal-time clock; processor-owned SpO₂ state with `elapsed_sec`;
`MotionState` enum keys; motion-coupling check (HR fundamental within 0.12 Hz of the motion
fundamental or its 2nd harmonic → confidence × 0.25, state `MOTION_ARTIFACT`); HRV withheld when
the distinct-sample rate < 25 Hz (v1 firmware: 10 Hz → ±100 ms RR quantisation);
`hr_quality_state` ∈ {VALID, LOW_CONFIDENCE, MOTION_ARTIFACT, NO_CONTACT, INSUFFICIENT_DATA}.

## Result (synthetic)
Rest HR MAE 16–18 → 0.3–0.4 BPM; RMSSD MAE 92 → 6.7 ms (v2-firmware path); motion confidence
0.63–0.84 → 0.14–0.17. HR under periodic motion artefact is still wrong (~28 BPM) — now flagged,
not fixed. SpO₂ remains an uncalibrated estimate; no reference oximeter data exists.
