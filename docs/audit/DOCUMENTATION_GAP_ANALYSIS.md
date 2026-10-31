# Documentation gap analysis — `develop` vs `transform/engineering-overhaul`

Date: 2026-10-31. Compared `develop` @ `917ff73` with `transform/engineering-overhaul` @ `574be5f`
(before this documentation pass). `develop` was read, not modified.

## 1. What `develop` contains

| Item | Size | Content |
|---|---|---|
| `README.md` | 1,007 lines | the whole documentation set: at-a-glance table, photos, motivation, feature lists, branch table, architecture Mermaid diagram, design principles, hardware tables, firmware variants, battery section, BLE box diagram, three pipeline stage tables, cross-pipeline fusion, biomarker table, dashboard description, Android app description, repository tree, getting-started (requirements, clone, flash, run, Android, sample output, troubleshooting), performance table, roadmap checklist, research focus, limitations, future vision, contributing, citation, licence, disclaimer |
| `docs/SRS/ParkinSense_SRS_v1.md` | 218 lines | draft requirements specification (v1.0) |
| `docs/ParkinSense.pdf` | — | the research paper |
| `docs/images/*.jpg` | 4 | prototype and dashboard photos |
| `docs/Architecture`, `docs/protocol`, `docs/firmware`, `docs/Roadmap`, `docs/Clinical` | — | **empty directories** |

### What makes it useful

1. A single narrative that explains *why* before *what*.
2. Stage-by-stage tables for every pipeline (stage → purpose).
3. Photos of the real hardware and dashboard.
4. A getting-started path with expected console output and a troubleshooting table.
5. Explicit limitations and a disclaimer.
6. Consistent visual structure (section dividers, tables, diagrams).

### What is weak or wrong in it (verified against `develop`'s own code)

| Claim in `develop` | What the code does |
|---|---|
| PPG sampled at ~50 Hz | firmware v4 keeps one sample per 100 ms (10 Hz) |
| Packet is 248 bytes | 8 + 10 × 20 = **208** bytes |
| Band-pass 4.0–6.5 Hz; 50 Hz notch rejects mains interference | band-pass 3–8 Hz; the notch is ~2 Hz below Nyquist on a battery device and has unity gain in 0–15 Hz |
| Temporal validator: 5 of 10 windows | `TemporalSmoother` was never constructed |
| State machine prevents flip-flopping | its output was computed and discarded; classification was raw `score >= 80` |
| HR from "rolling z-score, local energy gating, adaptive prominence" detector | `estimate_heart_rate` uses a single `find_peaks` pass + notch guard + median RR |
| Motion-aware HR confidence | never invoked (argument not passed; key spelling mismatch) |
| IMU at ±4 g / ±245 dps | settings assigned after `begin()`; sensor ran at driver defaults |
| Deep sleep in the µA range; ~7 mA; ~100 h | no power-management calls in firmware; no measurement data in the repository |
| Replay framework, dataset generation | `replay_v2.py` and `build_dataset.py` were 0-byte files |
| Android app (BLE, pipelines, history, export) | no Android/Flutter code in any branch |
| Firmware at `firmware/xiao_nrf52840/src/parksense_wearable_v4/` | v4 was at `parksense_ble_stream_optimized_v4/`; `parksense_wearable_v3` is a different sketch |

## 2. What the transformation branch had before this pass

README (~150 lines), `ARCHITECTURE.md` (one diagram + module table), `BLE_PROTOCOL.md`,
ADRs 0001–0009, `RESULTS.md`, `HARDWARE_TEST_PROCEDURE.md`, `REPLAY_AND_DATASETS.md`,
`BIOMARKER_FEASIBILITY.md`, `OPEN_SOURCE_REFERENCES.md`, `TRANSFORMATION_REPORT.md`, plus the
two original audit documents.

Accurate, but **not self-contained**: it assumed the reader knew `develop`'s README.

## 3. Gaps

| # | Gap | Category | Resolution in this pass |
|---|---|---|---|
| G1 | No hardware description, photos, component rationale | missing | `hardware/HARDWARE.md` (develop content verified/corrected) |
| G2 | No firmware guide (build, flash, loop design, v4 vs v5, serial output) | missing | `firmware/FIRMWARE.md` |
| G3 | Protocol lacked byte offsets, example bytes, encode/decode examples, error handling | incomplete | `protocol/BLE_PROTOCOL.md` rewritten |
| G4 | No installation / quick-start / troubleshooting guide | missing (was in develop README) | `getting-started/INSTALLATION.md` |
| G5 | No per-package Python reference | missing | `software/PYTHON_PACKAGES.md` |
| G6 | No algorithm mathematics (Welch, interpolation, SNR, HMM, PPG, steps) | missing | `algorithms/MOTION_AND_TREMOR.md`, `algorithms/PPG.md`, `algorithms/ACTIVITY.md` |
| G7 | No runtime / capture-schema reference (79 columns, metadata, quality states, metrics JSON) | missing | `runtime/RUNTIME_AND_RECORDING.md` |
| G8 | Replay/dataset guide brief | incomplete | `datasets/REPLAY_AND_DATASETS.md` expanded |
| G9 | Biomarker document lacked exact formulas and status taxonomy | incomplete | `biomarkers/BIOMARKERS.md` rewritten |
| G10 | No dashboard / API documentation | missing | `software/DASHBOARD_AND_API.md` |
| G11 | No testing guide (categories, commands, expected output, golden regeneration, benchmarks) | missing | `testing/TESTING.md` |
| G12 | No contributor guide (adding modules, versioning, ADRs, CI) | missing | `development/CONTRIBUTING.md` |
| G13 | No documentation index | missing | `docs/README.md` |
| G14 | README too thin compared with develop | outdated | README rewritten |
| G15 | Code comment pointed to a non-existent `docs/validation/METRICS.md` | broken link | fixed |
| G16 | SRS v1 describes requirements not met (bradykinesia, sleep, medication) without status | outdated | kept as `research/SRS_v1_historical.md` with a status banner |
| G17 | Paper PDF and photos unreferenced | orphaned | linked from README / hardware / research index |

## 4. Rewritten because the architecture changed

Everything in develop's README about module paths, the runtime entry point, file names
(`realtime_capture_v2.csv`), pipeline stages, dashboard sources, firmware locations and the
packet description. Develop text was used as a quality reference only; no technical
paragraph was copied without checking it against the current source.

## 5. New documentation needed for pipeline 3.0.0 / firmware 5.0.0

Signal-time model; integrity tracking; quality states; capture schema v3 and metadata.json;
protocol v2 (sequence, flags, gyro scale); firmware build/flash for v5 and the hardware
validation gate; replay/dataset/split workflow; synthetic benchmark reproduction; tremor
evidence + HMM mathematics; PPG fixes and their limits.

## 6. Intentionally not carried over from develop

Android app description (no code); measured power figures (no data); "~100 h" battery life;
"machine-learning ready" and similar unsupported claims; development-branch table (branches
`main`, `lakshya`, `spo2_test` are outside this documentation's scope and are listed only in
`development/CONTRIBUTING.md`).
