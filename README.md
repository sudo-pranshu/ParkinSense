# ParkinSense

ParkinSense is a wearable platform designed for continuous monitoring of Parkinson’s disease symptoms using inertial and physiological sensing.

The project aims to provide objective digital biomarkers that support early detection, symptom tracking, disease progression monitoring, and long-term clinical assessment.

Unlike traditional episodic clinical evaluations, ParkinSense focuses on continuous real-world monitoring through a lightweight wrist-worn device and a connected analytics platform.

---

## Objectives

- Continuous tremor monitoring
- Tremor frequency and amplitude analysis
- Daily tremor burden estimation
- Bradykinesia assessment
- Sleep and recovery tracking
- Medication response monitoring
- Longitudinal symptom progression analysis
- Development of digital biomarkers for Parkinson’s disease

---

## System Overview

The platform consists of:

### Wearable Device

- Seeed Studio XIAO nRF52840 Sense
- 6-axis IMU sensing
- Bluetooth Low Energy connectivity
- Rechargeable Li-ion battery
- Future support for optical heart-rate sensing and skin temperature monitoring
- Planned Expansion:
* Optical PPG Sensor
* Skin Temperature Sensor
* Extended Battery System
* Custom Wearable PCB

### Signal Processing Layer

- Sensor calibration
- Motion filtering
- FFT-based tremor analysis
- Feature extraction
- Activity classification

### Analytics Platform

- Real-time monitoring dashboard
- Historical symptom trends
- Tremor burden tracking
- Clinical data visualization

### Research Layer

- Digital biomarker development
- Parkinson’s disease progression modelling
- Machine learning assisted symptom analysis

---
##Digital Biomarkers

###Tremor Metrics

* Tremor Frequency
* Tremor Amplitude
* Tremor Energy
* Tremor Burden

###Motor Function Metrics

* Bradykinesia Index
* Movement Velocity
* Movement Variability
* Motion Asymmetry

###Physiological Metrics

* Heart Rate
* Heart Rate Variability
* Sleep Quality
* Recovery Metrics

###Longitudinal Metrics

* Daily Symptom Trends
* Medication Response
* Progression Indicators
* Behavioral Patterns---
## Repository Structure

```text
ParkinSense/

├── firmware/
│   └── xiao_nrf52840/
│
├── dashboard/
│   └── python/
│
├── hardware/
│
├── docs/
│   ├── Architecture/
│   ├── Clinical/
│   └── SRS/
│
├── research/
│
├── data/
│   ├── raw/
│   └── metadata/
│
└── README.md
```

---

## Development Roadmap

Phase 1 — Sensor Acquisition

* IMU integration
* Real-time streaming
* Data recording
* Signal validation

Phase 2 — Signal Processing

* FFT analysis
* Frequency-domain features
* Tremor detection
* Noise reduction

Phase 3 — Biomarker Development

* Tremor Index
* Tremor Burden
* Bradykinesia Metrics
* Motion Classification

Phase 4 — Wearable Integration

* BLE synchronization
* Mobile application
* Battery optimization
* Ergonomic enclosure

Phase 5 — Clinical Validation

* Data collection studies
* Algorithm validation
* Biomarker evaluation

Phase 6 — Predictive Analytics

* Longitudinal modelling
* Progression estimation
* Personalized monitoring

---

## Current Status

Active development.

Current milestone:

* IMU acquisition complete
* Dataset collection framework complete
* FFT analysis complete
* Tremor Index prototype complete

---

## Disclaimer

ParkinSense is currently a research and educational project. It is intended to diagnose/detect, and not treat, cure or prevent any disease and should not be used as a substitute for professional medical advice.
