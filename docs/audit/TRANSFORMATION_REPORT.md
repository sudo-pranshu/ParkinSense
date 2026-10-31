# ParkinSense engineering transformation — final report

Branch `transform/engineering-overhaul`, from `develop` @ `917ff73`. Pipeline 2.2.0 → 3.0.0.
Measured results: [`docs/validation/RESULTS.md`](../validation/RESULTS.md).

## 0. State found

* Uncommitted Issue #1 work (runtime, PPG, step counter, ADRs 0001–0003, review) — preserved
  as the first commit, unmodified.
* **`firmware/.../parksense_ble_stream_v3.ino` had been overwritten in the working tree by an
  unrelated ESP32 MQ-135/MQ-9 gas logger.** Restored; the gas logger remains recoverable from
  commit `cc7b9df`.
* CI ran `pytest` over print-scripts: **0 tests collected** (exit code 5 → red).
* No Android/Flutter code exists in any branch; the README described one in detail.
* `replay_v2.py` and `build_dataset.py` were empty files.
* No `LICENSE` file although the README declared MIT (added).

## 1. Audit findings — re-verified and resolved

Original audit (`ParkinSense_Engineering_Audit.html`, "A-") and post-Issue-#1 review
(`RUNTIME_ARCHITECTURE_REVIEW.md`, "R-"). Every item was re-checked against the source before
changing it.

| ID | Finding | Verified root cause | Resolution | Validation | Outcome |
|---|---|---|---|---|---|
| A-P0-1 | per-sample analysis | fixed by Issue #1 | kept; hop now drives nothing semantic | `test_rows_schema_and_analysis_markers` | ✅ verified |
| A-P0-2 | PPG rate contract | `PPGProcessor()` default fs=50 vs 104 Hz; firmware 10 Hz decimation | fs = slot rate; firmware v2 drains FIFO per tick | HR MAE 16–18 → 0.3 BPM (synthetic) | ✅ host verified · 🔧 firmware needs hardware |
| A-P0-3 | IMU ranges never applied, gyro wrap | `settings` set after `begin()`; `(int16_t)` cast | v2 firmware: settings before begin, ±500 dps, saturate + flag; v1 data flagged `possibly_clipped` | host C++ tests | 🔧 needs hardware (H4) |
| A-P0-4 | "deep sleep" busy-poll; unsupported µA claim | no power-management calls | RTOS yield between samples; claims removed from README | — | 🔧 needs PPK2 measurement (H5) |
| A-P1-5 | motion-aware PPG confidence never invoked | arg not passed; key spelling | enum keys, state passed, coupling check | motion confidence 0.84 → 0.17 | ✅ verified (synthetic) |
| A-P1-6 | temporal validator dead; state machine output discarded | — | HMM publishes classification; dead smoother removed | `test_temporal.py` | ✅ verified |
| A-P1-7 | PPG decimation without anti-aliasing | keep-newest at 10 Hz | v2 firmware ~100 Hz; HRV withheld below 25 Hz | `test_hrv_withheld_at_10hz_effective_rate` | ✅ host · 🔧 firmware |
| A-P1-8 | frequency = 3-axis mean, brittle agreement | — | summed-axis interpolated peak; power-weighted agreement | freq error 0.090 → 0.024 Hz | ✅ verified (synthetic) |
| A-P1-9 | filtfilt on sliding window | — | kept zero-phase (window-level outputs), SOS; edge-transient-free arm band | ADR-0005 | ✅ decided, documented |
| A-P1-10 | timestamp wrap at 71.6 min | no unwrap | `TimestampUnwrapper` | `test_timestamp_wrap_is_continuous` | ✅ verified |
| A-P1-11 | tests without assertions, CI cannot run | — | 64 pytest tests (+1 hardware, skipped); CI installs package, runs tests + firmware host tests | CI | ✅ verified locally |
| R-P0-1 | capture opened at import | module-level open | `SessionRecorder`; engine has no I/O | `test_import_has_no_side_effects`, `test_recorder_lifecycle` | ✅ verified |
| R-P0-2 | no fresh-analysis marker | — | `is_analysis_row`, `analysis_seq`; dataset builder uses only analysis rows | tests | ✅ verified |
| R-P0-3 | version not bumped | — | `PIPELINE_VERSION` 3.0.0 + algorithm/schema versions + metadata.json | — | ✅ |
| R-P0-4 | rate not validated | — | measured from header timestamps; OK/WARN/INVALID; INVALID marks tremor and HR | `test_rate_validation_flags_wrong_clock` | ✅ verified |
| R-P1-5 | replay/dataset empty | — | `replay/replay.py`, `datasets/builder.py`, `splits.py` | live == replay test | ✅ verified |
| R-P1-6 | state machine hop-coupled + dead band | — | HMM, time-based | `test_hop_invariance`, `test_no_dead_band_lockup` | ✅ verified |
| R-P1-7 | handler exceptions swallowed | bleak discards | counted, logged, escalated | `test_analysis_errors_are_surfaced` | ✅ verified |
| R-P1-8 | no sequence number | — | v2 header seq; v1 timestamp-gap detection | `test_sequence_loss_detected_for_v2`, `test_gap_detector` | ✅ host · 🔧 firmware |
| R-P1-9 | no monotonic host clock | — | `host_monotonic`, `device_time_us` | schema | ✅ |
| R-P2-10 | non-atomic metrics JSON + bare except | — | `os.replace`; dashboard keeps last frame | `test_dashboard_renders_from_live_session` | ✅ verified |
| R-P2-11 | MotionPipeline owns PPG | — | siblings in the engine | — | ✅ |
| R-P2-12 | duplicated walking_state | — | from StepCounter only | — | ✅ |
| R-P2-13 | no reset after gaps | — | gap > 0.5 s resets windows; reconnect = new session | `test_gap_resets_windows_and_is_recorded` | ✅ verified |
| R-P2-14 | no session id | — | `session_id` column + directory | — | ✅ |
| R-P3-15..22 | cleanliness | — | all addressed (P3-19: `process()` retained as documented wrapper) | — | ✅ |

