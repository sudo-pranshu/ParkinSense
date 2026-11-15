# Biomarker sidecar (`biomarkers.jsonl`, schema `biomarkers/1.0`)

Written next to `capture.csv` by the runtime and by `parkinsense-replay` (one JSON line per analysis window).
The capture schema (79 columns) is unchanged. **Evidence class: automated tests only.** The states describe how far a
value may be trusted by the software; none is hardware- or clinically validated.

* Versioned independently: `config.BIOMARKER_SCHEMA` / `BIOMARKER_VERSION` (1.0.0), also in `metadata.json` → `biomarkers`.
* A pure function of the per-analysis metrics: a replay of a capture gives a byte-identical file (tested).
* **`value` is `null` unless `state` is `VALID` or `LOW_CONFIDENCE`.**

| State | Meaning |
|---|---|
| `VALID` / `LOW_CONFIDENCE` | value published (low confidence: below the publish threshold) |
| `INVALID` | measured but rejected: `MOTION_ARTIFACT`, `NO_FINGER_CONTACT`, `NO_PULSE_PERIODICITY`, `DATA_GAP`, `SENSOR_FAULT`, `RATE_INVALID`, `UNKNOWN_WINDOW` (listed in `reasons`) |
| `INSUFFICIENT_DATA` | not enough clean signal yet (or no value produced) |
| `SENSOR_UNAVAILABLE` | the packet flags report the sensor as faulty (`PPG_FAULT`) |
| `NOT_ASSESSED` | reserved: no method exists (e.g. tremor severity is always `NOT_ASSESSED`) |

Record: `{schema, biomarker_version, analysis_seq, signal_time_s, biomarkers: {heart_rate, hrv_10s, spo2, tremor}}`;
each entry has `value, unit, state, reasons` plus:

| Biomarker | Extra fields and rules |
|---|---|
| `heart_rate` | `confidence`. Absent finger → `INVALID` / `NO_FINGER_CONTACT`; noise-gated window → `INVALID` / `NO_PULSE_PERIODICITY` ([noise gate](../validation/PPG_NOISE_GATE.md)) |
| `hrv_10s` | value `{rmssd_ms, sdnn_ms, pnn50_pct, mean_rr_ms}`, `window_s` (10), `n_nn_intervals`, `artefact_pct`, `hrv_confidence`, `withheld_reason`. **Never `VALID`**: capped at `LOW_CONFIDENCE` with `UNVALIDATED_PPG_HRV` and `EXPLORATORY_10S_WINDOW`; `exploratory: true`, `include_in_summaries: false` |
| `spo2` | `calibrated: false`. **Never `VALID`**: `LOW_CONFIDENCE` + `UNCALIBRATED_ESTIMATE` |
| `tremor` | value = P(tremor) from the temporal model, `tremor_state`, `severity: NOT_ASSESSED`. IMU fault / gap windows are `INVALID`, never "no tremor" |

## 10 s HRV policy (owner decision 2026-11-15)

The live card is labelled **EXPLORATORY · 10 s**. It is excluded from session summaries
(`analytics.heart_summary` no longer returns an RMSSD aggregate), from longitudinal insights and from any comparison
with conventional (5 min) HRV. The 10 s metrics are not interchangeable with conventional HRV.
