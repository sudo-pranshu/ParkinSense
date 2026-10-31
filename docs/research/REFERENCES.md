# Open-source and literature reference register

Licences were checked on the project pages on 2026-10-31. **No third-party code was copied
into ParkinSense.** Where an idea is used, it is re-implemented in our own code and cited
in the module docstring; attribution below is scholarly, not a licence obligation.

## Software

| Project | URL | Licence | Relevant part | Used how | Fit for our hardware |
|---|---|---|---|---|---|
| **ParaDigMa** (Radboud UMC) | github.com/biomarkersParkinson/paradigma | Apache-2.0 | wrist-gyro tremor pipeline (4 s windows, summed-axis PSD, 3–7 Hz peak, 0.5–3 Hz arm-movement filter, tremor-time and tremor-power aggregates); arm swing; PPG pulse rate | Ideas only: summed-axis PSD, ±0.625 Hz peak power, arm-band movement gating, tremor time / power definitions (`motion/features.py`, `analytics/biomarkers.py`). Their classifier uses MFCCs + logistic regression trained on PD@Home; we have no labelled data to train an equivalent, so we did not adopt it. | Validated at 50–100 Hz gyro; our 104 Hz gyro is compatible. A natural next step is to run ParaDigMa itself on our recordings as an external comparator (Apache-2.0 allows it as a dependency). |
| **NeuroKit2** | github.com/neuropsychology/neurokit | MIT | `ppg_findpeaks` (Elgendi), HRV indices | Not used. Candidate external comparator for beat detection/HRV. | Works at ≥ 25 Hz; needs v2 firmware (10 Hz v1 PPG is too coarse). |
| **HeartPy** | github.com/paulvangentcom/heartrate_analysis_python | **GPL-3.0** | PPG peak detection, HRV | Not used; GPL would impose copyleft on derived code. Comparison only, as a separate tool. | — |
| **gaitmap** (MaD Lab, FAU) | github.com/mad-lab-fau/gaitmap | MIT (core); **AGPL-3.0** (`gaitmap_mad`) | stride segmentation, gait parameters | Not used. Designed for **foot**-mounted IMUs — gait parameters do not transfer to a wrist sensor. | Poor fit. |
| **SciKit Digital Health** (Pfizer) | github.com/pfizer-opensource/SciKit-Digital-Health | MIT | wrist gait bout detection, activity, sleep | Not used. Candidate comparator for activity/sleep once longer recordings exist. | Lumbar/wrist accelerometer, ~50 Hz+; compatible in principle. |
| **GGIR** | CRAN package GGIR | Apache-2.0 | HDCZA sleep detection (van Hees 2018), activity summaries | Not used; documented as the reference for any future sleep work. | Needs multi-day wrist accelerometry; we have none. |
| **walking** (R) — Verisense step counter | CRAN package `walking` | GPL (≥3) package; Verisense functions credited MIT (Shimmer) | wrist step counting with continuity rules | Idea only (continuity/bout rule) in the experimental `step_counter_periodic.py`; no code copied. | Compatible; our variant did not pass the real-walking check. |
| **ppg-beats** (Charlton) | github.com/peterhcharlton/ppg-beats | not stated on the repository page — check `LICENSE.md` before any reuse | MATLAB benchmark of PPG beat detectors | Literature only (benchmark result: MSPTD and qppg best overall). | MATLAB; not integrated. |
| **SciPy** | scipy.org | BSD-3 | `welch`, `butter(output="sos")`, `sosfiltfilt` | Dependency. | — |

Proprietary systems — **PKG** (Global Kinetics), **Kinesia** (Great Lakes NeuroTech), WHOOP,
Oura, Apple Watch, Garmin, Fitbit — do not publish their algorithms. Anything said about them in
this repository is limited to published validation papers or vendor descriptions; nothing is
inferred about their internals.

## Literature (methods actually used)

| Topic | Reference | Where used |
|---|---|---|
| PD tremor band 3.5–7.5 Hz | Deuschl G, Bain P, Brin M. Consensus statement of the Movement Disorder Society on tremor. *Mov Disord* 1998;13(S3):2–23 | `config.TREMOR_BAND_HZ` |
| Real-life wrist tremor detection, tremor time/power | Timmermans NA, Terranova R, et al. A generalizable and open-source algorithm for real-life monitoring of tremor in Parkinson's disease. *npj Parkinson's Disease* 2025 (PMC12246068). Reported LOSO sensitivity 0.61, specificity 0.97. | features, context, biomarkers |
| Physical-unit tremor amplitude | Elble RJ, McNames J. Using portable transducers to measure tremor severity. *Tremor Other Hyperkinet Mov* 2016;6:375 | `tremor_amplitude_dps` |
| Spectral peak interpolation | Jacobsen E, Kootsookos P. Fast, accurate frequency estimators. *IEEE Signal Process Mag* 2007;24(3); Gasior M, Gonzalez JL. CERN-AB-2004-023 | `features._interp_peak` |
| HMM filtering | Rabiner LR. A tutorial on hidden Markov models. *Proc IEEE* 1989;77(2):257–286 | `tremor/temporal.py` |
| Window overlap convention | Banos O et al. Window size impact in human activity recognition. *Sensors* 2014;14(4) | ADR-0001 |
| Motion artefact & HR (TROIKA) | Zhang Z, Pi Z, Liu B. TROIKA. *IEEE Trans Biomed Eng* 2015;62(2) | motion-coupling check (detection, not subtraction) |
| PPG beat detector benchmark | Charlton PH et al. Detecting beats in the photoplethysmogram: benchmarking open-source algorithms. *Physiol Meas* 2022 (open access: openaccess.city.ac.uk/28452) | roadmap (MSPTD/qppg) |
| Elgendi PPG peaks | Elgendi M et al. Systolic peak detection in acceleration photoplethysmograms. *PLoS ONE* 2013, doi 10.1371/journal.pone.0076585 | roadmap |
| Gait regularity by autocorrelation | Moe-Nilssen R, Helbostad JL. Estimation of gait cycle characteristics by trunk accelerometry. *J Biomech* 2004;37(1):121–126 | experimental step counter |
| Wrist step counting | Rowlands AV et al. *J Sports Sci* 2022, doi 10.1080/02640414.2022.2147134 (Verisense step-count validation, as cited by the `walking` package); Brajdic A, Harle R. Walk detection and step counting on unconstrained smartphones. UbiComp 2013 | step counter notes |
| Sleep from wrist accelerometry | van Hees VT et al. Estimating sleep parameters using an accelerometer without sleep diary. *Sci Rep* 2018;8:12975 | feasibility doc only |
| Bradykinesia/dyskinesia (proprietary) | Griffiths RI et al. Automated assessment of bradykinesia and dyskinesia in Parkinson's disease. *J Parkinsons Dis* 2012, doi 10.3233/JPD-2012-11071 | feasibility doc only |

## Public datasets worth obtaining

| Dataset | Access | Why |
|---|---|---|
| PD@Home training data (Radboud Data Repository, doi 10.34973/2xxa-g520) | request | the only open, video-labelled real-life wrist tremor data we found; would allow real sensitivity/specificity for our detector |
| mPower (Sage Bionetworks / Synapse) | governed access | phone-based tapping/gait/tremor tasks; useful for feature ideas, not for wrist validation |
| PPG-DaLiA | public | wrist PPG + accelerometer during daily activities with ECG reference — the right set to validate HR under motion |
| BIDMC, CapnoBase | public | resting PPG beat-detection references |

Bibliographic details marked with a DOI or URL were checked against the source during this work; volume/page numbers given without one should be confirmed before citing in a paper.
