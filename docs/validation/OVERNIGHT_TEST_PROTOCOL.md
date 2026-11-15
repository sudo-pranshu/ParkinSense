# Overnight test protocol (MacBook Air M2, macOS)

Purpose: measure what the system does over ≈ 8 h unattended: link continuity, packet loss, timestamp gaps, PPG
behaviour without a finger, wear-state inference and the offline sleep estimate. **It produces numbers to report, not a
validation claim.** Evidence class: owner-run physical test. Firmware stays as is; profile B is the documented,
uncommitted `REQUIRE_FINGER_FOR_STREAMING = false` edit from the
[session checklist](HARDWARE_SESSION_CHECKLIST.md#switch-to-profile-b-step-3) (revert it afterwards).

## Safety (stop the test if any applies)

* Do not wear the board while it is charging or plugged into USB. Use a charged battery; no charging overnight on the wrist.
* Stop and remove the board on heat, swelling, redness, itching or any discomfort. Check the skin before sleeping.
* Secure the strap so nothing presses on the sensor; keep the board off bedding if it is not worn.

## Host set-up (once)

1. System Settings → Privacy & Security → Bluetooth: allow your terminal app. Keep the Mac **plugged in**.
2. Prevent sleep for the whole run: `caffeinate -dimsu -t 32400 &` (9 h). Keep the lid open or use an external display.
3. `./setup.sh`, then `./start_runtime.sh --wear --notes "overnight W9 profile B"`; start `./start_dashboard.sh` if you want to look at it.
4. Log: start time, board ID, firmware version, wrist/strap, room.

## Phases

| Time | Setup | What to check afterwards |
|---|---|---|
| 0–10 min | **No finger on the sensor**, wrist still | `biomarkers.jsonl`: `heart_rate`, `hrv_10s`, `spo2` are `INVALID`/`NO_FINGER_CONTACT` (or `SENSOR_UNAVAILABLE`) with `value: null` for every window. Any number published here is a **failure**: stop and report |
| 10–20 min | Finger on the sensor, still | `VALID`/`LOW_CONFIDENCE` HR appears; compare with a reference (pulse oximeter) **if you have one**, else report only that values appear |
| then | Board on the wrist, finger **off**, sleep | the main run |
| morning | Stop the runtime with Ctrl+C (finalises `metadata.json` → `COMPLETE`) | below |

## Afterwards

```bash
python -m parkinsense.sleep.api recordings/<session>/capture.csv --json sleep.json   # offline estimate (≥ 1 h)
parkinsense-replay recordings/<session>/capture.csv                                  # must reproduce the same outputs
grep -c . recordings/<session>/biomarkers.jsonl
cat recordings/<session>/metadata.json | python -m json.tool | grep -A14 '"integrity"'
```

Report, as numbers: duration, samples, `packets_lost_seq`, `timestamp_gaps`, `missing_samples_est`, rate status, number of
disconnects, wear-state time in each state (`metadata.json` → `wear`, **experimental**), the sleep report's data-quality
panel, and any `biomarkers.jsonl` record that violates "null value unless VALID/LOW_CONFIDENCE".

## What this does not show

No sleep-stage or clinical claim (the sleep output is an accelerometer-based estimate); wear state is inferred and
unvalidated; one night on one wrist is not a validation of PPG, HRV or SpO₂; battery life is not measured here (needs the
PPK2 tests).
