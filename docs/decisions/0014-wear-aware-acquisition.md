# ADR-0014 — Wear inference on the host; no firmware or protocol change in Phase 8

**Status:** Accepted · **Date:** 2026-11-06

## Context

Phase 8 requires wear-aware continuous monitoring: wear state, IMU acquisition, PPG availability, BLE and power as
separate concepts; hysteresis; no removal from stillness alone or from PPG contact loss alone; thresholds configurable
and evaluated; a minimal safe firmware change; protocol compatibility. Findings
([architecture](../architecture/WEAR_AWARE_ACQUISITION.md)): the firmware gate controls IMU reads, packet
construction and `notify()` but not PPG polling or advertising; there is no downlink; the hardware has no
skin-contact/proximity/temperature sensor; on public wrist data worn sleeping wrists are as still as a table-level noise
floor, so motion cannot decide removal.

## Decision

1. Implement wear inference as a pure, opt-in **host** module (`parkinsense/wear`, `RuntimeEngine(wear_monitor=...)`).
   Default behaviour, outputs and the capture schema are unchanged.
2. Keep the five concepts as separate enums; add `UNKNOWN` as a pre-evidence wear state; power state is always
   `UNKNOWN` on the host.
3. Require **joint** continuous evidence (no optical contact AND stillness) for POSSIBLY_REMOVED/REMOVED; treat PPG and
   IMU faults as no evidence; label wear `inferred`.
4. Ship `still_acc_sd_g = 1 mg` as the fail-safe default, **provisional** (selected on the public data it was scored on;
   removal sensitivity unmeasured). Thresholds live in `WearConfig` and in recorded metadata.
5. **No firmware change and no protocol change.** Independent IMU/PPG operation already exists via the compile-time profile
   `REQUIRE_FINGER_FOR_STREAMING = false` (type-checked in both settings). Bit 7 of `flags` stays reserved. A device-side
   wear state needs a skin-contact sensor and would be published as protocol v3 with firmware packing tests, Python
   decode tests and v1/v2 compatibility tests.
6. Do not select additional hardware yet; options and costs are documented, selection waits for W1–W6.

## Consequences

* The host can label worn/removed periods and stop counting table movement as steps once REMOVED, but it cannot save
  battery: the host has no downlink and the device has no wear signal.
* On-device low-power REMOVED mode, wear-gated PPG duty cycling and any battery claim are **deferred** and blocked on
  hardware (sensor) and measurement (PPK2).
* Overnight recording requires profile B plus H/W tests; it is not validated.
* If W1 shows the LSM6DS3 table noise is not clearly below worn-still noise, the stillness criterion should be
  dropped as removal evidence and the additional sensor becomes mandatory.
