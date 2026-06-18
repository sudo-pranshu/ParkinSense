# ParkinSense

<div align="center">

![Status](https://img.shields.io/badge/Status-Active%20Development-success)
![Platform](https://img.shields.io/badge/Platform-XIAO%20nRF52840%20Sense-blue)
![Sensors](https://img.shields.io/badge/Sensors-LSM6DS3%20IMU-orange)
![Stage](https://img.shields.io/badge/Stage-Digital%20Biomarker%20Research-yellow)

### Continuous Neurological Monitoring & Digital Biomarker Platform for Parkinson's Disease

*Building a WHOOP-style wearable platform for continuous Parkinson's disease monitoring through inertial sensing, signal processing, and digital biomarkers.*

</div>

---

## Overview

ParkinSense is a wearable neurological monitoring platform designed to continuously track Parkinsonian motor symptoms using wrist-worn sensing and advanced signal analysis.

The project focuses on transforming raw motion data into clinically relevant digital biomarkers capable of supporting:

- Early detection research
- Continuous symptom monitoring
- Disease progression tracking
- Medication response assessment
- Longitudinal neurological analytics

Unlike traditional episodic clinical assessments, ParkinSense emphasizes real-world, continuous monitoring through a lightweight wearable and an analytics-driven software platform.

---

## Vision

Develop a next-generation wearable system capable of quantifying Parkinsonian symptoms outside the clinic through continuous monitoring and digital biomarker extraction.

Long-term goals include:

- Rest tremor detection
- Tremor burden estimation
- Bradykinesia assessment
- Sleep and recovery monitoring
- Autonomic biomarker analysis
- Disease progression modelling

---

## System Architecture

```text
      Wearable Device
             │
             ▼
      Data Acquisition
             │
             ▼
      Signal Processing
             │
             ▼
      Feature Extraction
             │
             ▼
      Digital Biomarkers
             │
             ▼
      Analytics Platform
             │
             ▼
      Clinical Insights
```

---

## Hardware Platform

### Current Platform

- Seeed Studio XIAO nRF52840 Sense
- LSM6DS3 6-Axis IMU
- Bluetooth Low Energy (BLE)
- USB-C Interface
- Li-Ion Battery Support

### Planned Hardware Expansion

- MAX30102 Optical PPG Sensor
- Skin Temperature Sensor
- Extended Battery System
- Custom Wearable PCB
- WHOOP-Style Wearable Enclosure

---

## Digital Biomarkers

### Tremor Biomarkers

- Tremor Frequency
- Tremor Amplitude
- Tremor Energy
- Tremor Burden
- Tremor Stability

### Motor Function Biomarkers

- Bradykinesia Index
- Movement Velocity
- Motion Variability
- Motion Asymmetry
- Activity Classification

### Physiological Biomarkers *(Planned)*

- Heart Rate
- Heart Rate Variability (HRV)
- Recovery Metrics
- Sleep Quality
- Autonomic Nervous System Indicators

### Longitudinal Biomarkers

- Daily Symptom Trends
- Medication Response
- Progression Indicators
- Behavioral Patterns

---

## Signal Processing Pipeline

Current tremor detection architecture:

```text
Raw IMU Data
      │
      ▼
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
Band Energy Analysis
      │
      ▼
Motion Gating
      │
      ▼
Tremor Classification
```

Current detector features:

- Sampling Rate Estimation
- Windowed FFT Analysis
- Dominant Frequency Detection
- Frequency Stability Analysis
- Band Energy Ratio Analysis
- Motion-Based Rejection Logic

---

## Dataset Status

Current dataset collection includes:

- Stationary Baseline
- Normal Daily Motion
- Walking Motion
- Simulated Tremor
- External Vibration Reference

Current dataset size:

```text
7021+ IMU Samples
```

Dataset expansion is ongoing to improve robustness and generalization.

---

## Repository Structure

```text
ParkinSense
│
├── firmware
│   └── xiao_nrf52840
│
├── dashboard
│   └── python
│       ├── analytics
│       └── data
│
├── hardware
│
├── docs
│   ├── Architecture
│   ├── Clinical
│   └── SRS
│
├── research
│
└── README.md
```

---

## Development Roadmap

### Phase 1 — Sensor Acquisition

- [x] IMU Integration
- [x] Real-Time Streaming
- [x] Dataset Recording Framework
- [x] Signal Validation

### Phase 2 — Signal Processing

- [x] FFT Analysis
- [x] Windowed Frequency Analysis
- [x] Tremor Detector V3
- [x] Feature Extraction Pipeline
- [ ] Noise Reduction Pipeline

### Phase 3 — Digital Biomarkers

- [x] Tremor Index Prototype
- [ ] Tremor Burden Estimation
- [ ] Bradykinesia Metrics
- [ ] Motion Classification
- [ ] Symptom Severity Scoring

### Phase 4 — Wearable Platform

- [ ] BLE Streaming
- [ ] Real-Time Detection
- [ ] Battery Optimization
- [ ] Wearable Enclosure
- [ ] Mobile Integration

### Phase 5 — Clinical Validation

- [ ] Expanded Dataset Collection
- [ ] Algorithm Validation
- [ ] Biomarker Evaluation
- [ ] Pilot Testing

### Phase 6 — Predictive Analytics

- [ ] Longitudinal Modelling
- [ ] Progression Estimation
- [ ] Personalized Monitoring
- [ ] AI-Assisted Analytics

---

## Current Status

### Completed

- IMU Acquisition Pipeline
- Real-Time Data Streaming
- Dataset Collection Framework
- FFT Analysis Pipeline
- Window-Based Tremor Analysis
- Tremor Detector V3
- Digital Biomarker Architecture

### In Progress

- Dataset Expansion
- Tremor Burden Analytics
- BLE Streaming Framework
- Real-Time Monitoring Pipeline

### Upcoming

- MAX30102 Integration
- HR & HRV Monitoring
- Sleep Analytics
- Bradykinesia Assessment
- Mobile Dashboard

---

## Research Focus

ParkinSense is being developed as a digital biomarker platform rather than a simple tremor detector.

Research areas currently include:

- Rest Tremor Detection
- Tremor Characterization
- Tremor Burden Estimation
- Digital Biomarker Development
- Wearable Neurological Monitoring
- Continuous Disease Tracking
- Parkinson's Disease Analytics

---

## Disclaimer

ParkinSense is currently a research and educational project.

This platform is **not a certified medical device** and should not be used for diagnosis, treatment, or clinical decision-making.

Any metrics, analyses, or outputs generated by ParkinSense are intended solely for research, educational, and exploratory purposes.

---

<div align="center">

**ParkinSense • Wearable Neurological Monitoring • Digital Biomarkers • Parkinson's Disease Research**

</div>
