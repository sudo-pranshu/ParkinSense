# ParkinSense documentation

Documentation for `transform/engineering-overhaul` — pipeline **3.0.0**, capture schema **3**,
BLE protocol **v1 + v2**, firmware **5.0.0** (unverified on hardware) and **v4** (verified).
Every page states what is validated and what is not.

## Start here

| | |
|---|---|
| [Installation & quick start](getting-started/INSTALLATION.md) | install, flash, record, dashboard, no-hardware demo |
| [Troubleshooting](getting-started/TROUBLESHOOTING.md) | launch scripts, ports, environment, BLE, signal quality, dashboard states |
| [Architecture](architecture/ARCHITECTURE.md) | layers, data flow, module map, design principles |
| [Validation results](validation/RESULTS.md) | baseline vs current numbers and what they do (not) mean |

## Reference

| Area | Document |
|---|---|
| Hardware | [Hardware](hardware/HARDWARE.md) — parts, sensor configuration, units, finger gate, power status |
| Firmware | [Firmware](firmware/FIRMWARE.md) — v5 design, timing, scaling, BLE, v4 vs v5, build/flash, host tests |
| Protocol | [BLE protocol](protocol/BLE_PROTOCOL.md) — byte layout, flags, example bytes, decoding, rollover, loss |
| Python | [Package reference](software/PYTHON_PACKAGES.md) — every package's API, inputs/outputs, tests |
| Runtime | [Runtime & recording](runtime/RUNTIME_AND_RECORDING.md) — engine, time model, integrity, quality states, 79-column schema, metadata |
| Dashboard / API | [Dashboard & API](software/DASHBOARD_AND_API.md) — architecture, pages, quality semantics, live API, launch scripts, configuration |
| Replay & datasets | [Replay, datasets & methodology](datasets/REPLAY_AND_DATASETS.md) — replay, QC, windows, labels, leakage-safe splits, provenance |

## Algorithms (with equations)

| | |
|---|---|
| [Motion & tremor](algorithms/MOTION_AND_TREMOR.md) | Welch PSD, peak interpolation, amplitude, SNR, harmonic rejection, motion context, evidence, HMM |
| [PPG](algorithms/PPG.md) | sampling contract, finger detection, SQI, HR, motion coupling, HRV, SpO₂ estimate |
| [Activity](algorithms/ACTIVITY.md) | default step counter, experimental periodic counter |
| [Biomarkers](biomarkers/BIOMARKERS.md) | every metric's definition and status, aggregates, personal baselines, feasibility of the rest |

## Quality and process

| | |
|---|---|
| [Testing & benchmarks](testing/TESTING.md) | test categories, commands, golden regression, synthetic models, reproducing benchmarks |
| [Hardware test procedure](validation/HARDWARE_TEST_PROCEDURE.md) | H0–H11, reference-device validation |
| [Contributing](development/CONTRIBUTING.md) | rules, extending the system, versioning, roadmap |
| [Decision records](decisions/README.md) | ADR-0001 … 0009 |
| [References](research/REFERENCES.md) | open-source projects (licences checked), literature, datasets |

## Reports and history

| | |
|---|---|
| [Transformation report](audit/TRANSFORMATION_REPORT.md) | what changed in 3.0.0, finding by finding |
| [Dashboard 2.0 report](audit/DASHBOARD_2_REPORT.md) | dashboard and launcher overhaul, before/after measurements |
| [Documentation gap analysis](audit/DOCUMENTATION_GAP_ANALYSIS.md) | develop vs this branch |
| [Documentation audit report](audit/DOCUMENTATION_AUDIT_REPORT.md) | how these documents were verified |
| [Engineering audit (original)](audit/ParkinSense_Engineering_Audit.html), [runtime review](audit/RUNTIME_ARCHITECTURE_REVIEW.md) | pre-3.0.0 findings |
| [SRS v1 (historical)](research/SRS_v1_historical.md), [paper (PDF)](research/ParkinSense_paper.pdf) | original requirements and paper |
