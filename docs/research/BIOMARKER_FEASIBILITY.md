# Biomarker feasibility (single wrist IMU + finger PPG)

"Implemented" means computed and tested on synthetic ground truth. Nothing here is clinically
validated.

| Biomarker | Definition / formulation | Sensors | Status | Main limitation / validation needed |
|---|---|---|---|---|
| Rest-tremor presence | HMM posterior over per-window spectral evidence (ADR-0007) | gyro | **Implemented** | sensitivity/specificity on labelled patient data (e.g. PD@Home) |
| Tremor frequency | interpolated PSD peak, 3.5–7.5 Hz | gyro | **Implemented** | bench shaker (H8) |
| Tremor amplitude | RMS angular velocity in ±0.625 Hz of peak, deg/s | gyro | **Implemented** | depends on placement; compare with clinical rating, not a severity score |
| Tremor time % / power (daily) | ParaDigMa definitions, still windows only | gyro + accel | **Implemented** (`analytics/biomarkers.py`) | ≥ 10 min still data per period; needs multi-day wear |
| Rest vs action tremor | tremor during ACTIVE context = ACTION | gyro + accel | **Implemented (label only)** | action tremor detection rate depends on movement harmonics |
| Personal baseline / deviation | robust z vs 28-day median/MAD, provenance-gated | any daily metric | **Implemented** (`analytics/baseline.py`) | ≥ 7 qualifying days; not an alert |
| Heart rate | PPG beat detection (existing `algorithms.py`) | PPG | Implemented, fixed | reference strap (H7); motion → flagged, not corrected |
| HRV (RMSSD, SDNN, pNN50) | Task-Force time-domain metrics on RR | PPG | Implemented; withheld at < 25 Hz | v2 firmware required; ECG reference |
| SpO₂ | ratio-of-ratios, quadratic curve | PPG red/IR | **Estimate only** | calibration against a reference oximeter; never clinical |
| Steps / cadence | v1 threshold detector | accel | Implemented | false steps during arm movement |
| Bradykinesia | slowness/amplitude of voluntary movement (e.g. PKG BKS) | accel | **Not implemented** | proprietary references; needs labelled MDS-UPDRS data |
| Dyskinesia | choreiform 1–4 Hz movement power | accel | **Not implemented** | indistinguishable from voluntary movement without labels |
| Freezing of gait | freeze index (3–8 Hz / 0.5–3 Hz power) | ankle/shank accel | **Not feasible** at the wrist | sensor location |
| Gait asymmetry / step regularity | autocorrelation step vs stride regularity | trunk/ankle | **Not feasible** reliably at one wrist | arm swing ≠ leg symmetry |
| Sleep / wake | HDCZA (van Hees 2018) | wrist accel, multi-day | **Not implemented** | firmware streams only with a finger on the PPG sensor; no overnight data |
| Medication response | within-day pattern of tremor time vs dose times | gyro + log | **Not implemented** | needs dose timestamps and weeks of data |

Computational cost (measured, laptop CPU): ~18 ms per analysis packet including PPG; ~26×
real-time for the full runtime in Python. Embedded (on-device) feasibility not assessed.
