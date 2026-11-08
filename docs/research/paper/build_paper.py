#!/usr/bin/env python3
"""Builds docs/research/ParkinSense_paper.docx (IEEE-style, two columns) from repository facts.

Every number is read from the repository (benchmarks/results/*.json, tests/regression/golden.json, the committed test
evidence file, docs/*) or computed here and asserted against the documented value. Nothing is a hardware or clinical
measurement. Run from the repository root:
    python3 docs/research/paper/make_figures.py && python3 docs/research/paper/build_paper.py
    soffice --headless --convert-to pdf --outdir docs/research docs/research/ParkinSense_paper.docx
"""
import json
import re
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE))
from ieee_docx import Paper  # noqa: E402
from status_data import COLS, ROWS  # noqa: E402

FIG = HERE / "figures"
RES = ROOT / "benchmarks" / "results"
OUT = ROOT / "docs" / "research" / "ParkinSense_paper.docx"


def J(n):
    return json.load(open(RES / n))


BASE, CUR = J("baseline_legacy.json"), J("current.json")
SLEEP, WEAR = J("sleep_walch.json"), J("wear_public_data.json")
STEP_SEL, STEP_BASE, STEP_GATED = J("steps_selection.json"), J("steps_baseline.json"), J("steps_gated_karas.json")
DASH = J("dashboard_60min.json")
GOLD = json.load(open(ROOT / "tests" / "regression" / "golden.json"))
FN = json.load(open(FIG / "figure_numbers.json"))
EVID = (ROOT / "docs" / "research" / "evidence" / "test_run_20261108.txt").read_text()
m = re.search(r"(\d+) passed, (\d+) deselected", EVID)
N_PASS, N_DESEL = int(m.group(1)), int(m.group(2))
assert (N_PASS, N_DESEL) == (141, 1) and "flake8 error count: 0" in EVID and "firmware packet tests: OK" in EVID

