# Public dataset register

Purpose: algorithm development and external benchmarking should use public data wherever possible; ParkinSense
hardware recordings are for hardware verification (sensor behaviour, rate, noise, BLE, wear detection, power,
end-to-end compatibility). **Public data never substitutes for hardware validation.**

How this register was built (2026-11-05): each official landing page (UCI ML Repository, PhysioNet, NSRR, Radboud Data
Repository, arXiv/paper text) was fetched and read. A field not stated on the page is written **"not stated"**, not
guessed. Nothing was downloaded or scraped in Phase 8 except what Phases 7 already fetched
([MANIFEST](../../benchmarks/external/MANIFEST.md)); the build environment's network allow-list reaches GitHub and
PyPI only, so PhysioNet / UCI / NSRR / Radboud downloads from the shell are **not possible here** and access
conditions are recorded rather than exercised. No access control was bypassed.

Status column: **in use** = already used by a committed benchmark; **registered** = verified and available, not yet
ingested; **blocked** = access terms unconfirmed or restricted.

## 1. Register

| Dataset | Official source | Access / licence | Participants | Recordings | Sensors · placement · rate | Labels / reference | Population | Missingness | Known limitations | Intended use | Status |
|---|---|---|---|---|---|---|---|---|---|---|---|
| **PD@Home** (Timmermans) | Radboud Data Repository, doi 10.34973/2xxa-g520 (landing page: "Parkinson@Home – IMU sensor data and video annotations for real-life tremor detection") | Landing page states **neither access conditions nor licence**; the paper says the training data are "publicly available" there. **Must be confirmed before download** | 25 PD (motor fluctuations) + 24 controls on the landing page (paper analyses 24 + 24 after exclusions) | PD recorded twice (off medication, then 1 h after dose); ≥ 1 h unscripted at home per session | Wrist IMU (accel + gyro), **both wrists**, **200 Hz** | Manual video annotation of tremor; clinical data | PD with motor fluctuations; age-matched controls | not stated | Only 8 PD with tremor (paper); video labels cover short sessions; not our device | Tremor baseline benchmark (Phase 9), the dataset behind the Nature paper's LOSO results | **blocked** until access/licence confirmed |
| **PPP — Personalized Parkinson Project** | <https://www.personalizedparkinsonproject.com/home/data/requesting> (per paper) | On reasonable request (paper) | 517 PD + 50 controls (paper's external set) | up to 2 y wear; first 3 wk used by paper | Verily Study Watch, wrist, 100 Hz (50 Hz early) | no video labels | PD | not stated | Request-gated; labels are visual inspection of windows | External tremor validation, longitudinal tremor burden | **blocked** (request needed; a Phase 13 collaboration item) |
| **Daphnet Freezing of Gait** | UCI, doi 10.24432/C56K78 | CC BY 4.0, open | page names S01–S10 but states no count | 237 instances / 29 files (page) | 3 accelerometers: ankle (shank), upper leg (thigh), trunk; rate not stated on page | 0 = not part of experiment, 1 = no freeze, 2 = freeze | PD with freezing of gait | page: no missing values | Rate and subject count must be read from the readme; no gyro | FoG baseline (Phase 9) | registered |
| **Sleep-EDF Expanded** | PhysioNet, doi 10.13026/C2X676, v1.0.0 | Open (ODC-By 1.0) | SC study healthy adults 25–101; ST study 22 with mild insomnia symptoms (subject count of SC not stated on page) | 197 whole-night PSG (153 SC + 44 ST) | EEG Fpz-Cz, Pz-Oz and EOG 100 Hz; chin-EMG envelope, event marker 1 Hz; some respiration and rectal temperature 1 Hz. **No accelerometer on the page** | Hypnogram (R&K 1968: W, R, 1–4, M, ?) | Healthy adults; mild insomnia | not stated | **No wrist motion**, so useless for actigraphy sleep/wake; R&K not AASM | Sleep-stage research only; not for the accelerometer sleep estimator | registered, **not applicable to our sleep estimator** |
| **MESA Sleep** | NSRR <https://sleepdata.org/datasets/mesa> | Page says PSG and actigraphy raw data "can be downloaded directly"; **no DUA/request process described on the page**; acknowledgement of NHLBI/NSRR grants required. Confirm on NSRR before use | 2 237 in the MESA Sleep Exam (2010–2012) of 6 814 MESA participants | not stated | Wrist actigraphy (device not named on the page) + PSG | PSG scoring; epoch length not stated | Multi-ethnic adults 45–84 at baseline | not stated | Not reachable from this environment; actigraphy summary format (not raw 50 Hz) to be checked | The external sleep test set Walch et al. used; would give a second, much larger sleep benchmark | **blocked** (terms and format unconfirmed; allow-list) |
| **Walch / sleep-accel** | PhysioNet, doi 10.13026/hmhs-py35 | ODC-By 1.0 | 31 listed; 18 acceleration files available; **15 usable at ≥ 20 Hz and ≥ 3 h** for the wear benchmark; 17 for sleep scoring | 1 PSG night each | Apple Watch wrist accel, ~50 Hz irregular (two subjects ~10 Hz); PPG heart rate ~5 s | PSG AASM 30 s epochs, single scorer | Healthy adults | one subject < 50 % coverage; two at 10 Hz; one < 3 h | Healthy, one night, one scorer; 90.5 % sleep epochs | Sleep/wake benchmark; worn-sleep stillness distribution (wear) | **in use** |
| **Clemson pedometer** | Mattfeld et al., IEEE BIBM 2017, doi 10.1109/BIBM.2017.8217769 | Upstream project terms; a third-party min-max-normalised copy was used | 30 | 90 (3 gait conditions) | Wrist Shimmer3, 15 Hz | Annotated foot contacts | Healthy | not stated | 15 Hz; channels re-calibrated by us (unquantified error) | Step-count benchmark | **in use** |
| **Karas walk-climb-drive** | PhysioNet, doi 10.13026/51h0-a262 | ODbL 1.0 | 27 of 32 available | one per subject | Left-wrist ActiGraph 100 Hz (ankle/hip exist, unused) | Per-sample activity (walk, stairs, driving, clapping); no step events | Healthy | not stated | No step annotations | False steps, walking state; seated driving as a still-wrist worn condition (wear benchmark C) | **in use** |
| **CAPTURE-24** | Oxford University Research Archive, doi 10.5287/bodleian:NGx0JOMP5 (per arXiv:2402.19229) | CC BY 4.0 (per paper) | 151 retained (166 recruited) | ≈ 24 h each; 3 883 h total, 2 562 h annotated | Axivity AX3 dominant wrist, ±8 g, 100 Hz | Wearable-camera annotation of 206 CPA codes; sleep from diaries | Oxfordshire adults | camera images obstructed/blurred at times | Convenience sample; labels at ~0.03 Hz; **no non-wear label mentioned** in the text read | Free-living HAR and sleep benchmark; large worn-day stillness distribution (wear threshold calibration) | registered (download not possible from this environment) |
| **PAMAP2** | UCI, doi 10.24432/C5NW2H | CC BY 4.0 | 9 | 3 850 505 instances | 3 IMUs at 100 Hz (dominant wrist, chest, dominant ankle); heart rate ~9 Hz | 18 activities (+ transient) | Healthy adults | **Yes, NaN marks missing** | Small cohort | HAR and activity-intensity benchmarks | registered |
| **WISDM** (smartphone + smartwatch) | UCI, doi 10.24432/C5HK59 | CC BY 4.0 | 51 | 15 630 426 instances | Phone and watch accel + gyro, **20 Hz**; placement not stated on the page | 18 activities × 3 min | Healthy | none per page | Low rate; placement unstated | HAR sanity checks only | registered |
| **OPPORTUNITY** | UCI, doi 10.24432/C5M027 | CC BY 4.0 | 4 | 6 runs each (5 ADL + 1 drill) | 7 IMUs, 12 accelerometers, 4 UWB tags on body; object and ambient sensors; rate not stated on page | Locomotion, 13 hand actions, 17 gestures, 5 activity classes | Healthy | **Yes** | 4 subjects; kitchen scenario | Gesture/locomotion research; low priority | registered |
| **PPG-DaLiA** | UCI, doi 10.24432/C53890 | CC BY 4.0 | 15 | recording length not stated on page | Wrist Empatica E4: BVP 64 Hz, EDA 4 Hz, temperature 4 Hz, accel 32 Hz; chest RespiBAN: ECG, respiration, accel at 700 Hz | ECG-derived heart-rate ground truth | Healthy | none per page | Fingertip-vs-wrist PPG is the main difference from our finger sensor | PPG motion-artefact and HR-estimation benchmark (Phase 9); E4 skin temperature and accel give a **wear-adjacent signal** | registered |
| **WESAD** | UCI, doi 10.24432/C57K5T | **Licence not stated on the UCI page** ("see linked dataset"); acknowledgement policy applies | 15 | not stated | E4 wrist (BVP 64 Hz, EDA, temp 4 Hz, ACC 32 Hz); RespiBAN chest (ECG, EDA, EMG, resp, temp, ACC 700 Hz) | Neutral / stress / amusement + questionnaires | Healthy (lab) | none per page | Stress, not motion; licence unconfirmed | ECG-referenced HR/HRV under mild motion | **blocked** until licence confirmed |
| PD accelerometer dataset, *Scientific Data* 2021 ("Accelerometer data collected with a minimum set of wearable sensors from subjects with Parkinson's disease") | Found by search; the article page was not readable in this session | **Not verified** | not verified | not verified | not verified | not verified | PD | not verified | Entire row unverified | Candidate for bradykinesia/medication-state work | **blocked** (verify in Phase 9) |

