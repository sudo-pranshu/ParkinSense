# Biomarkers: definitions and status

Status vocabulary used throughout the repository:

| Status | Meaning |
|---|---|
| **Implemented & tested** | computed by the pipeline, covered by automated tests on synthetic and/or real recordings |
| **Experimental** | implemented, not the default, or failed an acceptance check |
| **Estimate only** | computed but known to be uncalibrated |
| **Not implemented** | no code |
| **Needs hardware / reference data** | cannot be validated with what exists |
| **Needs clinical validation** | applies to every row below — nothing has been tested on patients |

## Window-level outputs (every 0.5 s)

| Biomarker | Definition | Unit | Status |
|---|---|---|---|
| Tremor presence | HMM posterior ≥ 0.8 with hysteresis ([math](../algorithms/MOTION_AND_TREMOR.md#8-temporal-inference--hmm-forward-filter)) | bool | Implemented & tested (synthetic) |
| P(tremor) | HMM posterior | 0–1 | Implemented & tested; not a calibrated probability |
| Tremor frequency | interpolated peak of the summed gyro PSD in 3.5–7.5 Hz | Hz | Implemented & tested |
| Tremor amplitude | $\sqrt{P_T}$, gyro power within ±0.625 Hz of the peak | deg/s RMS | Implemented & tested; placement-dependent |
| Tremor type | `REST` / `ACTION` by motion context | label | Implemented (label only) |
| Motion context | REST / LOW MOTION / ACTIVE | label | Implemented & tested |
| Heart rate | median RR → BPM, EMA | BPM | Implemented & tested (synthetic); needs reference strap |
| HRV | RMSSD, SDNN, pNN50 over the 10 s buffer | ms, % | Implemented; withheld below 25 Hz PPG (firmware ≤ v4) |
| SpO₂ | ratio-of-ratios, generic curve | % | **Estimate only** |
| Steps, cadence, distance, walking, active minutes | [activity](../algorithms/ACTIVITY.md) | count, spm, m, min | Implemented & tested; known false steps during arm movement |

## Session / day aggregates (`analytics/biomarkers.py`)

Input: analysis rows of a capture or dataset. Hop $h = 0.5$ s, so each analysis row represents
0.5 s and percentages are time-weighted.

### Tremor (`tremor_summary`) — ParaDigMa definitions

Let $V$ = analysis rows with `tremor_quality` ∈ {VALID, LOW_CONFIDENCE}; $Q \subseteq V$ = rows with
motion state REST or LOW MOTION ("still"); $T \subseteq Q$ = rows with `classification = TREMOR`
and `tremor_type = REST`; $T^* \subseteq T$ = rows with window evidence ≥ 0.5.

* still minutes $= |Q|\,h/60$; if < 10 min → `tremor_time_pct = None` with a reason.
* $\text{tremor\_time\_pct} = 100\,|T|/|Q|$
* tremor frequency = median `dominant_frequency` over $T^*$.
* if tremor time ≥ 3.5 %: with $\ell = \log_{10}(P_T + 1)$ over $T^*$ — `tremor_power_median`,
  `tremor_power_modal` (centre of the fullest of 20 histogram bins), `tremor_power_p90`, and
  `tremor_amplitude_dps_median`; otherwise power is not reported.

Status: implemented, unit-free of clinical meaning; needs multi-day wear (ParaDigMa aggregates
daytime data over valid weeks) and labelled validation.

### Heart (`heart_summary`)

Rows with `hr_quality_state = VALID`; ≥ 2 valid minutes required. `hr_median`; `hr_rest_p10`
(10th percentile in REST, ≥ 20 rows); `rmssd_median`; `coverage_pct` = valid / all analysis rows.

### Activity (`activity_summary`)

Final `steps`, walking minutes, median cadence while walking, fraction of ACTIVE rows.

## Personal baselines (`analytics/baseline.py`)

For one daily metric $x_d$ (e.g. tremor time %):

$$m = \mathrm{median}(x_{d-27..d-1}),\quad \mathrm{MAD} = \mathrm{median}|x - m|,\quad
z_d = \frac{x_d - m}{1.4826\,\mathrm{MAD}}$$

over the last 28 **qualifying** days.

| Rule | Value / behaviour |
|---|---|
| minimum history | 7 qualifying days, otherwise `BUILDING_BASELINE` |
| deviation | $\lvert z\rvert \ge 3$ → `DEVIATION`, else `WITHIN_BASELINE` |
| freeze | days with $\lvert z\rvert \ge 3$ are **not** added (an acute change cannot pull the reference) |
| non-qualifying day | insufficient valid time → `INSUFFICIENT_DATA`, not added |
| provenance | `rate_status ≠ OK`, packet loss > 5 %, or a firmware / pipeline version different from the baseline's → `NOT_COMPARABLE`, not added |

Purpose: flag change relative to the individual while refusing to adapt to bad or incomparable
data. It is not an alert and has no diagnostic meaning. Status: implemented & unit-tested
(`test_baseline_needs_min_days_and_rejects_provenance_change`); no longitudinal data exist yet.

## Not implemented — feasibility with this hardware

| Biomarker | Typical definition | Sensors needed | Feasibility here | Blocker |
|---|---|---|---|---|
| Bradykinesia | slowness / reduced amplitude of voluntary movement (e.g. PKG BKS, proprietary; Griffiths et al. 2012) | wrist accel | possible in principle | labelled MDS-UPDRS data; proprietary references |
| Dyskinesia | excess 1–4 Hz involuntary movement power | wrist accel | hard: overlaps voluntary movement | labels |
| Freezing of gait | freeze index = power 3–8 Hz / power 0.5–3 Hz | shank/ankle accel | **not feasible at the wrist** | sensor location |
| Gait asymmetry, step regularity | autocorrelation step vs stride regularity | trunk/ankle | not reliable from one wrist | sensor location |
| Sleep / wake | HDCZA (van Hees et al. 2018) | multi-day wrist accel | blocked | firmware streams only with a finger on the PPG sensor |
| Medication response | within-day pattern of tremor time vs dose times | gyro + dose log | possible later | dose timestamps, weeks of data |
| Recovery / readiness scores | vendor-specific composites (WHOOP, Oura) | PPG overnight | not attempted | proprietary, unvalidated definitions; overnight data |

## Computational cost
Measured on a laptop CPU (Python 3.13): full runtime ≈ 26× real time; median 17.8 ms per packet
that triggers an analysis (motion + PPG). Embedded feasibility has not been assessed.
