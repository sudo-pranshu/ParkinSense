# Phase 8 validation plan

Four evidence classes are kept apart. A result from one class is never reported as another.

| Class | Meaning | Status in Phase 8 |
|---|---|---|
| **Automated / host firmware** | pytest, `g++` tests and type-checks that run in CI | done (§1) |
| **Simulated** | synthetic signals with known truth | done (§1) |
| **Research dataset** | other people's devices | done for the false-removal side only (§2) |
| **Owner-reported physical testing** | owner wore and ran the updated firmware, dashboard and system | reported working; **no ID, duration, log or measurement attached** (§3a) |
| **Physical hardware (documented tests)** | ParkinSense board, individually recorded tests | **every item in §3 is NOT RUN** |

## 1. Automated, host-firmware and simulated tests (run here)

| Test | Result |
|---|---|
| `pytest tests/unit/test_wear.py` (22 tests: evidence rules, hysteresis, gaps, IMU/PPG fault handling, re-wear, config validation, engine integration for protocol v1 and v2, recorder metadata, offline = live) | passed |
| `pytest tests/unit/test_step_version_label.py` (new labels, schema unchanged at 79 columns, legacy interpretation) | passed |
| Golden replay and all pre-Phase-8 tests (`pytest`) | see the final report for the run |
| `g++ … test_packet.cpp` (struct sizes, scaling, saturation, clip flags, scheduler incl. `micros()` wrap) | OK (firmware unchanged) |
| `g++ -fsyntax-only` sketch type-check, profile A (`REQUIRE_FINGER_FOR_STREAMING = true`) | OK |
| `g++ -fsyntax-only` sketch type-check, profile B (`= false`, config copied and edited in `/tmp`) | OK |

These prove the code does what it says on synthetic and stubbed input. They do **not** prove the firmware compiles against
the real nRF52 core and libraries, runs, or measures anything.

## 2. Research-dataset evaluation (false-removal side only)

