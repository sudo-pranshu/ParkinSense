# Open-source wearable ecosystem review (Phase 8)

Method: each repository below was **cloned (depth 1) and its LICENSE file and relevant source read in this session**
(2026-11-05), except where the "Checked" column says otherwise. Papers were read from their public text (PMC /
publisher abstracts). Nothing was copied. ParkinSense is MIT-licensed (`LICENSE`).

Reuse classes used in the register: **original** (ours), **adapted** (third-party code modified; needs attribution and a
compatible licence), **reference-only** (read, not reused), **methodology** (published method re-implemented from the
paper). No row is "adapted" today.

## 1. Register

| Project | Repository (verified) | Purpose | Language | Licence (read from LICENSE) | Maintenance (last commit seen) | Evidence | Relevance to ParkinSense | Reuse potential | Compatibility | Decision |
|---|---|---|---|---|---|---|---|---|---|---|
| **Open Wearables** (the-momentum) | <https://github.com/the-momentum/open-wearables> | Self-hosted API and unified schema for consumer-wearable providers (Garmin, Oura, Apple Health, Health Connect, …) | Python (FastAPI, SQLAlchemy, Celery), TypeScript frontend | MIT | 2026-11-05 | Product docs; no peer-reviewed algorithm claims read | Data model (`series_sample`, `event_record`, raw-resolution preservation, per-provider normalisation) is a useful template for Phase 11/12 export and cloud sync | Architecture only | MIT-compatible. Server-side platform: **not** for firmware or the signal-processing runtime | **Reference-only** now; **benchmark** its schema against our capture/metadata in Phase 11 |
| **OWEAR** (Open Wearables Initiative) | <https://www.owear.org/> (index of algorithms and datasets; hosts no code) | Registry plus neutral benchmarking of sensor-derived health measures; first pilots: gait and sleep | n/a | none stated ("uniform licensing agreement" planned) | Page has no dated updates; index described as "coming" — activity not confirmable | Programme description only | Venue to register our sleep/step benchmarks and to find labelled gait/sleep data | Methodology and community | n/a | **Reference-only**; revisit when its index is live; registering our algorithms is a Phase 13 option |
| **OpenEarable v1** | <https://github.com/OpenEarable/open-earable> | Arduino/nRF52840 earable sensing platform firmware 1.4.0 (IMU, pressure, microphone, SD logging, BLE services) | C++ (Arduino) | MIT | **2024-10-18** (≈2 years inactive) | Research platform papers (not read here) | Pattern source for a task manager, battery service, SD logger, BLE configuration service | Architecture patterns | MIT-compatible, but Arduino and different hardware | **Reference-only** |
| **OpenEarable 2** | <https://github.com/OpenEarable/open-earable-2> | nRF5340/Zephyr successor (sensor manager, time sync, battery, SD, FOTA) | C (Zephyr / nRF Connect SDK) | **Mixed:** top-level `LICENSE` is a custom "LicenseRef-PCFT" redistribution text (audio subsystem); sources carry `LicenseRef-Nordic-5-Clause` | 2026-11-05 | Research platform | Time-sync and sensor-manager separation; FOTA layout | Architecture patterns | **Custom licence terms: no code reuse without legal review**; different MCU family | **Reference-only** |
| **InfiniTime** (PineTime) | <https://github.com/InfiniTimeOrg/InfiniTime> | Open watch firmware for nRF52832 on FreeRTOS | C++ | **GPL-3.0** | 2026-11-03 | Widely deployed open firmware | See §3: device-state machine, background heart-rate task, wrist-raise logic, hardware watchdog, DFU | Architecture only | **GPL-3.0 is incompatible with embedding in our MIT firmware**: copying any source would make the combined firmware GPL-3.0. Not copied, not adapted | **Reference-only (architecture inspiration, legal decision documented below)** |
| **Nature tremor algorithm** — Timmermans et al., npj Parkinson's Disease 2025, doi 10.1038/s41531-025-01056-2 | Paper PMC12246068; code <https://github.com/biomarkersParkinson/pdathome_tremor> (MATLAB) and ParaDigMa <https://github.com/biomarkersParkinson/paradigma> (Python ≥ 3.11) | Wrist-gyroscope rest-tremor detector for real life | MATLAB; Python | **Apache-2.0** (both repos) | pdathome_tremor 2025-08-28; ParaDigMa 2026-10-28 | See §2 | Direct competitor to our PSD+HMM detector; ParaDigMa also has gait, arm-swing and PPG-quality models | Methodology and (with attribution + NOTICE) adaptable code | Apache-2.0 → MIT-compatible with NOTICE. Shipped model weights are a pickled classifier (`tremor_detection_clf_package.pkl`): never unpickle untrusted files; trained on Physilog 4 (200 Hz) and Verily Study Watch (100 Hz) | **Benchmark** (Phase 9). Candidate only if evaluated against our baseline on identical inputs |
| **GGIR** | <https://github.com/wadpac/GGIR> | Accelerometer processing: non-wear, sleep (HDCZA), activity | R | Apache-2.0 | 2026-10-28 (DESCRIPTION v3.3-9) | van Hees 2011/2015/2018 | Non-wear detection (`g.weardec.R`, `detect_nonwear_clipping.R`, `filterNonwearNight.R`), sleep-period detection; already the basis of our sleep baseline | Methodology (re-implemented from papers) | Apache-2.0; R runtime not wanted as a dependency | **Benchmark / methodology** (already used in Phase 7; non-wear rule in `sleep/night.py`) |
| **ssl-wearables, asleep, stepcount** (Oxford) | <https://github.com/OxWearables/ssl-wearables> (others literature only) | Self-supervised HAR, sleep, step models | Python | **Academic Use Licence** (University of Oxford) | 2024-10-24 | Peer-reviewed | Strong baselines | none | **Not compatible** (non-commercial academic terms) | **Reject for reuse**; compare only via published numbers |
| **Nordic Power Profiler Kit II (PPK2)** | Nordic documentation (not re-fetched this session) | Current measurement instrument for §3 of the validation plan | — | hardware | — | — | Required for H5/P1–P7 | Measurement only | — | **Adopt as the measurement instrument** (procedure in `docs/hardware/POWER_MEASUREMENT.md`) |

