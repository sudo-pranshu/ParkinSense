# ParkinSense

<div align="center">

![Status](https://img.shields.io/badge/Status-Active%20Development-success)
![Platform](https://img.shields.io/badge/Platform-XIAO%20nRF52840%20Sense-blue)
![Sensors](https://img.shields.io/badge/Sensors-LSM6DS3%20IMU-orange)
![BLE](https://img.shields.io/badge/BLE-100Hz%20Streaming-success)
![Branch](https://img.shields.io/badge/Branch-V2%20Signal%20Processing-yellow)
![License](https://img.shields.io/badge/License-MIT-lightgrey)

### Continuous Neurological Monitoring & Digital Biomarker Platform for Parkinson's Disease

*A WHOOP-style wearable platform for continuous Parkinson's disease monitoring through inertial sensing, advanced signal processing, digital biomarkers, and longitudinal analytics.*

</div>

---

## Table of Contents

- [Overview](#overview)
- [Development Branches](#development-branches)
- [System Architecture](#system-architecture)
- [Signal Processing Pipeline](#signal-processing-pipeline)
- [Hardware Platform](#hardware-platform)
- [Firmware](#firmware)
- [BLE Protocol](#ble-protocol)
- [Digital Biomarkers](#digital-biomarkers)
- [Dashboard](#dashboard)
- [Repository Structure](#repository-structure)
- [Getting Started](#getting-started)
  - [Requirements](#requirements)
  - [Clone Repository](#clone-repository)
  - [Flash Firmware](#flash-firmware)
  - [Run the Runtime](#run-the-runtime)
  - [Launch the Dashboard](#launch-the-dashboard)
  - [Runtime Output](#runtime-output)
  - [Troubleshooting](#troubleshooting)
- [Algorithm: V2 Signal Processing](#algorithm-v2-signal-processing)
- [Performance](#performance)
- [Development Roadmap](#development-roadmap)
- [Research Focus](#research-focus)
- [Citation](#citation)
- [Disclaimer](#disclaimer)

---

## Overview

ParkinSense is a wearable neurological monitoring platform that transforms raw inertial sensor data from a wrist-worn device into clinically relevant digital biomarkers for Parkinson's disease research.

The platform targets the gap between episodic clinical assessments and continuous real-world monitoring. Where a neurologist's office visit captures a snapshot, ParkinSense captures the full signal — tremor during meals, bradykinesia during morning routines, symptom fluctuation across medication cycles.

**Core capabilities:**

- Continuous IMU acquisition at 104 Hz via LSM6DS3
- Stable BLE streaming at ~100 Hz with binary packet protocol
- Modular, real-time signal processing pipeline (V2)
- Multi-stage tremor detection with false-positive rejection
- Confidence-weighted digital biomarker extraction
- Live analytics dashboard with real-time neurological metrics

**Intended use:**
Research, education, and exploratory prototyping. Not a medical device.

---

## Development Branches

### `main` — Stable V1

The stable production branch. Contains the original real-time Parkinson's monitoring platform, validated for demonstrations and stable testing.

**Features:**
- BLE streaming at ~100 Hz
- FFT-based tremor detection
- Realtime Plotly Dash dashboard
- Digital biomarker extraction (frequency, energy, confidence, burden)
- Dataset collection framework (7,000+ offline samples, 10,000+ realtime samples)

---

### `feature/v2-signal-processing` — Experimental V2

Next-generation signal processing architecture. A full redesign of the analytics pipeline with modular stages, clinical-oriented decision logic, and substantially improved false-positive rejection.

**Major improvements over V1:**

| Area | V1 | V2 |
|---|---|---|
| Architecture | Monolithic FFT pipeline | Modular staged pipeline |
| Filtering | None | Gravity removal + notch + Butterworth band-pass |
| Motion context | None | REST / LOW MOTION / ACTIVE classification |
| Tremor detection | Single-axis FFT magnitude | Multi-axis spectral analysis |
| False positive rejection | Persistence filter only | RMS gate + band ratio gate + ACTIVE penalty + temporal smoother |
| Confidence | Simple score product | Independent `ConfidenceEstimator` with multi-factor penalties |
| Temporal validation | Window counter | Persistence state machine (5-of-10 windows) |
| Analysis window | Sliding | Rolling 4-second buffer |

**V2 current status:**

```
Stable realtime execution        ✅
Reduced stationary false pos.    ✅
Improved tremor specificity      ✅
V2 runtime operational           ✅
```

**V2.2 upcoming (vector-magnitude branch):**

- Vector magnitude analysis (combined-PSD approach replacing per-axis best-pick)
- PSD quality metrics
- Harmonic detection
- Adaptive thresholds
- Signal-to-noise estimation
- MAX30102 integration
- Bradykinesia biomarkers
- Activity recognition
- Sleep and recovery analytics
- Machine learning inference

---

## System Architecture

### V1 Architecture

```
Wearable Device
      │
      ▼
BLE Streaming
      │
      ▼
FFT Processing
      │
      ▼
Digital Biomarkers
      │
      ▼
Dashboard
```

### V2 Architecture

```
Wearable Device
        │
        ▼
  LSM6DS3 IMU
        │
        ▼
  104 Hz Acquisition
        │
        ▼
  BLE Streaming
        │
        ▼
  Rolling Window Buffer (4 s)
        │
        ▼
  Gravity Removal
        │
        ▼
  50 Hz Notch Filter
        │
        ▼
  Butterworth Band-pass Filter
        │
        ▼
  Motion Context Detection
   (REST / LOW MOTION / ACTIVE)
        │
        ▼
  Feature Extraction
   (RMS, dominant freq, band ratio,
    spectral entropy, centroid, ZCR)
        │
        ▼
  Multi-axis Tremor Detection
        │
        ▼
  Confidence Estimation
        │
        ▼
  Rule-based Inference Engine
        │
        ▼
  Temporal Smoother
        │
        ▼
  Tremor State Machine
        │
        ▼
  Digital Biomarkers
        │
        ▼
  Realtime Dashboard
```

---

## Signal Processing Pipeline

### Stage 1 — Gravity Removal

Subtracts the static gravity component from the accelerometer signal to isolate dynamic motion.

### Stage 2 — 50 Hz Notch Filter

Removes 50 Hz mains interference present in electrically noisy environments. Applied to both accelerometer and gyroscope channels.

### Stage 3 — Butterworth Band-pass Filter

Isolates the physiologically relevant frequency band. Attenuates sub-1 Hz postural drift and high-frequency mechanical noise above the tremor band.

### Stage 4 — Motion Context Detection

Classifies each analysis window as one of:

| State | Description |
|---|---|
| `REST` | Wrist is stationary; tremor detection fully active |
| `LOW MOTION` | Minor movement; detection active with reduced confidence |
| `ACTIVE` | Intentional wrist movement; 40-point score penalty applied |

### Stage 5 — Feature Extraction

Per-axis features extracted from each 4-second window:

| Feature | Description |
|---|---|
| RMS | Signal energy in deg/s |
| Dominant Frequency | Spectral peak within 1–15 Hz |
| Band Ratio | Power in 4–6.5 Hz / total power |
| Spectral Entropy | Frequency distribution uniformity |
| Spectral Centroid | Power-weighted mean frequency |
| Zero Crossing Rate | Oscillation regularity |

### Stage 6 — Multi-axis Tremor Detection (`MultiAxisDetector`)

Evaluates spectral features across all three gyroscope axes. Applies a gyro RMS hard gate to immediately reject sensor noise and desk vibrations, then scores on four independent criteria:

| Criterion | Threshold | Score |
|---|---|---|
| Frequency in 4.0–6.5 Hz band | ✓ | +35 |
| Band ratio > 0.18 | ✓ | +30 |
| Axis agreement > 0.85 | ✓ | +20 |
| Axis dominance > 0.50 | ✓ | +20 |
| ACTIVE motion | ✓ | −40 |
| Gyro RMS < 0.8 deg/s | ✓ | Hard gate → score = 0 |

Tremor declared at score ≥ 80.

> **V2.2 note:** The next revision replaces per-axis best-pick with a combined-PSD vector approach (`PSD_gx + PSD_gy + PSD_gz`), eliminating orientation sensitivity and the frequency-folding artefact introduced by computing FFT on `|omega| = sqrt(gx² + gy² + gz²)`.

### Stage 7 — Confidence Estimation (`ConfidenceEstimator`)

Independent confidence score from 0–100, distinct from the tremor detection score. Penalizes:

- Unstable dominant frequency (std > 1.2 Hz → ×0.5)
- Weak tremor-band energy (band ratio < 0.20 → ×0.5)
- Active motion state (×0.6)

### Stage 8 — Temporal Smoother (`TemporalSmoother`)

10-window rolling smoother. Tremor confirmed only when ≥ 5 of the last 10 windows score ≥ 80. Eliminates single-window transient detections.

### Stage 9 — Tremor State Machine

Hysteretic state machine governing TREMOR_ONSET and TREMOR_RESOLVED transitions to prevent rapid switching at the detection boundary.

---

## Hardware Platform

### Wearable Unit

| Component | Specification |
|---|---|
| MCU | Seeed Studio XIAO nRF52840 Sense |
| IMU | LSM6DS3 (6-axis accelerometer + gyroscope) |
| Connectivity | Bluetooth Low Energy 5.0 |
| Interface | USB-C |
| Power | Li-Ion battery support |

### Operating Configuration

| Parameter | Value |
|---|---|
| Gyro ODR | 104 Hz |
| Accel ODR | 104 Hz |
| BLE Streaming Rate | ~100 Hz |
| BLE MTU | 247 bytes |
| Batch Size | 10 samples |
| Packet Size | 124 bytes |
| Analysis Window | 4 seconds (416 samples) |

---

## Firmware

The firmware runs on the XIAO nRF52840 Sense and performs:

1. LSM6DS3 initialization at 104 Hz ODR
2. Interrupt-driven IMU sample acquisition
3. Batch assembly (10 samples per packet)
4. Binary packet encoding with timestamp header
5. BLE notification dispatch

Firmware location: `firmware/xiao_nrf52840/`

---

## BLE Protocol

### Packet Structure

```
┌──────────────────────────────────────────┐
│  Header                                  │
│    Timestamp       (uint32, 4 bytes)     │
├──────────────────────────────────────────┤
│  IMU Samples × 10                        │
│    Accel X/Y/Z    (int16 × 3, 6 bytes)  │
│    Gyro  X/Y/Z    (int16 × 3, 6 bytes)  │
│    ─────────────────────────────         │
│    Per sample: 12 bytes                  │
│    Total payload: 120 bytes              │
├──────────────────────────────────────────┤
│  Total packet: 124 bytes                 │
└──────────────────────────────────────────┘
```

### Transport

- Service: Custom BLE GATT service
- Characteristic: Notify
- Connection interval: negotiated for ~100 Hz throughput

---

## Digital Biomarkers

| Biomarker | Description | Unit |
|---|---|---|
| Tremor Frequency | Dominant oscillation frequency | Hz |
| Tremor Score | Composite detection score | 0–100 |
| Tremor Confidence | Detection quality estimate | 0–100 |
| Tremor Severity | Categorical severity label | NONE / VERY MILD / MILD / MODERATE / HIGH / SEVERE |
| Tremor Persistence | Windows in tremor state (last 10) | count |
| Tremor Burden | % of monitoring windows in tremor | % |
| Motion State | Wrist activity context | REST / LOW MOTION / ACTIVE |
| Band Ratio | Tremor-band power fraction | 0–1 |
| Axis Agreement | Cross-axis frequency coherence | 0–1 |
| Rest Index | Inverse motion RMS (wrist stillness) | 0–1 |

---

## Dashboard

The real-time analytics dashboard is built with Plotly Dash and consumes the live BLE stream.

**Visualizations:**
- Live gyroscope waveforms (X / Y / Z)
- Real-time tremor score gauge
- Dominant frequency tracker
- Confidence and persistence indicators
- Tremor burden time series
- Motion state indicator
- Device connection status

**Architecture:**

```
BLE Receiver (ble_receiver.py)
        │
        ▼
Realtime CSV (realtime_capture.csv)
        │
        ▼
Metrics Engine (realtime_tremor.py)
        │
        ▼
Plotly Dash Dashboard (realtime_dashboard.py)
```

---

## Repository Structure

The repository is organized into modular components separating firmware, signal processing, realtime analytics, inference, and future wearable capabilities. Each module has a dedicated responsibility, making the system easier to maintain, extend, and validate.

```
ParkinSense
│
├── firmware/
│   └── xiao_nrf52840/
│
├── dashboard/
│   └── python/
│       ├── analytics/
│       ├── context/
│       ├── dashboard/
│       ├── data/
│       ├── detector/
│       ├── features/
│       ├── filters/
│       ├── inference/
│       ├── pipelines/
│       ├── realtime/
│       ├── runtime/
│       └── tests/
│
├── docs/
├── hardware/
├── research/
└── README.md
```

---

### `firmware/`

All embedded firmware running on the Seeed Studio XIAO nRF52840 Sense.

- IMU initialization and LSM6DS3 configuration
- Sensor sampling and timestamp generation
- Binary packet creation and BLE notification dispatch
- Future: MAX30102 integration, battery management

---

### `dashboard/python/`

Complete realtime analytics framework running on the host computer. Handles everything after BLE packets are received.

---

#### `filters/`

Signal preprocessing modules. Remove unwanted components before any neurological analysis is performed.

| File | Purpose |
|---|---|
| `gravity.py` | Low-pass gravity removal for linear acceleration extraction |
| `notch.py` | 50 Hz digital notch filter — removes mains electrical interference |
| `bandpass.py` | Butterworth band-pass filter, passband 4.0–6.5 Hz (Parkinsonian tremor band) |

---

#### `features/`

Quantitative biomarker extraction from filtered sensor signals.

| File | Purpose |
|---|---|
| `feature_extractor.py` | Core engine computing RMS, dominant frequency, band ratio, spectral entropy, centroid, zero crossings, signal energy, peak prominence, and more |
| `feature_vector.py` | Standardizes extracted features into a structured vector for downstream inference and future ML compatibility |

---

#### `context/`

Determines the current movement context of the user.

| File | Purpose |
|---|---|
| `motion_context.py` | Classifies wrist activity as REST, LOW MOTION, or ACTIVE using acceleration magnitude and motion RMS; prevents false positives during voluntary movement |

---

#### `detector/`

Neurological decision engine.

| File | Purpose |
|---|---|
| `multiaxis_detector.py` | Primary tremor detection algorithm; combines gyroscope axes, applies hard RMS gate, scores on frequency / band energy / axis agreement / axis dominance criteria; tremor declared at score ≥ 80 |
| `confidence.py` | Independent confidence estimator (0–100); penalizes weak band energy, unstable frequency, and active motion |
| `temporal.py` | Rolling 10-window smoother; confirms tremor only when ≥ 5 windows score ≥ 80, eliminating transient detections |
| `state_machine.py` | Finite state machine with states NO_TREMOR → POSSIBLE_TREMOR → CONFIRMED_TREMOR → RECOVERY; reduces flickering and models tremor progression |

---

#### `inference/`

Final decision-making layer.

| File | Purpose |
|---|---|
| `rule_engine.py` | Combines extracted features with motion context to produce final neurological inference; intended to be replaced or augmented by ML inference in a future phase |

---

#### `pipelines/`

End-to-end analytics orchestration.

| File | Purpose |
|---|---|
| `motion_pipeline.py` | Central V2 processing pipeline; sequences gravity removal → notch → band-pass → motion context → feature extraction → rule engine → temporal validation → state machine → feature vector |

---

#### `runtime/`

Current V2 realtime runtime.

| File | Purpose |
|---|---|
| `runtime_v2.py` | Main V2 entry point; manages BLE connection, packet decoding, rolling window buffer, pipeline execution, JSON/CSV logging, console output, and dashboard communication |

---

#### `realtime/`

Legacy V1 realtime implementation, retained for backward compatibility and comparison.

| File | Purpose |
|---|---|
| `ble_receiver.py` | BLE packet receiver |
| `realtime_tremor.py` | Original FFT-based tremor detector (V1) |
| `realtime_capture.csv` | Live capture log |
| `realtime_metrics.json` | Live metrics output |

---

#### `dashboard/`

Visualization layer.

| File | Purpose |
|---|---|
| `realtime_dashboard.py` | Interactive Plotly Dash dashboard; displays live gyroscope signals, tremor score, confidence, dominant frequency, motion state, classification, and digital biomarkers |

---

#### `analytics/`

Offline research utilities for FFT analysis, algorithm development, dataset evaluation, and performance comparison against V1.

---

#### `data/`

Recorded sensor datasets.

Current datasets:
- Stationary baseline
- Normal daily motion
- Walking
- Simulated Parkinsonian tremor
- External vibration reference

Future datasets: clinical recordings, medication response sessions, long-term wearable monitoring.

---

#### `tests/`

Validation scripts for individual modules. Covers filters, feature extraction, motion context, detector, state machine, and the full motion pipeline. Run before deploying changes to the realtime runtime.

---

### `docs/`

Architecture diagrams, design notes, system documentation, and development logs.

---

### `hardware/`

Hardware design resources. Future contents: PCB layouts, enclosure CAD models, wiring diagrams, sensor placement guides, battery integration.

---

### `research/`

Reference material: Parkinson's disease literature, signal processing references, clinical notes, benchmark datasets, and algorithm comparisons used during development.


---

## Getting Started

This section walks through building, flashing, running, and monitoring the ParkinSense platform from scratch.

---

### Requirements

#### Hardware

| Component | Notes |
|---|---|
| Seeed Studio XIAO nRF52840 Sense | Current supported board |
| USB-C cable | For flashing and power |
| Computer with BLE support | For receiving sensor stream |
| MAX30102 PPG sensor | Future — not currently required |
| Li-ion battery + enclosure | Future — not currently required |

#### Software

- Arduino IDE 2.x
- Python 3.11+
- Git

Install Python dependencies:

```bash
pip install numpy scipy pandas matplotlib plotly dash bleak pyqtgraph
```

---

### Clone Repository

```bash
git clone https://github.com/sudo-pranshu/ParkinSense.git
cd ParkinSense
```

**Branch selection:**

```bash
# Stable V1
git checkout main

# Experimental V2 signal processing
git checkout feature/v2-signal-processing

# Check current branch
git branch
```

---

### Flash Firmware

**1. Open Arduino IDE and navigate to:**

```
firmware/xiao_nrf52840/xiao_nrf52840.ino
```

**2. Install required libraries via Library Manager:**

| Library | Purpose |
|---|---|
| Adafruit TinyUSB | USB stack |
| Adafruit Bluefruit nRF52 | BLE |
| SparkFun LSM6DS3 | IMU driver |
| Wire | I2C |

**3. Select the board:**

```
Tools → Board → Seeed XIAO nRF52840 Sense
```

**4. Select the correct COM / serial port, then click Upload.**

**5. Verify via Serial Monitor at 115200 baud:**

```
ParkinSense Initializing...
IMU Ready
BLE Advertising...
Waiting for Connection...
```

> If upload fails: double-press the RESET button, re-select the board and port, and try again.

---

### Run the Runtime

Open a terminal in the repository root:

```bash
python -m dashboard.python.runtime.runtime_v2
```

Expected output on connection:

```
Searching for ParkinSense...
Connected
Streaming...
========== PARKINSENSE V2 ==========
```

The runtime automatically creates:

```
dashboard/python/realtime/realtime_capture_v2.csv
dashboard/python/realtime/realtime_metrics_v2.json
```

`realtime_capture_v2.csv` records every sample with timestamp and full IMU data (AccX/Y/Z, GyroX/Y/Z). These recordings are used for offline analysis, dataset generation, and algorithm validation.

---

### Launch the Dashboard

Open a **second terminal** in the repository root:

```bash
python dashboard/python/dashboard/realtime_dashboard.py
```

Then open your browser at:

```
http://127.0.0.1:8050
```

The dashboard displays live gyroscope waveforms, tremor score, confidence, dominant frequency, motion state, severity classification, and all digital biomarkers in real time.

---

### Complete Workflow

```
Flash Firmware
      |
      v
Power Device
      |
      v
BLE Advertising
      |
      v
run runtime_v2.py    <------------------+
      |                                 |
      v                                 |
Realtime Processing                     |
      |                             Collect Data /
      v                            Validate Algorithm /
JSON + CSV Generation              Improve Detector
      |                                 |
      v                                 |
Launch Dashboard ---------------------> +
      |
      v
Live Monitoring
```

---

### Runtime Output

The console prints a status block after each analysis window:

```
========== PARKINSENSE V2 ==========

State      : NO TREMOR
Score      : 18 / 100
Confidence : 91%
Frequency  : 5.12 Hz
Motion     : REST
```

To stop acquisition safely, press `CTRL + C`. The runtime flushes the CSV and closes the BLE connection before exiting.

---

### Troubleshooting

| Symptom | Check |
|---|---|
| Device not found | BLE advertising? Firmware uploaded? Bluetooth enabled on host? |
| Dashboard not updating | `runtime_v2.py` running? `realtime_metrics_v2.json` being written? |
| Sampling rate below 104 Hz | Close other BLE apps; reduce wireless interference; reconnect |
| Firmware upload fails | Double-press RESET; re-select board and port; retry |
| Dashboard shows stale data | Restart both runtime and dashboard; confirm JSON path matches |


---

## Algorithm: V2 Signal Processing

### Preprocessing

Gravity removal isolates the dynamic component of acceleration. A 50 Hz notch filter removes mains interference. A Butterworth band-pass filter isolates the physiologically relevant band, attenuating postural drift and high-frequency noise.

### Motion Context

Each 4-second window is classified as REST, LOW MOTION, or ACTIVE based on accelerometer RMS. ACTIVE windows receive a 40-point scoring penalty to suppress false positives during intentional movement.

### Feature Extraction

Per-axis spectral features are computed from the windowed gyroscope signal: RMS energy, dominant frequency from the FFT peak, tremor-band power ratio, spectral entropy, centroid, and zero crossing rate.

### Decision Engine

The multi-axis detector applies a hard gyro RMS gate (< 0.8 deg/s → immediate rejection) before scoring. Four independent spectral criteria contribute to a composite score; tremor is declared at score ≥ 80. The confidence estimator runs separately and penalizes detections with weak band energy or unstable frequency.

### Temporal Validation

The temporal smoother requires ≥ 5 of the last 10 analysis windows to score ≥ 80 before confirming tremor. This eliminates transient single-window detections. A hysteretic state machine governs TREMOR_ONSET and TREMOR_RESOLVED transitions.

### Realtime Output

Each window produces: tremor state, score, confidence, severity, dominant frequency, frequency stability, band ratio, axis agreement, motion state, and rest index.

---

## Performance

| Metric | Value |
|---|---|
| Sampling Rate | 104 Hz |
| BLE Streaming | ~100 Hz |
| Analysis Window | 4 seconds |
| Processing Latency | < 100 ms (post-window) |
| Runtime | Realtime |
| False Positive Rejection | Substantially improved over V1 (ongoing validation) |
| Tremor Threshold | Score ≥ 80 (5-of-10 window persistence) |

> Clinical sensitivity and specificity figures are not reported. Formal evaluation against a labelled clinical dataset is required before quantitative performance claims. See [Disclaimer](#disclaimer).

---

## Development Roadmap

### Phase 1 — Sensor Acquisition ✅
- [x] LSM6DS3 IMU integration
- [x] BLE streaming at 104 Hz
- [x] Binary packet protocol
- [x] Realtime CSV logging
- [x] Dataset collection framework

### Phase 2 — Signal Processing ✅
- [x] FFT tremor analysis (V1)
- [x] Tremor Detector V3 / V4
- [x] Modular V2 pipeline (gravity removal, notch, band-pass)
- [x] Motion context detection
- [x] Feature extraction pipeline
- [x] Multi-axis tremor detector
- [x] Confidence estimator
- [x] Temporal smoother

### Phase 3 — Digital Biomarkers ✅
- [x] Tremor frequency
- [x] Tremor score
- [x] Tremor confidence
- [x] Tremor persistence
- [x] Tremor burden
- [x] Motion state

### Phase 4 — V2.2 Vector Magnitude (In Progress)
- [ ] Combined-PSD vector detector
- [ ] PSD quality metrics
- [ ] Harmonic detection
- [ ] Adaptive thresholds
- [ ] Signal-to-noise estimation

### Phase 5 — Wearable Platform
- [x] BLE streaming
- [x] Realtime detection
- [x] Realtime dashboard
- [ ] Battery optimization
- [ ] Wearable enclosure
- [ ] Mobile dashboard

### Phase 6 — Advanced Biomarkers
- [ ] MAX30102 integration (heart rate + SpO2)
- [ ] Bradykinesia assessment
- [ ] Activity classification
- [ ] Sleep and recovery analytics
- [ ] HRV monitoring

### Phase 7 — Clinical Validation
- [ ] Expanded dataset collection
- [ ] Labelled clinical ground truth
- [ ] Biomarker validation
- [ ] Sensitivity / specificity analysis
- [ ] Pilot studies

### Phase 8 — Machine Learning
- [ ] ML-based tremor classifier
- [ ] Personalized adaptive thresholds
- [ ] Longitudinal anomaly detection
- [ ] Disease progression modelling

---

## Research Focus

- Parkinsonian rest tremor detection from wrist-worn inertial sensors
- Tremor burden estimation and longitudinal tracking
- Digital biomarker development for continuous neurological monitoring
- False-positive rejection in unconstrained daily-life settings
- Wearable system design for neurological applications
- Comparison of threshold-based vs. ML-based tremor classifiers

---

## Citation

If you use ParkinSense in academic work, please cite as:

```bibtex
@misc{parkinsense2025,
  author       = {Kumar, Pranshu},
  title        = {ParkinSense: Continuous Neurological Monitoring \& Digital Biomarker Platform for Parkinson's Disease},
  year         = {2025},
  howpublished = {\url{https://github.com/notpranshu/ParkinSense}},
  note         = {Open-source research prototype}
}
```

---

## Disclaimer

ParkinSense is a research and educational project developed as part of an undergraduate engineering programme.

**This platform is not a certified medical device.** It must not be used for clinical diagnosis, treatment planning, or medical decision-making of any kind.

All outputs — including tremor scores, severity labels, biomarkers, and analytics — are intended solely for research, educational, and exploratory purposes. No clinical accuracy claims are made or implied.

For Parkinson's disease assessment, consult a qualified neurologist.

---

<div align="center">

**ParkinSense &nbsp;·&nbsp; Realtime Neurological Monitoring &nbsp;·&nbsp; Digital Biomarkers &nbsp;·&nbsp; Parkinson's Disease Research**

*VJTI Mumbai &nbsp;·&nbsp; Electronics & Telecommunication Engineering*

</div>