`python -m benchmarks.wear_bench --out benchmarks/results/wear_public_data.json` — Walch (15 usable of 18 acceleration
files; 3 excluded: two at ~10 Hz, one < 3 h) and Karas driving (27 subjects, 623 min). Full numbers:
[architecture §3](../architecture/WEAR_AWARE_ACQUISITION.md#3-why-motion-alone-cannot-decide-removal-public-data-evidence-not-hardware)
and the [benchmark registry](BENCHMARK_REGISTRY.md).

Acceptance criteria fixed **before** the default was set, and what happened:

| # | Criterion (stated up front) | Result |
|---|---|---|
| E1 | Shipped default: 0 subjects ever REMOVED in worn-night worst case (PPG absent) | met at 1 mg (0/15) |
| E2 | Shipped default: 0 % REMOVED during labelled driving | met (0.0 % over 27 subjects) |
| E3 | Sensitivity to true removal | **not evaluable**: no public non-wear labels |
| E4 | Held-out threshold selection | **not met**: threshold chosen on the evaluated nights (optimistic) |

E3 and E4 are why the default is "provisional". A new independent worn-night set (CAPTURE-24 is a candidate, not
downloadable from this environment) is needed for E4; ParkinSense bench recordings for E3.

## 3a. Owner-reported physical testing (2026-11-06)

The owner reports having physically tested the updated ParkinSense firmware, dashboard and overall system on
themselves, and that everything worked perfectly. Board: Seeed Studio XIAO nRF52840 (owner statement).

What this is: a report by the person who built the device. What it is not, because nothing more was provided:
it names no firmware version or build profile (A/B), no test IDs, no durations, no packet-loss or rate figures, no battery
or current measurements, no overnight recording, and no files. It therefore satisfies **none** of the pass criteria
below, which require recorded data. It does raise the prior that the firmware boots, streams and the dashboard
displays it. Every test in §3 stays NOT RUN until its row in the results log exists. First-session checklist:
[HARDWARE_SESSION_CHECKLIST](HARDWARE_SESSION_CHECKLIST.md).

## 3. Physical hardware tests — documented tests all pending

Existing procedure: [HARDWARE_TEST_PROCEDURE](HARDWARE_TEST_PROCEDURE.md) (H0–H11). New tests below use the same rule:
**record date, board serial and host OS; never mark a test passed without running it.** Results log at the bottom.
Pass criteria are fixed here, before any data exists.

| ID | Priority item | Procedure | Pass criterion | Status |
|---|---|---|---|---|
| H0–H3 | IMU init, PPG init, IMU with contact, BLE v2 streaming, sequence continuity, packet loss | existing procedure | existing criteria | NOT RUN |
| H5 | Current | [POWER_MEASUREMENT](../hardware/POWER_MEASUREMENT.md) S1–S7 | tables filled; no claim without them | NOT RUN |
| H10, H11 | Timestamp wrap, reconnection | existing procedure | existing criteria | NOT RUN |
| **W0** | Record the wiring (board: XIAO nRF52840) | read the silkscreen/MCU of the prototype; photograph wiring; record whether MAX30102 INT is wired | BOM and `HARDWARE.md` corrected to match | board is the XIAO nRF52840 (owner); wiring read-back evidence (photo, `INFO_UF2.txt`, INT wiring) NOT RUN |
| **W1** | Bench noise floor | board rigid on a table, 3 surfaces × 10 min, profile B; `parkinsense-wear` epoch statistics | report per-epoch max-axis SD distribution and gyro SD; table 99th percentile < `still_acc_sd_g` with ≥ 2× margin, else the stillness test cannot separate a table from noise and a sensor is required | NOT RUN |
| **W2** | Worn-still distribution | worn on the wrist, seated still 10 min; supine still 30 min; **overnight with finger off the sensor** (≥ 5 nights, ≥ 3 people) | no night spends > 0 % in REMOVED and the worn 1st-percentile SD exceeds the W1 table 99th percentile by the same margin | NOT RUN |
| **W3** | Removal detection | worn → removed → table 30 min → re-worn, 10 repetitions, finger never on sensor | REMOVED reached within `removed_s` + 60 s in ≥ 9/10 and never while worn | NOT RUN |
| **W4** | Re-wear detection | re-wear (a) with finger on sensor, (b) without, (c) carry in hand 90 s, (d) table bumps ×5 | (a) RESUMING→WORN ≤ 30 s; (b) →WORN_PPG_UNAVAILABLE ≤ 90 s; (d) stays REMOVED; (c) recorded, not graded (known ambiguity) | NOT RUN |
| **W5** | Profile B contract | flash profile B; stream with no finger for 60 min | IMU packets arrive with no finger; `seq` gaps 0 at 1 m; timestamps monotonic; capture decodes; `rate_status` OK | NOT RUN |
| **W6** | Wrist optical signal | record IR/red with the sensor at the wrist (dorsal, ventral) vs finger | report DC level distribution against 50 000; pulse visible at rest (yes/no, SNR); decide whether the optical window can ever be the primary wear sensor | NOT RUN |
| **W7** | Sensor independence | cover/uncover the MAX30102 with opaque tape while streaming in profile B | IMU stream unbroken (0 lost packets from the manoeuvre); `PPG_FAULT` not set by covering; host PPG state flips to NO_CONTACT within 10 s | NOT RUN |
| **W8** | Overnight recording | ≥ 8 h profile B, battery start/end logged | declare *validated* only after inspection: duration ≥ 8 h, `packets_lost_seq` / packets < 1 %, no gap > 60 s, `metadata.json` COMPLETE, battery did not die, wear monitor's per-hour state table reviewed against a diary | NOT RUN |

Until W8 passes with a human-inspected capture, **overnight recording is not validated.**

## 4. Explicit non-claims

No *documented* ParkinSense hardware wear, removal, re-wear, power, overnight or wrist-PPG result exists. Public-data wear results
bound false removals on other sensors and say nothing about detecting a removed device.

## Results log

| Date | ID | Board | Result | Notes |
|---|---|---|---|---|
| | | | | |
