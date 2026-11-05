# Sleep and step estimation: hardware limits and validation requirements

No hardware or firmware change was made for sleep or steps. This page records what the current device
can and cannot support, and what must be validated on ParkinSense hardware before any accuracy claim.

## What the current design provides

| Input | Source | Use |
|---|---|---|
| Wrist acceleration, 104 Hz, signal-time stamps | IMU via BLE protocol v1/v2 | sleep and steps |
| Gyroscope, 104 Hz | IMU | tremor and motion context (not used by sleep) |
| IR / red PPG | MAX30102 | **not used by the sleep estimate** |

## Dependency on finger contact (firmware) — blocks overnight recording as shipped

Both firmware versions stream **only while a finger covers the MAX30102** (IR > 50 000 counts for three
consecutive 250 ms polls starts streaming; three polls below stop it; `docs/hardware/HARDWARE.md`, "Finger gate").
v5 sets `REQUIRE_FINGER_FOR_STREAMING = true` by default. Consequences:

* **With the shipped firmware there is no IMU stream, and therefore no sleep data, whenever the finger is off the
  sensor.** An overnight recording needs either a finger held on the sensor all night (unrealistic) or a firmware
  configuration with `REQUIRE_FINGER_FOR_STREAMING = false`. That change has **not** been made here (no firmware
  was modified); it is a documented requirement for whoever records sleep. Its effect on battery life, and on the
  PPG streams (which would be `NO_CONTACT` noise), is untested.
* The same gate means steps and tremor are only recorded while the finger is on the sensor.
* **No overnight heart rate or SpO₂.** The shipped sleep model is accelerometer-only. Heart-rate features were
  evaluated on public data (Apple Watch PPG) and did not help; on ParkinSense they would be absent, never
  interpolated.
* Requirement for a future firmware revision (not made): an IMU-only overnight streaming mode, with measured
  endurance. No current measurements exist for any firmware (`docs/hardware/HARDWARE.md`, "Power").

## IMU requirements the algorithms assume

* Accelerometer in **g**, calibrated so that a still device reads ‖a‖ ≈ 1 g (non-wear detection uses an absolute SD
  of 13 mg; gravity-angle features need correct axis scale ratios). Offset/scale error is not corrected.
* No clipping during walking: the v5 firmware sets ±4 g, v4 runs at the driver default; clipped samples are flagged (`possibly_clipped`).
* Stable 104 Hz with timestamps; gaps < 50 % coverage per 30 s epoch become gaps, never imputed.
* Wrist placement. Public data are wrist-worn; a finger-clip or ring would have different arm-swing coupling and
  would need its own validation.

## Validation needed on ParkinSense hardware (none done)

1. **Steps:** counted-by-hand walking trials (treadmill + corridor, ≥ 20 participants including slow and shuffling
   gait, with and without tremor), with video foot-contact annotation, run against production and the gated counter
   with the real motion context. Report per-condition error and walking-bout detection; compare with the Clemson
   numbers in `docs/validation/SLEEP_STEP_VALIDATION.md`.
2. **Sleep:** simultaneous PSG (or at least EEG-validated reference) nights, ≥ 20 participants, including people with
   Parkinson's disease on and off medication; report κ, sensitivity/specificity, TST/WASO error with CIs.
3. **Overnight reliability:** battery, BLE continuity over 8 h, skin contact/comfort, clipping, clock drift.
4. **Non-wear:** flat-signal detection thresholds on the real sensor noise floor.

Until then every sleep value is labelled *estimate* and no performance statement may cite ParkinSense hardware.
