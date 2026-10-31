# ParkinSense System Requirements Specification (SRS)

Version: 1.0

Status: Draft

Author: Pranshu Kumar

---

# 1. Project Overview

ParkinSense is a wearable Parkinson’s monitoring platform designed to provide continuous, objective assessment of motor and physiological biomarkers associated with Parkinson’s disease.

The system aims to support:

- Early detection
- Continuous symptom monitoring
- Disease progression tracking
- Digital biomarker development
- Clinical research

---

# 2. Primary Objectives

1. Continuous tremor monitoring
2. Tremor severity quantification
3. Bradykinesia assessment
4. Medication response tracking
5. Sleep quality assessment
6. Activity recognition
7. Longitudinal disease monitoring

---

# 3. Hardware Requirements

## Microcontroller

Seeed Studio XIAO nRF52840 Sense

Requirements:

- BLE support
- Low power operation
- Onboard IMU
- USB-C programming

---

## Sensors

### IMU

LSM6DS3

Measurements:

- Accelerometer
- Gyroscope

Sampling Frequency:

100 Hz minimum

Target:

200 Hz

---

### Optical Sensor

MAX86141

Measurements:

- Heart Rate
- HRV
- SpO₂

---

### Temperature Sensor

TMP117

Measurements:

- Skin temperature

---

# 4. Power Requirements

Target Battery Life:

24 hours minimum

Desired Battery Life:

48 hours

Charging:

USB-C

Battery:

300-500 mAh LiPo

---

# 5. Connectivity

Bluetooth Low Energy

Functions:

- Data Synchronization
- Firmware Updates
- Device Configuration

---

# 6. Digital Biomarkers

## Tremor Frequency

Target Range:

3-12 Hz

---

## Tremor Amplitude

Peak and RMS estimation

---

## Tremor Burden

Minutes spent in tremor per day

---

## Bradykinesia Index

Movement speed estimation

---

## Sleep Score

Sleep duration
Sleep quality
Movement during sleep

---

## Medication Response Score

Tremor reduction after medication intake

---

# 7. Dashboard Requirements

Patient Dashboard

- Daily summary
- Sleep metrics
- Tremor burden
- Recovery score

Clinical Dashboard

- Progression tracking
- Historical trends
- Biomarker visualization

Research Dashboard

- Raw data export
- CSV download
- Feature analysis

---

# 8. Validation Plan

Stage 1

Healthy subjects

Stage 2

Simulated tremor testing

Stage 3

Parkinson’s patient pilot testing

Stage 4

Clinical validation study

---

# 9. Future Scope

- Machine Learning
- Parkinson Risk Score
- Disease Progression Prediction
- Edge AI Inference
- Clinical Decision Support
