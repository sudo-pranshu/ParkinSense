# Implementation status and evidence matrix

Evidence classes: tests, synthetic, public data (other devices), ParkinSense hardware, clinical. No clinical evidence exists. Board: Seeed XIAO nRF52840 Sense.
Hardware tests H0–H11, W0–W8 and PPK2 S1–S7 are NOT RUN. An owner-reported informal test (2026-11-06) is not counted as evidence.

Status: Implemented, Bench-tested, Partial, In development, Planned, Future.

| ID | Capability | Status | Tests | Synthetic | Public data | Hardware | Clinical |
|---|---|---|---|---|---|---|---|
| C1 | BLE protocol v1 decode (fw v4) | Bench-tested | yes | yes | none | yes | none |
| C2 | BLE protocol v2 + fw 5.0.0 | Implemented | yes | yes | none | none | none |
| C3 | Tremor v3 (PSD + HMM) | Implemented | yes | yes | none | none | none |
| C4 | Motion context + tremor guard | Implemented | yes | yes | none | none | none |
| C5 | PPG 2.0: finger, SQI, heart rate | Implemented | yes | yes | none | partial | none |
| C6 | HRV (RMSSD, SDNN, pNN50) | Implemented | yes | yes | none | none | none |
| C7 | SpO2 ratio-of-ratios | Partial | yes | partial | none | none | none |
| C8 | Steps v1.1 (default) | Implemented | yes | yes | yes | none | none |
| C9 | Steps gated 3.0-dev (opt-in) | Partial | yes | none | yes | none | none |
| C10 | Sleep/wake 1.0 (offline) | Implemented | yes | yes | yes | none | none |
| C11 | Wear monitor 1.0 (opt-in) | Partial | yes | yes | partial | none | none |
| C12 | Runtime, recording, replay | Implemented | yes | yes | none | partial | none |
| C13 | Dashboard (live + history) | Implemented | yes | yes | none | partial | none |
| C14 | Personal baselines | Implemented | yes | none | none | none | none |
| C15 | Power and battery life | In development | none | none | none | none | none |
| C16 | Overnight recording | In development | none | none | none | none | none |
| C17 | Tremor on PD@Home; FoG on Daphnet | In development | none | none | none | none | none |
| C18 | Mobile app, product UI, cloud | Planned | none | none | none | none | none |
| C19 | Bradykinesia, dyskinesia, ML models | Future | none | none | none | none | none |
| C20 | Patient pilot, clinical validation | Future | none | none | none | none | none |

Source of truth for the paper figure: `docs/research/paper/status_data.py`. Paper: `docs/research/ParkinSense_paper.pdf`.
