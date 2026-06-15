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

## Repository Structure

```text
ParkinSense/

├── firmware/
├── hardware/
├── mobile_app/
├── dashboard/
├── docs/
├── research/
├── data/
└── README.md
```

---

## Development Roadmap

### Phase 1 — Data Acquisition

- Sensor integration
- BLE communication
- Data logging
- Battery optimization

### Phase 2 — Tremor Analytics

- Frequency analysis
- Amplitude estimation
- Spectral analysis
- Tremor event detection

### Phase 3 — Continuous Monitoring

- Daily symptom tracking
- Long-term trend analysis
- Sleep and activity monitoring

### Phase 4 — Digital Biomarkers

- Bradykinesia metrics
- Tremor burden metrics
- Medication response metrics
- Movement asymmetry analysis

### Phase 5 — Clinical Validation

- Data collection studies
- Comparative analysis
- Clinical evaluation

### Phase 6 — Predictive Analytics

- Progression modelling
- Risk scoring
- Personalized monitoring

---

## Current Status

Project planning and system architecture phase.

---

## Disclaimer

ParkinSense is a research and educational project. It is not intended to diagnose, treat, cure, or prevent any disease and should not be used as a substitute for professional medical advice.