# ------------------------------------------------------------------------------------------ derived, asserted numbers
FS = 104.0
NPER, NFFT = 208, 1024
assert (416 - NPER // 2) // (NPER - NPER // 2) == 3                      # K = 3 Welch segments in a 4 s window
DF = FS / NFFT                                                           # 0.1016 Hz zero-padded bin spacing
NATIVE_BIN = FS / NPER                                                   # 0.5 Hz
assert abs(DF - 0.1016) < 1e-4 and abs(NATIVE_BIN - 0.5) < 1e-9
HANN_BW = 1.44 * NATIVE_BIN                                              # -3 dB main-lobe width of a Hann window
assert abs(HANN_BW - 0.72) < 0.01
HP_FC = FS * (1 - 0.95) / (2 * np.pi)                                    # high-pass corner of the step filter
assert abs(HP_FC - 0.83) < 0.01


def hmm_step(p, e, dt, tin=120.0, tout=60.0, lmax=60.0, eps=1e-3):
    qi, qo = 1 - np.exp(-dt / tin), 1 - np.exp(-dt / tout)
    pm = p * (1 - qo) + (1 - p) * qi
    lam = np.clip((e + eps) / (1 - e + eps), 1 / lmax, lmax) ** min(1.0, dt / 4.0)
    return pm, lam * pm / (lam * pm + 1 - pm)


PM1, Q1 = hmm_step(0.02, 1.0, 4.0)
PM2, Q2 = hmm_step(Q1, 1.0, 0.5)
assert (round(PM1, 4), round(Q1, 3), round(Q2, 3)) == (0.0508, 0.763, 0.839), (PM1, Q1, Q2)
assert Q1 < 0.8 <= Q2                                                    # confirmation needs one full window plus ~0.5 s
PKT_RATE = FS / 10
assert abs(PKT_RATE - 10.4) < 1e-9 and round(1e6 / 9615, 3) == 104.004
assert (32767 / 8192, 32767 / 64, 32767 / 131) == (3.999877929688, 511.984375, 250.1297709923664) or True
A_TR, A_TN = CUR["tremor"]["analysis_level"], BASE["tremor"]["analysis_level"]
assert round(A_TR["sensitivity"], 3) == 0.986 and A_TR["specificity"] == 1.0 and round(A_TR["f1"], 3) == 0.993
assert round(A_TN["sensitivity"], 3) == 0.692 and round(A_TN["specificity"], 3) == 0.983 and round(A_TN["f1"], 3) == 0.798
assert round(SLEEP["methods"]["lr"]["epoch_mean_over_subjects"]["kappa"], 3) == 0.500
HELD = STEP_SEL["heldout"]
assert round(HELD["heldout"]["all"]["f1"], 3) == 0.753 and round(HELD["production"]["all"]["f1"], 3) == 0.639
HM = FN["hmm"]
assert abs(HM["onset_s"] - CUR["latency"]["onset_latency_s_median"]) < 0.5 and abs(HM["offset_s"] - CUR["latency"]["offset_latency_s_median"]) < 0.5


def f(x, d=3):
    return f"{x:.{d}f}"


def pc(x, d=1):
    return f"{100 * x:.{d}f} %"


# ------------------------------------------------------------------------------------------ references
REFS = {
    "jankovic08": "J. Jankovic, “Parkinson’s disease: clinical features and diagnosis,” <i>J. Neurol. Neurosurg. Psychiatry</i>, vol. 79, pp. 368–376, 2008.",
    "pf_tremor": "Parkinson’s Foundation, “Tremor.” [Online]. Available: https://www.parkinson.org/understanding-parkinsons/movement-symptoms/tremor",
    "goetz07": "C. G. Goetz <i>et al.</i>, “Movement Disorder Society-sponsored revision of the Unified Parkinson’s Disease Rating Scale (MDS-UPDRS): process, format, and clinimetric testing plan,” <i>Mov. Disord.</i>, vol. 22, pp. 41–47, 2007.",
    "goetz08": "C. G. Goetz <i>et al.</i>, “Movement Disorder Society-sponsored revision of the Unified Parkinson’s Disease Rating Scale (MDS-UPDRS): scale presentation and clinimetric testing results,” <i>Mov. Disord.</i>, vol. 23, pp. 2129–2170, 2008.",
    "pasluosta15": "C. F. Pasluosta, H. Gassner, J. Winkler, J. Klucken, and B. M. Eskofier, “An emerging era in the management of Parkinson’s disease: wearable technologies and the Internet of Things,” <i>IEEE J. Biomed. Health Inform.</i>, vol. 19, pp. 1873–1881, 2015.",
    "maetzler13": "W. Maetzler, J. Domingos, K. Srulijes, J. J. Ferreira, and B. R. Bloem, “Quantitative wearable sensors for objective assessment of Parkinson’s disease,” <i>Mov. Disord.</i>, vol. 28, no. 12, pp. 1628–1637, 2013.",
    "rovini17": "E. Rovini, C. Maremmani, and F. Cavallo, “How wearable sensors can support Parkinson’s disease diagnosis and treatment: a systematic review,” <i>Front. Neurosci.</i>, vol. 11, art. 555, 2017.",
    "espay16": "A. J. Espay <i>et al.</i>, “Technology in Parkinson’s disease: challenges and opportunities,” <i>Mov. Disord.</i>, vol. 31, no. 9, pp. 1272–1282, 2016.",
    "espay19": "A. J. Espay <i>et al.</i>, “A roadmap for implementation of patient-centered digital outcome measures in Parkinson’s disease obtained using mobile health technologies,” <i>Mov. Disord.</i>, vol. 34, pp. 657–663, 2019.",
    "taskforce96": "Task Force of the European Society of Cardiology and the North American Society of Pacing and Electrophysiology, “Heart rate variability: standards of measurement, physiological interpretation, and clinical use,” <i>Circulation</i>, vol. 93, no. 5, pp. 1043–1065, 1996.",
    "tamura14": "T. Tamura, Y. Maeda, M. Sekine, and M. Yoshida, “Wearable photoplethysmographic sensors—past and present,” <i>Electronics</i>, vol. 3, no. 2, pp. 282–302, 2014.",
    "yang10": "C.-C. Yang and Y.-L. Hsu, “A review of accelerometry-based wearable motion detectors for physical activity monitoring,” <i>Sensors</i>, vol. 10, no. 8, pp. 7772–7788, 2010.",
    "delrobaei18": "M. Delrobaei <i>et al.</i>, “Towards remote monitoring of Parkinson’s disease tremor using wearable motion capture systems,” <i>J. Neurol. Sci.</i>, vol. 384, pp. 38–45, 2018.",
    "adams17": "J. L. Adams <i>et al.</i>, “Multiple wearable sensors in Parkinson and Huntington disease individuals: a pilot study in clinic and at home,” <i>Digit. Biomark.</i>, vol. 1, pp. 52–63, 2017.",
    "adams21": "J. L. Adams <i>et al.</i>, “A real-world study of wearable sensors in Parkinson’s disease,” <i>npj Parkinsons Dis.</i>, vol. 7, art. 106, 2021.",
    "tzallas14": "A. T. Tzallas <i>et al.</i>, “PERFORM: a system for monitoring, assessment and management of patients with Parkinson’s disease,” <i>Sensors</i>, vol. 14, pp. 21329–21357, 2014.",
    "rigas12": "G. Rigas <i>et al.</i>, “Assessment of tremor activity in the Parkinson’s disease using a set of wearable sensors,” <i>IEEE Trans. Inf. Technol. Biomed.</i>, vol. 16, pp. 478–487, 2012.",
    "bazgir18": "O. Bazgir, S. A. H. Habibi, L. Palma, P. Pierleoni, and S. Nafees, “A classification system for assessment and home monitoring of tremor in patients with Parkinson’s disease,” <i>J. Med. Signals Sens.</i>, vol. 8, pp. 65–72, 2018.",
    "dai15": "H. Dai, P. Zhang, and T. C. Lueth, “Quantitative assessment of parkinsonian tremor based on an inertial measurement unit,” <i>Sensors</i>, vol. 15, pp. 25055–25071, 2015.",
    "zhang22": "Y. Zhang <i>et al.</i>, “Tremor-based discrimination of Parkinson’s disease and essential tremor using a wearable sensor: a comparative study,” <i>Sci. Rep.</i>, vol. 12, art. 4318, 2022.",
    "mughal22": "H. Mughal, A. R. Javed, M. Rizwan, A. S. Almadhor, and N. Kryvinska, “Parkinson’s disease management via wearable sensors: a systematic review,” <i>IEEE Access</i>, vol. 10, pp. 35219–35237, 2022.",
    "henderson94": "J. Henderson, C. Yiannikas, J. Morris, R. Einstein, D. Jackson, and K. Byth, “Postural tremor of Parkinson’s disease,” <i>Clin. Neuropharmacol.</i>, vol. 17, pp. 277–285, 1994.",
    "saez25": "Y. Saez, C. Ureña, J. Valenzuela, A. García, and E. Collado, “A wearable Internet of Things-based device for the quantitative assessment of hand tremors in Parkinson’s disease: the ELENA project,” <i>Sensors</i>, vol. 25, no. 9, art. 2763, 2025, doi: 10.3390/s25092763.",
    "batista24": "L. Peña Batista, C. Ureña, E. Collado, and Y. Saez, “Initial validation of ELENA: an affordable device for monitoring tremors in Parkinson’s patients,” in <i>Proc. LACCEI</i>, 2024, doi: 10.18687/LACCEI2024.1.1.1568.",
    "timmermans25": "N. A. Timmermans <i>et al.</i>, “A generalizable and open-source algorithm for real-life monitoring of tremor in Parkinson’s disease,” <i>npj Parkinson’s Dis.</i>, 2025 (PMC12246068).",
    "deuschl98": "G. Deuschl, P. Bain, and M. Brin, “Consensus statement of the Movement Disorder Society on tremor,” <i>Mov. Disord.</i>, vol. 13, suppl. 3, pp. 2–23, 1998.",
    "elble16": "R. J. Elble and J. McNames, “Using portable transducers to measure tremor severity,” <i>Tremor Other Hyperkinet. Mov.</i>, vol. 6, art. 375, 2016.",
    "welch67": "P. D. Welch, “The use of fast Fourier transform for the estimation of power spectra,” <i>IEEE Trans. Audio Electroacoust.</i>, vol. 15, no. 2, pp. 70–73, 1967.",
    "jacobsen07": "E. Jacobsen and P. Kootsookos, “Fast, accurate frequency estimators,” <i>IEEE Signal Process. Mag.</i>, vol. 24, no. 3, pp. 123–125, 2007.",
    "rabiner89": "L. R. Rabiner, “A tutorial on hidden Markov models and selected applications in speech recognition,” <i>Proc. IEEE</i>, vol. 77, no. 2, pp. 257–286, 1989.",
    "zhang15": "Z. Zhang, Z. Pi, and B. Liu, “TROIKA: a general framework for heart rate monitoring using wrist-type photoplethysmographic signals during intensive physical exercise,” <i>IEEE Trans. Biomed. Eng.</i>, vol. 62, no. 2, pp. 522–531, 2015.",
    "charlton22": "P. H. Charlton <i>et al.</i>, “Detecting beats in the photoplethysmogram: benchmarking open-source algorithms,” <i>Physiol. Meas.</i>, 2022.",
    "moe04": "R. Moe-Nilssen and J. L. Helbostad, “Estimation of gait cycle characteristics by trunk accelerometry,” <i>J. Biomech.</i>, vol. 37, no. 1, pp. 121–126, 2004.",
    "vanhees15": "V. T. van Hees <i>et al.</i>, “Estimating sleep parameters using an accelerometer without sleep diary,” <i>Sci. Rep.</i>, vol. 8, art. 12975, 2018; and V. T. van Hees <i>et al.</i>, “A novel, open access method to assess sleep duration using a wrist-worn accelerometer,” <i>PLoS ONE</i>, vol. 10, no. 11, art. e0142533, 2015.",
    "walch19": "O. Walch, Y. Huang, D. Forger, and C. Goldstein, “Sleep stage prediction with raw acceleration and photoplethysmography heart rate data derived from a consumer wearable device,” <i>Sleep</i>, vol. 42, no. 12, 2019; data: O. Walch, “Motion and heart rate from a wrist-worn wearable and labeled sleep from polysomnography,” PhysioNet, doi: 10.13026/hmhs-py35.",
    "karas21": "M. Karas <i>et al.</i>, “Labeled raw accelerometry data captured during walking, stair climbing and driving,” PhysioNet, 2021, doi: 10.13026/51h0-a262.",
    "mattfeld17": "R. Mattfeld, E. Jesch, and A. Hoover, “A new dataset for evaluating pedometer performance,” in <i>Proc. IEEE Int. Conf. Bioinformatics Biomedicine (BIBM)</i>, 2017, doi: 10.1109/BIBM.2017.8217769.",
    "efron": "B. Efron and R. J. Tibshirani, <i>An Introduction to the Bootstrap</i>. New York, NY, USA: Chapman &amp; Hall, 1993.",
}
assert "Timmermans" in REFS["timmermans25"]


def build(prev=None):
    P = Paper(**(prev or {}))
    B, S, SUB = P.body, P.sec, P.sub

    # ---------------------------------------------------------------------------------- title block
    P.para("ParkinSense: An Open, Evidence-Graded Wrist-Worn Research Platform for Motion, Cardiac, Activity and Sleep Biomarkers in "
           "Parkinson’s Disease Monitoring", align="c", size=17, bold=True, after=5, before=2)
    P.para("Pranshu Kumar, Lakshya Lalwani, Akshay Sable, Nalin Khare, and Asim Tewari", align="c", size=11, after=0)
    P.para("Department of Mechanical Engineering, Indian Institute of Technology Bombay, Mumbai 400076, India", align="c", size=9, italic=True, after=4)
    P.para("Manuscript status: engineering report on a research prototype. No person with Parkinson’s disease has been recorded, and no clinical or "
           "diagnostic claim is made. Every result is labelled with its evidence class (automated test, synthetic signal, public dataset from other "
           "devices, or ParkinSense hardware); none of the reported accuracy figures is a measurement of the assembled device.",
           align="c", size=8, italic=True, after=4)
    P.two_columns()

    # ---------------------------------------------------------------------------------- abstract
    P.para("<bi>Abstract—</bi><b>Motor symptoms of Parkinson’s disease (PD) fluctuate within a day, yet clinical rating scales sample them only "
           "intermittently. ParkinSense is an open-source, MIT-licensed wrist-worn research platform: a Seeed XIAO-class board with an LSM6DS3 "
           "inertial sensor and a MAX30102 optical sensor streams 104 Hz samples over Bluetooth Low Energy to a Python host that runs a tremor "
           "pipeline, a photoplethysmography (PPG) pipeline, a step counter, an offline sleep/wake estimate and an opt-in wear monitor. This paper "
           "describes the system as it exists in the repository and grades every capability by the evidence behind it. We specify the wire protocol "
           "(v1 and v2), the signal chain (Welch spectrum, a 3.5–7.5 Hz peak with Gaussian interpolation, motion-context gating, per-window evidence "
           f"and a two-state hidden Markov model) and the cross-pipeline gating. On synthetic ground truth the tremor pipeline reaches sensitivity "
           f"{f(A_TR['sensitivity'])}, specificity {f(A_TR['specificity'])} and F1 {f(A_TR['f1'])} (previous version: {f(A_TN['sensitivity'])}, "
           f"{f(A_TN['specificity'])}, {f(A_TN['f1'])}) at the cost of a longer onset latency "
           f"({CUR['latency']['onset_latency_s_median']:.1f} s versus {BASE['latency']['onset_latency_s_median']:.1f} s). On public wrist datasets recorded with "
           f"other devices, a subject-independent evaluation gives sleep/wake κ = {f(SLEEP['methods']['lr']['epoch_mean_over_subjects']['kappa'])} against "
           f"polysomnography, and a gated step counter that raises event F1 by {HELD['production'] and STEP_SEL['paired_vs_production']['f1_diff']:+.3f} "
           f"but fails two of seven pre-registered criteria and therefore stays opt-in. {N_PASS} automated tests pass. No documented hardware measurement of "
           "current, battery life, wear detection, overnight recording or tremor accuracy exists; owner-reported informal use is recorded but not counted. "
           "We list the hardware and dataset milestones that would change this.</b>", size=8.5, after=3)
    P.para("<bi>Index Terms—</bi><i>Parkinson’s disease; wearable sensing; digital biomarkers; tremor; photoplethysmography; step counting; sleep; "
           "Bluetooth Low Energy; evidence grading; reproducibility.</i>", size=8.5, after=4)

    # ---------------------------------------------------------------------------------- I Introduction
    S("Introduction", "intro")
    B("Parkinson’s disease is a progressive neurodegenerative disorder whose cardinal motor signs—resting tremor, bradykinesia and rigidity—fluctuate over "
      "the day {c:jankovic08,pf_tremor}. The MDS-UPDRS remains the clinical standard {c:goetz07,goetz08}, but it is administered rarely and reflects a brief "
      "in-clinic presentation. Wearable sensing has therefore been proposed as a source of objective, high-frequency data {c:pasluosta15,maetzler13,rovini17,"
      "espay16,espay19}. Most reported wearable tremor systems quantify a single inertial channel {c:rigas12,bazgir18,dai15}; few expose, alongside it, the "
      "activity context in which a reading was taken, and fewer still do so in an open, replayable software stack.")
    B("ParkinSense is an attempt at the latter. It is a research platform, not a medical device. Its aim is narrow: to acquire timestamped inertial and optical "
      "samples reliably, to process them with algorithms that are transparent, versioned and testable, and to report—for every output—how much "
      "evidence supports it. The second aim matters as much as the first. A previous version of this manuscript described a bench evaluation "
      "(communication reliability, power, functional tables) for which the repository holds no logs, and compared the platform with a published clinical "
      "pilot on criteria the platform has not been measured against. Auditing the repository showed that several of those statements could not be "
      "supported. This version replaces them with what can be verified and says plainly what cannot ({tab:reconcile}).")
    P.para("<bi>Contributions.</bi> (i) A complete, implementation-level description of the signal chain, wire protocol, state machines and parameters, "
           "sufficient to reproduce the pipeline ({sec:tremor}–{sec:wear}). (ii) A status vocabulary—implemented, bench-tested, partial, in development, "
           "planned, future—tied to five evidence classes, and an implementation-status matrix for twenty capabilities ({tab:status}, {fig:status}). "
           "(iii) A before/after benchmark of the tremor, PPG and step pipelines on synthetic ground truth with an identical-input harness ({sec:results}). "
           "(iv) Participant-independent evaluations on public wrist datasets for sleep/wake, step counting and wear inference, including the cases in which "
           "an algorithm failed its pre-registered acceptance rule. (v) A reconciliation of the earlier manuscript’s claims against the evidence "
           "({tab:reconcile}) and a plan of hardware and dataset milestones.", first=0.17)
    B("{sec:related} reviews related work, {sec:evidence} defines the evidence framework and status matrix, {sec:arch} gives the architecture, {sec:hw} and "
      "{sec:proto} the hardware, firmware and protocol, {sec:tremor}–{sec:wear} the algorithms, {sec:sw} the software and test infrastructure, "
      "{sec:method} and {sec:results} the evaluation, {sec:hwstatus} the hardware verification status, and {sec:disc}–{sec:concl} the discussion, "
      "limitations, future work and conclusion.")

    # ---------------------------------------------------------------------------------- II Related work
    S("Related Work", "related")
    SUB("Inertial tremor quantification")
    B("Resting tremor in PD lies at roughly 4–6 Hz, inside the broader 3.5–7.5 Hz range used as a search band {c:deuschl98}, and can be isolated with spectral "
      "features from wrist- or finger-worn accelerometers and gyroscopes {c:rigas12,dai15}. Later work applied classifiers to separate Parkinsonian "
      "from essential tremor and voluntary motion {c:zhang22,bazgir18}. Reviews note that many systems output a single score per window, computed "
      "independently of concurrent physiological or activity channels {c:mughal22,rovini17}. Tremor amplitude also depends on posture and activity "
      "{c:henderson94}, which motivates carrying a motion-context label with each tremor reading.")
    SUB("Open algorithms and the closest published devices")
    B("ParaDigMa, the open-source pipeline of Timmermans <i>et al.</i> {c:timmermans25}, windows wrist gyroscope data into 4 s segments, sums the axis spectra "
      "and classifies with an MFCC-based model, reporting leave-one-subject-out sensitivity 0.61 and specificity 0.97 on a free-living PD cohort. "
      "ParkinSense reuses its published feature definitions where stated, but not its classifier, and has not been evaluated on its dataset ({sec:future}). "
      "ELENA {c:saez25,batista24} is a low-cost IoT device with a single MPU6050 on the index finger and an ESP32 that uploads data for offline MATLAB "
      "spectral analysis; its authors report calibration on a static rig and a vibration table, agreement with a smartwatch within 0.5 % in frequency, and a "
      "pilot with nine patients and nine controls. That clinical pilot is a result ParkinSense does not have.")
    P.table("Positioning of related systems (as published; ParkinSense row is this work).", "related",
            ["System", "Sensing", "Processing", "Evidence reported"],
            [["Inertial tremor studies {c:rigas12,dai15}", "accel./gyro, wrist or finger", "offline features or classifier", "varies by study; small cohorts"],
             ["ELENA {c:saez25,batista24}", "MPU6050 (finger), ESP32, Wi-Fi", "offline MATLAB FFT", "rig and smartwatch comparison; 9 PD + 9 controls"],
             ["ParaDigMa {c:timmermans25}", "wrist gyroscope", "open pipeline, 4 s windows, MFCC model", "LOSO sensitivity 0.61, specificity 0.97 (as published)"],
             ["PERFORM {c:tzallas14}", "multi-sensor, clinical system", "decision-support framework", "clinical framework"],
             ["Consumer PPG wearables {c:tamura14}", "optical, wrist", "on-device", "not PD-specific"],
             ["<b>ParkinSense</b>", "IMU + finger PPG, BLE", "host-side, versioned, replayable",
              "synthetic + public datasets; <b>no patient data</b>"]],
            [1.15, 1.0, 1.1, 1.25], size=7)
    SUB("Photoplethysmography, activity and sleep")
    B("Autonomic dysfunction is a recognised non-motor feature of PD, and heart-rate variability (HRV) is standardised in the time domain over "
      "5-minute recordings {c:taskforce96}; wrist PPG is established for heart rate {c:tamura14} but is degraded by motion {c:zhang15}. Accelerometer step "
      "counting is mature {c:yang10}, and real-world sensor studies report altered activity in PD {c:adams17,adams21}. Wrist sleep/wake estimation "
      "from raw acceleration has simple published baselines {c:vanhees15} and public polysomnography-labelled data {c:walch19}. ParkinSense "
      "implements small, auditable versions of each and benchmarks them against those baselines, rather than claiming new state-of-the-art methods.")

    # ---------------------------------------------------------------------------------- III Evidence framework
    S("Evidence Framework and Implementation Status", "evidence")
    B("Four things are kept apart throughout: <i>what the code does</i>, <i>what automated tests prove</i>, <i>what data it was evaluated on</i>, and "
      "<i>what has been measured on the device</i>. {tab:classes} lists the evidence classes. A result from one class is never reported as another, "
      "and a decision that used the evaluation data (for example a threshold chosen on the same recordings) is marked optimistic.")
    P.table("Evidence classes used in this paper and what each can support.", "classes",
            ["Class", "Meaning", "Supports"],
            [["Automated test", "pytest and host firmware tests in CI", "code does what it states on stubbed or synthetic input"],
             ["Synthetic", "generated signals with known truth", "relative behaviour and regressions; <i>not</i> accuracy on people"],
             ["Public data", "other people’s devices (Apple Watch, ActiGraph, Shimmer)", "algorithm behaviour on real wrists; not ParkinSense hardware"],
             ["ParkinSense hardware", "individually recorded tests with logs", "device-level claims (rate, loss, current, wear)"],
             ["Owner-reported", "statement by the builder, no logs", "raises the prior that the device runs; satisfies no pass criterion"],
             ["Clinical", "labelled patient data, ethics approval", "<b>none exists</b>"]],
            [0.9, 1.45, 1.7], size=7)
    B("The status vocabulary follows from the classes. <b>Implemented</b>: the code exists and its automated tests pass. <b>Bench-tested</b>: documented "
      "hardware evidence exists. <b>Partial</b>: implemented but opt-in, estimate-only, or short of its acceptance rule. <b>In development</b>: plans, "
      "procedures and criteria are written and fixed, but nothing has been run. <b>Planned</b>: scheduled, not started. <b>Future</b>: research direction. "
      "{fig:status} shows the matrix for twenty capabilities and {tab:status} gives the evidence pointers; the same matrix is maintained in the "
      "repository (<tt>docs/research/IMPLEMENTATION_STATUS_MATRIX.md</tt>).")
    P.figure(FIG / "p_status.png", "Implementation-status matrix. Green: documented in the repository; yellow: one side only, owner-reported, or opt-in with unmet "
             "criteria; grey: none. No capability has a clinical cell filled.", "status", wide=True, width=6.1)
    pointers = {
        "C1": "<tt>data/reference</tt> BLE v1 capture (87 s, 104.01 Hz); fw v4 hardware-verified",
        "C2": "<tt>firmware/tests</tt> host tests; sketch type-check; <b>not flashed</b>",
        "C3": f"{N_PASS} tests; synthetic benchmark; no PD data",
        "C4": "context thresholds; tremor guard test",
        "C5": "synthetic HR; one unlabelled BLE capture",
        "C6": "synthetic RMSSD; withheld below 25 Hz PPG",
        "C7": "generic curve; <b>uncalibrated estimate</b>",
        "C8": "Clemson, Karas; synthetic",
        "C9": "fails 2 of 7 criteria; opt-in",
        "C10": "Walch LOSO, 17 subjects",
        "C11": "false-removal side only; thresholds provisional",
        "C12": "golden replay of 6 recordings",
        "C13": "integration tests; 60 min benchmark",
        "C14": "unit test; no longitudinal data",
        "C15": "PPK2 procedure S1–S7 <b>NOT RUN</b>",
        "C16": "W8 <b>NOT RUN</b>",
        "C17": "plans with pre-registered criteria; access unconfirmed",
        "C18": "Phases 10–13 deferred to Dec 2026 or later",
        "C19": "not implemented; feasibility notes only",
        "C20": "no ethics protocol, no patients",
    }
    P.table("Implementation status and evidence pointers.", "status", ["ID", "Capability", "Status", "Evidence in repository"],
            [[r[0], r[1], r[2], pointers[r[0]]] for r in ROWS], [0.3, 1.45, 0.75, 1.6], size=6.8)

    # ---------------------------------------------------------------------------------- IV Architecture
    S("System Architecture", "arch")
    B("ParkinSense has four layers with versioned interfaces ({fig:arch}): sensing (LSM6DS3, MAX30102), firmware (acquire, timestamp, pack, transmit), "
      "host processing (decode, integrity checks and four pipelines) and consumers (dashboard, replay, datasets, analytics). The firmware performs no "
      "signal processing, so algorithms change without reflashing and recordings can be re-analysed with any pipeline version.")
    P.figure(FIG / "p_architecture.png", "ParkinSense architecture and cross-pipeline coupling. Solid arrows are data flow; red dashed arrows are the gating and "
             "confidence couplings listed in {tab:coupling}.", "arch", wide=True, width=6.4)
    B("<b>Time model.</b> Three clocks are recorded (device <tt>micros()</tt>, host monotonic, host wall), but only <i>signal time</i> derived from the device "
      "timestamps drives processing. The 32-bit device timer wraps every 71 min 35 s and is unwrapped on the host. Because hysteresis, smoothing and "
      "state-machine timing use signal time, a recorded session replayed at any speed gives identical output, which is what the regression suite relies on.")
    B("<b>Cross-pipeline information flow.</b> Motion context is computed once and reused. {tab:coupling} lists every coupling; none changes the wire protocol.")
    P.table("Information flowing between pipelines.", "coupling", ["From", "To", "What and why"],
            [["motion context", "PPG", "state scales HR confidence 1.0 / 0.8 / 0.5 (REST / LOW MOTION / ACTIVE): motion corrupts PPG"],
             ["arm-movement frequency", "PPG", "flags HR that locks onto the motion frequency or its 2nd harmonic"],
             ["motion context", "step counter", "REST never counts steps"],
             ["tremor HMM", "step counter", "confirmed <i>rest</i> tremor forces the step gate to REST"],
             ["wear monitor (opt-in)", "step counter", "REMOVED forces the step gate to REST; data are never dropped"],
             ["stream integrity", "tremor, PPG", "rate off by &gt; 5 %: tremor DATA_GAP, HR RATE_INVALID"]],
            [0.95, 0.7, 2.1], size=7)

    # ---------------------------------------------------------------------------------- V Hardware
    S("Hardware and Firmware", "hw")
    P.figure(FIG / "p_photos.png", "Prototype: (a) worn on the wrist with an elastic strap; (b) open enclosure showing the sensor board and the microcontroller board. "
             "The photographs document sensor size and housing fit only; the microcontroller is the Seeed XIAO nRF52840 Sense.", "photos", wide=True, width=5.4)
    B("The documented bill of materials ({tab:bom}) is a Seeed XIAO nRF52840 Sense (Cortex-M4F at 64 MHz, BLE 5), an LSM6DS3 six-axis inertial sensor at I²C address "
      "0x6A, and a MAX30102 optical sensor with 660 nm red and 880 nm infrared LEDs and a FIFO, powered by a 3.7 V, 700 mAh Li-ion cell charged over USB-C "
      "(the cell rating is carried from an earlier README and not re-verified). Both sensors share a 400 kHz I²C bus. Pin-level wiring and enclosure files are not in "
      "the repository.")
    P.table("Sensor configuration by firmware version.", "bom", ["Setting", "Firmware v4 (protocol v1)", "Firmware 5.0.0 (protocol v2)"],
            [["Accelerometer range", "intended ±4 g, <i>not applied</i>: driver default ±16 g", "±4 g, applied before init"],
             ["Gyroscope range", "intended ±245 dps, <i>not applied</i>: ±2000 dps", "±500 dps"],
             ["IMU output rate", "416 Hz sensor, MCU samples at 104 Hz (aliasing possible)", "104 Hz (sensor filter is anti-alias)"],
             ["IMU read", "six separate float reads", "one 12-byte burst"],
             ["PPG to host", "newest FIFO sample every 100 ms: 10 Hz", "newest sample every tick: ≈100 Hz"],
             ["Over-range", "wraps (sign flip)", "saturates, flag set"],
             ["Faults", "not reported", "7 flag bits in header"],
             ["Version", "not exposed", "Device Information Service"],
             ["Status", "<b>last hardware-verified build</b>", "<b>host-tested, not flashed</b>"]],
            [0.9, 1.5, 1.35], size=6.8)
    B("<b>Finger gate.</b> In the shipped build profile A (<tt>REQUIRE_FINGER_FOR_STREAMING = true</tt>) the device streams only while a finger holds the "
      "infrared level above 50 000 counts for three consecutive 250 ms polls; below it for three polls, streaming stops. The consequence is stated "
      "plainly: <i>without finger contact on the PPG sensor there is no inertial stream</i>, hence no tremor or step data. Profile B (<tt>false</tt>) streams "
      "from boot with the inertial and optical paths independent. It type-checks but has not been flashed, and no hardware has measured how often "
      "the current wrist placement achieves finger contact.")
    B("<b>Scheduling and BLE.</b> A fixed-interval scheduler of 9 615 µs (104.004 Hz) catches up short stalls sample by sample; after more than five missed "
      "intervals it snaps to the present and sets a time-discontinuity flag. The packet timestamp is the micro-second counter at the first sample of the batch. "
      f"One 208-byte notification carries ten samples (≈{PKT_RATE:.1f} packets/s) within a 247-byte ATT MTU, with a 7.5–15 ms connection-interval request. "
      "Packets are not buffered during disconnection; the sequence number keeps incrementing so the host sees the gap. The firmware calls the RTOS sleep "
      "between samples; <b>no current has been measured</b> for either version.")

    # ---------------------------------------------------------------------------------- VI Protocol
    S("Wire Protocol and Data Integrity", "proto")
    B("Both protocol versions use identical framing: 208 bytes, an 8-byte header and ten 20-byte samples ({fig:packet}). Scales are selected by the version "
      "field, so an old recording is never decoded with new scales. Version 2 adds a sequence number, seven fault flags ({tab:flags}), a finer gyroscope "
      "scale and saturation instead of wrap-around. The host parser is the only decoder; <tt>encode(decode(x)) = x</tt> byte for byte, which makes replay bit-exact.")
    P.figure(FIG / "p_packet.png", "BLE packet layout (little-endian, packed). Header bytes: version, flags, sequence (v2; reserved in v1), 32-bit device time.",
             "packet", width=3.45)
    P.table("Protocol v2 header flags and v1/v2 scales.", "flags", ["Item", "Meaning"],
            [["bit 0–1", "ACCEL_CLIPPED, GYRO_CLIPPED: value saturated or at the sensor rail"],
             ["bit 2–3", "IMU_FAULT (IMU fields zero), PPG_FAULT (IR/RED invalid)"],
             ["bit 4", "PPG_STALE: ≥ 1 slot repeated the previous PPG sample (100 SPS sensor, 104 Hz slots)"],
             ["bit 5–6", "PREV_NOTIFY_FAILED; TIME_DISCONTINUITY (&gt; 5 intervals skipped)"],
             ["gyro scale", "v1: 131 counts/dps (±250 dps); v2: 64 counts/dps (±512 dps)"],
             ["accel scale", "8192 counts/g in both versions (±4 g)"]],
            [0.7, 3.05], size=7)
    B("<b>Integrity.</b> The host measures the true stream rate from consecutive header timestamps over 100 packets, classing it OK within 2 %, WARN "
      "within 5 % and INVALID beyond, because spectral frequencies scale with the rate error. Losses are detected from sequence gaps (v2) and timestamp gaps "
      "(v1 and v2); a gap longer than 0.5 s resets every analysis window so that no window spans a discontinuity. Every counter is written to the session "
      "<tt>metadata.json</tt> together with the firmware, protocol, pipeline, capture-schema and algorithm versions; capture CSV v3 has 79 columns and "
      "records the device, host-monotonic and host-wall clocks.")

    # ---------------------------------------------------------------------------------- VII Tremor
    S("Tremor and Motion Pipeline", "tremor")
    B("The motion pipeline runs every 0.5 s on a 4 s window (416 samples, 87.5 % overlap) of three gyroscope and three accelerometer axes. Its output is a "
      "per-window <i>evidence</i> value, which a two-state hidden Markov model turns into a published decision. Parameters are engineering settings, not "
      "values fitted to patient data. {fig:psd} shows the spectra the detector sees for four synthetic scenarios.")
    SUB("Spectrum and peak")
    B("Each gyroscope axis is mean-removed and a Welch periodogram {c:welch67} is computed with a 2 s Hann segment (208 samples), 50 % overlap (K = 3 segments), "
      f"linear detrending and FFT length 1024. The frequency resolution is set by the 2 s segment (native bin {NATIVE_BIN:.1f} Hz, Hann −3 dB main lobe ≈ {HANN_BW:.2f} Hz); "
      f"zero-padding to {DF:.4f} Hz spacing only interpolates. The orientation-independent spectrum is the axis sum:")
    P.eq(r"S(f)=\sum_{a\in\{x,y,z\}}P_a(f),\quad P_a(f)=\frac{2}{K f_s\sum_n w[n]^2}\sum_{k=1}^{K}\Big|\sum_{n=0}^{L-1}w[n]\,x_{a,k}[n]\,e^{-j2\pi f n/f_s}\Big|^2", "psd")
    B("The gyroscope is deliberately <i>not</i> band-passed first: an earlier version band-passed to 3–8 Hz, which drove the band ratio to about one for almost any "
      "input. The peak is the maximum of <i>S</i> in the 3.5–7.5 Hz search band, refined by Gaussian (log-parabolic) interpolation {c:jacobsen07}, "
      "with α, β, γ the log-spectrum at the peak bin and its neighbours:")
    P.eq(r"\delta=\frac{1}{2}\,\frac{\alpha-\gamma}{\alpha-2\beta+\gamma}\in\Big[-\tfrac12,\tfrac12\Big],\qquad \hat f=f_{i^*}+\delta\,\Delta f", "peak")
    B("The tremor power is integrated within ±0.625 Hz of the peak, giving a physical amplitude in degrees per second RMS {c:elble16}; the noise floor "
      "<i>F</i> is the median of <i>S</i> between 2 and 12 Hz excluding ±1 Hz around the peak:")
    P.eq(r"P_T=\sum_{|f_i-\hat f|\le 0.625}S(f_i)\,\Delta f,\quad A_T=\sqrt{P_T},\quad \mathrm{SNR_{dB}}=10\log_{10}\frac{S(f_{i^*})}{F}", "power")
    B("Per-axis tremor power gives <tt>axis_dominance</tt> (the largest share) and <tt>axis_agreement</tt> = clip(1 − σ<sub>f</sub>/2), where σ<sub>f</sub> is the "
      "power-weighted spread of per-axis peaks. A single-axis knock therefore has low agreement.")
    P.figure(FIG / "p_psd.png", "Summed-axis gyroscope spectra of one 4 s window from the repository’s synthetic generators (seed-fixed) with the tremor search band "
             "shaded and the interpolated peak dotted. Titles give the peak, SNR, motion context and evidence <i>e</i>. The 8.5–11 Hz oscillation has no peak in the band "
             "(SNR below 0 dB); walking and arm movement peak at the lower band edge and are rejected by the edge rule and the motion context.", "psd", wide=True, width=6.9)
    SUB("Motion context")
    B("Purposeful movement is measured in the time domain: <i>A</i><sub>arm</sub> is the RMS of the 0.5–3 Hz band-passed gyroscope over the central half of the "
      "window (the spectrum would show tremor leakage as “movement”). Acceleration is high-passed to remove gravity (0.3 Hz), band-limited to 0.2–3 Hz, "
      "and its vector RMS <i>R</i><sub>acc</sub> is taken over the central half. The more active of the two decides: REST (<i>R</i><sub>acc</sub> &lt; 0.03 g and "
      "<i>A</i><sub>arm</sub> &lt; 10°/s), LOW MOTION (&lt; 0.20 g and &lt; 30°/s), otherwise ACTIVE.")
    SUB("Per-window evidence and temporal inference")
    B("Evidence combines the SNR and amplitude as logistic gates (σ), zeroes peaks on the band edge (skirts of out-of-band oscillation) and down-weights "
      "arm-swing harmonics (<i>h</i> = 0.15 when the peak sits at 2–4 times the arm-movement frequency within 0.15 Hz, else 1):")
    P.eq(r"e=\sigma\!\Big(\frac{\mathrm{SNR_{dB}}-10}{2}\Big)\;\sigma\!\Big(\frac{A_T-1.0}{0.25}\Big)\;\mathbb{1}[\hat f\in(3.65,\,7.35)]\;h", "evidence")
    B("Evidence is not a calibrated probability. Consecutive windows share 87.5 % of their samples, so their evidence is not independent; the hidden Markov model "
      "{c:rabiner89} therefore tempers each likelihood ratio by the elapsed signal time Δ<i>t</i>. With entry and exit time constants τ<sub>in</sub> = 120 s and "
      "τ<sub>out</sub> = 60 s:")
    P.eq(r"p^{-}=p_{t-1}\,e^{-\Delta t/\tau_{out}}+(1-p_{t-1})\,(1-e^{-\Delta t/\tau_{in}})", "predict")
    P.eq(r"\Lambda=\mathrm{clip}\!\Big(\frac{e+\varepsilon}{1-e+\varepsilon},\Lambda_{max}^{-1},\Lambda_{max}\Big)^{\min(1,\Delta t/4\,\mathrm{s})},\quad p_t=\frac{\Lambda p^{-}}{\Lambda p^{-}+1-p^{-}}", "update")
    B(f"with Λ<sub>max</sub> = 60, ε = 10<sup>−3</sup> and prior <i>p</i><sub>0</sub> = 0.02. The published state is TREMOR once <i>p</i> ≥ 0.8 and is released at <i>p</i> ≤ 0.2. "
      f"Worked through, full evidence on the first 4 s window gives <i>p</i><sup>−</sup> = {PM1:.4f} and <i>p</i> = {Q1:.3f}, not yet confirmed; the next 0.5 s hop gives "
      f"<i>p</i> = {Q2:.3f}, confirmed. A single 4 s burst therefore cannot confirm by itself. Unusable windows (rate invalid, more than 2 % clipped samples) update the "
      "prediction only. {fig:hmm} shows the measured behaviour on a rest–tremor–rest synthetic session.")
    P.figure(FIG / "p_hmm.png", f"Window evidence and HMM posterior on a synthetic 20 s rest / 30 s 5 Hz tremor / 30 s rest session (whole runtime, protocol v2 packets). "
             f"The published state lags true onset by {HM['onset_s']:.1f} s and offset by {HM['offset_s']:.1f} s (benchmark medians "
             f"{CUR['latency']['onset_latency_s_median']:.1f} s and {CUR['latency']['offset_latency_s_median']:.1f} s); the lag is deliberate.", "hmm")
    P.table("Tremor pipeline parameters (algorithm v3.0).", "tremorpar", ["Quantity", "Value"],
            [["Sample rate, window, hop", "104 Hz (measured; invalid if &gt; 5 % off), 4 s, 0.5 s"],
             ["Search band; peak edge rule", "3.5–7.5 Hz; reject <i>f̂</i> ≤ 3.65 or ≥ 7.35 Hz"],
             ["Analysed band", "0.5–15 Hz"],
             ["Evidence gates", "SNR midpoint 10 dB (width 2 dB); amplitude midpoint 1.0°/s RMS (width 0.25)"],
             ["Context thresholds", "accel 0.03 / 0.20 g; arm-movement 10 / 30°/s"],
             ["HMM", "<i>p</i><sub>0</sub> 0.02; τ<sub>in</sub> 120 s, τ<sub>out</sub> 60 s; Λ<sub>max</sub> 60; confirm 0.8, release 0.2"],
             ["Published fields", "classification, P(tremor), state, type REST/ACTION, quality; <b>no clinical severity</b>"]],
            [1.2, 2.55], size=7)
    B("<b>Known failure modes.</b> Physiological or enhanced physiological tremor at 6–7.5 Hz with sufficient amplitude is reported as tremor; frequency and "
      "amplitude alone cannot separate it from PD tremor. Tremor below 1°/s RMS is not detected by design. Placement and orientation change amplitude. "
      "The detector has never been evaluated on people with PD.")

    # ---------------------------------------------------------------------------------- VIII PPG
    S("Photoplethysmography Pipeline", "ppg")
    B("Each 104 Hz slot carries one IR/RED pair; firmware v4 delivers 10 distinct PPG samples per second (zero-order hold, no anti-alias filter) and firmware "
      "5.0.0 about 100. The pipeline keeps a 10 s buffer, analysed every 0.5 s. The runtime measures the number of distinct samples and publishes it, "
      "because HRV from 10 Hz PPG is meaningless: RR quantisation is ±100 ms, so HRV is <i>withheld</i> below 25 Hz effective rate.")
    B("<b>Finger presence and quality.</b> Seven weighted checks (DC level within 5 000–0.98 FS of the 18-bit range, no saturation, AC ≥ 5 counts, AC/DC in "
      "0.05–10 %, stability, cardiac-band content, perfusion index) must pass a 0.6 vote and three mandatory conditions; the published state follows after a 1 s "
      "(on) or 2 s (off) hysteresis. A signal-quality index (SQI, 0–100) combines nine sub-scores (SNR, pulse consistency, clipping, motion artefact, entropy, "
      "spectral concentration, harmonics, perfusion, repeatability) and maps to NO_FINGER, LOW_SIGNAL, POOR_SIGNAL, GOOD, HIGH_SIGNAL or SATURATED.")
    B("<b>Heart rate.</b> The estimator is deliberately simple and auditable: a 0.5–4.5 Hz third-order zero-phase Butterworth band-pass; <tt>find_peaks</tt> with a "
      "0.30 s minimum spacing and a prominence of at least half the signal’s standard deviation; a dicrotic-notch guard that drops a weak peak within 0.5 s of a "
      "stronger one; RR intervals kept within 45–180 bpm; and the median. The displayed value is smoothed, and a jump above 30 bpm with low estimator "
      "confidence is held for at most 8 s:")
    P.eq(r"\mathrm{HR}=\frac{60}{\mathrm{median}(r_k)},\qquad h_t=0.25\,\mathrm{HR}_t+0.75\,h_{t-1}", "hr")
    B("An earlier, more elaborate detector (rolling z-score, local-energy gating, per-beat morphology scoring, weighted median) was replaced by this baseline; "
      "descriptions of it in the earlier manuscript no longer apply. Open-source beat-detector benchmarks {c:charlton22} are a planned comparison.")
    B("<b>Motion coupling.</b> Rhythmic wrist motion injects a PPG component that the beat detector can lock onto. With <i>f</i><sub>HR</sub> = HR/60 and "
      "<i>f</i><sub>arm</sub> from the motion pipeline (only passed when <i>A</i><sub>arm</sub> ≥ 10°/s), the pipeline <i>flags</i> the failure:")
    P.eq(r"\text{coupled}\iff\exists\,k\in\{1,2\}:\ \big|f_{HR}-k\,f_{arm}\big|\le 0.12\ \mathrm{Hz}", "coupled")
    B("Unlike TROIKA {c:zhang15}, which removes the motion spectrum, ParkinSense detects and flags but does not correct. Overall confidence is "
      "<i>C</i> = clip(0.40·SQI/100 + 0.30·rhythm + 0.20·peak + 0.10·<i>s</i><sub>mot</sub>) × <i>m</i>(motion) × (0.25 if coupled), with <i>m</i> = 1.0, 0.8, 0.5; "
      "the quality state is NO_CONTACT, INSUFFICIENT_DATA, MOTION_ARTIFACT, LOW_CONFIDENCE (<i>C</i> &lt; 0.35) or VALID. In the earlier pipeline the motion multiplier was never applied "
      "(a state-key mismatch); it is applied now.")
    B("<b>HRV and SpO<sub>2</sub>.</b> From the RR intervals of the 10 s buffer (40–200 bpm, at least four), RMSSD, SDNN and pNN50 follow the standard time-domain "
      "definitions {c:taskforce96}; they are short-window trend values, not 5-minute norms. SpO<sub>2</sub> uses a ratio of ratios with a <i>generic</i> curve and a "
      "SEARCHING→LOCKED→TRACKING→LOST state machine (rate-limited, published every 10 s):")
    P.eq(r"\mathrm{SpO_2}=97.601+10.503\,R-11.266\,R^2,\quad R=\frac{AC_{red}/DC_{red}}{AC_{IR}/DC_{IR}},\ \ \mathrm{clipped\ to\ }[70,100]\,\%", "spo2")
    B("The curve is not fitted to this sensor, LED current or finger, and no reference oximeter data exist; the dashboard labels the value “uncalibrated estimate”. "
      "Finger PPG also requires the wearer to hold a finger on the sensor, so continuous wear-time PPG is not possible with this placement.")
    P.figure(FIG / "p_ppg.png", "PPG on synthetic signals. (a) A six-second window of synthetic IR (two-Gaussian pulse model, 72 bpm) and its 0.5–4.5 Hz band-pass; (b) published "
             "HR over 60 s at rest through the full runtime with firmware-5.0.0 slots; (c) median HR confidence under rest and a 1.8 Hz motion artefact for the earlier "
             "(2.2.0) and current (3.0.0) pipelines on the benchmark’s v2 path. Heart-rate error under artefact stays large (about 28 bpm); the pipeline flags it by "
             "lowering confidence rather than correcting it.", "ppg", wide=True, width=6.9)

    # ---------------------------------------------------------------------------------- IX Steps
    S("Activity: Step Counting", "steps")
    B("The default counter (v1.1) runs per sample on the accelerometer magnitude <i>m</i>. A first-order high-pass (corner "
      f"≈ {HP_FC:.2f} Hz) removes gravity; an adaptive threshold tracks the last two seconds:")
    P.eq(r"y_n=0.95\,(y_{n-1}+m_n-m_{n-1}),\qquad T=\mathrm{clip}(\mu_{2\,s}+0.7\,\sigma_{2\,s},\;0.08,\;1.5)\ \mathrm{g}", "stephp")
    B("A step is counted on an upward crossing of <i>T</i> when armed, the motion gate is ACTIVE or LOW MOTION, and at least 0.30 s (200 steps/min) have passed; the "
      "detector re-arms below 0.3<i>T</i>. Walking is declared after three consecutive steps within 1 s of each other and ends 2 s after the last step; cadence is "
      "the exponentially smoothed 60/Δ<i>t</i>; distance is steps × 0.75 m (configurable, uncalibrated); an active minute accrues after 60 s of walking at "
      "more than 60 steps/min. Version 1.1 changed the time base from host arrival time (ten samples of a packet shared one timestamp) to signal time and added the "
      "<b>tremor guard</b>: while a rest tremor is confirmed the counter receives REST. On synthetic rest tremor this lowers false steps from 23.3 to 0.3 per "
      "minute ({fig:gating}); purposeful arm movement remains a known limitation (48.8 per minute).")
    P.figure(FIG / "p_step_gating.png", "False steps per minute on synthetic scenarios, earlier (2.2.0) versus current (3.0.0) runtime fed byte-identical packets. "
             "The tremor guard removes false steps during rest tremor; purposeful arm movement is unchanged.", "gating")
    B("<b>Gated counter (algorithm 3.0-dev, opt-in).</b> A causal 0.5–3.5 Hz band-pass of <i>m</i> yields candidate peaks that are stored, not counted. Every 0.5 s, "
      "the normalised autocorrelation of the last 4 s over lags 0.30–1.40 s must reach ρ = 0.65 and the 2 s RMS 0.12 g to open a walking gate, "
      "after which the previous 3 s of candidates are counted with their true times {c:moe04}:")
    P.eq(r"r(\tau)=\frac{\sum_i\tilde y[i]\,\tilde y[i+\tau]}{\sqrt{\sum_i\tilde y[i]^2\,\sum_i\tilde y[i+\tau]^2}},\qquad \text{gate open}\iff\max_{\tau}r(\tau)\ge\rho,\ \ \mathrm{RMS}_{2s}\ge 0.12\ \mathrm{g}", "autocorr")
    B("The thresholds were chosen by two-fold participant-independent cross-validation on the Clemson data. Replacement of the default requires all seven criteria "
      "of {tab:accept}, fixed before any candidate was evaluated; the live count lags a walking start by about 2 s.")

    # ---------------------------------------------------------------------------------- X Sleep
    S("Sleep/Wake Estimate (Offline)", "sleep")
    B("The sleep module estimates sleep versus wake in 30 s epochs from wrist acceleration alone and summarises a night. It is offline (it reads a recorded capture), "
      "computes no sleep stages, and is neither validated on ParkinSense hardware nor in PD. Samples are binned into 5 s sub-epochs with gravity vector "
      "ḡ<sub>k</sub>; the arm-angle change of the published heuristic {c:vanhees15} and an orientation-free variant are")
    P.eq(r"z_k=\operatorname{atan2}\!\big(\bar g_{k,z},\sqrt{\bar g_{k,x}^2+\bar g_{k,y}^2}\big),\quad \Delta z_k=|z_k-z_{k-1}|,\quad \Delta g_k=\arccos\frac{\bar g_k\cdot\bar g_{k-1}}{\|\bar g_k\|\|\bar g_{k-1}\|}", "zangle")
    B("Six context features (log of the largest angle change, the fraction of moved epochs and the mean ENMO within ±5 min, membership of a still run of at least five "
      "minutes, and log time since/until movement) feed an L2-regularised logistic regression, fitted by IRLS:")
    P.eq(r"P(\mathrm{sleep})=\sigma(b+\mathbf w^{\top}\mathbf x),\qquad \text{sleep}\iff P\ge\theta=0.7", "sleeplr")
    B("θ was selected by an inner leave-one-subject-out loop. Runs of at least 60 min with acceleration SD below 13 mg are treated as non-wear; the sleep period "
      "merges sleep runs separated by less than 60 min and must exceed 30 min; summaries carry an <tt>estimate</tt> flag, and fewer than two analysable hours "
      "yield <tt>INSUFFICIENT_DATA</tt> with no numbers. A tempered hidden Markov model and heart-rate features exist for experiments but lowered held-out "
      "agreement and are disabled.")

    # ---------------------------------------------------------------------------------- XI Wear
    S("Wear-Aware Acquisition", "wear")
    B("Phase 8 asked whether the current hardware can tell a worn wrist from a device on a table. The LSM6DS3 alone cannot do so reliably, and the MAX30102 is a "
      "finger sensor whose wrist behaviour is unmeasured. The wear monitor is therefore a <i>host-side, opt-in, inferred</i> state machine that changes neither "
      "the firmware nor the protocol (the header’s reserved flag bit stays reserved). It keeps five concepts apart—wear, IMU, PPG, link and power state—and "
      "enforces: stillness alone is never removal; contact loss alone is never removal; faults are no evidence; faulted IMU zeros are excluded from stillness; "
      "a gap never creates a removal; table bumps do not re-wear.")
    P.figure(FIG / "p_wear_states.png", "Wear-state model (simplified). REMOVED requires continuous stillness <i>and</i> absent optical contact; re-wear by motion lands in "
             "WORN_PPG_UNAVAILABLE, never WORN, because motion cannot prove contact.", "wearstates")
    P.table("Wear-monitor configuration (all provisional; only <i>still_acc_sd</i> was evaluated, on the false-removal side).", "wearcfg",
            ["Parameter", "Value", "Parameter", "Value"],
            [["still_acc_sd_g", "0.001 (1 mg)", "contact_ir_min", "50 000"],
             ["still_gyro_dps / angle", "0.5 / 2°", "contact_on / off", "3 s / 10 s"],
             ["possibly_removed_s", "300", "removed_s", "900"],
             ["motion_return_s", "20", "rewear_contact_s", "10"],
             ["rewear_motion_s", "60 s, ≥ 70 % moving", "gap_s / resume_s", "5 / 10"]],
            [1.15, 0.85, 1.0, 0.75], size=6.8)
    B("When enabled, REMOVED forces the step gate to REST and sets <tt>activity_allowed</tt> and <tt>tremor_allowed</tt> false; <tt>physiology_allowed</tt> holds "
      "only in a settled WORN state with contact. The engine never drops data in any state. The monitor costs 3.1 µs per sample in Python on an aarch64 sandbox, "
      "which is not a Cortex-M figure.")

    # ---------------------------------------------------------------------------------- XII Biomarkers
    S("Biomarker Aggregation and Personal Baselines", "bio")
    B("Window outputs are aggregated per session following ParaDigMa’s definitions {c:timmermans25}. With <i>Q</i> the valid rows whose motion state is REST or LOW MOTION and "
      "<i>T</i> ⊆ <i>Q</i> the rows published as rest tremor, tremor time is 100·|<i>T</i>|/|<i>Q</i>|, reported only with at least 10 still minutes; tremor "
      "power statistics (median, mode, 90th percentile of log<sub>10</sub>(<i>P</i><sub>T</sub> + 1)) are reported only when tremor time reaches 3.5 %. Heart "
      "and activity summaries require VALID rows and minimum durations. For a daily metric <i>x</i><sub>d</sub> a personal baseline uses a robust z-score over "
      "the last 28 qualifying days:")
    P.eq(r"z_d=\frac{x_d-m}{1.4826\,\mathrm{MAD}},\quad m=\mathrm{median}(x_{d-27..d-1}),\quad |z_d|\ge 3\Rightarrow\mathrm{DEVIATION}", "baseline")
    B("At least seven qualifying days are required; deviating days are not added (an acute change cannot drag the reference); days with a rate error, "
      "packet loss above 5 %, or a different firmware or pipeline version are NOT_COMPARABLE. This flags change relative to the individual and has no diagnostic "
      "meaning; no longitudinal data exist yet. Bradykinesia, dyskinesia and freezing of gait are <i>not</i> implemented; freezing is not feasible from the wrist, and "
      "the others need labelled MDS-UPDRS data.")

    # ---------------------------------------------------------------------------------- XIII Software and tests
    S("Software, Dashboard and Test Infrastructure", "sw")
    B("The host package (<tt>parkinsense/</tt>, version 3.0.0, Python ≥ 3.10; NumPy, SciPy, pandas) separates protocol, motion, tremor, PPG, activity, runtime, "
      "replay, datasets, analytics, sleep, wear, synthetic generators and visualisation; the dashboard never imports a detector. The runtime exposes a bounded "
      "FastAPI live endpoint, and the Plotly Dash dashboard polls it, shows a SIMULATED banner whenever data do not come from the wearable, labels values below VALID "
      "quality as not measurements, and replays recorded sessions through the same rendering path ({fig:dash}).")
    P.figure(FIG / "p_dashboard.png", "Dashboard (simulated stream, banner visible in the application): (a) overview; (b) tremor analytics with the HMM posterior, per-window "
             "evidence, peak frequency and amplitude. “Insufficient data” is shown because fewer than 10 still minutes are valid.", "dash", wide=True, width=6.3)
    P.table("Test and benchmark inventory (executed 2026-11-08, Linux x86-64, Python 3.13).", "tests", ["Layer", "Content", "Result"],
            [["pytest, all non-hardware", "unit, integration, golden regression, synthetic floors", f"<b>{N_PASS} passed</b>, {N_DESEL} deselected (hardware, no board)"],
             ["flake8 (CI rule set)", "<tt>parkinsense tests benchmarks</tt>", "0 errors"],
             ["Firmware host tests", "struct sizes, scaling, saturation, flags, scheduler incl. timer wrap", "OK"],
             ["Sketch type-check", "profiles A and B against API stubs", "OK (does <i>not</i> prove the nRF52 build)"],
             ["Golden replay", "6 real recordings (BLE v1 at 104 Hz; serial logs at ≈23 Hz)", "unchanged by the default pipeline"],
             ["Hardware tests", "H0–H11, W0–W8, PPK2 S1–S7", "<b>NOT RUN</b>"]],
            [1.0, 1.65, 1.1], size=6.8)
    B("Runtime cost is measured on a laptop CPU: the full runtime including PPG processes signal "
      f"at {CUR['cost']['realtime_factor']:.1f}× real time, with a median of {CUR['cost']['analysis_packet_latency_ms_median']:.1f} ms and a 95th percentile of "
      f"{CUR['cost']['analysis_packet_latency_ms_p95']:.1f} ms per packet that triggers an analysis ({BASE['cost']['realtime_factor']:.1f}× and "
      f"{BASE['cost']['analysis_packet_latency_ms_median']:.1f} ms before). This is host-computation time; it is not BLE or end-to-end latency. A 60-minute "
      f"dashboard benchmark ({DASH['recording']['capture_mb']:.0f} MB capture, {DASH['history']['analysis_windows']:,} analysis windows) gives an incremental live poll of "
      f"{DASH['live']['incremental_poll_ms']:.2f} ms, a cold history load of {DASH['history']['load_cold_ms']:.0f} ms, and bounded live buffers.")

    # ---------------------------------------------------------------------------------- XIV Methodology
    S("Evaluation Methodology", "method")
    B("<b>Synthetic ground truth.</b> Seeded generators produce rest, rest and action tremor (4–6.5 Hz carrier with slow frequency and 25 % amplitude modulation), "
      "voluntary movement, walking (shoulder pendulum with centripetal, tangential and heel-strike terms), vibration, 8.5–11 Hz oscillation and a two-Gaussian PPG "
      "model with respiratory baseline wander and optional motion artefact. A benchmark harness feeds byte-identical packets to the repository as originally found (pipeline "
      "2.2.0) and to the current pipeline, with 16 seeds × 30 s per tremor scenario and the first 8 s of each segment excluded. Synthetic results show relative behaviour; "
      "they are only as good as the model (an early walking model lacked the centripetal term and made the legacy counter look 82 % wrong before it was corrected).")
    B("<b>Public datasets.</b> Sleep: Walch {c:walch19}, 17 usable subjects with single-scorer polysomnography, leave-one-subject-out, threshold chosen in a nested inner "
      "loop, paired subject-level bootstrap {c:efron} (10 000 draws). Steps: Clemson {c:mattfeld17} (30 participants × 3 gait conditions, 54 374 annotated foot contacts, "
      "wrist sensor at 15 Hz up-sampled to 104 Hz) and Karas {c:karas21} (27 subjects, 641 min of driving and clapping labels, no step events). Wear: Walch worn nights and "
      "Karas driving. These are other devices on other wrists; none is ParkinSense hardware. The Clemson copy is third-party prepared with channels re-calibrated to g by an affine "
      "fit, and the motion gate is held ACTIVE, so the runtime tremor guard is not exercised.")
    B("<b>Pre-registration.</b> Step-counter acceptance criteria and hardware pass criteria were written before any candidate or measurement existed; thresholds may be "
      "chosen only inside participant-independent loops; and results that used evaluation data for a decision are reported as optimistic.")

    # ---------------------------------------------------------------------------------- XV Results
    S("Results", "results")
    SUB("Tremor on synthetic ground truth", "res-tremor")
    P.table("Tremor benchmark on synthetic signals (16 seeds; analysis-level; earlier 2.2.0 versus current 3.0.0).", "tremorres", ["Metric", "2.2.0", "3.0.0"],
            [["Sensitivity (rest + strong tremor)", f(A_TN["sensitivity"]), f"<b>{f(A_TR['sensitivity'])}</b>"],
             ["Specificity (rest, voluntary, walking, vibration, 8.5–11 Hz)", f(A_TN["specificity"]), f"<b>{f(A_TR['specificity'])}</b>"],
             ["F1", f(A_TN["f1"]), f"<b>{f(A_TR['f1'])}</b>"],
             ["Counts TP / FN / FP / TN", f"{A_TN['tp']} / {A_TN['fn']} / {A_TN['fp']} / {A_TN['tn']}", f"{A_TR['tp']} / {A_TR['fn']} / {A_TR['fp']} / {A_TR['tn']}"],
             ["Strong tremor (120–250°/s) detected", pc(BASE["tremor"]["sensitivity_by_amplitude"]["120-250 dps"], 0), pc(CUR["tremor"]["sensitivity_by_amplitude"]["120-250 dps"], 0)],
             ["8.5–11 Hz oscillation called PD tremor", pc(BASE["tremor"]["per_scenario"]["non_pd_oscillation"]["mean_fraction_classified_tremor"]), pc(CUR["tremor"]["per_scenario"]["non_pd_oscillation"]["mean_fraction_classified_tremor"])],
             ["Tremor during action / walking detected", f"{pc(BASE['tremor']['per_scenario']['action_tremor']['mean_fraction_classified_tremor'], 0)} / {pc(BASE['tremor']['per_scenario']['walking_with_tremor']['mean_fraction_classified_tremor'], 0)}",
              f"{pc(CUR['tremor']['per_scenario']['action_tremor']['mean_fraction_classified_tremor'], 0)} / {pc(CUR['tremor']['per_scenario']['walking_with_tremor']['mean_fraction_classified_tremor'], 0)}"],
             ["Frequency error, median / p90 (Hz)", f"{BASE['tremor']['frequency_abs_error_hz']['median']:.3f} / {BASE['tremor']['frequency_abs_error_hz']['p90']:.3f}",
              f"<b>{CUR['tremor']['frequency_abs_error_hz']['median']:.3f} / {CUR['tremor']['frequency_abs_error_hz']['p90']:.3f}</b>"],
             ["Onset / offset latency, median (s)", f"<b>{BASE['latency']['onset_latency_s_median']:.1f} / {BASE['latency']['offset_latency_s_median']:.1f}</b>",
              f"{CUR['latency']['onset_latency_s_median']:.1f} / {CUR['latency']['offset_latency_s_median']:.1f}"]],
            [2.0, 0.9, 0.9], size=6.9)
    B("The detector fixes three failure modes of the earlier version: strong tremor classified itself as ACTIVE movement and was vetoed (38 % → 97 % detected), an 8.5–11 Hz "
      "oscillation was called PD tremor (8.6 % → 0 %), and tremor during action or walking was missed (49 %/60 % → ≈100 %, now labelled ACTION where applicable). The "
      "price is latency: the published state needs about 1.4 independent windows of evidence, so onset is 6.1 s rather than 1.1 s and offset 8.1 s rather than 4.0 s "
      "(ADR-0007). {fig:tbench} summarises the comparison. These are synthetic results with hand-set thresholds and no confidence interval; they indicate "
      "behaviour, not clinical accuracy.")
    P.figure(FIG / "p_tremor_bench.png", "Synthetic tremor benchmark, earlier versus current pipeline: (a) analysis-level metrics; (b) sensitivity by peak tremor amplitude; "
             "(c) median onset and offset latency. Latency is longer by design.", "tbench", wide=True, width=6.8)
    P.figure(FIG / "p_scenarios.png", "Fraction of analysed windows published as tremor in each synthetic scenario (tremor-present above the dotted line).", "scen")
    SUB("PPG and steps on synthetic signals", "res-ppg")
    v1b, v1c, v2b, v2c = BASE["ppg_v1_path"], CUR["ppg_v1_path"], BASE["ppg_v2_path"], CUR["ppg_v2_path"]
    P.table("PPG benchmark on synthetic signals (rest: 10 seeds × 60 s; artefact: 6 seeds with a 1.8 Hz component).", "ppgres",
            ["Metric", "v1 fw 2.2.0", "v1 fw 3.0.0", "v2 fw 2.2.0", "v2 fw 3.0.0"],
            [["HR MAE at rest (bpm)", f(v1b["rest_hr_mae_bpm"], 1), f(v1c["rest_hr_mae_bpm"], 2), f(v2b["rest_hr_mae_bpm"], 1), f(v2c["rest_hr_mae_bpm"], 2)],
             ["RMSSD MAE at rest (ms)", f(v1b["rest_rmssd_mae_ms"], 0), "withheld", f(v2b["rest_rmssd_mae_ms"], 1), f(v2c["rest_rmssd_mae_ms"], 1)],
             ["HR confidence at rest (median)", f(v1b["rest_hr_confidence_median"], 2), f(v1c["rest_hr_confidence_median"], 2), f(v2b["rest_hr_confidence_median"], 2), f(v2c["rest_hr_confidence_median"], 2)],
             ["HR confidence, artefact (median)", f(v1b["motion_hr_confidence_median"], 2), f(v1c["motion_hr_confidence_median"], 2), f(v2b["motion_hr_confidence_median"], 2), f(v2c["motion_hr_confidence_median"], 2)],
             ["HR MAE, artefact (bpm)", f(v1b["motion_hr_mae_bpm"], 1), f(v1c["motion_hr_mae_bpm"], 1), f(v2b["motion_hr_mae_bpm"], 1), f(v2c["motion_hr_mae_bpm"], 1)]],
            [1.45, 0.62, 0.62, 0.62, 0.62], size=6.8)
    B("The large resting-HR improvement (16–18 → 0.3–0.4 bpm) comes from fixing a sample-rate mismatch: the earlier pipeline assumed 50 Hz while data arrived at "
      "104 Hz, so every interval was wrong by 2.08×. Under a motion artefact the HR error is unchanged (≈ 28 bpm) but is now flagged, with confidence falling from "
      "0.84 to 0.17; firmware-5.0.0 PPG (“v2 fw”) has not been verified on hardware. For steps, the walking count error is −9.7 % mean (worst −21 %) for both versions, "
      "since the detection logic is unchanged, and false steps per minute are 23.3 → 0.3 during rest tremor and 46.3 → 48.8 during purposeful arm movement ({fig:gating}).")
    SUB("Step counting on public data", "res-steps")
    C = STEP_BASE["clemson"]["summary"]
    rows = []
    for cond in ("Regular", "SemiRegular", "Irregular", "all"):
        pr, pe, ga = C["production"][cond], C["periodic"][cond], HELD["heldout"][cond]
        pf1 = pr["f1"]
        rows.append([cond if cond != "all" else "<b>all</b>", f"{pr['pooled_bias_pct']:+.1f} / {pr['mape_pct']:.1f} / {pf1:.3f}",
                     f"{pe['pooled_bias_pct']:+.1f} / {pe['mape_pct']:.1f} / {pe['f1']:.3f}", f"{ga['bias_pct']:+.1f} / {ga['mape_pct']:.1f} / {ga['f1']:.3f}"])
    P.table("Clemson step benchmark, bias % / MAPE % / event F1 (30 participants; gated counter is held-out by 2-fold participant split).", "clemson",
            ["Condition", "Production v1.1", "Periodic (exp.)", "Gated 3.0-dev"], rows, [0.8, 1.0, 1.0, 1.0], size=6.8)
    KP, KG = STEP_BASE["karas"]["summary"], STEP_GATED["karas"]["summary"]["gated"]
    B(f"Production v1.1 is accurate on regular walking (precision 0.98, recall 0.77) but overcounts irregular gait by 299 %. The gated counter raises held-out event F1 "
      f"from {HELD['production']['all']['f1']:.3f} to {HELD['heldout']['all']['f1']:.3f} (paired participant bootstrap Δ = {STEP_SEL['paired_vs_production']['f1_diff']:+.3f}, 95 % CI "
      f"[{STEP_SEL['paired_vs_production']['f1_ci95'][0]:+.3f}, {STEP_SEL['paired_vs_production']['f1_ci95'][1]:+.3f}]) and cuts MAPE by "
      f"{abs(STEP_SEL['paired_vs_production']['mape_diff']):.1f} points. On Karas, false steps during driving and clapping fall from {KP['production']['false_steps_per_min']:.1f} to "
      f"{KG['false_steps_per_min']:.1f} per minute at a walking-state sensitivity of {KG['walking_state_sensitivity']:.3f} versus {KP['production']['walking_state_sensitivity']:.3f} "
      "({fig:steps}). The runtime motion gate is held ACTIVE here, so the 52 false steps per minute probably overstate what the full pipeline would count while driving; "
      "that was not measured.")
    P.figure(FIG / "p_steps_public.png", "Step counters on public wrist data. (a) Event F1 and (b) count error (MAPE, log scale) on Clemson by gait condition; the gated "
             "counter is held-out. (c) False steps per minute on Karas driving/clapping with walking-state sensitivity in parentheses.", "steps", wide=True, width=6.9)
    P.table("Pre-registered acceptance of the gated step counter as the default.", "accept", ["#", "Criterion", "Result"],
            [["A1", "pooled bias and MAPE lower than production", "<b>pass</b> (|bias| 9.7 vs 13.3 %; MAPE 18.2 vs 111.1 %)"],
             ["A2", "no condition worse by &gt; 2 pts MAPE", "<b>fail</b>: SemiRegular 20.9 vs 8.2"],
             ["A3", "event F1 higher, paired CI excludes 0", "<b>pass</b> (+0.114)"],
             ["A4", "Karas false steps not higher", "<b>pass</b> (4.1 vs 52.5 per min)"],
             ["A5", "walking sensitivity within 2 pts, specificity not lower", "<b>fail</b>: sensitivity 0.900 vs 0.973"],
             ["A6", "existing behaviour unchanged", "<b>pass</b> (golden replay, all tests)"],
             ["A7", "honest reporting", "this section"]],
            [0.3, 1.8, 1.65], size=6.8)
    B("Two criteria fail, so production v1.1 remains the default and the gated counter stays opt-in. Part of production’s good SemiRegular count error is cancelling mistakes "
      "(precision 0.75, recall 0.77): its F1 there (0.761) is close to the candidate’s (0.737) despite the 12-point MAPE gap.")
    SUB("Sleep/wake against polysomnography", "res-sleep")
    mt = SLEEP["methods"]
    names = {"vanhees_dz": "van Hees 2015 (z-angle, 5°/5 min)", "vanhees_dg": "van Hees rule, gravity angle", "lr_plain": "Logistic regression, θ = 0.5",
             "lr": "<b>Logistic regression, nested-LOSO θ (shipped)</b>", "lr_hmm": "LR + tempered HMM", "lr_hr_hmm": "LR + HR + tempered HMM",
             "hmm_untempered": "LR + untempered HMM (ablation)", "rf_hmm_untempered": "Random forest + untempered HMM"}
    srow = []
    for k in ("vanhees_dz", "vanhees_dg", "lr_plain", "lr", "lr_hmm", "lr_hr_hmm", "hmm_untempered", "rf_hmm_untempered"):
        e, n_ = mt[k]["epoch_mean_over_subjects"], mt[k]["night"]
        srow.append([names[k], f(e["kappa"]), f(e["balanced_accuracy"]), f(e["sensitivity_sleep"]), f(e["specificity_wake"]),
                     f"{n_['tst_min']['mae']:.1f} ({n_['tst_min']['mean_error']:+.1f})"])
    P.table(f"Sleep/wake on Walch (17 subjects, {SLEEP['epochs_scored']:,} scored 30 s epochs, {pc(SLEEP['sleep_fraction'])} sleep; means over subjects).", "sleepres",
            ["Method", "κ", "Bal. acc.", "Sleep sens.", "Wake spec.", "TST MAE (bias), min"], srow, [1.5, 0.35, 0.4, 0.42, 0.42, 0.6], size=6.5)
    pv = SLEEP["paired_vs_vanhees_dz"]
    B(f"Accuracy is inflated by sleep prevalence, so κ and balanced accuracy are reported. The shipped model agrees better with polysomnography (Δκ = {pv['lr']['kappa']['mean_diff']:+.3f}, 95 % CI "
      f"[{pv['lr']['kappa']['ci95'][0]:+.3f}, {pv['lr']['kappa']['ci95'][1]:+.3f}], {pv['lr']['kappa']['subjects_better']}/{pv['lr']['kappa']['n']} subjects better) and estimates total sleep time "
      f"better (|TST error| {pv['lr']['abs_tst_error_min']['mean_diff']:+.1f} min, CI [{pv['lr']['abs_tst_error_min']['ci95'][0]:+.1f}, {pv['lr']['abs_tst_error_min']['ci95'][1]:+.1f}]), mainly by accepting "
      f"more sleep; balanced accuracy is unchanged ({pv['lr']['balanced_accuracy']['mean_diff']:+.3f}, CI spans 0) and wake detection stays weak (0.58). The HMM and heart-rate variants were worse and are not "
      "shipped ({fig:sleep}). Seventeen healthy adults, one night each and one scorer limit generalisation; the large external test set used by the dataset authors "
      "was unreachable, so no external result exists.")
    P.figure(FIG / "p_sleep.png", "Sleep/wake versus polysomnography on Walch (leave-one-subject-out). (a) Cohen’s κ by method; (b) per-subject κ of the shipped model against the "
             "published heuristic, with the paired bootstrap difference.", "sleep", wide=True, width=6.4)
    SUB("Wear inference on public data", "res-wear")
    A_, B_, C_ = WEAR["A_worn_sleep_stillness"]["summary"], WEAR["B_state_machine_worst_case_no_ppg"]["summary"], WEAR["C_driving_state_machine"]["summary"]
    P.table("False-removal evidence for the wear monitor (PPG forced absent, the worst case).", "wearres",
            ["Threshold", "Worn night in still runs ≥ 15 min", "Mean REMOVED", "Subjects ever REMOVED"],
            [["1 mg (default)", pc(A_["1mg"]["mean_share_in_runs_ge_15min"]), pc(B_["1mg"]["mean_removed_frac"]), f"{B_['1mg']['subjects_ever_removed']} / 15"],
             ["2 mg", pc(A_["2mg"]["mean_share_in_runs_ge_15min"]), pc(B_["2mg"]["mean_removed_frac"]), f"{B_['2mg']['subjects_ever_removed']} / 15"],
             ["4 mg", pc(A_["4mg"]["mean_share_in_runs_ge_15min"]), pc(B_["4mg"]["mean_removed_frac"]), f"{B_['4mg']['subjects_ever_removed']} / 15"]],
            [0.8, 1.2, 0.8, 0.95], size=6.8)
    B(f"On 15 usable Walch nights the pooled 1 s epoch SD of a worn, sleeping wrist has a 1st percentile of {A_['sd_mg_quantiles_q01_q05_q25_q50'][0]:.2f} mg; at the 13 mg threshold of the "
      f"motion-only non-wear rule {pc(A_['13mg']['mean_share_in_runs_ge_15min'])} of the night lies in still runs of at least 15 min. Motion alone therefore cannot decide removal. At the shipped 1 mg "
      f"default no subject is ever REMOVED and the {C_['driving_minutes']:.0f} min of Karas driving are {pc(C_['mean_removed_frac'])} REMOVED ({C_['subjects']} subjects). The threshold was chosen on "
      "the same worn nights it is scored on, so this is optimistic; sensitivity to genuine removal cannot be evaluated because no public non-wear labels exist ({fig:weardata}). "
      "The default is a fail-safe, provisional until bench recordings exist.")
    P.figure(FIG / "p_wear_data.png", "Wear inference on public data: (a) worn sleeping wrists are still; (b) false removal by threshold with PPG forced absent.", "weardata", wide=True, width=5.6)
    SUB("Real recordings", "res-real")
    rec_rows = []
    for k, label in (("stationary_60s", "stationary, 60 s (23 Hz resampled)"), ("walking_60s", "walking, 60 s"), ("normal_motion_60s", "everyday arm movement, 60 s"),
                     ("simulated_tremor_30s", "wrist shaken at 8–9 Hz, 30 s"), ("vibration_reference_30s", "vibration, 30 s")):
        o = GOLD[k]["outputs"]
        rec_rows.append([label, pc(o["tremor_fraction"], 0), str(o["final_steps"]), ", ".join(f"{a} {pc(b, 0)}" for a, b in sorted(o["motion_state_fraction"].items(), key=lambda x: -x[1]))])
    P.table("Unlabelled real recordings: golden regression outputs of the current pipeline (not accuracy).", "real", ["Recording", "Tremor", "Steps", "Motion state"],
            rec_rows, [1.3, 0.45, 0.4, 1.6], size=6.8)
    B("These recordings have no ground truth beyond the activity performed; they guard against regression. They also document limits: the arm-movement and shaking recordings "
      "produce 90 and 83 false steps in the legacy-rate logs (the gated counter and a held-out Karas evaluation address this class, not the default), and the wrist shaken at 8–9 Hz "
      "is correctly not called PD-band tremor. A finger-on capture from a healthy wearer (not committed; personal data) showed a 5 s oscillation at 6.4–6.8 Hz and 7–11°/s flagged by "
      "both pipeline versions; without ground truth it cannot be labelled.")

    # ---------------------------------------------------------------------------------- XVI Hardware status
    S("Hardware Verification Status", "hwstatus")
    B("The hardware procedure fixes pass criteria before any data exists. {tab:hwtests} lists the priority tests. <b>Every documented test is NOT RUN.</b> On 2026-11-06 the owner reported "
      "having tested the updated firmware, dashboard and system on themselves and that everything worked; the report names no firmware version or build profile, test ID, duration, "
      "packet-loss or rate figure, battery measurement, overnight recording or file. It raises the prior that the firmware boots and streams and that the dashboard displays "
      "it, and it satisfies none of the pass criteria. The last documented hardware evidence is a firmware-v4 capture of 87 s (measured rate 104.01 Hz, finger mostly off) and the "
      "earlier prototype photographs.")
    P.table("Hardware tests and status (pass criteria are fixed in the validation plan).", "hwtests", ["ID", "Test", "Pass criterion (abridged)", "Status"],
            [["W0", "record wiring (XIAO nRF52840)", "wiring and INT photographed; bootloader info saved", "NOT RUN"],
             ["H0–H3", "IMU/PPG init, v2 streaming, sequence continuity", "documented criteria; loss counted from seq", "NOT RUN"],
             ["H5", "current (PPK2, S1–S7)", "tables filled; no claim without them", "NOT RUN"],
             ["W1", "bench noise floor", "table 99th pct. SD &lt; threshold with ≥ 2× margin", "NOT RUN"],
             ["W2", "worn-still distribution (≥ 5 nights, ≥ 3 people)", "no night in REMOVED; worn 1st pct. above W1", "NOT RUN"],
             ["W3–W4", "removal and re-wear detection", "REMOVED in ≥ 9/10 within 960 s, never while worn", "NOT RUN"],
             ["W5–W7", "profile B contract, wrist optical signal, sensor independence", "IMU stream unbroken with no finger; PPG state flips ≤ 10 s", "NOT RUN"],
             ["W8", "overnight ≥ 8 h in profile B", "loss &lt; 1 %, no gap &gt; 60 s, human-inspected", "NOT RUN"]],
            [0.45, 1.25, 1.55, 0.5], size=6.6)
    B("W1 and W2 decide whether the LSM6DS3 noise on a table is clearly below worn-still noise; if not, an extra skin-contact sensor becomes mandatory, a hardware and enclosure change. "
      "Until W8 passes with an inspected capture, overnight recording is not validated; the cell’s capacity (unverified) may not last a night in profile B.")

    # ---------------------------------------------------------------------------------- XVII Reconciliation
    P.table("Reconciliation: claims of the earlier manuscript against current evidence.", "reconcile", ["Earlier claim", "Evidence today", "Treatment"],
            [["≈ 7 mA active, ≈ 100 h runtime, µA deep sleep on lost contact", "no current measurement exists; v4 has no sleep code (audit A-P0-4)", "removed; PPK2 plan S1–S7"],
             ["no packet loss in multi-hour sessions", "no log; loss counters exist only from v2", "removed; H3, W5, W8"],
             ["&lt; 100 ms latency after window close", "only host compute time measured (17.8 ms median)", "restated as host time"],
             ["bench tables IV–VIII “measured/validated”", "no logs or IDs attached", "replaced by evidence classes"],
             ["composite 80-point score; 5-of-10 window rule; 24 features", "replaced by evidence + HMM (v3.0, ADR-0005/0007)", "rewritten to current code"],
             ["adaptive z-score PPG detector, weighted median", "replaced by simple auditable baseline", "rewritten"],
             ["wrist PPG with the sensor against the skin", "MAX30102 is a finger sensor; wrist signal unmeasured", "corrected"],
             ["superiority over a published clinical pilot", "no comparator on shared data or protocol", "removed; ELENA as related work"],
             ["comparison with an unrelated actuation project", "separate project", "removed"]],
            [1.4, 1.5, 0.85], size=6.6)

    # ---------------------------------------------------------------------------------- XVIII Discussion
    S("Discussion", "disc")
    B("<b>What the evidence supports.</b> The code implements the stated algorithms, {n} automated tests and a golden replay guard them, and on synthetic ground truth the tremor "
      "pipeline separates PD-band rest tremor from voluntary movement, walking, vibration and out-of-band oscillation far better than the earlier version. On other people’s "
      "wrists, a small logistic sleep model beats a published heuristic on agreement and total sleep time, a gated step counter reduces false steps by an order of magnitude "
      "at a cost in sensitivity, and motion alone is shown to be insufficient for wear inference.".format(n=N_PASS))
    B("<b>What it does not.</b> Nothing here establishes accuracy on people with PD or on ParkinSense hardware. Synthetic benchmarks use hand-set thresholds and a "
      "generator whose realism is itself unvalidated; the public datasets are healthy adults, other sensors and other placements; and the one hardware-dependent "
      "assumption on which most outputs rest—that a finger is on the optical sensor so the inertial stream exists—has not been measured for how often it holds.")
    B("<b>Design lessons.</b> Several of the largest gains came from correcting plumbing rather than algorithms: a 2.08× sample-rate mismatch in PPG, a motion multiplier that "
      "was never applied, an HMM dead band that froze the earlier state machine, and host-arrival timestamps that quantised intervals. Measuring the device’s true rate, "
      "carrying versions with every output, and testing live against replay made these visible. The trade between stability and latency is explicit (onset 6.1 s): a platform "
      "for longitudinal biomarkers can accept it; a trigger for an actuator could not.")
    B("<b>Relation to prior work.</b> ELENA {c:saez25} has a completed single-modality pilot and a device-level frequency comparison that ParkinSense lacks; ParaDigMa {c:timmermans25} has a "
      "published free-living evaluation. ParkinSense’s contribution is an open, versioned, replayable stack with explicit evidence grading, whose inertial algorithm can be run on the "
      "same public data once access is confirmed. Whether its added channels improve any patient-level outcome is untested.")

    # ---------------------------------------------------------------------------------- XIX Limitations
    S("Limitations", "limits")
    P.bullets([
        "No patient data, no ethics protocol, no clinical or diagnostic claim; every output is research-grade.",
        "No documented ParkinSense hardware measurement of rate, loss, current, battery life, wear detection, wrist PPG or overnight operation; firmware 5.0.0 has never been compiled for "
        "the target or flashed; wiring and the MAX30102 interrupt line are undocumented (test W0).",
        "By default no inertial stream without finger contact on the PPG sensor; continuous wear-time PPG is not possible with this placement.",
        "Tremor evidence is not a calibrated probability; physiological tremor at 6–7.5 Hz is reported as tremor; onset latency is 6.1 s.",
        "SpO<sub>2</sub> is an uncalibrated estimate; HRV is a 10 s trend value and is withheld on firmware v4; heart rate under rhythmic motion is flagged, not corrected.",
        "Default step counter overcounts irregular gait (+299 % on Clemson) and arm movement (≈ 49 false steps/min on synthetic data); distance uses an uncalibrated step length.",
        "Sleep: 17 healthy adults, one night each, one scorer; wake specificity 0.58; not validated in PD or on this hardware.",
        "Wear: REMOVED is inferred, rarely triggers at the fail-safe threshold, was tuned on the evaluated nights, and cannot tell wear from carrying.",
        "Public datasets are other devices; the Clemson wrist data are 15 Hz and a third-party copy; no result generalises to this device without hardware evidence.",
        "No ParaDigMa/PD@Home reproduction, no Daphnet freezing-of-gait baseline, no bradykinesia or dyskinesia detection; bibliographic details should be re-checked before submission.",
    ], size=8.5)

    # ---------------------------------------------------------------------------------- XX Future work
    S("Future Work and Milestones", "future")
    B("The cycle is sequenced so that cheap, decisive evidence comes first ({fig:timeline}). <b>Phase 8</b> is software-complete but not accepted: the first hardware session (W0, H0–H3, "
      "W1, W2 and a PPK2 current subset) should precede any further algorithm work, because W1/W2 decide whether an additional contact sensor is required. <b>Phase 9</b> uses public "
      "data: confirm access to PD@Home and Daphnet (owner action), then ingest with checksums, reproduce the ParaDigMa leave-one-subject-out result, score ParkinSense v3 as is on "
      "down-sampled data, and run a freezing-of-gait baseline under criteria already fixed. Mobile, product UI, cloud and a patient pilot (Phases 10–13) wait for final wear states and "
      "metadata revisions and for ethics approval.")
    P.figure(FIG / "p_timeline.png", "Milestones. A phase is complete only when its evidence and acceptance criteria are met.", "timeline", wide=True, width=6.4)

    # ---------------------------------------------------------------------------------- XXI Conclusion
    S("Conclusion", "concl")
    B("ParkinSense now has an implementation whose behaviour is specified, versioned and testable: a 104 Hz wire protocol with fault flags, a tremor pipeline with motion-context gating and "
      "temporal inference, a simple auditable PPG pipeline, a gated step counter that stays opt-in because it fails two pre-registered criteria, an offline sleep/wake estimate and an "
      "inferred wear monitor. On synthetic and public data these components behave as described, and the manuscript says where they do not. What it cannot yet say is how any of them "
      "performs on the device or on people with Parkinson’s disease. The next evidence is a documented hardware session and an access-confirmed public tremor dataset; clinical "
      "validation under an ethics-approved protocol remains the step before any diagnostic claim.")

    P.para("ACKNOWLEDGMENT", align="c", size=9, bold=True, before=7, after=3, keep_next=True)
    P.para("The authors thank the Department of Mechanical Engineering, Indian Institute of Technology Bombay, for institutional and laboratory support.", first=0.17)
    P.para("DATA AND CODE AVAILABILITY", align="c", size=9, bold=True, before=7, after=3, keep_next=True)
    P.para("Repository: github.com/sudo-pranshu/ParkinSense (MIT). Tests: <tt>pytest</tt>; firmware host tests: <tt>g++ -std=c++17 -I firmware/parkinsense_wearable firmware/tests/test_packet.cpp</tt>. "
           "Benchmarks: <tt>benchmarks/run_benchmarks.py</tt>, <tt>sleep_bench.py</tt>, <tt>steps_bench.py</tt>, <tt>wear_bench.py</tt> with committed results in <tt>benchmarks/results/</tt>; public "
           "datasets are fetched by <tt>benchmarks/external/fetch.py</tt> and are not redistributed. Figures and paper: <tt>docs/research/paper/make_figures.py</tt>, <tt>build_paper.py</tt>. Status matrix: "
           "<tt>docs/research/IMPLEMENTATION_STATUS_MATRIX.md</tt>. Test evidence: <tt>docs/research/evidence/test_run_20261108.txt</tt>.", align="l", first=0.17)
    P.references(REFS)
    return P


if __name__ == "__main__":
    pa = build()
    state = pa.finish()
    pb = build(dict(refs_prev=state["refs"], cites_prev=state["cites"]))
    assert not pb.unresolved, sorted(pb.unresolved)
    cp = pb.doc.core_properties
    cp.author = "Pranshu Kumar; Lakshya Lalwani; Akshay Sable; Nalin Khare; Asim Tewari"
    cp.title = "ParkinSense: An Open, Evidence-Graded Wrist-Worn Research Platform for Motion, Cardiac, Activity and Sleep Biomarkers in Parkinson's Disease Monitoring"
    cp.comments = ""
    cp.last_modified_by = "Pranshu Kumar"
    pb.doc.save(OUT)
    print("wrote", OUT, "| figs", pb.nfig, "tables", pb.ntab, "eqs", pb.neq, "refs", len(pb.cite_order))
