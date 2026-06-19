# ParkinSense

<div align="center">

![Status](https://img.shields.io/badge/Status-Active%20Development-success)
![Platform](https://img.shields.io/badge/Platform-XIAO%20nRF52840%20Sense-blue)
![Sensors](https://img.shields.io/badge/Sensors-LSM6DS3%20IMU-orange)
![Connectivity](https://img.shields.io/badge/BLE-100Hz%20Streaming-success)
![Stage](https://img.shields.io/badge/Stage-Realtime%20Digital%20Biomarkers-yellow)

### Continuous Neurological Monitoring & Digital Biomarker Platform for Parkinson's Disease

*Building a WHOOP-style wearable platform for continuous Parkinson's disease monitoring through inertial sensing, signal processing, digital biomarkers, and longitudinal analytics.*

</div>

---

# Overview

ParkinSense is a wearable neurological monitoring platform designed to continuously monitor Parkinsonian motor symptoms using a wrist-worn wearable and real-time signal processing.

The system transforms raw inertial sensor data into clinically relevant digital biomarkers capable of supporting:

- Continuous symptom monitoring
- Tremor quantification
- Medication response analysis
- Disease progression research
- Longitudinal neurological analytics

Unlike traditional episodic clinical assessments, ParkinSense focuses on real-world continuous monitoring and objective symptom quantification.

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
Realtime Tremor Analysis
```

Packet Structure:

```text
Packet Header
 ├─ Timestamp (4 bytes)

10 IMU Samples
 ├─ ax
 ├─ ay
 ├─ az
 ├─ gx
 ├─ gy
 └─ gz
```

Packet Size:

```text
124 bytes
```

---

# Dataset Status

Current datasets:

- stationary_60s.csv
- normal_motion_60s.csv
- walking_60s.csv
- simulated_tremor_30s.csv
- vibration_reference_30s.csv

Current Dataset Categories:

- Stationary Baseline
- Daily Motion
- Walking
- Simulated Parkinsonian Tremor
- External Vibration Reference

Current Collection Volume:

```text
7000+ Offline Samples
10000+ Realtime Samples
```

Dataset expansion is ongoing.

---

# Tremor Detection Pipeline

Current Tremor Detector Version:

```text
Tremor Detector V4
```

Pipeline:

```text
Gyroscope Magnitude
        │
        ▼
5 Second Window
        │
        ▼
FFT Analysis
        │
        ▼
Dominant Frequency Extraction
        │
        ▼
Band Energy Analysis
        │
        ▼
Frequency Stability Analysis
        │
        ▼
Decision Gates
        │
        ▼
Persistence Filter
        │
        ▼
Tremor Classification
```

---

# Extracted Features

Current features:

- RMS Motion
- Dominant Frequency
- Frequency Stability
- Band Energy Ratio
- Best Tremor Axis
- Tremor Confidence
- Tremor Persistence
- Tremor Burden

---

# Decision Logic

Current detector uses:

## Motion Gate

```text
10 < RMS Motion < 70
```

## Frequency Gate

```text
4 Hz ≤ Frequency ≤ 7 Hz
```

## Energy Gate

```text
Band Energy Ratio > 0.30
```

## Stability Gate

```text
Frequency Std Dev < 1.50 Hz
```

Classification Threshold:

```text
Tremor Score ≥ 75
```

---

# Current Digital Biomarkers

## Tremor Frequency

Dominant tremor frequency measured from FFT analysis.

## Tremor Energy

Energy concentration within Parkinsonian tremor bands.

## Tremor Stability

Temporal consistency of dominant tremor frequency.

## Tremor Confidence

Detector confidence score.

## Tremor Persistence

Multi-window confirmation logic for reducing false positives.

## Tremor Burden

Percentage of monitoring windows classified as tremor.

---

# Current Repository Structure

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
│       │    ├── tremor_detector_v3.py
│       │
│       ├── realtime
│       │    ├── ble_receiver.py
│       │    ├── realtime_tremor.py
│       │    └── realtime_capture.csv
│       │
│       └── data
│
├── hardware
│
├── docs
│
├── research
│
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
- Realtime Data Logging
- FFT Processing Pipeline
- Tremor Detector V4
- Realtime Tremor Detection
- Confidence Scoring
- Tremor Persistence Logic
- Tremor Burden Tracking

## In Progress

- Dataset Expansion
- Biomarker Validation
- Realtime Analytics Refinement

## Upcoming

- Bradykinesia Assessment
- MAX30102 Integration
- HR Monitoring
- HRV Monitoring
- Sleep Analytics
- Mobile Dashboard

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
