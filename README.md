# ParkinSense

<div align="center">

![Status](https://img.shields.io/badge/Status-Active%20Development-success)
![Platform](https://img.shields.io/badge/Platform-XIAO%20nRF52840%20Sense-blue)
![Sensors](https://img.shields.io/badge/Sensors-LSM6DS3%20IMU-orange)
![Connectivity](https://img.shields.io/badge/BLE-100Hz%20Streaming-success)
![Stage](https://img.shields.io/badge/Stage-Realtime%20Neurological%20Analytics-yellow)

### Continuous Neurological Monitoring & Digital Biomarker Platform for Parkinson's Disease

*Building a WHOOP-style wearable platform for continuous Parkinson's disease monitoring through inertial sensing, signal processing, digital biomarkers, and longitudinal analytics.*

</div>

---

# Overview

ParkinSense is a wearable neurological monitoring platform designed to continuously monitor Parkinsonian motor symptoms using a wrist-worn device and realtime signal processing.

The platform transforms raw inertial sensor data into clinically relevant digital biomarkers capable of supporting:

- Continuous symptom monitoring
- Tremor quantification
- Medication response assessment
- Disease progression research
- Longitudinal neurological analytics

Unlike traditional episodic clinical assessments, ParkinSense focuses on objective, continuous monitoring in real-world environments.

---

# Current Achievements

ParkinSense currently supports:

- Continuous IMU acquisition at 104 Hz
- Stable BLE streaming at ~100 Hz
- Binary packet-based sensor transport
- Realtime CSV data logging
- FFT-based tremor analysis
- Frequency stability tracking
- Tremor confidence estimation
- Tremor persistence filtering
- Tremor burden estimation
- Realtime analytics dashboard
- Live neurological biomarker visualization

Current platform status:

```text
Sensor Acquisition      ✅
BLE Streaming           ✅
Realtime Analytics      ✅
Tremor Detection        ✅
Digital Biomarkers      ✅
Live Dashboard          ✅
```

---

# Vision

Develop a next-generation wearable capable of quantifying Parkinsonian symptoms outside clinical environments through continuous sensing and digital biomarker extraction.

Long-term objectives:

- Rest Tremor Detection
- Tremor Burden Estimation
- Bradykinesia Assessment
- Sleep Monitoring
- Recovery Monitoring
- Autonomic Biomarker Analysis
- Disease Progression Modelling

---

# System Architecture

```text
Wearable Device
       │
       ▼
IMU Acquisition
       │
       ▼
BLE Streaming
       │
       ▼
Realtime Analytics Engine
       │
       ▼
Feature Extraction
       │
       ▼
Digital Biomarkers
       │
       ▼
Clinical Insights
```

---

# Hardware Platform

## Current Hardware

- Seeed Studio XIAO nRF52840 Sense
- LSM6DS3 6-Axis IMU
- Bluetooth Low Energy (BLE)
- USB-C Interface
- Li-Ion Battery Support

## Current Operating Configuration

| Parameter | Value |
|------------|---------|
| Sample Rate | 104 Hz |
| Streaming Rate | ~100 Hz |
| BLE MTU | 247 Bytes |
| Batch Size | 10 Samples |
| Packet Size | 124 Bytes |
| Transport | BLE Notifications |

---

# Realtime Streaming Pipeline

Current firmware performs:

```text
IMU Sampling
      │
      ▼
104 Hz Acquisition
      │
      ▼
Binary Packet Encoding
      │
      ▼
BLE Notification
      │
      ▼
Python Receiver
      │
      ▼
CSV Logging
      │
      ▼
Realtime Analytics
```

Packet Structure:

```text
Packet Header
 ├─ Timestamp

IMU Samples
 ├─ Accelerometer
 └─ Gyroscope
```

Packet Size:

```text
124 bytes
```

---

# Realtime Analytics Engine

ParkinSense performs realtime neurological analysis directly from BLE sensor streams.

Analytics pipeline:

```text
BLE Stream
     │
     ▼
Packet Decoder
     │
     ▼
Rolling Window Buffer
     │
     ▼
FFT Processing
     │
     ▼
Feature Extraction
     │
     ▼
Decision Engine
     │
     ▼
Digital Biomarkers
```

Realtime outputs:

- Dominant Tremor Frequency
- Tremor Score
- Tremor Confidence
- Tremor Persistence
- Tremor Burden
- Classification Status

---

# Dataset Status

Current datasets include:

- Stationary Baseline
- Normal Daily Motion
- Walking Motion
- Simulated Parkinsonian Tremor
- External Vibration Reference

Current collection volume:

```text
7000+ Offline Samples
10000+ Realtime Samples
```

Dataset expansion is ongoing to improve robustness and generalization.

---

# Tremor Detection Pipeline

Current Tremor Detector:

```text
Tremor Detector V4
```

Pipeline:

```text
Gyroscope Magnitude
        │
        ▼
Windowed Analysis
        │
        ▼
FFT Processing
        │
        ▼
Frequency Extraction
        │
        ▼
Energy Analysis
        │
        ▼
Frequency Stability Analysis
        │
        ▼
Decision Engine
        │
        ▼
Persistence Filter
        │
        ▼
Tremor Classification
```

---

# Current Digital Biomarkers

## Tremor Frequency

Dominant tremor frequency extracted from spectral analysis.

## Tremor Energy

Energy concentration within Parkinsonian tremor bands.

## Tremor Stability

Temporal consistency of dominant tremor frequencies.

## Tremor Confidence

Detector confidence estimation.

## Tremor Persistence

Multi-window validation logic for reducing false positives.

## Tremor Burden

Percentage of monitoring windows classified as tremor.

---

# Dashboard

ParkinSense includes a realtime analytics dashboard built using Plotly Dash.

Current dashboard capabilities:

- Live Gyroscope Visualization
- Realtime Tremor Metrics
- Confidence Monitoring
- Tremor Burden Tracking
- Device Status Monitoring
- Live Classification Display

Dashboard architecture:

```text
BLE Receiver
      │
      ▼
Realtime CSV
      │
      ▼
Metrics Engine
      │
      ▼
Plotly Dashboard
```

---

# Repository Structure

```text
ParkinSense
│
├── firmware
│   └── xiao_nrf52840
│
├── dashboard
│   └── python
│
│       ├── analytics
│       │    └── tremor_detector_v3.py
│
│       ├── realtime
│       │    ├── ble_receiver.py
│       │    ├── realtime_tremor.py
│       │    ├── realtime_capture.csv
│       │    └── realtime_metrics.json
│
│       ├── dashboard
│       │    └── realtime_dashboard.py
│
│       └── data
│
├── hardware
├── docs
├── research
└── README.md
```

---

# Development Roadmap

## Phase 1 — Sensor Acquisition

- [x] IMU Integration
- [x] BLE Streaming
- [x] Realtime Data Acquisition
- [x] Binary Packet Protocol
- [x] Dataset Collection Framework

## Phase 2 — Signal Processing

- [x] FFT Analysis
- [x] Windowed Tremor Detection
- [x] Tremor Detector V3
- [x] Tremor Detector V4
- [x] Feature Extraction Pipeline

## Phase 3 — Digital Biomarkers

- [x] Tremor Frequency
- [x] Tremor Energy
- [x] Tremor Stability
- [x] Tremor Confidence
- [x] Tremor Persistence
- [x] Tremor Burden

## Phase 4 — Wearable Platform

- [x] BLE Streaming
- [x] Realtime Detection
- [x] Realtime Dashboard
- [ ] Battery Optimization
- [ ] Wearable Enclosure
- [ ] Mobile Dashboard

## Phase 5 — Clinical Validation

- [ ] Expanded Dataset Collection
- [ ] Real Patient Data Collection
- [ ] Biomarker Validation
- [ ] Pilot Studies

## Phase 6 — Advanced Analytics

- [ ] Bradykinesia Metrics
- [ ] Activity Classification
- [ ] Longitudinal Tracking
- [ ] Personalized Analytics
- [ ] AI-Assisted Monitoring

---

# Current Status

## Completed

- IMU Acquisition Pipeline
- Stable BLE Streaming (~100 Hz)
- Binary Packet Protocol
- Realtime Data Logging
- FFT Processing Pipeline
- Tremor Detector V4
- Realtime Tremor Detection
- Confidence Scoring
- Persistence Filtering
- Tremor Burden Tracking
- Plotly Dashboard
- Realtime Analytics Engine

## In Progress

- Dataset Expansion
- Biomarker Validation
- Dashboard Enhancements

## Upcoming

- Bradykinesia Assessment
- Activity Classification
- MAX30102 Integration
- Heart Rate Monitoring
- HRV Monitoring
- Sleep Analytics
- Mobile Application

---

# Research Focus

Current research areas:

- Parkinsonian Rest Tremor Detection
- Tremor Burden Estimation
- Digital Biomarker Development
- Continuous Neurological Monitoring
- Wearable Healthcare Systems
- Longitudinal Symptom Tracking

---

# Disclaimer

ParkinSense is a research and educational project.

This platform is **not a certified medical device** and must not be used for diagnosis, treatment, or clinical decision-making.

All outputs, biomarkers, and analytics are intended solely for research, educational, and exploratory purposes.

---

<div align="center">

**ParkinSense • Realtime Neurological Monitoring • Digital Biomarkers • Parkinson's Disease Research**

</div>
