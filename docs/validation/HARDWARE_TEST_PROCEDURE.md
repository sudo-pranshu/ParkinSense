# Hardware validation procedure (firmware 5.0.0 / protocol v2)

None of these tests has been performed. Record results in the table at the bottom, with date,
board serial and host OS. Never mark a test passed without running it.

Setup: XIAO nRF52840 Sense with LSM6DS3 + MAX30102 wired as in v4; Arduino IDE with the
Seeed nRF52 core, `Seeed_Arduino_LSM6DS3`, `SparkFun MAX3010x`. Open
`firmware/parkinsense_wearable/parkinsense_wearable.ino` and build. Host: `pip install -e ".[live,dashboard]"`.

| ID | Test | Procedure | Pass criterion |
|---|---|---|---|
| H0 | Build | Compile for XIAO nRF52840 Sense | no errors/warnings in our files |
| H1 | Boot & ranges | Serial monitor 115200 | prints `IMU OK (4g/500dps/104Hz)`, `MAX30102 OK`, `ParkinSense 5.0.0 ready` |
| H2 | Rate | Finger on sensor, `parkinsense-live --once`, 10 min | `metadata.json`: `rate_status` OK, `device_rate_hz` 103–105 |
| H3 | Loss | Same session | `packets_lost_seq / packets` < 1 % at 1 m; record RSSI |
| H4 | Gyro range | Rotate wrist briskly (> 300 deg/s) | gx/gy/gz exceed 250 without sign flips; `GYRO_CLIPPED` only above ~500 |
| H5 | Current | Nordic PPK2 in series, 60 s each: idle (no finger), streaming connected, streaming not connected | record mA; compare with v4 under the same setup. **No power claim until this is done.** |
| H6 | PPG rate | Finger on, 60 s | replay summary `ppg_effective_rate_hz` ≥ 90 (v4: ~10) |
| H7 | HR vs reference | Finger on, seated, 5 min, simultaneous chest strap (e.g. Polar H10) | HR MAE vs strap; report coverage of VALID windows |
| H8 | Tremor bench | Shaker or tremor phantom at 4, 5, 6 Hz, 10–60 deg/s | reported frequency within 0.1 Hz; detection confirmed |
| H9 | Firmware rev | Connect with `parkinsense-live` | capture `firmware_version` = 5.0.0 |
| H10 | Wrap | 75-min session | `timestamp_wraps` = 1, no `window_resets` from the wrap |
| H11 | Disconnect | Walk out of range for 30 s, return | new session directory; previous `metadata.json` status COMPLETE |

Results log:

| Date | ID | Board | Result | Notes |
|---|---|---|---|---|
| | | | | |
