# ParkinSense

<div align="center">

![Status](https://img.shields.io/badge/Status-Active%20Development-success)
![Platform](https://img.shields.io/badge/Platform-nRF52840-blue)
![Language](https://img.shields.io/badge/Language-C++%20%7C%20Python-orange)
![Stage](https://img.shields.io/badge/Stage-Research-yellow)

### Continuous Neurological Monitoring & Digital Biomarker Platform for Parkinson's Disease

*Building the next generation of wearable neurological monitoring through real-world sensing, signal processing, and digital biomarkers.*

</div>

---

## Overview

ParkinSense is a wearable platform designed for continuous monitoring of Parkinson's disease symptoms using inertial and physiological sensing.

The project aims to provide objective digital biomarkers that support:

- Early detection research
- Symptom tracking
- Disease progression monitoring
- Long-term clinical assessment
- Digital health research

Unlike traditional episodic clinical evaluations, ParkinSense focuses on continuous real-world monitoring through a lightweight wrist-worn device and a connected analytics platform.

---

## Objectives

### Core Monitoring

- Continuous tremor monitoring
- Tremor frequency analysis
- Tremor amplitude analysis
- Tremor burden estimation

### Motor Assessment

- Bradykinesia assessment
- Movement variability analysis
- Motion asymmetry detection
- Activity classification

### Physiological Monitoring

- Sleep tracking
- Recovery monitoring
- Heart-rate monitoring *(planned)*
- Heart-rate variability *(planned)*

### Clinical Analytics

- Medication response monitoring
- Longitudinal symptom progression analysis
- Digital biomarker development
- Research-driven neurological insights

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
 Digital Biomarkers
        │
        ▼
 Analytics Dashboard
        │
        ▼
 Clinical Insights
```

---

## Hardware Platform

### Current Hardware

- Seeed Studio XIAO nRF52840 Sense
- LSM6DS3 6-Axis IMU
- Bluetooth Low Energy (BLE)
- USB-C Interface
- Rechargeable Li-ion Battery

### Planned Expansion

- Optical PPG Sensor
- Skin Temperature Sensor
- Extended Battery System
- Custom Wearable PCB
- WHOOP-Style Form Factor

---

## Digital Biomarkers

### Tremor Metrics

- Tremor Frequency
- Tremor Amplitude
- Tremor Energy
- Tremor Burden

### Motor Function Metrics

- Bradykinesia Index
- Movement Velocity
- Movement Variability
- Motion Asymmetry

### Physiological Metrics

- Heart Rate
- Heart Rate Variability (HRV)
- Sleep Quality
- Recovery Metrics

### Longitudinal Metrics

- Daily Symptom Trends
- Medication Response
- Progression Indicators
- Behavioral Patterns

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
├── data
│   ├── raw
│   └── metadata
│
└── README.md
```

---

## Development Roadmap

### Phase 1 — Sensor Acquisition

- [x] IMU Integration
- [x] Real-Time Streaming
- [x] Data Recording
- [x] Signal Validation

### Phase 2 — Signal Processing

- [x] FFT Analysis
- [x] Frequency-Domain Features
- [ ] Tremor Detection v2
- [ ] Noise Reduction Pipeline

### Phase 3 — Biomarker Development

- [x] Tremor Index Prototype
- [ ] Tremor Burden Estimation
- [ ] Bradykinesia Metrics
- [ ] Motion Classification

### Phase 4 — Wearable Integration

- [ ] BLE Synchronization
- [ ] Mobile Application
- [ ] Battery Optimization
- [ ] Ergonomic Enclosure

### Phase 5 — Clinical Validation

- [ ] Data Collection Studies
- [ ] Algorithm Validation
- [ ] Biomarker Evaluation
- [ ] Pilot Testing

### Phase 6 — Predictive Analytics

- [ ] Longitudinal Modelling
- [ ] Progression Estimation
- [ ] Personalized Monitoring
- [ ] AI-Assisted Analysis

---

## Current Status

### Completed

- IMU acquisition pipeline
- Real-time sensor streaming
- Dataset collection framework
- FFT analysis pipeline
- Tremor Index prototype
- Analytics architecture

### In Progress

- Structured dataset acquisition
- Tremor Detector v2
- Sliding-window analysis
- Frequency stability analysis

### Upcoming

- Tremor burden estimation
- BLE streaming
- Real-time dashboard enhancements
- Bradykinesia analytics

---

## Research Focus

ParkinSense is being developed as a digital biomarker platform that extends beyond simple tremor detection.

Current research areas include:

- Tremor characterization
- Tremor burden estimation
- Rest-state tremor detection
- Bradykinesia assessment
- Longitudinal monitoring
- Wearable neurological sensing
- Continuous disease monitoring

---

## Disclaimer

ParkinSense is currently a research and educational project.

This project is not a certified medical device and should not be used as a substitute for professional medical advice, diagnosis, or treatment.

Any analyses, metrics, or outputs generated by this platform are intended solely for research, educational, and exploratory purposes.

---

<div align="center">

**ParkinSense • Wearable Neurological Monitoring • Digital Biomarkers • Parkinson's Research**

</div>