## 2. Gaps (stated plainly)

* **Wear-state detection:** no public dataset with *non-wear ground truth on a wrist IMU* was found. The web search surfaced
  CAPTURE-24 and papers but nothing with labelled non-wear intervals. Consequence: removal **sensitivity cannot be
  measured on public data**. Public data bounds the *false-removal* side only (worn sleeping/driving wrists). Removal and
  re-wear must be recorded on ParkinSense hardware (plan tests W1–W6).
* **Bradykinesia / dyskinesia:** no verified open dataset yet (see the unverified row). Phase 9 task.
* **ECG reference with our PPG geometry:** none; PPG-DaLiA and WESAD use wrist green/PPG, not a finger MAX30102.
* **Raw acceleration at 104 Hz from a PD wrist:** only PD@Home (200 Hz) qualifies, and its access is unconfirmed.

## 3. Ingestion and harmonisation (planned, Phase 9; not built in Phase 8)

Existing loaders: `parkinsense/datasets/reference.py` (Walch, Clemson, Karas) return a `ReferenceRecording` that
preserves provenance and source file names, never mutates the downloaded files, and records resampling in the
benchmark JSON (`resampled_to_hz`, `gate`). Rules adopted for every future loader:

1. Original files are read-only; derived arrays are written elsewhere with a manifest (source path + SHA-256).
2. Resampled data is labelled as resampled and is never described as native 104 Hz. Clemson (15 Hz → 104 Hz) is the
   standing example of what this cannot test.
3. Participant identifiers are kept so `datasets.splits` can assert leakage-free splits.
4. Axis convention, units (g, deg/s) and sampling-rate metadata are stored per recording; missing data is NaN, never 0.
5. Every preprocessing step is listed in the benchmark's `provenance`.

The unified framework (common schema, label maps, quality flags) will be designed in Phase 9 with the first tremor
baseline, when two real loaders (PD@Home, Daphnet) exist to generalise from. Building it now from one family of
datasets would risk the wrong abstraction.
