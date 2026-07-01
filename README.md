<div align="center">

# 🧠 ParkinSense

![Status](https://img.shields.io/badge/Status-Active%20Development-success)
![Platform](https://img.shields.io/badge/Platform-XIAO%20nRF52840%20Sense-blue)
![Sensors](https://img.shields.io/badge/Sensors-LSM6DS3%20IMU%20%2B%20MAX30102-red)
![BLE](https://img.shields.io/badge/BLE-104Hz%20Streaming-success)
![Pipeline](https://img.shields.io/badge/Pipeline-V2.5-brightgreen)
![Dashboard](https://img.shields.io/badge/Dashboard-Live%20Plotly-orange)

### Continuous Neurological Monitoring & Digital Biomarker Platform

*A wearable sensing platform for continuous Parkinson's disease monitoring using inertial sensing, physiological sensing, digital biomarkers, and real-time analytics.*

</div>

<br>

## 📑 Table of Contents

- [Overview](#-overview)
- [Core Features](#-core-features)
- [Development Branches](#-development-branches)
- [System Architecture](#-system-architecture)
- [Hardware Platform](#-hardware-platform)
- [Firmware](#-firmware)
- [BLE Protocol](#-ble-protocol)
- [Signal Processing Pipeline](#-signal-processing-pipeline)
- [Physiological Monitoring](#-physiological-monitoring)
- [Digital Biomarkers](#-digital-biomarkers)
- [Dashboard](#-dashboard)
- [Repository Structure](#-repository-structure)
- [Getting Started](#-getting-started)
- [Performance](#-performance)
- [Development Roadmap](#-development-roadmap)
- [Research Focus](#-research-focus)
- [Citation](#-citation)
- [Disclaimer](#%EF%B8%8F-disclaimer)

<br>

## 🔭 Overview

ParkinSense is an open-source wearable research platform designed for **continuous neurological monitoring** of Parkinson's disease using wrist-worn sensors.

Instead of relying solely on periodic clinical assessments, ParkinSense continuously measures motion and physiological signals throughout everyday activities. The platform combines inertial sensing, optical sensing, digital signal processing, and real-time inference to generate quantitative neurological biomarkers.

The project has evolved into a modular wearable platform inspired by modern health wearables such as WHOOP, while remaining focused on Parkinsonian symptom monitoring and biomedical signal analysis.

**Current sensing capabilities:**

| | |
|---|---|
| 📐 | 6-axis inertial sensing |
| 💡 | Optical PPG sensing |
| 📡 | Real-time BLE streaming |
| 🌊 | Multi-stage tremor detection |
| 🏃 | Motion-context aware inference |
| ❤️ | Live physiological monitoring |
| 📊 | Digital biomarker extraction |

<br>

## ✨ Core Features

### Motion Monitoring
- Continuous 104 Hz IMU acquisition
- LSM6DS3 accelerometer and gyroscope
- Binary BLE packet streaming
- Multi-axis tremor detection
- Motion context classification
- False-positive rejection
- Confidence estimation
- Tremor burden estimation

### Physiological Monitoring
**Current:**
- MAX30102 optical sensor
- IR acquisition
- RED acquisition
- Finger detection
- Real-time PPG streaming

**Upcoming:**
- Heart rate
- Heart rate variability (RMSSD)
- SpO₂ estimation
- Recovery score
- Sleep analytics

### Software Platform
- Modular V2 signal-processing pipeline
- Live Plotly Dash dashboard
- Offline dataset recorder
- Replay framework
- Digital biomarker extraction
- Research-oriented architecture
- Future ML compatibility

<br>

## 🌳 Development Branches

### `main`
**Stable release** — contains the validated V2 neurological monitoring platform.

- Stable BLE streaming
- V2 motion pipeline
- Real-time dashboard
- Offline analytics
- Dataset recorder

### `feature/v2-signal-processing`
Development branch used during the redesign of the signal-processing architecture.

| Area | Previous | Current |
|------|----------|---------|
| Pipeline | FFT only | Modular |
| Filters | None | Gravity + Notch + Band-pass |
| Motion Detection | None | REST / LOW MOTION / ACTIVE |
| Detector | Single axis | Multi-axis |
| Confidence | Basic | Independent estimator |
| Validation | Sliding window | Temporal smoother |
| Runtime | Legacy | Runtime V2 |

### `feature/v2-max30102` 🔧 *current*
Adds complete physiological sensing to the wearable platform.

**Current additions:**
- MAX30102 integration
- Binary packet upgrade
- IR streaming
- RED streaming
- Finger detection
- PPG Fusion module
- Unified runtime
- Updated dashboard

**Upcoming:**
- Heart rate · HRV · SpO₂ · Recovery metrics · Sleep analytics

<br>

## 🏗️ System Architecture

```
                   Wearable Device
                          │
          ┌───────────────┴───────────────┐
          │                                │
          ▼                                ▼
     LSM6DS3 IMU                      MAX30102
          │                                │
          └───────────────┬────────────────┘
                           │
                           ▼
                  Binary BLE Packet
                           │
                           ▼
                    Runtime V2
                           │
        ┌──────────────────┴──────────────────┐
        │                                      │
        ▼                                      ▼
 Motion Processing Pipeline               PPG Fusion
        │                                      │
        └──────────────────┬───────────────────┘
                            ▼
                  Digital Biomarkers
                            │
                            ▼
                 Plotly Dash Dashboard
```

<br>

## 🔌 Hardware Platform

### Wearable Device

| Component | Specification |
|------------|----------------|
| MCU | Seeed Studio XIAO nRF52840 Sense |
| IMU | SparkFun LSM6DS3 |
| Optical Sensor | MAX30102 |
| BLE | Bluetooth Low Energy 5.0 |
| Battery | 3.7 V 700 mAh Li-ion (902035) |
| Charging | USB-C |
| Expansion | I²C |

### Operating Configuration

| Parameter | Value |
|------------|--------|
| Accelerometer ODR | 104 Hz |
| Gyroscope ODR | 104 Hz |
| BLE Streaming | ~104 Hz |
| BLE MTU | 247 Bytes |
| Samples / Packet | 10 |
| Packet Size | 248 Bytes |
| Analysis Window | 4 seconds |
| Runtime | Continuous |

<br>

## 🧩 Firmware

The wearable firmware is built around a modular architecture separating sensing, packet generation, and BLE communication.

**Responsibilities:**
1. Initialize LSM6DS3
2. Initialize MAX30102
3. Sample IMU at 104 Hz
4. Sample optical sensor
5. Assemble binary packet
6. Timestamp samples
7. Stream packets over BLE
8. Monitor sensor availability
9. Battery-powered operation

The firmware supports simultaneous inertial and optical acquisition without affecting BLE throughput.

**Location:** `firmware/xiao_nrf52840/`

<br>

## 📡 BLE Protocol

Each BLE notification contains one complete sensor packet.

```
┌─────────────────────────────────────┐
│ Header                               │
│   Version   (1B)                     │
│   Flags     (1B)                     │
│   Reserved  (2B)                     │
│   Timestamp (4B)                     │
├─────────────────────────────────────┤
│ 10 × Samples                         │
│   Acc X · Acc Y · Acc Z              │
│   Gyro X · Gyro Y · Gyro Z           │
│   IR · RED                           │
└─────────────────────────────────────┘
```

**Header**

| Field | Type |
|--------|------|
| Version | uint8 |
| Flags | uint8 |
| Reserved | uint16 |
| Timestamp | uint32 |

**Per sample**

| Signal | Type |
|----------|------|
| Acc X / Y / Z | int16 |
| Gyro X / Y / Z | int16 |
| IR | uint32 |
| RED | uint32 |

> The versioned packet format allows future additions while maintaining backward compatibility between firmware and runtime.

<br>

## 🔬 Signal Processing Pipeline

The V2 pipeline is built as a sequence of independent processing stages. Each module has a single responsibility, allowing algorithms to be validated, replaced, or extended without affecting the rest of the system.

```
Raw BLE Packet
      │
      ▼
Packet Decoder
      │
      ▼
Rolling Buffer (4s)
      │
      ├────────────── IMU ──────────────┐
      │                                 │
      ▼                                 ▼
Gravity Removal                   PPG Fusion
      │                                 │
50 Hz Notch Filter                Finger Detection
      │                                 │
Butterworth Band-pass             IR / RED Processing
      │                                 │
Feature Extraction                Future HR / SpO₂
      │                                 │
Motion Context                    Physiological Features
      │                                 │
Rule Engine                       Future Fusion
      │                                 │
Temporal Validation                     │
      └───────────────┬─────────────────┘
                       ▼
              Digital Biomarkers
                       ▼
              Realtime Dashboard
```

### Stage 1 — Packet Decoding
Incoming BLE notifications are decoded into structured sensor samples: timestamp, accelerometer, gyroscope, IR, RED, packet version, and status flags.

### Stage 2 — Rolling Buffer
Sensor samples accumulate into a rolling 4-second analysis window.

> Stable FFT resolution · Better frequency estimation · Reduced variance · Lower false positives

### Stage 3 — Gravity Removal
The gravity component is removed from the accelerometer using a low-pass estimator — separating static orientation from motion, improving motion-context classification, and removing postural bias.

### Stage 4 — Notch Filtering
A digital 50 Hz notch filter suppresses mains interference in electrically noisy environments. Applied to both gyroscope and accelerometer.

### Stage 5 — Butterworth Band-pass
Signals are filtered into the Parkinsonian tremor band: **4.0 Hz – 6.5 Hz**.

> Removes slow drift · Removes high-frequency vibration · Improves SNR

### Stage 6 — Motion Context
`MotionContext` classifies each window into:

| State | Description |
|---------|------------|
| `REST` | Stationary wrist |
| `LOW MOTION` | Small voluntary movement |
| `ACTIVE` | Intentional movement |

Motion state is used by the detector to suppress false positives.

### Stage 7 — Feature Extraction
The `FeatureExtractor` computes biomarkers from each gyroscope axis:

RMS · Dominant Frequency · Band Ratio · Spectral Entropy · Spectral Centroid · Zero Crossing Rate · Peak Magnitude · Frequency Stability

*Planned:* Spectral Flatness · Harmonic Ratio · PSD Quality · Signal-to-Noise Ratio

### Stage 8 — Multi-axis Tremor Detection
Instead of analyzing a single axis, the detector evaluates all three gyroscope axes simultaneously.

| Feature | Score |
|----------|------|
| Frequency in tremor band | +35 |
| Band ratio | +30 |
| Axis agreement | +20 |
| Axis dominance | +20 |
| ACTIVE penalty | −40 |
| RMS gate | Immediate rejection |

Tremor is declared when **Score ≥ 80**.

### Stage 9 — Confidence Estimation
Confidence is computed independently of the tremor score, and is reduced when dominant frequency varies, tremor band energy is weak, or wrist motion is excessive. A window can therefore be classified as Tremor with low confidence, or No Tremor with high confidence.

### Stage 10 — Temporal Validation
A rolling 10-window history requires **5 positive windows** before confirming tremor, removing transient detections caused by sudden motion.

### Stage 11 — State Machine
The detector uses hysteresis to avoid rapidly switching between states:

```
NO TREMOR → POSSIBLE → CONFIRMED → RECOVERY → NO TREMOR
```

<br>

## ❤️ Physiological Monitoring

ParkinSense includes an optical sensing subsystem using the MAX30102.

**Current functionality:** IR acquisition · RED acquisition · Finger detection · BLE transmission · Runtime decoding · Dashboard visualization

The current implementation focuses on validating the hardware and data pipeline before physiological analytics are introduced.

### PPG Fusion Module
The PPG Fusion layer acts as the interface between the optical sensor and the analytics pipeline.

**Current:** IR validation · RED validation · Finger detection · Sensor availability

**Future:** Heart rate estimation · Heart rate variability · Respiratory rate · SpO₂ estimation · Recovery metrics · Signal quality estimation · Motion artifact rejection

<br>

## 📊 Digital Biomarkers

| Biomarker | Description |
|-----------|-------------|
| Tremor Score | Composite detector output |
| Tremor Frequency | Dominant oscillation |
| Confidence | Detector certainty |
| Tremor Severity | Severity category |
| Motion State | Activity context |
| Tremor Burden | Long-term percentage |
| Band Ratio | Tremor band energy |
| Axis Agreement | Cross-axis consistency |
| Axis Dominance | Dominant tremor axis |
| Rest Index | Wrist stillness metric |
| Finger Detection | Optical sensor status |
| IR Signal | Raw infrared intensity |
| RED Signal | Raw red intensity |

*Future:* Heart Rate · HRV · SpO₂ · Recovery Score · Sleep Quality · Bradykinesia Index · Dyskinesia Index · Medication Response · Longitudinal Symptom Burden

<br>

## 📺 Dashboard

The dashboard provides real-time visualization of all computed biomarkers, refreshing automatically every 100 ms while remaining synchronized with the runtime metrics.

**Current components:** Live Gyroscope · Tremor Score Gauge · Motion State · Confidence · Severity · Tremor Burden · Dominant Frequency · Band Ratio · IR Signal · RED Signal · Finger Detection · Axis Information

**Coming soon:** Heart Rate · HRV · SpO₂ · Recovery · Sleep Analytics · Battery Status

<br>

## 📁 Repository Structure

```
ParkinSense
│
├── firmware/
│
├── dashboard/
│   └── python/
│       ├── analytics/
│       ├── calibration/
│       ├── context/
│       ├── dashboard/
│       ├── data/
│       ├── dataset/
│       ├── detector/
│       ├── detectors/
│       ├── features/
│       ├── filters/
│       ├── fusion/
│       ├── inference/
│       ├── models/
│       ├── pipeline/
│       ├── pipelines/
│       ├── realtime/
│       ├── replay/
│       ├── runtime/
│       └── utils/
│
├── docs/
├── hardware/
├── research/
└── README.md
```

The repository is intentionally modular to support rapid algorithm development while maintaining separation between firmware, analytics, and future machine-learning components.

<br>

## 🚀 Getting Started

This guide walks through setting up the complete ParkinSense platform, from flashing the wearable firmware to visualizing live neurological and physiological biomarkers.

### Requirements

**Hardware**

| Component | Purpose |
|------------|----------|
| Seeed Studio XIAO nRF52840 Sense | Main wearable MCU |
| SparkFun LSM6DS3 | 6-axis IMU |
| MAX30102 | Optical PPG sensor |
| 3.7 V 700 mAh Li-ion Battery (902035) | Portable power supply |
| USB-C Cable | Programming and charging |
| BLE-enabled Computer | Runtime and dashboard |

**Software**
- Python 3.11+
- Arduino IDE 2.x
- Git

```bash
pip install numpy scipy pandas matplotlib plotly dash bleak pyqtgraph
```

### Clone the Repository

```bash
git clone https://github.com/sudo-pranshu/ParkinSense.git
cd ParkinSense
```

### Select Branch

```bash
git checkout feature/v2-max30102
git branch
```

Expected output:
```
* feature/v2-max30102
```

### Flash the Firmware

Open Arduino IDE and navigate to:
```
firmware/xiao_nrf52840/src/parksense_wearable_v3/
```

Install required libraries:
- Adafruit Bluefruit nRF52
- Adafruit TinyUSB
- SparkFun LSM6DS3
- SparkFun MAX3010x
- Wire

Select **Board → Seeed XIAO nRF52840 Sense**, choose the correct serial port, then click **Upload**.

**Expected serial output:**
```
ParkinSense Initializing...

Initializing IMU...
✓ IMU Ready

Initializing MAX30102...
✓ MAX30102 Ready

Battery Connected
BLE Advertising...
Waiting for Connection...
```

### Run the Runtime

```bash
python -m dashboard.python.runtime.runtime_v2
```

Expected output:
```
Searching for ParkinSense...
Connected
Streaming...

========== PARKINSENSE V2 ==========
```

The runtime automatically generates `realtime_capture_v2.csv` and `realtime_metrics_v2.json`.

### Launch the Dashboard

```bash
python dashboard/python/dashboard/realtime_dashboard_v2.py
```

Open **http://127.0.0.1:8050** — the dashboard updates continuously while the wearable is streaming.

### Complete Workflow

```
Flash Firmware → Power Wearable → BLE Advertising → Runtime V2
       → Packet Decoder → Motion Pipeline → PPG Fusion
       → Digital Biomarkers → Dashboard
```

### Sample Runtime Output

```
========== PARKINSENSE V2 ==========

State          : NO TREMOR
Score          : 14 / 100
Confidence     : 96 %
Frequency      : 5.18 Hz
Severity       : NONE
Motion         : REST
Best Axis      : GY
IR             : 91243
RED            : 61871
Finger         : YES

=====================================
```

### Troubleshooting

| Problem | Solution |
|----------|----------|
| Device not found | Ensure BLE is enabled and firmware is running |
| Dashboard not updating | Verify `runtime_v2.py` is running |
| No IMU data | Check LSM6DS3 wiring |
| No PPG values | Verify MAX30102 SDA/SCL connections |
| Finger always NO | Place finger completely over sensor |
| Runtime crashes | Confirm Python dependencies are installed |
| BLE disconnects | Restart runtime and reconnect |

<br>

## ⚡ Performance

| Metric | Value |
|----------|---------|
| IMU Sampling | 104 Hz |
| BLE Streaming | ~104 Hz |
| Analysis Window | 4 s |
| Packet Size | 248 Bytes |
| Runtime Latency | <100 ms after analysis window |
| Dashboard Refresh | 100 ms |
| Runtime | Continuous |

The current implementation supports simultaneous IMU and optical streaming while maintaining stable BLE throughput.

<br>

## 🗺️ Development Roadmap

**Phase 1 — Hardware**
- [x] LSM6DS3 Integration
- [x] MAX30102 Integration
- [x] BLE Streaming
- [x] Battery-powered Operation

**Phase 2 — Signal Processing**
- [x] Gravity Removal
- [x] Notch Filter
- [x] Butterworth Band-pass
- [x] Motion Context
- [x] Feature Extraction
- [x] Multi-axis Detector
- [x] Confidence Estimation
- [x] Temporal Validation
- [x] State Machine

**Phase 3 — Physiological Monitoring**
- [x] IR Acquisition
- [x] RED Acquisition
- [x] Finger Detection
- [ ] Heart Rate
- [ ] HRV
- [ ] SpO₂

**Phase 4 — Digital Biomarkers**
- [x] Tremor Frequency
- [x] Tremor Score
- [x] Confidence
- [x] Motion Context
- [x] Tremor Burden
- [x] Rest Index

**Phase 5 — Wearable Platform**
- [x] Rechargeable Li-ion Operation
- [x] Live Dashboard
- [x] Runtime V2
- [x] BLE Packet Versioning
- [ ] Battery Monitoring
- [ ] Power Optimization
- [ ] Mobile Companion App

**Phase 6 — Machine Learning**
- [ ] Adaptive Thresholds
- [ ] Personalized Models
- [ ] Activity Recognition
- [ ] Bradykinesia Detection
- [ ] Dyskinesia Detection
- [ ] Long-term Progression Analysis

<br>

## 🔍 Research Focus

- Parkinsonian rest tremor
- Digital biomarkers
- Wearable neurological monitoring
- Continuous disease tracking
- Motion artifact rejection
- Physiological signal fusion
- Biomedical signal processing
- Edge AI for wearables

<br>

## 📖 Citation

```bibtex
@misc{parkinsense2026,
  author       = {Pranshu Kumar},
  title        = {ParkinSense: Continuous Neurological Monitoring and Digital Biomarker Platform},
  year         = {2026},
  howpublished = {\url{https://github.com/sudo-pranshu/ParkinSense}},
  note         = {Open-source wearable neurological monitoring platform}
}
```

<br>

## ⚠️ Disclaimer

ParkinSense is an open-source research platform intended for educational and experimental purposes.

It is **not** a certified medical device and must not be used for diagnosis, treatment, or clinical decision-making. All outputs, including tremor detection, confidence scores, physiological metrics, and digital biomarkers, are intended solely for research and development.

Clinical validation with appropriately labeled datasets is required before any medical application.

---

<div align="center">

### ParkinSense
**Continuous Neurological Monitoring & Digital Biomarker Platform**

Developed by **Pranshu Kumar**

*Wearable Computing • Biomedical Signal Processing • Digital Health • Parkinson's Disease Research*

</div>
