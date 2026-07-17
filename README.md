<div align="center">

# 🧠 ParkinSense

![Status](https://img.shields.io/badge/Status-Active%20Development-success)
![Platform](https://img.shields.io/badge/Platform-XIAO%20nRF52840%20Sense-blue)
![Sensors](https://img.shields.io/badge/Sensors-LSM6DS3%20IMU%20%2B%20MAX30102-red)
![BLE](https://img.shields.io/badge/BLE-104Hz%20Streaming-success)
![Pipeline](https://img.shields.io/badge/Pipeline-V2.5-brightgreen)
![PPG](https://img.shields.io/badge/PPG-HR%20%7C%20HRV%20%7C%20SpO₂-blueviolet)
![Activity](https://img.shields.io/badge/Activity-Steps%20%7C%20Cadence%20%7C%20Distance-yellow)
![Dashboard](https://img.shields.io/badge/Dashboard-Live%20Plotly-orange)
![Android](https://img.shields.io/badge/Android-Companion%20App-3DDC84)
![Firmware](https://img.shields.io/badge/Firmware-v3%20Dev%20%7C%20v4%20Power--Optimized-lightgrey)

### Continuous Neurological Monitoring & Digital Biomarker Platform

*A wearable sensing platform for continuous Parkinson's disease monitoring using inertial sensing, physiological sensing, activity tracking, and real-time analytics.*

</div>

<br>

## 📑 Table of Contents

- [Overview](#-overview)
- [Why ParkinSense?](#-why-parkinsense)
- [Why Another Parkinson's Wearable?](#-why-another-parkinsons-wearable)
- [Core Features](#-core-features)
- [Development Branches](#-development-branches)
- [System Architecture](#-system-architecture)
- [Design Principles](#-design-principles)
- [Hardware Platform](#-hardware-platform)
- [Firmware](#-firmware)
- [Battery Optimization](#-battery-optimization)
- [BLE Protocol](#-ble-protocol)
- [Signal Processing Pipeline](#-signal-processing-pipeline)
- [Physiological Monitoring](#-physiological-monitoring)
- [Activity Monitoring](#-activity-monitoring)
- [Digital Biomarkers](#-digital-biomarkers)
- [Dashboard](#-dashboard)
- [Android Companion Application](#-android-companion-application)
- [Repository Structure](#-repository-structure)
- [Wearable Platform](#-wearable-platform)
- [App Screenshots](#-app-screenshots)
- [Getting Started](#-getting-started)
- [Performance](#-performance)
- [Development Roadmap](#%EF%B8%8F-development-roadmap)
- [Research Focus](#-research-focus)
- [Future Wearable Features](#-future-wearable-features)
- [Citation](#-citation)
- [Disclaimer](#%EF%B8%8F-disclaimer)

<br>

## 🔭 Overview

ParkinSense is an open-source wearable research platform designed for **continuous neurological monitoring** of Parkinson's disease using wrist-worn sensors.

Instead of relying solely on periodic clinical assessments, ParkinSense continuously measures motion and physiological signals throughout everyday activities. The platform combines inertial sensing, optical sensing, digital signal processing, and real-time inference to generate quantitative neurological, physiological, and activity biomarkers.

The project now runs **three parallel processing pipelines** from the same sensor stream:

- **Motion Processing Pipeline** — tremor detection and neurological biomarkers
- **PPG Processing Pipeline** — heart rate, RR intervals, HRV, and SpO₂ estimation
- **Step Tracking Pipeline** — step count, cadence, distance, and active-minute tracking

The PPG pipeline currently provides heart rate, RR intervals, heart rate variability (RMSSD, SDNN, Mean RR, pNN50), a SpO₂ estimate, signal quality scoring, finger detection, and sensor status classification. These are research-grade estimates intended for signal-processing development and are **not** medical-grade or clinically validated measurements.

The step tracking pipeline is a from-scratch accelerometer-based pedestrian step detector — not a repackaged third-party library — built around an adaptive threshold, motion-state gating (so tremor or handling can't be miscounted as steps), and bout-based active-minute accounting.

<br>

## 🤔 Why ParkinSense?

ParkinSense was built to explore how modern wearable architectures can be applied to continuous neurological monitoring. Rather than focusing on a single algorithm or an isolated dataset, it integrates embedded firmware, Bluetooth Low Energy streaming, real-time signal processing, physiological sensing, activity tracking, digital biomarker extraction, live visualization, and offline dataset generation into one modular platform. The architecture is designed to support future machine-learning models, longitudinal monitoring, and additional wearable health features, while remaining suitable for reproducible research.

<br>

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
| 👣 | Step counting & cadence estimation |
| 📏 | Distance estimation |
| ⏱ | Active minute tracking |
| 🚶 | Walking detection |
| 📊 | Digital biomarker extraction |

<br>

## 🌐 Why Another Parkinson's Wearable?

Most wearable projects targeting Parkinson's disease tremor stop at a single sensing channel — typically inertial tremor quantification, often processed offline once the recording session has ended. ParkinSense takes a different approach: rather than isolating one channel, it integrates motion sensing, PPG (cardiac) sensing, activity tracking, BLE streaming, a live dashboard, a native Android companion app, a Python reference runtime, dataset generation, and ongoing research into one platform.

Concretely, this means:

- **Motion + Cardiac + Activity** biomarkers come from a single synchronized sensor stream, not three separate tools bolted together
- **Real-time, on-device processing** across all three pipelines, rather than an offline post-processing step
- **Cross-pipeline gating** — the same motion-context classification that flags tremor is reused to gate the step counter (rejecting tremor/handling artifacts) and to discount PPG confidence during movement, instead of each channel re-deriving its own notion of "is the body moving"
- **Two access paths** — a Python reference stack for research and algorithm development, and a native Android app for standalone, Python-free deployment
- **A documented, replicable architecture** — filter orders, window lengths, state-machine transitions, and confidence heuristics are described in enough detail to be reproduced or extended

This is an architectural comparison — an integrated, multi-modal platform versus a single-channel tool — not a performance claim. ParkinSense has not yet undergone the kind of clinical validation that some single-modality tremor wearables have already completed, and every metric it reports is explicitly labeled research-grade pending that validation (see [Disclaimer](#%EF%B8%8F-disclaimer)).

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

### Activity Monitoring
- Real-time step counting from accelerometer magnitude
- High-pass filtering to remove gravity / slow drift
- Adaptive, self-tuning detection threshold (rolling mean + k·σ)
- Hysteresis-based peak detection (no double-counting per step)
- Refractory period gating implausibly fast "steps"
- Motion-state gated detection (tremor/handling can't register as steps)
- Multi-step walking confirmation before declaring "walking"
- EMA-smoothed cadence (steps/min and step-rate in Hz)
- Distance estimation from configurable step length
- Bout-based active-minute accounting (sustained + cadence-qualified)
- Per-step confidence and walking-regularity confidence heuristics

**Upcoming:**
- Activity type classification (walk vs. run vs. climb)
- Floors climbed, calorie estimation, VO₂ max

### Software Platform
- Modular V2 signal-processing pipeline (motion + PPG + activity)
- Unified runtime combining all three pipelines
- Live Plotly Dash dashboard with physiological and activity panels
- Native Android companion app with its own live dashboard, recording, replay, and export
- Two power-optimized firmware variants (v3 development / v4 power-optimized)
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
Adds physiological sensing and activity tracking to the wearable platform. This work landed directly on `develop` rather than a separate feature branch.

**Completed:**
- MAX30102 integration
- Binary packet upgrade
- IR / RED streaming
- Finger detection with ON/OFF hysteresis
- Signal Quality Index + sensor status classification
- PPG Processing Pipeline (`PPGProcessor`, `ppg/ppg_processor.py` + `ppg/algorithms.py`)
- Heart rate estimation (adaptive peak detection, RR extraction, EMA smoothing)
- Heart rate variability (RMSSD, SDNN, Mean RR, pNN50)
- SpO₂ estimation with signal-lock state machine
- Motion-aware HR confidence fusion
- Step Tracking Pipeline (`StepCounter`)
- Cadence estimation, distance estimation, walking detection
- Bout-based active-minute accounting
- Unified runtime merging motion + PPG + activity pipelines
- Updated dashboard with live physiological and activity panels
- v4 power-optimized firmware (deep sleep, automatic wake, BLE scheduling optimization)
- Native Android companion application (BLE, processing, dashboard, recording, replay, export)

**Upcoming:**
- Recovery metrics
- Sleep analytics
- Activity type classification

### Platform Components at a Glance

| Component | Used For |
|---|---|
| `main` | Stable, validated V2 neurological monitoring platform |
| `develop` | Active development branch — physiological + activity sensing, current work |
| **v3 Firmware** | General development — maximum debugging, serial logging, algorithm tuning, feature implementation |
| **v4 Firmware** | Power-optimized firmware for continuous wearable deployment — builds on v3, adds deep sleep and BLE scheduling optimization |
| **Python Runtime** | Reference signal-processing stack — algorithm development, dataset generation, Plotly dashboard |
| **Android App** | Native mobile companion — BLE, on-device processing, dashboard, session recording, replay, export |

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
     ┌─────────────────────┼─────────────────────┐
     │                     │                     │
     ▼                     ▼                     ▼
 Motion Pipeline      PPG Pipeline       Step Counter Pipeline
     │                     │                     │
 Gravity · Notch ·    Finger Detection ·   High-pass · Adaptive
 Bandpass             SQI                  Threshold
     │                     │                     │
 Feature Extraction   Bandpass · Peak     Peak Detection ·
                       Detection           Hysteresis
     │                     │                     │
 Tremor Detection     RR Intervals ·      Cadence · Distance ·
                       HR · HRV            Active Minutes
     │                     │                     │
 Confidence ·          SpO₂ · Motion-      Step / Walking
 Temporal Validation   aware Confidence    Confidence
     │                     │                     │
 Tremor State          EMA Stabilization   Walking Confirmation
 Machine
     │                     │                     │
     └─────────────────────┴─────────────────────┘
                           ▼
                  Digital Biomarkers
                           │
              ┌─────────────┴─────────────┐
              ▼                           ▼
       CSV / JSON Logging          Plotly Dash Dashboard
                                    Android App Dashboard
```

<br>

## 🧭 Design Principles

- Modular processing pipelines, each independently testable
- Single responsibility per module
- Runtime independent from the dashboard
- Continuous streaming architecture
- Research-first implementation
- Extensible sensor-fusion framework
- Backward-compatible, versioned BLE protocol

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
| Step Detector Adaptive Window | ~2 seconds |
| Runtime | Continuous |

### Processing Rates

| Pipeline | Rate |
|----------|------|
| Motion | 104 Hz |
| PPG | ~50 Hz |
| Step Tracking | 104 Hz (shares the accelerometer stream with Motion) |
| Dashboard Refresh | 10 Hz (100 ms interval) |
| CSV Logger | Continuous |

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

Firmware now ships in two variants — **v3** for development and **v4** for power-optimized wearable deployment — sharing the same core sensing and packet-generation logic. See [Battery Optimization](#-battery-optimization) below for details.

**Location:** `firmware/xiao_nrf52840/`

<br>

## 🔋 Battery Optimization

ParkinSense ships two firmware variants built on the same core sensing and BLE stack, differing in how aggressively they manage power.

### Firmware Variants

| | v3 Firmware | v4 Firmware |
|---|---|---|
| Purpose | General development | Power-optimized wearable deployment |
| Debugging | Maximum — serial logging, verbose output | Debug-gated, minimal overhead |
| Recommended for | Development, debugging, algorithm testing, feature implementation | Continuous, all-day wearable operation |
| Power behavior | Not power-optimized | Deep sleep, optimized BLE scheduling, reduced processing overhead |

**v3 Firmware** is the general-purpose development build. It prioritizes visibility over efficiency — maximum debugging, serial logging, and easier iteration — making it the right choice while implementing features, tuning algorithms, or validating new pipeline changes.

**v4 Firmware** builds directly on v3 and adds the power-optimization layer required for actual wearable deployment: reduced MCU wake time, optimized BLE scheduling, reduced unnecessary processing, optimized sensor handling, and improved runtime efficiency. It is the firmware built specifically for continuous wearable operation.

| Mode | Firmware |
|------|----------|
| Development | v3 |
| Production wearable | v4 |

### Power Optimization Features

**Deep Sleep**
When the MAX30102 detects loss of skin contact, the firmware automatically stops continuous sensing, stops unnecessary processing, and enters an ultra-low-power sleep state. Current draw drops into the microamp range.

**Automatic Wake-up**
When skin contact returns, the device wakes automatically, restarts the sensors, resumes BLE, and resumes streaming — no button required.

**Sensor-aware Power Management**
The PPG pipeline already determines whether a finger is present. Rather than let this information go unused, the firmware uses it directly to control the wearable's power state, so power is only spent actively sensing while the device is actually being worn.

**BLE Optimization**
Optimized packet scheduling reduces unnecessary radio activity while still supporting continuous streaming without sacrificing battery life.

### Measured Power

Power was measured on the assembled wearable prototype using a **Nordic Power Profiler Kit II** — measured, not estimated from component datasheets.

| State | Current |
|-------|---------|
| Active Streaming (sensing + BLE) | ~7 mA |
| Deep Sleep | Microamp range |

**Battery:** 3.7 V, 700 mAh Li-ion
**Estimated runtime:** ~100 hours continuous, based on the measured ~7 mA active current.

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

> The versioned packet format allows future additions while maintaining backward compatibility between firmware and runtime. Both the PPG pipeline and the step counter run off the same decoded accelerometer stream — no additional wire format changes were required to add step tracking. The same protocol is decoded natively by both the Python runtime and the Android app.

<br>

## 🔬 Signal Processing Pipeline

ParkinSense runs **three parallel processing pipelines** from the same BLE packet stream — a motion pipeline for tremor biomarkers, a PPG pipeline for cardiac biomarkers, and a step-tracking pipeline for activity biomarkers. Each stage has a single responsibility, so algorithms can be validated, replaced, or extended without affecting the rest of the system.

```
Raw BLE Packet
      │
      ▼
Packet Decoder
      │
      ▼
Rolling Buffer
      │
      ├───────────── IMU ─────────────┬──────────────┐
      │                                │              │
      ▼                                ▼              ▼
 Motion Pipeline                  PPG Pipeline   Step Counter Pipeline
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
A beat-by-beat ratio-of-ratios estimate (with RED/IR peak alignment validation, calibration mapping, and a SEARCHING → LOCKED → TRACKING → LOST signal-lock state machine) produces a rate-limited, confidence-weighted SpO₂ estimate, published on a throttled cadence. This is a research-grade estimate, not a clinically validated pulse-oximetry reading.

**Motion-aware Confidence**
Overall HR confidence is discounted according to the Motion Pipeline's reported activity state, so a walking or running window is trusted less than a resting one without being discarded outright.

**Physiological Biomarkers**
Heart rate, RR intervals, HRV metrics, SpO₂ estimate, sensor status, and confidence/quality sub-scores are emitted for logging and the dashboard.

<br>

### 👣 Step Tracking Pipeline

**Raw Accelerometer**
The step counter runs off the same 104 Hz accelerometer stream as the motion pipeline, so no additional sensor acquisition is required.

**Acceleration Magnitude**
Each sample's three axes are combined into a single magnitude (`√(ax²+ay²+az²)`), collapsing orientation-dependent motion into one scalar signal.

**High-Pass Filtering**
A first-order high-pass filter (α = 0.95) removes gravity and slow postural drift from the magnitude signal, leaving only its oscillatory component — the part that actually reflects footstrike impacts.

**Adaptive Threshold**
A rolling ~2-second buffer of the filtered magnitude feeds a self-tuning threshold: `mean + k·σ` (k = 0.7), clamped between a floor and ceiling. This lets the same detector work for a brisk walk or a gentle stroll without hand-tuned constants per user.

**Peak Detection & Hysteresis**
Only the signed, positive-going excursion of the filtered signal triggers a step — using the absolute value would double-count each oscillation. Once triggered, the detector re-arms only after the signal drops well below the threshold (a hysteresis band), so a single step can't be counted twice as it decays.

**Refractory Period**
A minimum inter-step interval, derived from a configurable maximum cadence (200 steps/min by default), rejects any "step" arriving faster than a human could physically step — filtering high-frequency noise or bounce.

**Motion-State Gating**
Steps are only registered while the Motion Pipeline's context classifier reports genuine body movement (`active` / `walking` / `moving`). This is what prevents hand tremor, in-pocket fidgeting, or device handling from being miscounted as steps — the Motion Pipeline has already solved "is the body moving," so the step counter doesn't re-solve it.

**Walking Confirmation**
"Walking" only flips `True` after 3 consecutive steps land at a gait-consistent interval, so a single stray movement isn't reported as the start of a walk. It clears quickly via a walking-timeout once steps stop arriving.

**Cadence Estimation**
Instantaneous step-to-step intervals are smoothed with an EMA (α = 0.3) to produce a stable steps-per-minute figure, also reported in Hz for gait-analysis contexts that prefer that unit.

**Distance Estimation**
Distance accumulates as `step_count × step_length_m`, where step length is a constructor parameter (not a hardcoded constant) so it can later be calibrated per user — e.g. from height — without touching detection logic.

**Active-Minute Accounting**
Deliberately stricter than "walking": a bout only starts accruing active minutes once it has been sustained continuously for a minimum duration *and* cadence exceeds a minimum threshold. This keeps a short walk to the kitchen from padding activity totals the way a real activity bout would.

**Confidence Heuristics**
Two independent 0–1 heuristics are computed: step confidence, from how far the triggering peak cleared the adaptive threshold (margin ratio); and walking confidence, from the coefficient of variation of recent step intervals — a steady gait produces tightly clustered intervals, an irregular one doesn't.

**Activity Biomarkers**
Step count, cadence (spm and Hz), distance, walking state, active minutes, and both confidence scores are emitted for logging and the dashboard. An `activity_type` field is reserved for future walk/run/climb classification but currently reports only `"walking"` or `None`.

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
        ├─────────────────┬─────────────────────┐
        ▼                 ▼                     ▼
 Motion Pipeline     PPG Pipeline        Step Counter Pipeline
 (Gravity → Notch    (Finger Detection   (High-pass → Adaptive
  → Bandpass →        → SQI → Bandpass    Threshold → Peak
  Motion Context →     → Peak Detection   Detection → Cadence
  Features →           → RR → HR → EMA    → Distance → Active
  Tremor Detection →   → HRV → SpO₂ →     Minutes → Confidence)
  Confidence →          Motion-aware
  Temporal              Confidence)
  Validation →
  State Machine)
        │                 │                     │
        └─────────────────┴─────────────────────┘
                           ▼
             Digital Biomarker Fusion
                           │
        ┌──────────────────┴──────────────────┐
        ▼                                      ▼
 Realtime CSV Logging                  JSON Metrics Export
        │                                      │
        └──────────────────┬───────────────────┘
                            ▼
                 Plotly Dash Dashboard
                    Android App Dashboard
                            │
                            ▼
                Offline Replay & Analysis
```

<br>

## ❤️ Physiological Monitoring

ParkinSense includes an optical sensing subsystem built around the MAX30102, producing cardiac biomarkers alongside the motion pipeline's tremor biomarkers.

**Current functionality:** IR/RED acquisition · finger detection with hysteresis · signal quality estimation · sensor status classification · adaptive peak detection · RR interval extraction · heart rate estimation · EMA stabilization · heart rate variability (RMSSD, SDNN, Mean RR, pNN50) · SpO₂ estimation · motion-aware confidence fusion · BLE transmission · runtime decoding · dashboard visualization (Python and Android)

All of the above are research-grade signal-processing estimates, intended for algorithm development and validation rather than clinical use.

### PPG Fusion Module
The PPG Fusion layer (`PPGProcessor`) acts as the stateful interface between the optical sensor and the analytics pipeline, maintaining rolling buffers, EMA smoothing state, finger-presence hysteresis, and SpO₂ publish throttling across calls.

**Current:** IR validation · RED validation · finger detection · sensor availability · signal quality · heart rate · RR intervals · HRV · SpO₂ estimation · motion-aware confidence fusion

**Future:** Respiratory rate · recovery metrics

<br>

## 👣 Activity Monitoring

The activity subsystem continuously analyzes wrist accelerometer data to estimate daily activity metrics alongside neurological and physiological biomarkers, using the standalone `StepCounter` module.

**Current capabilities:** Step count · cadence (steps/min and Hz) · distance estimate · walking detection · active-minute tracking · step confidence · walking-regularity confidence

The detector is motion-state gated by the Motion Pipeline's classifier, so tremor and incidental device handling are rejected rather than miscounted as steps. `reset()` clears session totals (steps, distance, active minutes) without discarding calibration, so it can be called on BLE reconnect or a future "start workout" action without recreating the object.

**Future:** Activity type classification (walk vs. run vs. climb) · floors climbed · calorie estimation · VO₂ max

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
| Step Count | Cumulative detected steps |
| Cadence | EMA-smoothed steps/min (and Hz) |
| Distance | Estimated distance from step length |
| Walking State | Confirmed walking flag |
| Active Minutes | Sustained, cadence-qualified activity time |
| Step Confidence | Peak-margin heuristic (0–1) |
| Walking Confidence | Step-interval regularity heuristic (0–1) |

*Future:* Recovery Score · Sleep Quality · Bradykinesia Index · Dyskinesia Index · Medication Response · Activity Type Classification · Longitudinal Symptom Burden

<br>

## 📺 Dashboard

The dashboard (`realtime_dashboard_v2.py`) is a dark-themed Plotly Dash app that polls `realtime_metrics_v2.json` and `realtime_capture_v2.csv` on a 100 ms `dcc.Interval` tick and re-renders in place.

**Layout**

Metric cards are grouped into three labeled sections, each rendered as its own row of cards:

- **Parkinson's** — Status, Tremor Score, Frequency, Severity, Burden, Confidence, Motion, Rest Index, Best Axis, Band Ratio
- **Activity** — Steps, Cadence, Distance (converted to km), Walking, Active Minutes
- **Vitals** — Heart Rate, SpO₂, Finger

Cards are simple title/value tiles; boolean- or state-like values (`TREMOR` / `NO TREMOR`, `YES` / `NO`, `WAITING`) are color-coded — green for a clear/positive state, red for a flagged one, grey while waiting for data — so status is readable at a glance without reading the number.

Below the cards sit four live graphs:

- **Live Gyroscope** — GX/GY/GZ traces
- **Tremor Score Gauge** — a 0–100 gauge indicator with green/yellow/orange/red zones
- **Heart Rate & SpO₂** — dual-axis line trend (HR on the primary axis, SpO₂ pinned to an 80–100% secondary axis)
- **Cadence Trend** — a filled area trace of steps/min

The three trend graphs (gyroscope, vitals, cadence) show a rolling **60-second** window, computed from the on-device `sample_timestamp_us` column rather than a fixed row count — so "last 60 seconds" means the same span regardless of the streaming rate, falling back to the last 400 rows if no timestamp column is present.

**Not yet on the dashboard:** the PPG pipeline computes HRV (RMSSD/SDNN/Mean RR/pNN50), Signal Quality (SQI), and Sensor Status, and the firmware streams raw IR/RED — all of this is logged to CSV/JSON today, but none of it has a card or graph in the current Python dashboard build.

**Coming soon:** Recovery · Sleep Analytics · Battery Status · Activity Type · HRV, SQI, Sensor Status, and IR/RED visualization

**Architecture note:** the dashboard is intentionally decoupled from the processing pipelines. All computation happens inside Runtime V2; the dashboard only reads the exported `realtime_metrics_v2.json` and `realtime_capture_v2.csv` files and never imports the pipeline modules directly. This means the motion, PPG, and step-counter pipelines can be tested, replayed, or replaced without touching the UI at all.

<br>

## 📱 Android Companion Application

ParkinSense includes a native Android application that brings the Python runtime experience directly to a mobile device. The Android application is not a simple BLE terminal — it is intended to be, and is being built toward, a complete wearable companion similar to commercial wearable ecosystems.

### Purpose

The app performs, entirely on-device:

- BLE communication
- Real-time decoding
- Signal processing (motion, PPG, and step pipelines)
- Dashboard visualization
- Session recording
- Data storage
- Export
- History
- Session replay

— without requiring Python.

### Core Features

| Feature | Description |
|---|---|
| BLE Device Discovery | Scans for and lists nearby ParkinSense wearables |
| Auto Reconnect | Automatically restores a dropped BLE connection |
| MTU Negotiation | Negotiates BLE MTU for full-rate packet streaming |
| Packet Decoder | Parses the binary BLE packet format natively on-device |
| Real-time Motion Processing | Runs the motion/tremor pipeline live |
| Real-time PPG Processing | Runs the PPG (HR/HRV/SpO₂) pipeline live |
| Step Counter | Runs the step-tracking pipeline live |
| Dashboard | Live cards and charts across neurological, physiological, and activity data |
| Recording Sessions | Captures a full session with metadata |
| Session History | Browsable list of past recordings |
| CSV Export | Export a session as CSV |
| JSON Export | Export a session as JSON |
| Replay | Re-plays a recorded session through the live rendering path |
| Settings | App and device configuration |
| Diagnostics | Developer-facing BLE and pipeline diagnostics |
| Dark Mode | Full dark theme |

### Dashboard

The Android dashboard mirrors the grouping used in the Python dashboard, with live cards and charts organized into sections:

- **Neurological** — tremor state, score, frequency, severity, burden, confidence
- **Physiological** — heart rate, HRV, SpO₂, signal quality, sensor status
- **Activity** — steps, cadence, distance, walking state, active minutes
- **Connection** — BLE status, device name, signal strength
- **Battery** *(coming soon)* — wearable battery level

Live cards update in sync with the underlying pipelines, similar to the card-based layout in the Python dashboard. Live charts render with smooth, continuously updating graphs, keeping motion, PPG, and activity series visually synchronized the same way they are in the Python dashboard.

### Session Recording

Every recording creates a complete session, capturing:

- Start time
- End time
- Duration
- Firmware version
- Device name
- Average heart rate
- Average SpO₂
- Steps
- Cadence
- Distance
- Tremor metrics
- Motion metrics
- Session notes

### Session History

Recorded sessions appear in history. Each session can be:

- Opened
- Reviewed
- Exported
- Deleted
- Shared
- Replayed

### Session Replay

Old recordings can be replayed exactly like live streaming — graphs animate and metrics update in place. Useful for algorithm validation, clinical review, debugging, and education, without needing the wearable connected.

### Export

Sessions can be exported with the following filters:

- Current Session
- Today
- Yesterday
- Last 7 Days
- Last 30 Days
- This Month
- Custom Date
- Custom Date Range
- All Sessions

**Supported formats:** CSV · JSON · ZIP

Exported files include raw data, processed biomarkers, session metadata, and timestamps.

### BLE Architecture

The Android app's internal architecture closely mirrors the Python Runtime V2 architecture:

- BLE Manager
- Packet Decoder
- Pipeline Dispatcher
- Motion Pipeline
- PPG Pipeline
- Step Pipeline
- Database
- Dashboard
- Export Manager

### Reliability Features

- Automatic reconnect
- Notification recovery
- Packet validation
- Duplicate packet rejection
- Buffer management
- Connection monitoring
- Stream recovery
- Background recovery
- Crash protection
- Pipeline isolation

### Diagnostics

A developer diagnostics page surfaces:

- RSSI
- MTU
- Packets/sec
- Samples/sec
- Packet loss
- Decoder rate
- Pipeline status
- Buffer status
- Reconnect count
- BLE state

### Future Features

- Cloud Sync
- OTA Firmware Updates
- Battery Health
- Recovery
- Sleep
- Medication Tracking
- Clinician Portal
- Longitudinal Analytics

<br>

## 📁 Repository Structure

```
ParkinSense
│
├── firmware/
│   └── xiao_nrf52840/
│       └── src/
│           ├── parksense_wearable_v3/   # Development firmware
│           └── parksense_wearable_v4/   # Power-optimized wearable firmware
│
├── Android/
│   └── app/                              # Native Android companion app
│       ├── ble/                          # BLE Manager, discovery, auto-reconnect
│       ├── decoder/                      # Packet Decoder
│       ├── pipeline/                     # Motion / PPG / Step pipelines
│       ├── database/                     # Session storage & history
│       ├── dashboard/                    # Live dashboard UI
│       ├── export/                       # CSV / JSON / ZIP export
│       └── diagnostics/                  # BLE + pipeline diagnostics
│
├── dashboard/
│   └── python/
│       ├── activity/
│       │   └── step_counter.py
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
│       ├── ppg/
│       │   ├── __init__.py
│       │   ├── algorithms.py
│       │   └── ppg_processor.py
│       ├── realtime/
│       ├── replay/
│       ├── runtime/
│       ├── utils/
│       ├── __init__.py
│       ├── config.py
│       ├── live_dashboard.py
│       └── record_imu.py
│
├── docs/
├── hardware/
├── research/
└── README.md
```

**Folder responsibilities**

| Folder | Responsibility |
|---|---|
| `firmware/` | Wearable firmware — v3 (development) and v4 (power-optimized) variants |
| `Android/` | Native Android companion app — BLE, on-device processing, dashboard, recording, replay, export |
| `dashboard/python/activity/` | Step-tracking pipeline (`step_counter.py`) |
| `dashboard/python/ppg/` | PPG pipeline (`ppg_processor.py`, `algorithms.py`) |
| `dashboard/python/pipeline/`, `pipelines/` | Motion pipeline and unified runtime pipeline orchestration |
| `dashboard/python/filters/` | Gravity removal, notch, and band-pass filtering |
| `dashboard/python/detector/`, `detectors/` | Tremor detection and state-machine logic |
| `dashboard/python/features/` | Per-axis feature extraction |
| `dashboard/python/context/` | Motion-context classification (`REST` / `LOW MOTION` / `ACTIVE`) |
| `dashboard/python/fusion/` | Motion-aware confidence fusion |
| `dashboard/python/runtime/` | Runtime V2 — packet decoding and cross-pipeline orchestration |
| `dashboard/python/realtime/` | Realtime CSV/JSON logging |
| `dashboard/python/replay/` | Offline replay framework |
| `dashboard/python/dataset/` | Dataset generation utilities |
| `dashboard/python/calibration/` | Calibration routines |
| `dashboard/python/inference/`, `models/` | Reserved for future ML models |
| `docs/` | Project documentation |
| `hardware/` | Hardware design files |
| `research/` | Research notes and the IEEE paper |

The repository is intentionally modular to support rapid algorithm development while maintaining separation between firmware, mobile, analytics, and future machine-learning components.

<br>

## 📸 Wearable Platform

<div align="center">

| Prototype | Wrist Wear |
|---|---|
| `docs/images/prototype_enclosure.jpg` | `docs/images/wrist_wear.jpg` |

| Dashboard | Android App |
|---|---|
| `docs/images/dashboard_screenshot.jpg` | `docs/images/android_app.jpg` |

| Architecture |
|---|
| `docs/images/architecture_diagram.png` |

</div>

*(Add the corresponding image files under `docs/images/` for these to render on GitHub.)*

<br>

## 📷 App Screenshots

| Screen | Image |
|---|---|
| Connection Screen | `docs/images/app_connection.jpg` |
| Dashboard | `docs/images/app_dashboard.jpg` |
| Session History | `docs/images/app_session_history.jpg` |
| Replay | `docs/images/app_replay.jpg` |
| Export | `docs/images/app_export.jpg` |
| Settings | `docs/images/app_settings.jpg` |
| Diagnostics | `docs/images/app_diagnostics.jpg` |

*(Add the corresponding image files under `docs/images/` for these to render on GitHub.)*

<br>

## 🚀 Getting Started

This guide walks through setting up the complete ParkinSense platform, from flashing the wearable firmware to visualizing live neurological, physiological, and activity biomarkers.

### Requirements

**Hardware**

| Component | Purpose |
|------------|----------|
| Seeed Studio XIAO nRF52840 Sense | Main wearable MCU |
| SparkFun LSM6DS3 | 6-axis IMU |
| MAX30102 | Optical PPG sensor |
| 3.7 V 700 mAh Li-ion Battery (902035) | Portable power supply |
| USB-C Cable | Programming and charging |
| BLE-enabled Computer or Android Device | Runtime and dashboard |

**Software**
- Python 3.11+
- Arduino IDE 2.x
- Git
- Android Studio (for the companion app)

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

Open Arduino IDE and navigate to the development firmware for day-to-day iteration:
```
firmware/xiao_nrf52840/src/parksense_wearable_v3/
```

Or the power-optimized build for actual wearable deployment:
```
firmware/xiao_nrf52840/src/parksense_wearable_v4/
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

### Use the Android App

Build and install the app from `Android/` in Android Studio, then:

1. Open the app and scan for nearby ParkinSense wearables
2. Connect — the app negotiates MTU and starts streaming automatically
3. View live neurological, physiological, and activity data on the dashboard
4. Start a recording to capture a full session
5. Review, export, or replay sessions from Session History

### Complete Workflow

```
Flash Firmware (v3 dev / v4 power-optimized) → Power Wearable → BLE Advertising
       → Runtime V2 (Python) or Android App
       → Packet Decoder → Motion Pipeline + PPG Pipeline + Step Counter Pipeline
       → Digital Biomarkers → CSV/JSON Logging / Session Storage → Dashboard
```

### Sample Runtime Output

```
========== PARKINSENSE V2 ==========

Motion
State          : NO TREMOR
Score          : 14 / 100
Confidence     : 96 %
Frequency      : 5.18 Hz
Severity       : NONE
Motion         : REST
Best Axis      : GY
-------------------------------------

Activity
Steps          : 482
Cadence        : 108.4 spm
Distance       : 361.5 m
Walking        : NO
Active Minutes : 6.2
-------------------------------------

Vitals
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

Raw
IR             : 91243
RED            : 61871

=====================================
```

### Realtime Dataset Logging

Every processed sample is logged to `realtime_capture_v2.csv` for offline replay, validation, and future ML dataset generation. Logged fields include: timestamp, raw accelerometer and gyroscope samples, IR/RED, heart rate, RR intervals, RMSSD, SDNN, Mean RR, pNN50, SpO₂, SQI, sensor status, motion state, tremor score, step count, cadence, distance, walking flag, active minutes, and step/walking confidence.

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
| Steps not incrementing | Confirm Motion Pipeline is reporting `active`/`walking`/`moving`, not `REST` |
| Walking never turns YES | Requires 3 consecutive steps at a consistent gait interval — try a longer, steadier walk |
| Active Minutes stuck at 0 | Bout must sustain past the minimum duration and cadence threshold — brief walks won't qualify |
| Runtime crashes | Confirm Python dependencies are installed |
| BLE disconnects | Restart runtime and reconnect |
| Android app can't find device | Check Bluetooth/Location permissions and confirm firmware is advertising |
| Android app keeps disconnecting | Check the Diagnostics page for RSSI, reconnect count, and BLE state |

<br>

## ⚡ Performance

| Metric | Value |
|----------|---------|
| IMU Sampling | 104 Hz |
| PPG Sampling | ~50 Hz |
| BLE Streaming | ~104 Hz |
| Motion Analysis Window | 4 s |
| PPG Analysis Window | 10 s (rolling) |
| Step Detector Adaptive Window | ~2 s (rolling) |
| SpO₂ Publish Cadence | ~10 s (throttled) |
| Packet Size | 248 Bytes |
| Runtime Latency | <100 ms after analysis window |
| Dashboard Refresh | 100 ms |
| Active Current (v4, measured) | ~7 mA |
| Deep Sleep Current (v4, measured) | Microamp range |
| Estimated Battery Life (v4) | ~100 hours continuous |
| Runtime | Continuous |

The current implementation supports simultaneous IMU and optical streaming, running the motion, PPG, and step-counter pipelines every cycle, while maintaining stable BLE throughput and continuous CSV logging.

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
- [x] SpO₂ Estimation
- [x] Motion-aware HR Confidence

**Phase 4 — Activity Monitoring**
- [x] Step Counter
- [x] Cadence Estimation
- [x] Distance Estimation
- [x] Walking Detection
- [x] Active Minute Accounting
- [ ] Activity Type Classification
- [ ] Floors Climbed
- [ ] Calorie Estimation
- [ ] VO₂ Max

**Phase 5 — Digital Biomarkers**
- [x] Tremor Frequency
- [x] Tremor Score
- [x] Confidence
- [x] Motion Context
- [x] Tremor Burden
- [x] Rest Index
- [x] Heart Rate / HRV / SpO₂ Biomarkers
- [x] Step / Cadence / Distance / Active Minute Biomarkers

**Phase 6 — Wearable Platform**
- [x] Rechargeable Li-ion Operation
- [x] Live Dashboard
- [x] Runtime V2 (Unified Motion + PPG + Activity)
- [x] BLE Packet Versioning
- [x] Realtime CSV Logging
- [x] JSON Metrics Export
- [x] Power Optimization (v4 Firmware)
- [x] Mobile Companion App (Android)
- [ ] Battery Level Monitoring
- [ ] Cloud Sync
- [ ] OTA Firmware Updates

**Phase 7 — Machine Learning**
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
- Human activity recognition
- Biomedical signal processing
- Edge AI for wearables
- Sensor fusion
- Wearable computing
- Embedded systems
- Biomedical AI

<br>

## 🚀 Future Wearable Features

**Health**
- Sleep detection
- Recovery score
- Respiratory rate
- Stress metrics

**Activity**
- Activity type classification (walk / run / climb)
- VO₂ max
- Calorie estimation
- Floors climbed

**Platform**
- Battery-level monitoring
- Cloud synchronization
- OTA firmware updates
- Longitudinal analytics
- Personalized models
- Digital therapeutics
- Clinician portal
- Medication tracking

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

It is **not** a certified medical device and must not be used for diagnosis, treatment, or clinical decision-making. All outputs, including tremor detection, confidence scores, physiological metrics, activity metrics, and digital biomarkers, are intended solely for research and development.

Clinical validation with appropriately labeled datasets is required before any medical application.

---

<div align="center">

### ParkinSense
**Continuous Neurological Monitoring & Digital Biomarker Platform**

Developed by **Pranshu Kumar**

*Wearable Computing • Biomedical Signal Processing • Digital Health • Parkinson's Disease Research*

</div>
