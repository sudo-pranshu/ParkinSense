<div align="center">

# 🧠 ParkinSense

![Status](https://img.shields.io/badge/Status-Active%20Development-success)
![Platform](https://img.shields.io/badge/Platform-XIAO%20nRF52840%20Sense-blue)
![Sensors](https://img.shields.io/badge/Sensors-LSM6DS3%20IMU%20%2B%20MAX30102-red)
![BLE](https://img.shields.io/badge/BLE-104Hz%20Streaming-success)
![Pipeline](https://img.shields.io/badge/Pipeline-V2.5-brightgreen)
![PPG](https://img.shields.io/badge/PPG-HR%20%7C%20HRV%20%7C%20SpO₂-blueviolet)
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

Instead of relying solely on periodic clinical assessments, ParkinSense continuously measures motion and physiological signals throughout everyday activities. The platform combines inertial sensing, optical sensing, digital signal processing, and real-time inference to generate quantitative neurological and physiological biomarkers.

The project has evolved into a dual-pipeline wearable platform inspired by modern health wearables such as WHOOP, combining a mature multi-axis tremor-detection pipeline with a full PPG-based cardiac pipeline — heart rate, RR intervals, HRV, and SpO₂ — while remaining focused on Parkinsonian symptom monitoring and biomedical signal analysis.

**Current sensing capabilities:**

| | |
|---|---|
| 📐 | 6-axis inertial sensing |
| 💡 | Optical PPG sensing (IR + RED) |
| 📡 | Real-time BLE streaming |
| 🌊 | Multi-stage tremor detection |
| 🏃 | Motion-context aware inference |
| ❤️ | Heart rate, RR intervals & HRV |
| 🫁 | SpO₂ estimation |
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
- MAX30102 optical sensor
- IR acquisition
- RED acquisition
- Finger-presence detection with hysteresis
- Signal Quality Index (SQI) estimation
- Sensor status classification (NO_FINGER / LOW_SIGNAL / POOR_SIGNAL / GOOD / HIGH_SIGNAL / SATURATED)
- Adaptive peak detection and RR interval extraction
- Heart rate estimation with confidence scoring
- EMA-based heart rate stabilization
- Heart rate variability (RMSSD, SDNN, Mean RR, pNN50)
- SpO₂ estimation (ratio-of-ratios with signal-lock tracking)
- Motion-aware heart rate confidence fusion

**Upcoming:**
- Recovery score
- Sleep analytics

### Software Platform
- Modular V2 signal-processing pipeline (motion + PPG)
- Unified runtime combining both pipelines
- Live Plotly Dash dashboard with physiological panels
- Offline dataset recorder
- Realtime CSV logging
- JSON metrics export
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

### `develop` 🔧 *current*
Adds complete physiological sensing to the wearable platform. This work landed directly on `develop` rather than a separate feature branch.

**Completed:**
- MAX30102 integration
- Binary packet upgrade
- IR / RED streaming
- Finger detection with ON/OFF hysteresis
- Signal Quality Index + sensor status classification
- PPG Processing Pipeline (`PPGProcessor`)
- Heart rate estimation (adaptive peak detection, RR extraction, EMA smoothing)
- Heart rate variability (RMSSD, SDNN, Mean RR, pNN50)
- SpO₂ estimation with signal-lock state machine
- Motion-aware HR confidence fusion
- Unified runtime merging motion + PPG pipelines
- Updated dashboard with live physiological panels

**Upcoming:**
- Recovery metrics
- Sleep analytics

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
 Motion Processing Pipeline               PPG Processing Pipeline
        │                                      │
 Gravity · Notch · Bandpass              Finger Detection · SQI
        │                                      │
 Feature Extraction                      Bandpass · Peak Detection
        │                                      │
 Tremor Detection                        RR Intervals · HR · HRV
        │                                      │
 Confidence · Temporal Validation        SpO₂ · Motion-aware Confidence
        │                                      │
 Tremor State Machine                    EMA Stabilization
        │                                      │
        └──────────────────┬───────────────────┘
                            ▼
                  Digital Biomarkers
                            │
              ┌─────────────┴─────────────┐
              ▼                           ▼
       CSV / JSON Logging          Plotly Dash Dashboard
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
| PPG (IR/RED) Sampling | ~50 Hz |
| BLE Streaming | ~104 Hz |
| BLE MTU | 247 Bytes |
| Samples / Packet | 10 |
| Packet Size | 248 Bytes |
| Motion Analysis Window | 4 seconds |
| PPG Analysis Window | 10 seconds (rolling) |
| Runtime | Continuous |

<br>

## 🧩 Firmware

The wearable firmware is built around a modular architecture separating sensing, packet generation, and BLE communication.

**Responsibilities:**
1. Initialize LSM6DS3
2. Initialize MAX30102
3. Sample IMU at 104 Hz
4. Sample optical sensor (IR + RED)
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

ParkinSense runs **two independent processing pipelines** from the same BLE packet stream — a motion pipeline for tremor biomarkers and a PPG pipeline for cardiac biomarkers. Each stage has a single responsibility, so algorithms can be validated, replaced, or extended without affecting the rest of the system.

```
Raw BLE Packet
      │
      ▼
Packet Decoder
      │
      ▼
Rolling Buffer
      │
      ├────────────── IMU ──────────────┐
      │                                 │
      ▼                                 ▼
 Motion Pipeline                   PPG Pipeline
```

### 🏃 Motion Pipeline

**Raw Samples**
Accelerometer and gyroscope samples arrive from the decoded BLE packet at 104 Hz.

**Rolling Buffer**
Samples accumulate into a 4-second analysis window, giving stable FFT resolution, better frequency estimation, reduced variance, and lower false-positive rates.

**Gravity Removal**
A low-pass estimator subtracts the gravity component from the accelerometer signal, separating static orientation from motion and removing postural bias.

**Notch Filter**
A digital 50 Hz notch filter suppresses mains interference on both the accelerometer and gyroscope in electrically noisy environments.

**Butterworth Band-pass**
Signals are filtered into the Parkinsonian tremor band (4.0–6.5 Hz), removing slow drift and high-frequency vibration to improve SNR.

**Motion Context**
`MotionContext` classifies each window as `REST`, `LOW MOTION`, or `ACTIVE`, so the detector can suppress false positives during intentional movement.

**Feature Extraction**
`FeatureExtractor` computes RMS, dominant frequency, band ratio, spectral entropy, spectral centroid, zero-crossing rate, peak magnitude, and frequency stability per gyroscope axis.

**Tremor Detection**
All three gyroscope axes are scored simultaneously (frequency in band, band ratio, axis agreement, axis dominance, ACTIVE-state penalty, RMS gate), and tremor is declared when the composite score reaches 80/100.

**Confidence**
A separate confidence estimator is reduced when dominant frequency is unstable, tremor-band energy is weak, or wrist motion is excessive — decoupling "is this tremor" from "how sure are we."

**Temporal Validation**
A rolling 10-window history requires 5 positive windows before confirming tremor, filtering out transient detections from sudden movement.

**State Machine**
Hysteresis-based states (`NO TREMOR → POSSIBLE → CONFIRMED → RECOVERY → NO TREMOR`) prevent rapid switching between tremor states.

**Biomarkers**
Tremor score, dominant frequency, severity, tremor burden, band ratio, axis agreement/dominance, and rest index are emitted for logging and the dashboard.

<br>

### 💡 PPG Pipeline

**Raw IR/RED**
IR and RED sample pairs arrive from the decoded BLE packet at the optical sensor's native rate.

**Rolling Buffer**
`PPGProcessor` maintains a rolling ~10-second buffer per channel, giving the downstream algorithms enough cardiac cycles to work with while staying responsive to changing conditions.

**Finger Detection**
Per-sample finger presence is assessed from DC level, AC/DC ratio, saturation, and cardiac-frequency content, then debounced with asymmetric ON/OFF hysteresis (fast to confirm, slower to release) so brief contact wobbles don't flicker the reading.

**Signal Quality**
A Signal Quality Index (SQI) is computed from spectral concentration, harmonic ratio, perfusion index, and pulse repeatability, giving a 0–100 score for how trustworthy the current buffer is.

**Sensor Status**
The raw signal is classified into `NO_FINGER`, `LOW_SIGNAL`, `POOR_SIGNAL`, `GOOD`, `HIGH_SIGNAL`, or `SATURATED`, combining DC level, clipping, and the SQI score into one actionable label.

**Bandpass Filtering**
A zero-phase Butterworth band-pass isolates the cardiac band (0.5–4.5 Hz), removing baseline wander and high-frequency motion/EMG noise before any peak detection happens.

**Peak Detection**
Systolic peaks are located with rolling z-score normalization, local energy gating, adaptive prominence scaling, a refractory period, and a physical-domain pulse-width gate — then scored for per-beat confidence (prominence, SNR, width, symmetry, upstroke/downstroke slope, RR consistency).

**RR Interval Extraction**
Beat-to-beat intervals are derived from accepted peaks, filtered against physiological bounds, and cleaned with confidence-weighted outlier rejection so a handful of noisy beats can't distort the interval set.

**Heart Rate Estimation**
A confidence-weighted median of the cleaned RR intervals produces the raw per-window BPM, alongside a composite confidence score built from beat quality, rhythm regularity, signal quality, and perfusion.

**EMA Stabilization**
The published heart rate is smoothed with an exponential moving average, with low-confidence outlier windows held back rather than allowed to swing the display.

**HRV**
Once enough clean RR intervals are available, RMSSD, SDNN, Mean RR, and pNN50 are computed using standard time-domain HRV definitions, each carrying its own confidence and artifact-percentage diagnostics.

**SpO₂**
A beat-by-beat ratio-of-ratios estimate (with RED/IR peak alignment validation, calibration mapping, and a SEARCHING → LOCKED → TRACKING → LOST signal-lock state machine) produces a rate-limited, confidence-weighted SpO₂ reading, published on a throttled cadence.

**Motion-aware Confidence**
Overall HR confidence is discounted according to the Motion Pipeline's reported activity state, so a walking or running window is trusted less than a resting one without being discarded outright.

**Physiological Biomarkers**
Heart rate, RR intervals, HRV metrics, SpO₂, sensor status, and every confidence/quality sub-score are emitted for logging and the dashboard.

<br>

### 🔗 End-to-End Workflow

```
Firmware Init (IMU + MAX30102)
        │
        ▼
BLE Advertising & Connection
        │
        ▼
Binary Packet Streaming (~104 Hz)
        │
        ▼
Runtime V2 — Packet Decoding
        │
        ├─────────────────────────────┐
        ▼                             ▼
 Motion Pipeline                PPG Pipeline
 (Gravity → Notch → Bandpass    (Finger Detection → SQI → Bandpass
  → Motion Context → Features    → Peak Detection → RR → HR → EMA
  → Tremor Detection →           → HRV → SpO₂ → Motion-aware
  Confidence → Temporal           Confidence)
  Validation → State Machine)
        │                             │
        └─────────────┬───────────────┘
                       ▼
             Digital Biomarker Fusion
                       │
        ┌──────────────┴──────────────┐
        ▼                             ▼
 Realtime CSV Logging          JSON Metrics Export
        │                             │
        └──────────────┬──────────────┘
                        ▼
             Plotly Dash Dashboard
                        │
                        ▼
              Offline Replay & Analysis
```

<br>

## ❤️ Physiological Monitoring

ParkinSense includes a complete optical sensing subsystem built around the MAX30102, producing cardiac biomarkers alongside the motion pipeline's tremor biomarkers.

**Current functionality:** IR/RED acquisition · finger detection with hysteresis · signal quality estimation · sensor status classification · adaptive peak detection · RR interval extraction · heart rate estimation · EMA stabilization · heart rate variability (RMSSD, SDNN, Mean RR, pNN50) · SpO₂ estimation · motion-aware confidence fusion · BLE transmission · runtime decoding · dashboard visualization

### PPG Fusion Module
The PPG Fusion layer (`PPGProcessor`) acts as the stateful interface between the optical sensor and the analytics pipeline, maintaining rolling buffers, EMA smoothing state, finger-presence hysteresis, and SpO₂ publish throttling across calls.

**Current:** IR validation · RED validation · finger detection · sensor availability · signal quality · heart rate · RR intervals · HRV · SpO₂ · motion-aware confidence fusion

**Future:** Respiratory rate · recovery metrics

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
| Signal Quality (SQI) | 0–100 PPG signal trust score |
| Sensor Status | NO_FINGER / LOW / POOR / GOOD / HIGH / SATURATED |
| Heart Rate | EMA-stabilized BPM estimate |
| RR Intervals | Beat-to-beat interval series (ms) |
| HRV (RMSSD, SDNN) | Short-term heart rate variability |
| Mean RR / pNN50 | Additional HRV time-domain metrics |
| SpO₂ | Blood oxygen saturation estimate |
| HR Confidence | Composite, motion-aware trust score |

*Future:* Recovery Score · Sleep Quality · Bradykinesia Index · Dyskinesia Index · Medication Response · Longitudinal Symptom Burden

<br>

## 📺 Dashboard

The dashboard provides real-time visualization of all computed biomarkers, refreshing automatically every 100 ms while remaining synchronized with the runtime metrics.

**Current components:** Live Gyroscope · Tremor Score Gauge · Motion State · Confidence · Severity · Tremor Burden · Dominant Frequency · Band Ratio · IR Signal · RED Signal · Finger Detection · Axis Information · **Heart Rate** · **HRV (RMSSD/SDNN/Mean RR/pNN50)** · **SpO₂** · **Signal Quality / Sensor Status**

**Coming soon:** Recovery · Sleep Analytics · Battery Status

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
git checkout develop
git branch
```

Expected output:
```
* develop
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
       → Packet Decoder → Motion Pipeline + PPG Pipeline
       → Digital Biomarkers → CSV/JSON Logging → Dashboard
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

-------------------------------------
Heart Rate     : 71.4 BPM
SpO2           : 97.8 %
Signal Quality : 68.2
Finger         : YES
Sensor Status  : GOOD

RMSSD          : 24.3 ms
SDNN           : 31.6 ms
Mean RR        : 840.0 ms
pNN50          : 12.5 %
-------------------------------------

IR             : 91243
RED            : 61871

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
| Heart Rate stuck near None | Hold still for the full 10 s buffer to fill; check Signal Quality/Sensor Status |
| HRV always None | Needs several consecutive clean RR intervals — improve finger contact/stillness |
| Runtime crashes | Confirm Python dependencies are installed |
| BLE disconnects | Restart runtime and reconnect |

<br>

## ⚡ Performance

| Metric | Value |
|----------|---------|
| IMU Sampling | 104 Hz |
| PPG Sampling | ~50 Hz |
| BLE Streaming | ~104 Hz |
| Motion Analysis Window | 4 s |
| PPG Analysis Window | 10 s (rolling) |
| SpO₂ Publish Cadence | ~10 s (throttled) |
| Packet Size | 248 Bytes |
| Runtime Latency | <100 ms after analysis window |
| Dashboard Refresh | 100 ms |
| Runtime | Continuous |

The current implementation supports simultaneous IMU and optical streaming, running both the motion and PPG pipelines every cycle, while maintaining stable BLE throughput.

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
- [x] Signal Quality Estimation
- [x] Sensor Status Classification
- [x] Heart Rate
- [x] RR Interval Extraction
- [x] HRV (RMSSD, SDNN, Mean RR, pNN50)
- [x] SpO₂
- [x] Motion-aware HR Confidence

**Phase 4 — Digital Biomarkers**
- [x] Tremor Frequency
- [x] Tremor Score
- [x] Confidence
- [x] Motion Context
- [x] Tremor Burden
- [x] Rest Index
- [x] Heart Rate / HRV / SpO₂ Biomarkers

**Phase 5 — Wearable Platform**
- [x] Rechargeable Li-ion Operation
- [x] Live Dashboard
- [x] Runtime V2 (Unified Motion + PPG)
- [x] BLE Packet Versioning
- [x] Realtime CSV Logging
- [x] JSON Metrics Export
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
