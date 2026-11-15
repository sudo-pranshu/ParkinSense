# ADR-0015: IMU faults and missing samples are UNKNOWN, never stillness

Status: accepted (owner approved 2026-11-15) · Pipeline 3.0.0 → 3.1.0

## Problem
Packets with `IMU_FAULT` carry zero IMU fields, and lost packets / short timestamp gaps remove samples from a window.
In 3.0.0 both entered the 4 s analysis window unchanged: zeros look like a motionless arm, so a dead IMU could be
published as `REST` / `NO TREMOR`, drive the step gate, and (offline) count as sleep.

## Decision
* `IMU_MAX_MISSING_FRACTION = 0.02` (`config.py`). For each analysis window,
  `(faulty + missing) / (window + missing) > 0.02` ⇒ the window is **UNKNOWN**. `missing` = samples inferred from lost
  packets (`lost × 10`) or a short timestamp gap (> 0.5 s already resets the windows).
* UNKNOWN window: `classification`/`tremor_state` = `UNKNOWN`, `motion_state` and all tremor numbers empty (not zero),
  `tremor_quality` = `SENSOR_FAULT` (faulty fraction alone exceeds the threshold) or `DATA_GAP`; the HMM is only
  predicted; the step counter is not fed and its continuity is broken; `hr_quality_state` VALID is capped to
  `LOW_CONFIDENCE` because motion-artefact rejection cannot run without the IMU.
* Raw rows are always recorded unchanged; `flags` still marks the fault.
* Offline sleep: `IMU_FAULT` rows are masked to NaN before epoching (existing coverage rule then yields "no data").
* Integrity counters `imu_fault_samples`, `imu_unusable_windows` are added to `integrity()`.

## Consequences
* Capture schema unchanged (79 columns). `classification` and `tremor_state` gain the value `UNKNOWN`; consumers that
  compare with `"TREMOR"` are unaffected.
* Recordings without faults or loss replay identically to 3.0.0 (golden regression unchanged); only the label differs.
* The 2 % value is a conservative engineering choice, not an empirically tuned one.

Evidence: automated tests only (`tests/unit/test_imu_fault.py`); no hardware fault injection has been performed.
