# ADR-0018: Biomarker sidecar with explicit states; 10 s HRV is exploratory

Status: accepted (owner decisions 2026-11-14/15) · Pipeline 3.1.0 · Sidecar 1.0.0

## Problem

Per-sample capture columns cannot say *why* a value is or is not trustworthy, and 10 s PPG HRV was summarised as if it
were conventional HRV.

## Decision

* Add `biomarkers.jsonl` (schema `biomarkers/1.0`): one record per analysis, six states, value null unless
  `VALID`/`LOW_CONFIDENCE`, derived purely from engine metrics (replay-deterministic), versioned independently of the
  pipeline. Capture schema unchanged (additive-only rule respected). Details: [SIDECAR.md](../biomarkers/SIDECAR.md).
* HRV from 10 s windows is `EXPLORATORY · 10 s`: never `VALID`, not summarised, not used longitudinally.
  `analytics.heart_summary` drops `rmssd_median`.
* SpO₂ is never `VALID` (uncalibrated).
* Engine metrics gain additive keys (`hrv_n_intervals`, `hrv_artifact_pct`, `hrv_confidence`, `hrv_withheld_reason`,
  `ppg_noise_rejected`, `pulse_periodicity`); `/metrics` stays backward compatible.

## Consequences

* Breaking only for code that read `heart_summary()["rmssd_median"]` (none in the repo besides the Cardiovascular card,
  which now shows an explanatory card instead).
* Evidence: automated tests only.