Not verified in this phase (listed so they are not forgotten; **no licence or URL claimed**): bradykinesia, dyskinesia
and freezing-of-gait detection repositories, and any wear-state detection code beyond GGIR. They belong to Phase 9
and need the same clone-and-read treatment. Public **datasets** are tracked separately in
[the dataset register](../datasets/DATASET_REGISTER.md).

## 2. The Nature tremor paper and code — what was verified

| Item | Verified content (from the paper's methods/results text) |
|---|---|
| Sensors / rates | Training: Physilog 4 at 200 Hz (PD@Home). External: Verily Study Watch at 100 Hz (50 Hz in some participants). Down-sampled to 50 or 100 Hz. Wrist, device-sided arm |
| Windows / features | 4 s windows; Welch PSD per axis summed over three axes; peak frequency plus **12 MFCCs** (15 filterbanks, 0–25 Hz). The first five MFCCs contributed most; MFCC outperformed simple PSD features |
| Classifier | Logistic regression, threshold at 95 % specificity; cycling windows oversampled 100× |
| Post rules | Detections kept only with peak frequency 3–7 Hz; windows with 0.5–3 Hz non-tremor arm-movement power removed |
| Validation | PD@Home: leave-one-subject-out, 24 PD + 24 controls (8 PD with tremor): sensitivity 0.61 (SD 0.20), specificity 0.97 (SD 0.05). PPP external (no video labels; 7 160 windows from 179 participants visually inspected): PPV 0.80–0.94, NPV 0.88–0.96, sensitivity 0.37–0.58, specificity 0.98–1.0 |
| Longitudinal | Test-retest ICC first vs second week: tremor time 0.98 (n = 495), median tremor power 0.96 (n = 187) |
| Stated limits | Only 8 PD participants with tremor in training; no video gold standard in PPP; rhythmic non-tremor activities (brushing teeth, stirring) can pass; not validated as a trial endpoint; one wrist only |
| Code / licence | Article states code locations but **no licence**; the licence (Apache-2.0) was read from the two repositories' LICENSE files. Raw PD@Home data: Radboud Data Repository (doi 10.34973/2xxa-g520), access terms not stated on the landing page |

Compatibility with ParkinSense input: our gyro stream is 104 Hz (v1 ±250 dps with wrap risk; v2 ±512 dps), 4 s windows
are already our analysis window, and Welch PSD is already in our pipeline, so a fair identical-input comparison is
feasible. What is **not** known: whether MFCC beats our PSD+HMM detector on the same data. The paper compares MFCC
against *its own* simple PSD features, not against ours. **No candidate has been implemented in Phase 8.**

## 3. Patterns learned from InfiniTime (architecture only; no source reused)

Read from `src/systemtask`, `src/heartratetask`, `src/components/motion`, `src/components/ble`:

| Pattern (verified in source) | Where | Use for ParkinSense |
|---|---|---|
| Explicit device power state enum `Sleeping / Running / GoingToSleep / AODSleeping` | `SystemTask.h` | Our wear/power states should likewise be explicit and separate from sensor states |
| Heart-rate task has its own state `Disabled / Waiting / BackgroundMeasuring / ForegroundMeasuring`, controlled by messages (`GoToSleep, WakeUp, Enable, Disable`) | `HeartRateTask.h` | PPG availability must be a **separate task state**, independent of the IMU (design requirement R2) |
| Hardware watchdog started at boot with a 7 s timeout (`Setup(timeoutSeconds, sleepBehaviour, haltBehaviour)`) | `SystemTask.cpp` | A watchdog is part of REMOVED/RESUMING safety (a hung low-power mode must not lose a night); not implemented here |
| Motion controller derives a wake gesture (`ShouldRaiseWake`) from the accelerometer | `MotionController.h` | Motion can wake a low-power mode; consistent with our re-wear design |
| BLE advertising with undirected connectable mode | `NimbleController.cpp` | Advertising continues in low power (current v5 behaviour) |

Nothing in this table was measured on hardware. InfiniTime's actual current draw is not claimed.

## 4. Licence decisions

1. **InfiniTime (GPL-3.0): no code reuse.** Our firmware is MIT; any copied or derived source would impose GPL-3.0 on the
   firmware distribution. Architecture ideas are not copyrightable expression, so §3 is allowed; the repository was
   cloned for reading only.
2. **OpenEarable 2:** custom/mixed licence text; treated as reference-only until reviewed by someone qualified.
3. **Oxford ssl-wearables / asleep / stepcount:** Academic Use Licence; excluded from reuse (unchanged from Phase 7).
4. **Apache-2.0 sources (ParaDigMa, pdathome_tremor, GGIR):** reuse possible with attribution and the NOTICE text. Phase 8
   copies nothing. Any adaptation in Phase 9 must go to a separate `third_party/` directory with the upstream LICENSE and
   a pinned commit, and be recorded in [LICENCES_AND_ATTRIBUTION](LICENCES_AND_ATTRIBUTION.md).
5. **MIT sources (Open Wearables, OpenEarable v1):** compatible; patterns only.

## 5. What this review changes

* The wear architecture keeps **PPG availability, IMU acquisition and wear state as separate tasks/states**
  (InfiniTime pattern) — [architecture](../architecture/WEAR_AWARE_ACQUISITION.md).
* The motion-only non-wear rule inherited from GGIR / van Hees (all-axes SD < 13 mg for ≥ 60 min) was **measured against
  worn sleeping wrists** and found unsafe as the sole removal evidence
  ([validation](../validation/PHASE_8_VALIDATION_PLAN.md) §2).
* Phase 9 receives a concrete, licence-cleared baseline (ParaDigMa tremor, Apache-2.0) to benchmark against.
