# Hardware session checklist (first physical validation)

Status of every test below: **NOT RUN** until you fill the results table in
[PHASE_8_VALIDATION_PLAN](PHASE_8_VALIDATION_PLAN.md#results-log). Nothing here is a result. Pass criteria are copied from
that plan and [HARDWARE_TEST_PROCEDURE](HARDWARE_TEST_PROCEDURE.md); they are not changed. No firmware or architecture
change is part of this session. The only edit is the compile-time profile flag (step 4).

**Board (owner statement):** Seeed Studio XIAO nRF52840 (Sense). This resolves the photo discrepancy in
[HARDWARE.md](../hardware/HARDWARE.md) by statement only; W0 collects the read-back evidence.

## Run order

Importance order is W0, W1, W2, H1–H3, PPK2. The run order below minimises reflashing:

| Step | Tests | Firmware build |
|---|---|---|
| 1 | W0 | none |
| 2 | H0, H1, H2, H3, H9 | shipped profile A (`REQUIRE_FINGER_FOR_STREAMING = true`) |
| 3 | W1, W2 (seated, supine) | profile B (`= false`) |
| 4 | PPK2 S1, S2, S4, S5 (+ idle proxy for S3), v4 vs v5 | A and B, back to back |

Profile B is needed for W1 and W2 because profile A sends nothing without a finger on the sensor
([architecture §1](../architecture/WEAR_AWARE_ACQUISITION.md)).

## Before you start

```bash
cd ParkinSense && git checkout transform/engineering-overhaul && git pull
pip install -e ".[live,dashboard]"
mkdir -p recordings/hw            # raw evidence; keep out of git
```

Note for every test: date, board (photo of the physical unit), firmware profile, host OS, BLE adapter, distance.
Hash every raw file you keep: `sha256sum <file>`.

## W0 — board and wiring identity

| | |
|---|---|
| Setup | Board out of the enclosure, both sides photographed in focus; USB-C to the PC |
| Commands | Double-tap the reset pad: a `XIAO-SENSE` (or similar) drive appears. Copy `INFO_UF2.txt` verbatim. In Arduino IDE note *Tools → Board* and the port |
| Expected | Silkscreen reads XIAO nRF52840 (Sense); `INFO_UF2.txt` names the bootloader/board. I do not predict its exact text |
| Record | Whether the IMU is the on-board one or an external LSM6DS3 module; MAX30102 module wiring (SDA, SCL, 3V3, GND) and whether **INT is wired**; enclosure on/off |
| Pass | Photos and `INFO_UF2.txt` saved; `HARDWARE.md` BOM and wiring match what you read |
| Save | `recordings/hw/W0/` (photos, `INFO_UF2.txt`); results-log row |

## H0–H3, H9 — firmware 5.0.0, profile A

| | |
|---|---|
| Setup | Arduino IDE 2.x, *Seeed nRF52 Boards* core (Adafruit-Bluefruit based), libraries from [FIRMWARE.md](../firmware/FIRMWARE.md#build-and-flash-v5). Finger resting on the MAX30102 (H2/H3), host within 1 m, line of sight |
| H0 build | Open `firmware/parkinsense_wearable/parkinsense_wearable.ino`, select *Seeed XIAO nRF52840 Sense*, Verify then Upload. **Pass:** no errors or warnings in our files. Save the full compiler log |
| H1 boot | Serial monitor 115200. **Expected:** `IMU OK (4g/500dps/104Hz)`, `MAX30102 OK`, `ParkinSense 5.0.0 ready (protocol v2)`, then with a finger `finger detected -> streaming` and `RATE=… IR=… SEQ=… BLE=…`. **Pass:** the first three lines appear. Save the serial log |
| H2 rate | `parkinsense-live --once --out recordings/hw/H2 --notes "H2/H3 fw5.0.0 profile A finger on"`; run 10 min; Ctrl-C |
| H3 loss | Same session. Read `metadata.json` |
| H2 expected | `measured.rate_status` = `OK`; `measured.device_rate_hz` between 103 and 105 |
| H3 expected | `integrity.loss_fraction_seq` < 0.01 (equals `packets_lost_seq / packets`); `status` = `COMPLETE` |
| H9 | `firmware_version` in `metadata.json` = `5.0.0` |
| Also | `python -m parkinsense.replay.replay recordings/hw/H2/<session>/capture.csv --out recordings/hw/H2/replay` and keep the output |
| Save | `metadata.json`, `capture.csv` (hash it), serial log, RSSI at the host if the OS shows it, results-log rows |

If a test fails, record the failure and stop that branch: do not edit firmware to make it pass during this session.

## Switch to profile B (step 3)

```bash
grep -n "REQUIRE_FINGER_FOR_STREAMING" firmware/parkinsense_wearable/config.h
# edit that line to:  = false;   then rebuild and upload. Do not commit the edit.
git diff --stat                    # expect exactly config.h
# afterwards:  git checkout firmware/parkinsense_wearable/config.h
```

**Expected:** with no finger on the sensor the serial monitor still prints `RATE=…` lines and the host receives packets
(this is W5's first observation; record it).

## W1 — table noise floor (3 surfaces × 10 min)

| | |
|---|---|
| Setup | Profile B. Board fixed flat, no finger, no touching, nothing moving the surface. Three different surfaces (for example heavy desk, floor slab, soft surface such as a folded towel). Record the surface and the room activity |
| Commands | Per surface A, B, C:<br>`parkinsense-live --once --out recordings/hw/W1 --notes "W1 surface=A"` — 10 min, Ctrl-C<br>`python -m benchmarks.imu_noise_report recordings/hw/W1/<session>/capture.csv --label W1-A --out recordings/hw/W1/W1_A.json` |
| Expected | JSON with `median_rate_hz` ≈ 104, `gaps_ge_5s` 0, `acc_sd_mg` and `gyro_sd_dps` percentiles p01…p99 |
| Pass | For all three surfaces `acc_sd_mg.p99` < half of the default stillness threshold, i.e. < 0.5 mg (`table_p99_below_half_threshold` = true). If not, that is a **finding**: motion stillness cannot separate a table from sensor noise on this hardware and an extra sensor is required ([architecture](../architecture/WEAR_AWARE_ACQUISITION.md)). I have not checked the LSM6DS3 datasheet noise figure against this; the measurement decides |
| Save | three `capture.csv` + `metadata.json`, three JSON reports, surface photos |

## W2 — worn-still noise (seated and supine)

| | |
|---|---|
| Setup | Profile B, board worn on the wrist as intended, finger **not** on the sensor. Seated, arm resting, still for 10 min. Then supine, still, 30 min (awake is fine; log your own movements) |
| Commands | `parkinsense-live --once --out recordings/hw/W2 --notes "W2 seated"` (then `… "W2 supine"`)<br>`python -m benchmarks.imu_noise_report <capture.csv> --label W2-seated --table-json recordings/hw/W1/W1_A.json recordings/hw/W1/W1_B.json recordings/hw/W1/W1_C.json --out recordings/hw/W2/W2_seated.json`<br>`python -m parkinsense.wear.api <capture.csv> --out recordings/hw/W2/wear_seated.json` |
| Expected | `margin_worn_p01_over_table_p99` in the JSON; wear report with `time_in_state_s` |
| Pass | (plan W2, short-session form) `margin_worn_p01_over_table_p99` ≥ 2 **and** `time_in_state_s.REMOVED` = 0 for both sessions. A worn wrist that reaches POSSIBLY_REMOVED or REMOVED is a failure of the default threshold, not of the test |
| Not yet | The overnight part of W2 (≥ 5 nights, ≥ 3 people) and W8 are separate later sessions. Overnight stays **not validated** |
| Save | captures, metadata, JSON reports, a diary line with your own movements |

## PPK2 — current consumption (first session subset)

| | |
|---|---|
| Setup | [POWER_MEASUREMENT](../hardware/POWER_MEASUREMENT.md) §1: PPK2 in **source-meter** mode feeding the board's battery input at 3.7 V, USB disconnected. Confirm the BAT pad polarity and the mode steps against Seeed's pinout and Nordic's PPK2 documentation before connecting (neither was re-fetched). Photograph the wiring. Use the PPK2 desktop app at its maximum sample rate and export the raw CSV |
| Runs | S1 worn/finger on, streaming connected; S2 profile B with the sensor covered and the wrist moving; S4 and S5 streaming connected vs advertising only; idle-no-finger in profile A as the labelled proxy for S3. Each: 60 s settle then ≥ 5 min, ≥ 3 runs. Then repeat S1 with `firmware/legacy/ble_stream_v4` on the same board, wiring and host, back to back |
| Not yet | S6 (≥ 20 reconnections) and S7 (≥ 8 h) are later sessions |
| Expected | A trace with visible BLE connection-event structure in the first 10 s. I give **no** expected current |
| Pass | Completeness only: every run ≥ 5 min after settling, ≥ 3 runs for S1–S5, raw CSV kept, supply voltage and profile recorded, v4 and v5 measured back to back. No power or battery-life claim until the log table is filled |
| Save | raw PPK2 exports (hash), app screenshots, wiring photo, rows in the POWER_MEASUREMENT §6 table |

## After the session

1. Fill the results rows (date, ID, board, result, notes) in `PHASE_8_VALIDATION_PLAN.md` and `POWER_MEASUREMENT.md`.
2. Send me the JSON reports, `metadata.json` files and serial logs (raw captures if you are comfortable); I will update
   the evidence record from them and nothing else.
3. Anything that failed is reported as a finding with the data attached.