New findings during this work:

| ID | Finding | Resolution |
|---|---|---|
| N-1 | SpO₂ lock and rate-limit added the full 10 s buffer per call (20× too fast at a 0.5 s hop); SpO₂ state was a module global never reset | `elapsed_sec`; processor-owned state |
| N-2 | Strong tremor vetoed itself through broadband motion context (38 % detection) | context excludes the tremor band |
| N-3 | `band_ratio` on band-passed data was ~uninformative | un-band-passed spectrum |
| N-4 | Every capture lost its first 4 s of raw data | rows written from the first sample |
| N-5 | Dashboard re-read the whole capture every 100 ms (unusable after ~1 h) | bounded tail read |
| N-6 | Step timing on host arrival time (packet-quantised) | signal time |
| N-7 | Tremor produced ~23 false steps/min | tremor guard |
| N-8 | Firmware version never recorded (`"unknown"`) | Device Information Service (v2 fw) |

## 2. Status by category

**Implemented and verified (automated tests, synthetic ground truth and/or real recordings):**
package restructure; RuntimeEngine; recorder/provenance; protocol v1/v2 host decoding;
integrity tracking; replay (deterministic, live-equivalent); dataset builder; leakage-safe
splits; tremor features/evidence/HMM; motion context; PPG rate/state/quality fixes; HRV gating;
motion-coupling flag; step tremor guard; session biomarkers; personal baseline; dashboard tail
read; CI; firmware packing/scheduler logic (host).

**Implemented, not fully verified:** dashboard UI under a live device (callback tested, not
visually inspected); `app.py` BLE lifecycle (needs a device); firmware sketch (type-checked
against stubs only — not compiled with the nRF52 core).

**Requires physical hardware:** everything in firmware 5.0.0 — build, ranges, burst read, PPG
rate, sequence numbers, notify-failure flag, power, DIS firmware revision
(`docs/validation/HARDWARE_TEST_PROCEDURE.md`, H0–H11).

**Requires labelled clinical/reference data:** tremor sensitivity/specificity in PD; tremor
amplitude vs clinical rating; HR/HRV vs ECG; SpO₂ calibration; step accuracy in daily life;
any bradykinesia/dyskinesia/sleep feature.

**Deferred (risk or insufficient evidence):** periodicity step counter (failed real-walking
check); trained tremor classifier (no labels); accelerometer-based HR correction (TROIKA-style
subtraction) — detection only; Android app work (no code in repo); sleep, bradykinesia,
dyskinesia, FoG; battery telemetry (needs a protocol field).

## 3. Prioritised remaining work

1. Flash firmware 5.0.0 and run H0–H6; until then keep v4 for data collection.
2. Record a chest-strap reference session (H7) — first real HR/HRV accuracy figure.
3. Request PD@Home data; evaluate tremor LOSO; consider running ParaDigMa as a comparator.
4. Decide the finger-gated streaming policy (`REQUIRE_FINGER_FOR_STREAMING`): it prevents
   tremor monitoring without PPG contact and makes sleep monitoring impossible.
5. Fix arm-movement false steps with labelled walking/non-walking recordings.
6. Measure power on a PPK2 before stating any battery figure.
7. Bring the mobile app into version control (or reference its repo) and align it with the
   v3 metrics/quality fields.

## 4. Files

`git diff --stat 917ff73..transform/engineering-overhaul` is authoritative. Summary: 68 added,
56 removed (dead code and print-script tests), 36 moved (32 unchanged moves into `parkinsense/`,
`data/reference/`, `firmware/legacy/`, `docs/`), 7 modified in place.

Removed modules (all retrievable from `cc7b9df`): `dashboard/python/{analytics/*, realtime/*,
detectors/*, pipeline/*, fusion/*, inference/*, models/*, calibration/*, live_dashboard.py,
record_imu.py, dashboard/{components,dashboard_v2,graphs,layout,realtime_dashboard}.py,
runtime/runtime_v2_backup.py, detector/{temporal,state_machine,confidence}.py,
filters/{gravity,notch}.py, features/feature_vector.py, utils/signal_utils.py,
replay/replay_v2.py, dataset/build_dataset.py}` and `tests/*.py` (print scripts; their checks
are now assertions).
