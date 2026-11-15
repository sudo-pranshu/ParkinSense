# PPG noise gate (pipeline 3.1.0, WP-09 stage B)

**Evidence class: automated tests + synthetic signals + one unlabelled real recording. Not hardware-validated, not
clinically validated.** Thresholds are provisional until reference recordings with simultaneous ECG exist.

## What it does

A window with finger contact is rejected as noise when its **pulse periodicity** is low. Periodicity is the highest
normalised autocorrelation of the band-passed IR signal over lags that correspond to 40–200 bpm. It is independent of
amplitude, so a weak but regular pulse (low perfusion) is not penalised.

| Constant (`ppg/algorithms.py`) | Value | Effect |
|---|---|---|
| `PULSE_PERIODICITY_MIN_WINDOW_SEC` | 6.0 | shorter windows: no verdict (gate inactive) |
| `PULSE_PERIODICITY_REJECT` | 0.30 | below: HR and SpO₂ withheld, state `INSUFFICIENT_DATA`, `ppg_noise_rejected=true` |
| `PULSE_PERIODICITY_LOW_CONFIDENCE` | 0.45 | below: HR quality capped at `LOW_CONFIDENCE` |
| `PULSE_RHYTHM_MIN_IN_GRAY_ZONE` | 0.70 | P in 0.30–0.45 **and** rhythm quality below this: rejected |

New outputs: `pulse_periodicity` (None when not computed) and `ppg_noise_rejected`. Capture schema unchanged.
Absent finger is still `NO_CONTACT` (checked first; the gate runs only with contact).

## Measured (synthetic, `tests/unit/test_ppg_noise_gate.py` and scratch grids)

| Case | Result |
|---|---|
| white / band-limited / pink noise, 400 windows each | 100 % rejected, none VALID-capable |
| brown (random-walk) noise, 400 windows | 98 % rejected, 2 % accepted (**known limitation**) |
| low-perfusion pulses, AC/DC amplitudes 20/5, 50/10, 100/20, 300/100 | all protected (tests) |
| pulses with SNR ≥ 1 across HR/HRV grid, 48 cases | 3 rejected (6 %): HR 110–130 bpm with RMSSD ≈ 90 ms, i.e. very irregular rhythm |
| periodicity vs. amplitude | independent (test) |

Thresholds were chosen from these grids; the brown-noise leakage was documented rather than fitted away, because a
stricter threshold rejects more genuine irregular pulses.

## Real recording (the only one available)

`data/reference/ble_v1_104hz/parkinsense_20260630_123551.csv` (85 s bench recording, PPG effective rate ≈ 10 Hz held to
104 Hz, no reference ECG). In its 58 finger-contact analyses periodicity is median 0.15, maximum 0.32. Inspection of
the finger segments (≈ 30–50 s): spectral peak wanders between 0.6 and 1.2 Hz, peak share 0.11–0.58, AC/DC 10–15 %
(implausibly large for a pulse), and the reported HR stays at 59.9 ± 2 bpm regardless, i.e. it does not follow the
signal. Before the gate: 16 `VALID`, 37 `LOW_CONFIDENCE`. After: 58 `INSUFFICIENT_DATA`.

**Consequence:** golden `median_valid_hr` 61.0 → `None`, `valid_hr_fraction` 0.0964 → 0.0 for this recording only
(`tests/regression/golden.json`; all other recordings and all motion outputs unchanged). The old 61 bpm was a regression
snapshot of the previous algorithm, never a validated HR. This is evidence the old `VALID` was unsupported by the
signal; it is **not** proof that no pulse was present, since no reference exists.

## Limitations and how to retire them

* Thresholds come from synthetic signals; real-finger behaviour (pressure changes, cold fingers, dark skin, ambient
  light) is untested.
* Brown-like drift can pass (≈ 2 %). Very irregular rhythm (AF-like) may be rejected; the gate is not an arrhythmia
  detector and must not be read as one.
* Windows shorter than 6 s are not gated.
* To validate: record PPG with a reference pulse oximeter/ECG (`HARDWARE_SESSION_CHECKLIST.md`), include deliberate
  low-perfusion (cold finger, light touch) and noise (motion, loose contact) segments, and report rejection and
  false-rejection rates before changing any threshold.
