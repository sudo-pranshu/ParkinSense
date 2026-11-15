# ADR-0017: Reject PPG windows without a periodic pulse; protect low-perfusion pulses

Status: accepted (owner approved conditionally 2026-11-15) · Pipeline 3.1.0

## Problem

Heart rate and SpO₂ could be reported `VALID` from windows with finger contact but no coherent pulse (noise, pressure
transients). Amplitude-based rejection would also discard genuine low-perfusion pulses.

## Decision

Use amplitude-independent pulse periodicity (autocorrelation of band-passed IR over 40–200 bpm lags) as the
discriminator. P < 0.30 rejects; 0.30–0.45 rejects only with weak rhythm quality; < 0.45 caps quality at
`LOW_CONFIDENCE`. Rejected windows publish no HR/SpO₂ (`INSUFFICIENT_DATA`). Contact detection is unchanged.
Details and measured numbers: [PPG_NOISE_GATE.md](../validation/PPG_NOISE_GATE.md).

## Consequences

* Behaviour change: the real bench recording loses its 16 `VALID` windows; golden updated for that one recording
  (reason documented above), nothing else changes.
* ≈ 2 % brown-noise leakage and ≈ 6 % false rejection of very irregular synthetic pulses (known, documented).
* Thresholds provisional; retune only with reference data.

Evidence: automated + synthetic tests, one unlabelled real recording. No hardware or clinical validation.
