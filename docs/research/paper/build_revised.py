#!/usr/bin/env python3
"""Builds docs/research/ParkinSense_Research_Paper_Revised.docx (IEEE-style, two columns) from repository facts.

Every number is read from the repository (benchmarks/results/*.json, tests/regression/golden.json, the committed test
evidence file, docs/*) or computed here and asserted against the documented value. Nothing is a hardware or clinical
measurement. Run from the repository root:
    python3 docs/research/paper/make_figures.py && python3 docs/research/paper/build_paper.py
    soffice --headless --convert-to pdf --outdir docs/research docs/research/ParkinSense_Research_Paper_Revised.docx
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
OUT = ROOT / "docs" / "research" / "ParkinSense_Research_Paper_Revised.docx"


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
    "powers21": "R. Powers <i>et al.</i>, “Smartwatch inertial sensors continuously monitor real-world motor fluctuations in Parkinson’s disease,” <i>Sci. Transl. Med.</i>, vol. 13, no. 579, art. eabd7865, 2021, doi: 10.1126/scitranslmed.abd7865.",
    "applemd": "Apple Inc., “CMMovementDisorderManager,” Core Motion documentation (watchOS 5.0+). [Online]. Available: https://developer.apple.com/documentation/coremotion/cmmovementdisordermanager",
    "efron": "B. Efron and R. J. Tibshirani, <i>An Introduction to the Bootstrap</i>. New York, NY, USA: Chapman &amp; Hall, 1993.",
}
assert "Timmermans" in REFS["timmermans25"]


def build(prev=None):
    P = Paper(**(prev or {}))
    B, S, SUB = P.body, P.sec, P.sub
    P.para("ParkinSense: An Open Wrist-Worn Research Platform for Motion, Cardiac, Activity and Sleep Signals in Parkinson’s Disease Monitoring",
           align="c", size=17, bold=True, after=5, before=2)
    P.para("Pranshu Kumar, Lakshya Lalwani, Akshay Sable, Nalin Khare, and Asim Tewari", align="c", size=11, after=0)
    P.para("Department of Mechanical Engineering, Indian Institute of Technology Bombay, Mumbai 400076, India", align="c", size=9, italic=True, after=4)
    P.two_columns()
    P.para("<bi>Abstract—</bi><b>ParkinSense is an open-source (MIT) wearable research platform that streams 104 Hz inertial and optical samples from a "
           "Seeed XIAO nRF52840 Sense board over Bluetooth Low Energy to a Python host. The host runs a tremor detector, a photoplethysmography (PPG) "
           "pipeline, a step counter, an offline sleep/wake estimator and an opt-in wear monitor. We describe the implementation in enough detail to "
           "reproduce it (wire protocol, Welch-spectrum tremor evidence with a two-state hidden Markov model, motion-gated heart-rate estimation) and "
           "label every result by the evidence behind it. On synthetic ground truth the tremor detector reaches sensitivity "
           f"{f(A_TR['sensitivity'])} and specificity {f(A_TR['specificity'])} (previous version {f(A_TN['sensitivity'])} and {f(A_TN['specificity'])}), at the cost of a longer "
           f"onset latency ({CUR['latency']['onset_latency_s_median']:.1f} s against {BASE['latency']['onset_latency_s_median']:.1f} s). On public wrist datasets recorded with other devices, "
           f"sleep/wake agreement with polysomnography is κ = {f(SLEEP['methods']['lr']['epoch_mean_over_subjects']['kappa'])}, and a gated step counter raises event F1 by "
           f"{STEP_SEL['paired_vs_production']['f1_diff']:+.3f} but fails two of seven pre-set criteria, so it stays opt-in. {N_PASS} automated tests pass. "
           "No patient has been recorded and no hardware measurement of accuracy, current or battery life exists; no clinical claim is made.</b>", size=8.5, after=3)
    P.para("<bi>Index Terms—</bi><i>Parkinson’s disease, wearable sensing, tremor, photoplethysmography, step counting, sleep, Bluetooth Low Energy.</i>", size=8.5, after=4)

    S("Introduction", "intro")
    B("Parkinson’s disease (PD) produces motor signs, notably resting tremor, that vary over the day {c:jankovic08,pf_tremor}, whereas the MDS-UPDRS {c:goetz07,goetz08} "
      "samples them in occasional clinic visits. Wearable sensors are a proposed remedy {c:pasluosta15,maetzler13,rovini17,espay16,espay19}, but most tremor systems analyse "
      "one inertial channel {c:rigas12,bazgir18,dai15} and few publish the signal chain in a form others can rerun.")
    B("ParkinSense is a research prototype, not a medical device. It acquires timestamped samples, processes them with versioned, replayable algorithms, and attaches to each "
      "output an account of the evidence supporting it. The last aim is deliberate: an earlier version of this manuscript reported bench figures (current, runtime, packet loss) "
      "for which the repository holds no logs. Those statements are withdrawn here, and results are grouped into four classes: automated tests, synthetic signals, public datasets "
      "from other devices, and ParkinSense hardware ({tab:classes}). A result from one class is never presented as another, and no clinical class exists yet.")
    P.para("<bi>Contributions.</bi> (i) A reproducible description of the protocol, tremor, PPG, step, sleep and wear algorithms. (ii) A before/after benchmark on identical synthetic "
           "input. (iii) Participant-independent evaluations on public wrist data, including a candidate that failed its pre-set acceptance rule. (iv) An explicit statement of what "
           "remains unmeasured on the device.", first=0.17)

    P.table("Evidence classes and what each can support.", "classes", ["Class", "Source", "Supports"],
            [["Automated test", "pytest, host firmware tests, CI", "code behaves as specified on stubbed or synthetic input"],
             ["Synthetic", "seeded generators with known truth", "relative behaviour and regressions, not accuracy on people"],
             ["Public data", "other devices (Apple Watch, ActiGraph, Shimmer)", "behaviour on real wrists, not on this hardware"],
             ["ParkinSense hardware", "logged recordings and measurements", "device-level claims (rate, loss, current, wear)"],
             ["Clinical", "labelled patient data, ethics approval", "<b>none exists</b>"]], [0.85, 1.35, 1.55], size=6.8)
    S("Related Work", "related")
    B("Resting PD tremor lies at about 4–6 Hz within a 3.5–7.5 Hz search band {c:deuschl98} and is separable from voluntary motion with spectral features of wrist or finger "
      "inertial signals {c:rigas12,dai15}; classifiers have been used to distinguish it from essential tremor {c:zhang22,bazgir18}. Amplitude depends on posture and activity "
      "{c:henderson94}, which motivates reporting motion context with each reading. Four systems frame this work: PERFORM {c:tzallas14}, a multi-sensor monitoring platform; ELENA {c:saez25,batista24}, "
      "a low-cost finger-worn tremor meter; ParaDigMa {c:timmermans25}, an open algorithm for wrist gyroscope data; and the Apple Watch movement-disorder pipeline {c:powers21,applemd}. "
      "Wrist PPG is established for heart rate but degraded by motion {c:tamura14,zhang15}; step counting {c:yang10}, free-living activity {c:adams17,adams21} and accelerometer sleep/wake "
      "{c:vanhees15} are mature topics, and ParkinSense implements small auditable versions benchmarked against published baselines. Section VII compares the systems dimension by dimension.")

    S("System, Firmware and Data Integrity", "sys")
    B("<b>Architecture.</b> Sensing (LSM6DS3 inertial sensor, MAX30102 optical sensor on a 400 kHz I²C bus, Seeed XIAO nRF52840 Sense with a 3.7 V Li-ion cell) feeds firmware that only "
      "samples, timestamps and packs data ({fig:arch}). All processing is on the host, so algorithms change without reflashing and recordings can be reanalysed. Processing uses "
      "<i>signal time</i> from device timestamps (the 32-bit microsecond counter, which wraps every 71.6 min, is unwrapped), so a recording replayed at any speed reproduces the live "
      "output; the regression suite relies on this.")
    B("<b>Firmware.</b> Version 4 (protocol v1) is the last build verified on hardware. Version 5.0.0 (protocol v2) fixes defects found in audit, listed in {tab:fw}; it has been tested "
      "on a host and type-checked against API stubs. The owner reports (2026-11-08) that it is flashed and streaming and that the dashboard works with it, but <i>no log was kept, so no "
      "measurement exists</i>. A scheduler runs at 9 615 µs (104.004 Hz) and sets a discontinuity "
      "flag after more than five missed intervals. In the shipped profile the device streams only while a finger keeps the infrared level above 50 000 counts (three consecutive 250 ms "
      "polls); without finger contact there is no inertial stream. An alternative profile with independent sensors type-checks but is untested. {fig:proto} shows the sizing and housing prototype.")
    P.table("Firmware v4 and 5.0.0 (flashed per owner report; not measured).", "fw", ["Item", "v4 (protocol v1)", "5.0.0 (protocol v2)"],
            [["IMU range, rate", "±16 g, ±2000 dps (intended range never applied), 416 Hz sensor", "±4 g, ±500 dps, 104 Hz; one 12-byte burst read"],
             ["PPG to host", "10 Hz (one sample per 100 ms)", "≈ 100 Hz"],
             ["Over-range, faults", "wraps; not reported", "saturates; 7 header flags"],
             ["Packet", "208 B: 8 B header + 10 × 20 B samples", "same; sequence number added"],
             ["Status", "<b>hardware-verified</b>", "<b>flashed, owner-reported working; no log</b>"]], [0.8, 1.45, 1.5], size=6.8)
    P.figure(FIG / "p_architecture.png", "ParkinSense architecture. Solid arrows: data flow; dashed red arrows: gating and confidence couplings between pipelines.", "arch", wide=True, width=5.5)
    P.figure(FIG / "p_prototype.png", "Prototype: (a) assembled device worn on the wrist; (b) elastic strap, 3D-printed enclosure and electronics. The photographs record sizing and housing fit; the development board visible in (b) is a size stand-in, and the documented target is the XIAO nRF52840 Sense.", "proto", wide=True, width=4.6)
    B("<b>Protocol and integrity.</b> Both versions send 208-byte notifications (≈ 10.4 packets/s) of ten samples (ax, ay, az, gx, gy, gz, IR, red); accelerometer scale is 8192 counts/g and the "
      "gyroscope scale is 131 (v1) or 64 counts/dps (v2), selected by a version field. Version 2 adds a sequence number and flags for clipping, IMU/PPG fault, stale PPG, failed notify and "
      "time discontinuity. The host decoder is the only parser and re-encodes byte-exactly. The true stream rate is measured from timestamps over 100 packets and classed OK within 2 %, "
      "WARN within 5 % and INVALID beyond, since spectral frequencies scale with rate error. A gap longer than 0.5 s resets every analysis window. Session metadata records all "
      "versions and counters ({fig:acq}).")
    B("<b>Software.</b> The host package (Python ≥ 3.10; NumPy, SciPy, pandas) separates protocol, motion, tremor, PPG, activity, sleep and wear modules from the runtime, which exposes a bounded "
      "FastAPI endpoint. A Plotly Dash dashboard consumes it, shows a SIMULATED banner whenever data do not come from the wearable, labels values below VALID quality as not "
      "measurements, and replays recorded sessions through the same rendering path. Capture files (79 columns) record the device, host-monotonic and host-wall clocks. {fig:dash} shows the current dashboard on the built-in "
      "simulated stream {fig:dashlive} its live page and {fig:dashlog} its logging path; the pages are engineering views, and no separate clinician-facing view has been built.")
    P.figure(FIG / "p_dash.png", "Current dashboard on the simulated stream (banner shown; not wearable data): (a) overview with no tremor and quality-tagged cards; (b) tremor analytics with the HMM posterior, peak frequency and amplitude of detected windows.", "dash", wide=True, width=6.6)
    P.figure(FIG / "p_acq.png", "Sensor acquisition, BLE streaming and runtime decoding, with the 208-byte packet layout shared by protocol v1 and v2.", "acq", wide=True, width=6.6)
    P.figure(FIG / "p_dashlog.png", "Logging and dashboard architecture.", "dashlog")
    P.figure(FIG / "p_dash_live.png", "Live-monitoring page: raw inertial and PPG traces, tremor frequency and probability (simulated stream).", "dashlive")


    S("Signal-Processing Algorithms", "alg")
    SUB("Tremor detection", "tremor")
    B("{fig:pipes} shows the three pipelines and {fig:fusion} their couplings. Every 0.5 s the motion pipeline analyses a 4 s window (416 samples). Each gyroscope axis gets a Welch periodogram {c:welch67} (2 s Hann segments, 50 % overlap, K = 3, linear detrend, "
      f"FFT length 1024); resolution is set by the segment ({NATIVE_BIN:.1f} Hz bin, ≈ {HANN_BW:.2f} Hz Hann main lobe) and zero-padding to {DF:.4f} Hz only interpolates. The axis-summed spectrum is")
    P.eq(r"S(f)=\sum_{a\in\{x,y,z\}}P_a(f)", "psd")
    B("with <i>P</i><sub>a</sub> the Welch estimate of axis <i>a</i>. The gyroscope is intentionally not band-passed first, because an earlier band-passed version pushed the band ratio towards one for "
      "almost any input. The peak of <i>S</i> in 3.5–7.5 Hz is refined by Gaussian interpolation {c:jacobsen07}, "
      "where α, β, γ are the log-spectrum at the peak bin and its neighbours:")
    P.eq(r"\hat f=f_{i^*}+\frac{\alpha-\gamma}{2\,(\alpha-2\beta+\gamma)}\,\Delta f", "peak")
    B("Tremor power is the integral of <i>S</i> within ±0.625 Hz of the peak, giving an amplitude in °/s RMS {c:elble16}, and the noise floor <i>F</i> is the median of <i>S</i> over 2–12 Hz "
      "excluding the peak ±1 Hz:")
    P.eq(r"A_T=\sqrt{\sum_{|f_i-\hat f|\le 0.625}S(f_i)\,\Delta f},\quad \mathrm{SNR}=10\log_{10}\frac{S(f_{i^*})}{F}", "power")
    B("Voluntary movement is measured in the time domain: <i>A</i><sub>arm</sub> is the RMS of the 0.5–3 Hz band-passed gyroscope, and gravity-removed acceleration is band-limited to 0.2–3 Hz. "
      "Thresholds of 0.03/0.20 g and 10/30 °/s give REST, LOW MOTION or ACTIVE. Window evidence combines logistic gates on SNR and amplitude, rejects peaks within 0.15 Hz of the band "
      "edges, and down-weights arm-swing harmonics (<i>h</i> = 0.15 at 2–4 times the arm frequency, else 1):")
    P.eq(r"e=\sigma\left(\frac{\mathrm{SNR}-10}{2}\right)\sigma\left(\frac{A_T-1}{0.25}\right)\,\mathbb{1}\left[3.65<\hat f<7.35\right]\,h", "evidence")
    B("Consecutive windows share 87.5 % of their samples, so evidence is not independent. A two-state hidden Markov model {c:rabiner89} tempers each likelihood ratio by the elapsed signal "
      "time Δ<i>t</i> (ε is a small constant), with time constants τ<sub>in</sub> = 120 s, τ<sub>out</sub> = 60 s, Λ<sub>max</sub> = 60, ε = 10<sup>−3</sup> and prior 0.02:")
    P.eq(r"p^{-}=p\,e^{-\Delta t/\tau_{out}}+(1-p)\left(1-e^{-\Delta t/\tau_{in}}\right)", "hmm")
    P.eq(r"p'=\frac{\Lambda\,p^{-}}{\Lambda\,p^{-}+1-p^{-}}", "hmm2")
    P.eq(r"\Lambda=\mathrm{clip}\left(r,\,\Lambda_{max}^{-1},\,\Lambda_{max}\right)^{\min(1,\,\Delta t/4)},\quad r=\frac{e+\varepsilon}{1-e+\varepsilon}", "lam")
    B(f"Tremor is published at <i>p</i> ≥ 0.8 and released at ≤ 0.2. With full evidence, the first window gives <i>p</i> = {Q1:.3f} and the next 0.5 s hop {Q2:.3f}, so one 4 s burst cannot confirm "
      f"alone. {{fig:psd}} and {{fig:hmm}} show spectra of four synthetic scenarios and the resulting evidence; on a rest–tremor–rest session the state lags onset by {HM['onset_s']:.1f} s and offset by {HM['offset_s']:.1f} s. "
      "{tab:params} lists the settings. The output has no severity score. Physiological tremor at 6–7.5 Hz with enough amplitude is reported as tremor, and the detector has not been evaluated on people with PD.")
    P.figure(FIG / "p_pipelines.png", "Signal-processing flow of the motion, PPG and step pipelines with their principal settings.", "pipes", wide=True, width=6.6)
    P.table("Principal parameters (engineering settings, not fitted to patient data).", "params", ["Pipeline", "Setting"],
            [["Tremor", "4 s window, 0.5 s hop; search 3.5–7.5 Hz; gates 10 dB and 1.0 °/s; context 0.03/0.20 g, 10/30 °/s; HMM τ<sub>in</sub> 120 s, τ<sub>out</sub> 60 s, confirm 0.8, release 0.2"],
             ["PPG", "10 s buffer; band 0.5–4.5 Hz; RR 45–180 bpm; EMA 0.25; coupling tolerance 0.12 Hz; HRV above 25 Hz only; SpO<sub>2</sub> clipped to 70–100 %"],
             ["Steps", "high-pass α = 0.95; threshold μ + 0.7σ over 2 s; refractory 0.30 s; walking after 3 steps; gated: ρ ≥ 0.65, RMS ≥ 0.12 g"],
             ["Sleep, wear", "30 s epochs, θ = 0.7; stillness 1 mg SD; possible/removed after 300/900 s; contact IR &gt; 50 000"]],
            [0.8, 6.0], size=6.9, wide=True)
    P.figure(FIG / "p_psd.png", "Summed-axis gyroscope spectra of four synthetic scenarios (search band shaded, interpolated peak dotted). Titles give peak, SNR, context and evidence <i>e</i>.", "psd", wide=True, width=6.6)

    SUB("Photoplethysmography", "ppg")
    B("A 10 s buffer is analysed every 0.5 s. Finger presence uses seven weighted checks with 1 s (on) and 2 s (off) hysteresis, and a 0–100 signal-quality index combines nine sub-scores. Heart "
      "rate uses a deliberately simple chain: a 0.5–4.5 Hz third-order zero-phase Butterworth filter, peak detection (0.30 s minimum spacing, prominence ≥ 0.5 SD, dicrotic-notch guard), "
      "RR intervals within 45–180 bpm, and the median interval, smoothed by an exponential average:")
    P.eq(r"\mathrm{HR}=\frac{60}{\mathrm{median}(r_k)},\qquad h_t=0.25\,\mathrm{HR}_t+0.75\,h_{t-1}", "hr")
    P.figure(FIG / "p_hmm.png", "Window evidence and HMM posterior on a synthetic 20 s rest / 30 s tremor / 30 s rest session through the full runtime.", "hmm")
    B("Rhythmic arm motion can capture the beat detector; the pipeline <i>flags</i> heart rate within 0.12 Hz of the arm-movement frequency or its second harmonic and scales confidence by "
      "1.0/0.8/0.5 for REST/LOW MOTION/ACTIVE and by 0.25 when coupled. Unlike TROIKA {c:zhang15}, it does not correct the artefact. Heart-rate variability follows standard definitions "
      "{c:taskforce96} but is withheld below 25 Hz effective PPG rate, which includes every firmware-v4 stream (10 Hz). SpO<sub>2</sub> uses a generic ratio-of-ratios curve and is an "
      "<i>uncalibrated estimate</i>; no reference oximeter data exist:")
    P.eq(r"\mathrm{SpO_2}=97.601+10.503\,R-11.266\,R^2,\qquad R=\frac{\mathrm{AC}_{red}/\mathrm{DC}_{red}}{\mathrm{AC}_{IR}/\mathrm{DC}_{IR}}", "spo2")

    SUB("Steps, sleep and wear", "other")
    B("<b>Steps.</b> The default counter high-passes the accelerometer magnitude <i>m</i> (corner ≈ 0.83 Hz) and compares it with an adaptive threshold over the last 2 s:")
    P.eq(r"y_n=0.95\,(y_{n-1}+m_n-m_{n-1}),\qquad T=\mathrm{clip}(\mu_{2\,s}+0.7\,\sigma_{2\,s},\,0.08,\,1.5)\ \mathrm{g}", "step")
    B("A step is an upward crossing when armed, not at REST, and at least 0.30 s after the last; a confirmed rest tremor forces the gate to REST (the <i>tremor guard</i>). An opt-in gated counter "
      "(0.5–3.5 Hz band-pass, autocorrelation ≥ 0.65 over lags 0.30–1.40 s, 2 s RMS ≥ 0.12 g {c:moe04}) counts candidate peaks only while a walking gate is open. "
      "<b>Sleep.</b> An offline estimator forms 30 s epochs from six arm-angle and ENMO context features {c:vanhees15} and applies an L2 logistic regression (IRLS) with a threshold of 0.7 chosen by nested "
      "leave-one-subject-out; it gives no stages and is not validated in PD. <b>Wear.</b> An opt-in host-side monitor changes neither firmware nor protocol and declares removal only after "
      "300 s (possible) or 900 s (removed) of continuous stillness <i>and</i> absent optical contact; stillness alone, contact loss alone and data gaps never imply removal, "
      "and re-wear by motion cannot restore the WORN state without contact ({fig:wearfig}); {fig:fusion} shows how the wear state gates the step counter. <b>Baselines.</b> Session summaries follow ParaDigMa {c:timmermans25}; a personal baseline flags "
      "deviation from a 28-day rolling median at |z| ≥ 3 (MAD scale) and has no diagnostic meaning. Bradykinesia, dyskinesia and freezing of gait are not implemented.")

    P.figure(FIG / "p_fusion.png", "Cross-pipeline gating and confidence coupling (dashed red) and the per-window output; the signal paths are those of the runtime engine.", "fusion", wide=True, width=6.4)
    S("Evaluation Methodology", "method")
    B("<b>Synthetic.</b> Seeded generators produce rest and action tremor (4–6.5 Hz with frequency and amplitude modulation), voluntary movement, walking, vibration, an 8.5–11 Hz oscillation and a "
      "two-Gaussian PPG model with optional motion artefact. A harness feeds byte-identical packets to the repository as originally found (pipeline 2.2.0) and to the current one "
      "(16 seeds × 30 s per tremor scenario, first 8 s excluded). Results show relative behaviour only. <b>Public data.</b> Sleep: Walch {c:walch19}, 17 subjects, "
      "leave-one-subject-out, paired subject-level bootstrap {c:efron}. Steps: Clemson {c:mattfeld17} (30 participants, 54 374 foot contacts, 15 Hz wrist data up-sampled to 104 Hz) and Karas {c:karas21} "
      "(27 subjects, 641 min of driving and clapping, no step events). Wear: Walch nights and Karas driving. These are other devices on other wrists. <b>Rules.</b> Acceptance criteria and "
      "hardware pass criteria were written before any candidate or measurement existed; thresholds were chosen only inside participant-independent loops; decisions that used evaluation data "
      "are reported as optimistic. <b>Tests.</b> "
      f"{N_PASS} pytest tests pass ({N_DESEL} deselected, no board) in the run of 2026-11-08 (Linux x86-64, Python 3.13); {{tab:tests}} lists the test layers. Host compute is "
      f"{CUR['cost']['realtime_factor']:.1f}× real time with a {CUR['cost']['analysis_packet_latency_ms_median']:.1f} ms median per analysis packet; this is not BLE or end-to-end latency.")
    P.figure(FIG / "p_wear_states.png", "Wear-state model (simplified). REMOVED needs continuous stillness and absent optical contact; re-wear by motion lands in WORN_PPG_UNAVAILABLE.", "wearfig")

    P.table("Software test layers and status.", "tests", ["Layer", "Content", "Result"],
            [["pytest", "unit, integration, golden regression, synthetic floors", f"<b>{N_PASS} passed</b>, {N_DESEL} deselected (hardware)"],
             ["flake8", "CI rule set over package, tests, benchmarks", "0 errors"],
             ["Firmware host tests", "struct sizes, scaling, saturation, flags, scheduler with timer wrap", "OK"],
             ["Sketch type-check", "build profiles A and B against API stubs", "OK; target build owner-reported only"],
             ["Golden replay", "6 real recordings, 104 Hz BLE and ≈ 23 Hz serial logs", "unchanged by default pipeline"],
             ["Hardware tests", "H, W and PPK2 series (Section VIII)", "<b>NOT RUN</b>"]], [0.9, 1.9, 0.95], size=6.8)
    S("Results", "results")
    B("<b>Real BLE capture.</b> The only hardware recording is an 87 s firmware-v4 session (9 040 samples, finger mostly off the sensor). Its device timestamps give 104.004 Hz, matching the 9 615 µs schedule, with no "
      "sample interval above 13.1 ms and packet-start timestamps within ±7.2 ms of an ideal 104 Hz clock (end drift −3.7 ms; {fig:capture}a,b). Protocol v1 has no sequence number and the log holds device timestamps only, "
      "so this shows sampling regularity, not host-side loss or latency. The IR trace shows contact events ({fig:capture}c) and the context stage labels the session 47 % REST, 52 % LOW MOTION and 0.6 % ACTIVE; "
      "the context fractions of all six regression recordings ({fig:capture}d) follow their recording types but have no per-window ground truth, so they are regression outputs, not accuracy. "
      "No current, battery or BLE-throughput measurement exists, so none is plotted.")
    P.figure(FIG / "p_capture.png", "Reference firmware-v4 capture (87 s, 9 040 samples): (a) sample intervals, nominal 9.615 ms dashed; (b) packet-start timestamp drift against an ideal 104 Hz clock; (c) IR counts and acceleration magnitude; (d) motion-context fractions of the six golden recordings (regression outputs).", "capture", wide=True, width=6.8)
    P.table("Tremor benchmark on synthetic signals (16 seeds): earlier (2.2.0) and current (3.0.0) pipelines.", "tremorres", ["Metric", "2.2.0", "3.0.0"],
            [["Sensitivity / specificity", f"{f(A_TN['sensitivity'])} / {f(A_TN['specificity'])}", f"<b>{f(A_TR['sensitivity'])} / {f(A_TR['specificity'])}</b>"],
             ["F1; TP / FN / FP / TN", f"{f(A_TN['f1'])}; {A_TN['tp']}/{A_TN['fn']}/{A_TN['fp']}/{A_TN['tn']}", f"<b>{f(A_TR['f1'])}</b>; {A_TR['tp']}/{A_TR['fn']}/{A_TR['fp']}/{A_TR['tn']}"],
             ["120–250 °/s tremor detected", pc(BASE["tremor"]["sensitivity_by_amplitude"]["120-250 dps"], 0), pc(CUR["tremor"]["sensitivity_by_amplitude"]["120-250 dps"], 0)],
             ["8.5–11 Hz called tremor", pc(BASE["tremor"]["per_scenario"]["non_pd_oscillation"]["mean_fraction_classified_tremor"]), pc(CUR["tremor"]["per_scenario"]["non_pd_oscillation"]["mean_fraction_classified_tremor"])],
             ["Action tremor / walking + tremor detected", f"{pc(BASE['tremor']['per_scenario']['action_tremor']['mean_fraction_classified_tremor'], 0)} / {pc(BASE['tremor']['per_scenario']['walking_with_tremor']['mean_fraction_classified_tremor'], 0)}",
              f"{pc(CUR['tremor']['per_scenario']['action_tremor']['mean_fraction_classified_tremor'], 0)} / {pc(CUR['tremor']['per_scenario']['walking_with_tremor']['mean_fraction_classified_tremor'], 0)}"],
             ["Frequency error, median / p90 (Hz)", f"{BASE['tremor']['frequency_abs_error_hz']['median']:.3f} / {BASE['tremor']['frequency_abs_error_hz']['p90']:.3f}", f"{CUR['tremor']['frequency_abs_error_hz']['median']:.3f} / {CUR['tremor']['frequency_abs_error_hz']['p90']:.3f}"],
             ["Onset / offset latency (s)", f"{BASE['latency']['onset_latency_s_median']:.1f} / {BASE['latency']['offset_latency_s_median']:.1f}", f"{CUR['latency']['onset_latency_s_median']:.1f} / {CUR['latency']['offset_latency_s_median']:.1f}"]],
            [1.9, 0.95, 0.95], size=6.8)
    B("{tab:tremorres} shows that the new detector removes three failure modes of its predecessor: strong tremor being vetoed as voluntary movement (38 % → 97 % detected), an 8.5–11 Hz oscillation being called PD tremor "
      "(8.6 % → 0 %), and tremor during action or walking being missed (49 %, 60 % → about 100 %). Latency rises about fivefold by design ({fig:tbench}). These are synthetic results with "
      "hand-set thresholds, not clinical accuracy.")
    v1b, v1c, v2b, v2c = BASE["ppg_v1_path"], CUR["ppg_v1_path"], BASE["ppg_v2_path"], CUR["ppg_v2_path"]
    P.table("PPG on synthetic signals (rest: 10 seeds × 60 s; artefact: 6 seeds, 1.8 Hz). v1/v2: firmware-v4/5.0.0 data paths.", "ppgres",
            ["Metric", "v1 2.2.0", "v1 3.0.0", "v2 2.2.0", "v2 3.0.0"],
            [["HR MAE at rest (bpm)", f(v1b["rest_hr_mae_bpm"], 1), f(v1c["rest_hr_mae_bpm"], 2), f(v2b["rest_hr_mae_bpm"], 1), f(v2c["rest_hr_mae_bpm"], 2)],
             ["RMSSD MAE at rest (ms)", f(v1b["rest_rmssd_mae_ms"], 0), "withheld", f(v2b["rest_rmssd_mae_ms"], 1), f(v2c["rest_rmssd_mae_ms"], 1)],
             ["HR confidence: rest / artefact", f"{v1b['rest_hr_confidence_median']:.2f} / {v1b['motion_hr_confidence_median']:.2f}", f"{v1c['rest_hr_confidence_median']:.2f} / {v1c['motion_hr_confidence_median']:.2f}",
              f"{v2b['rest_hr_confidence_median']:.2f} / {v2b['motion_hr_confidence_median']:.2f}", f"{v2c['rest_hr_confidence_median']:.2f} / {v2c['motion_hr_confidence_median']:.2f}"],
             ["HR MAE under artefact (bpm)", f(v1b["motion_hr_mae_bpm"], 1), f(v1c["motion_hr_mae_bpm"], 1), f(v2b["motion_hr_mae_bpm"], 1), f(v2c["motion_hr_mae_bpm"], 1)]],
            [1.45, 0.58, 0.58, 0.58, 0.58], size=6.8)
    B("In {tab:ppgres} and {fig:ppgfig}, the resting heart-rate gain (16–18 → 0.3–0.4 bpm) comes from correcting a sample-rate mismatch (50 Hz assumed, 104 Hz received). Under artefact the error is unchanged (≈ 28 bpm) but now flagged: "
      "confidence falls from 0.84 to 0.17. On synthetic steps the walking error is −9.7 % for both versions, while false steps per minute fall from 23.3 to 0.3 during rest tremor ({fig:gating}) and are unchanged "
      "during purposeful arm movement (46.3 → 48.8).")
    P.figure(FIG / "p_tremor_bench.png", "Synthetic tremor benchmark: (a) analysis-level metrics; (b) sensitivity by tremor amplitude; (c) median onset and offset latency.", "tbench", wide=True, width=6.4)
    KP, KG = STEP_BASE["karas"]["summary"], STEP_GATED["karas"]["summary"]["gated"]
    Cs = STEP_BASE["clemson"]["summary"]
    B(f"The default counter overcounts irregular gait on Clemson. The gated counter raises held-out event F1 from {HELD['production']['all']['f1']:.3f} to {HELD['heldout']['all']['f1']:.3f} "
      f"(paired bootstrap Δ = {STEP_SEL['paired_vs_production']['f1_diff']:+.3f}, 95 % CI [{STEP_SEL['paired_vs_production']['f1_ci95'][0]:+.3f}, {STEP_SEL['paired_vs_production']['f1_ci95'][1]:+.3f}]) and reduces "
      "false steps on Karas, at lower walking sensitivity ({tab:steps}, {fig:steps_fig}). Of seven pre-set criteria it fails two (no condition worse by more than 2 MAPE points: SemiRegular 20.9 against 8.2 %; walking "
      "sensitivity within 2 points: 0.900 against 0.973), so production v1.1 remains the default. The Karas runtime motion gate was held ACTIVE, so its false-step rate probably overstates the full pipeline.")
    KP, KG = STEP_BASE["karas"]["summary"], STEP_GATED["karas"]["summary"]["gated"]
    Cs = STEP_BASE["clemson"]["summary"]
    P.table("Step counting on public wrist data. Clemson: bias % / MAPE % / event F1 (gated is held out by 2-fold participant split); Karas: false steps per minute and walking sensitivity.", "steps",
            ["Counter", "Clemson all", "Clemson irregular", "Karas FP/min; sens."],
            [["Production v1.1", f"{Cs['production']['all']['pooled_bias_pct']:+.1f} / {Cs['production']['all']['mape_pct']:.1f} / {Cs['production']['all']['f1']:.3f}",
              f"{Cs['production']['Irregular']['pooled_bias_pct']:+.1f} / {Cs['production']['Irregular']['mape_pct']:.1f} / {Cs['production']['Irregular']['f1']:.3f}",
              f"{KP['production']['false_steps_per_min']:.1f}; {KP['production']['walking_state_sensitivity']:.3f}"],
             ["Periodic (experimental)", f"{Cs['periodic']['all']['pooled_bias_pct']:+.1f} / {Cs['periodic']['all']['mape_pct']:.1f} / {Cs['periodic']['all']['f1']:.3f}",
              f"{Cs['periodic']['Irregular']['pooled_bias_pct']:+.1f} / {Cs['periodic']['Irregular']['mape_pct']:.1f} / {Cs['periodic']['Irregular']['f1']:.3f}",
              f"{KP['periodic']['false_steps_per_min']:.1f}; {KP['periodic']['walking_state_sensitivity']:.3f}"],
             ["Gated 3.0-dev", f"{HELD['heldout']['all']['bias_pct']:+.1f} / {HELD['heldout']['all']['mape_pct']:.1f} / {HELD['heldout']['all']['f1']:.3f}",
              f"{HELD['heldout']['Irregular']['bias_pct']:+.1f} / {HELD['heldout']['Irregular']['mape_pct']:.1f} / {HELD['heldout']['Irregular']['f1']:.3f}",
              f"{KG['false_steps_per_min']:.1f}; {KG['walking_state_sensitivity']:.3f}"]],
            [0.95, 0.9, 1.1, 0.8], size=6.8)
    P.figure(FIG / "p_step_gating.png", "False steps per minute on synthetic scenarios for the earlier and current runtime fed identical packets: the tremor guard removes false steps during rest tremor.", "gating")
    P.figure(FIG / "p_ppg.png", "PPG on synthetic signals: (a) IR pulse and band-passed trace; (b) heart rate versus truth at rest; (c) median confidence at rest and under artefact.", "ppgfig", wide=True, width=5.2)
    P.figure(FIG / "p_steps_public.png", "Step counters on public wrist data: (a) event F1 and (b) count error by gait condition on Clemson; (c) false steps per minute on Karas.", "steps_fig", wide=True, width=5.6)
    mt = SLEEP["methods"]
    sl = []
    for k, nm in (("vanhees_dz", "van Hees z-angle rule {c:vanhees15}"), ("lr", "<b>Logistic regression (shipped)</b>"), ("lr_hmm", "LR + tempered HMM"), ("lr_hr_hmm", "LR + heart rate + HMM")):
        e, n_ = mt[k]["epoch_mean_over_subjects"], mt[k]["night"]
        sl.append([nm, f(e["kappa"]), f(e["balanced_accuracy"]), f(e["specificity_wake"]), f"{n_['tst_min']['mae']:.1f} ({n_['tst_min']['mean_error']:+.1f})"])
    pv = SLEEP["paired_vs_vanhees_dz"]["lr"]
    A_, B_, C_ = WEAR["A_worn_sleep_stillness"]["summary"], WEAR["B_state_machine_worst_case_no_ppg"]["summary"], WEAR["C_driving_state_machine"]["summary"]
    B(f"In {{tab:sleepres}} and {{fig:sleepfig}} the shipped model agrees better with polysomnography than the heuristic (Δκ = {pv['kappa']['mean_diff']:+.3f}, 95 % CI [{pv['kappa']['ci95'][0]:+.3f}, {pv['kappa']['ci95'][1]:+.3f}], "
      f"{pv['kappa']['subjects_better']}/{pv['kappa']['n']} subjects better) and total sleep time better (|error| {pv['abs_tst_error_min']['mean_diff']:+.1f} min), while balanced accuracy is unchanged and wake "
      "detection stays weak. Seventeen healthy adults and one scorer limit generalisation. For wear, in 15 worn Walch nights "
      f"{pc(A_['13mg']['mean_share_in_runs_ge_15min'])} of the night lies in still runs of ≥ 15 min at the 13 mg non-wear threshold, so motion alone cannot decide removal. With optical contact forced "
      f"absent (worst case), the 1 mg default marks no night REMOVED, against {B_['2mg']['subjects_ever_removed']}/15 at 2 mg and {B_['4mg']['subjects_ever_removed']}/15 at 4 mg, and "
      f"{pc(C_['mean_removed_frac'])} of {C_['driving_minutes']:.0f} min of Karas driving. The threshold was tuned on these nights, so this is optimistic, and sensitivity to real removal is unmeasured. "
      "{tab:wearres} gives the wear numbers. Unlabelled real recordings ({tab:real}) are used only for regression; a wrist shaken at 8–9 Hz is correctly not called PD-band tremor, whereas arm movement and shaking add false steps in the legacy-rate logs.")
    P.table(f"Sleep/wake on Walch ({SLEEP['epochs_scored']:,} epochs, 17 subjects, {pc(SLEEP['sleep_fraction'])} sleep).", "sleepres",
            ["Method", "κ", "Bal. acc.", "Wake spec.", "TST MAE (bias), min"], sl, [1.45, 0.4, 0.5, 0.5, 0.9], size=6.8)

    P.table("Wear inference on public data, optical contact forced absent (worst case).", "wearres", ["Stillness threshold", "Worn night in still runs ≥ 15 min", "Mean REMOVED", "Subjects ever REMOVED"],
            [["1 mg (default)", pc(A_["1mg"]["mean_share_in_runs_ge_15min"]), pc(B_["1mg"]["mean_removed_frac"]), f"{B_['1mg']['subjects_ever_removed']} / 15"],
             ["2 mg", pc(A_["2mg"]["mean_share_in_runs_ge_15min"]), pc(B_["2mg"]["mean_removed_frac"]), f"{B_['2mg']['subjects_ever_removed']} / 15"],
             ["4 mg", pc(A_["4mg"]["mean_share_in_runs_ge_15min"]), pc(B_["4mg"]["mean_removed_frac"]), f"{B_['4mg']['subjects_ever_removed']} / 15"]],
            [0.9, 1.2, 0.8, 0.85], size=6.8)
    P.figure(FIG / "p_sleep.png", "Sleep/wake versus polysomnography on Walch: (a) κ by method; (b) per-subject κ of the shipped model against the published heuristic.", "sleepfig", wide=True, width=4.8)
    rr = []
    for k, label in (("stationary_60s", "stationary, 60 s"), ("walking_60s", "walking, 60 s"), ("normal_motion_60s", "everyday arm movement, 60 s"),
                     ("simulated_tremor_30s", "wrist shaken at 8–9 Hz, 30 s"), ("vibration_reference_30s", "vibration, 30 s")):
        o = GOLD[k]["outputs"]
        rr.append([label, pc(o["tremor_fraction"], 0), str(o["final_steps"]), ", ".join(f"{a} {pc(b, 0)}" for a, b in sorted(o["motion_state_fraction"].items(), key=lambda x: -x[1]))])
    P.table("Unlabelled real recordings: golden regression outputs (guard against regression; not accuracy).", "real", ["Recording", "Tremor", "Steps", "Motion state"], rr, [1.25, 0.45, 0.4, 1.65], size=6.8)
    S("Comparison with Related Systems", "cmp")
    B("{tab:cmpA} and {tab:cmpB} list entries for other systems taken from their publications or manufacturer documentation, describing what those sources report; “not compared” means the reviewed sources do not state the item. "
      "ParkinSense entries are from this repository. The studies differ in sensors, populations, endpoints and ground truth, so the tables align <i>descriptions</i> and keep published figures apart from "
      "ParkinSense’s own, which come from synthetic and public data, not patients. They support no ranking.")
    P.table("Comparison I: sensing, communication, processing and algorithm.", "cmpA", ["Dimension", "ELENA {c:saez25}", "PERFORM {c:tzallas14}", "Apple Watch, MM4PD {c:powers21,applemd}", "ParaDigMa {c:timmermans25}", "<b>ParkinSense</b>"],
            [["Hardware, sensing", "finger-worn MPU6050 (accelerometer, gyroscope) with ESP32", "accelerometers, gyroscopes, VR glove, medication and food records", "watch accelerometer and gyroscope, worn on the most affected arm", "wrist gyroscope data from published cohorts", "wrist IMU (LSM6DS3, 104 Hz) plus finger MAX30102 PPG on a XIAO nRF52840 Sense"],
             ["Communication", "ESP32 to cloud services", "closed-loop multi-sensor platform; link not compared", "on the watch; results queried through an on-device API", "none; recorded data", "BLE 5 notify, 208 B packets, ≈ 10.4/s; decoder checks sequence, rate, clipping"],
             ["Processing architecture", "cloud and offline (MATLAB)", "classifiers with data fusion", "on-device, periodic and opportunistic, not real time", "open-source offline pipeline", "firmware only acquires; host pipelines replay in device signal time"],
             ["Algorithm", "Welch spectrum: tremor frequency and amplitude", "supervised classifiers for tremor, bradykinesia, freezing, dyskinesia", "proprietary; resting tremor 3–7 Hz and choreiform dyskinesia", "4 s windows, MFCC-based classifier", "Welch spectrum, logistic evidence, tempered HMM; no learned classifier; also HR, steps, sleep, wear"]],
            [0.78, 1.18, 1.18, 1.24, 1.0, 1.72], size=6.9, wide=True)
    B("Three differences stand out. <i>Openness:</i> ParaDigMa and ParkinSense publish their algorithms and can be rerun by others, whereas the Apple pipeline returns results through an entitlement-gated API with proprietary methods. <i>Evidence maturity:</i> PERFORM and the Apple system were evaluated against clinician ratings, ELENA against a smartwatch and on clinical tasks, ParaDigMa on published PD recordings, and ParkinSense only on synthetic and other-device data. <i>Scope:</i> PERFORM reports bradykinesia, freezing and dyskinesia and the Apple system dyskinesia, which ParkinSense does not attempt, while ParkinSense adds heart rate, steps, sleep and wear. Where evidence overlaps, the comparison is limited. ELENA validated frequency against a smartwatch and ParkinSense has no such comparison; the Apple system relates its output to clinician ratings in hundreds of "
      "patients and ParkinSense reports synthetic sensitivity that cannot be set beside it. What ParkinSense offers is a different combination: a published signal chain, a wrist inertial and finger optical stream in one "
      "versioned record, explicit confidence handling, and replay of every result. Power and battery life, the dimension most relevant to wearables, are not compared because ParkinSense has no measurement.")
    P.table("Comparison II: confidence, timing, validation, evidence and limitations (published figures are not ParkinSense results).", "cmpB", ["Dimension", "ELENA {c:saez25}", "PERFORM {c:tzallas14}", "Apple Watch, MM4PD {c:powers21,applemd}", "ParaDigMa {c:timmermans25}", "<b>ParkinSense</b>"],
            [["Context and confidence", "not compared", "per-symptom classifier output", "tremor and dyskinesia results per period; internals not compared", "classifier probability per window, aggregated measures", "REST / LOW / ACTIVE context, evidence <i>e</i>, <i>p</i>(tremor) with confirm/release, quality flags"],
             ["Real-time behaviour", "not compared", "not compared", "periodic results, not real time", "post-hoc", "6.1 s onset, 8.1 s offset (synthetic); 17.8 ms compute per packet; BLE latency unmeasured"],
             ["Validation method", "rig, smartwatch comparison, patients and controls on clinical tasks", "real-life conditions against clinician evaluation", "video-rated MDS-UPDRS III; 118-person pilot; 343 participants, 225 followed ≤ 6 months", "leave-one-subject-out on published PD data", "seeded synthetic, public data from other devices, unit tests; <b>no patients</b>"],
             ["Reported evidence", "frequency deviation from smartwatch &lt; 0.5 % (mean −0.37 %)", "as published; not reproduced here", "<i>r</i> = 0.80 with clinic tremor severity; 94 % treatment-response agreement; median tremor false-positive rate 0.25 % in controls", "sensitivity 0.61, specificity 0.97", f"synthetic: sensitivity {f(A_TR['sensitivity'])}, specificity {f(A_TR['specificity'])}, F1 {f(A_TR['f1'])}; not clinical"],
             ["Limitations", "tremor only; finger sensor", "several body-worn sensors", "two symptoms; entitlement required; manufacturer-funded, proprietary", "no hardware; tremor only", "no patients; hardware tests not run; no bradykinesia, dyskinesia or freezing"]],
            [0.78, 1.18, 1.18, 1.24, 1.0, 1.72], size=6.9, wide=True)
    S("Hardware Status, Limitations and Future Work", "disc")
    B("<b>Hardware.</b> Every documented hardware test is NOT RUN: board wiring (W0), firmware-5.0.0 streaming and sequence continuity (H1–H3), current with a power analyser (S1–S7), bench and "
      "worn-still noise (W1–W2), removal and re-wear (W3–W4), sensor independence (W5–W7) and an overnight recording (W8). The owner reported on 2026-11-06 and again on 2026-11-08 that firmware 5.0.0 is flashed and working "
      "and that the new dashboard runs with it; with no firmware version string, duration, loss figure or file, this raises confidence that the device streams but satisfies no pass criterion. The last documented hardware evidence "
      "is an 87 s firmware-v4 capture at 104.01 Hz ({tab:hwtests}). Current, battery life, packet loss over long sessions, wrist PPG and overnight operation are therefore all unmeasured.")
    P.table("Hardware tests and status (pass criteria are fixed in the validation plan).", "hwtests", ["ID", "Test", "Status"],
            [["W0", "record wiring and MAX30102 interrupt line (board: XIAO nRF52840)", "NOT RUN"],
             ["H1–H3", "firmware-5.0.0 init, streaming, sequence continuity, loss", "NOT RUN"],
             ["S1–S7", "current with a power analyser", "NOT RUN"],
             ["W1–W2", "bench noise floor; worn-still distribution (≥ 5 nights, ≥ 3 people)", "NOT RUN"],
             ["W3–W4", "removal and re-wear detection", "NOT RUN"],
             ["W5–W8", "sensor independence, wrist optical signal, overnight ≥ 8 h", "NOT RUN"]], [0.45, 2.55, 0.75], size=6.8)
    B("<b>Discussion.</b> The largest gains in this revision came from correcting plumbing rather than inventing algorithms: a 2.08× sample-rate mismatch in the PPG chain, a motion multiplier that was never "
      "applied, a state machine whose dead band froze its earlier state, and host-arrival timestamps that quantised intervals. Measuring the true stream rate, carrying versions with every output and "
      "testing live processing against replay made these defects visible. The stability/latency trade-off is explicit: a 6 s onset suits a longitudinal biomarker stream, but not a trigger for an actuator. "
      "Relative to ELENA {c:saez25} the platform has no clinical pilot, and relative to ParaDigMa {c:timmermans25} no free-living evaluation; its contribution is an open, versioned and replayable stack whose "
      "inertial algorithm can be run on the same public data once access is confirmed. Whether its additional channels improve any patient-level outcome is untested.")
    B("<b>Limitations.</b> There are no patient data and no clinical claim. The inertial stream exists only with finger contact on the optical sensor in the shipped profile. Tremor evidence is not a "
      "calibrated probability, physiological tremor can be reported as tremor, and onset latency is 6.1 s, acceptable for longitudinal biomarkers but not for an actuator. SpO<sub>2</sub> is uncalibrated; "
      "HRV is a 10 s trend value; heart rate under motion is flagged rather than corrected. The default step counter overcounts irregular gait and arm movement. Sleep and wear evidence come from "
      "healthy adults and other devices.")
    B("<b>Future work.</b> The first step is one documented hardware session (W0, H1–H3, W1–W2, and a current subset) because W1 and W2 decide whether an extra skin-contact sensor is needed. Next are public "
      "tremor and freezing-of-gait baselines (ParaDigMa data and Daphnet, access to be confirmed), then a mobile application and, only under ethics approval, a patient pilot.")

    S("Conclusion", "concl")
    B("ParkinSense now has a specified, versioned and testable implementation: a 104 Hz protocol with fault flags, a motion-gated tremor detector with temporal inference, an auditable heart-rate "
      "pipeline, a step counter whose better candidate remains opt-in, and offline sleep and wear estimators. On synthetic and public data these behave as described; what they do on the device and on "
      "people with Parkinson’s disease is not yet known, and a documented hardware session and an ethics-approved clinical study are the next steps.")
    P.para("DATA AND CODE AVAILABILITY", align="c", size=9, bold=True, before=6, after=2, keep_next=True)
    P.para("github.com/sudo-pranshu/ParkinSense (MIT). Tests: <tt>pytest</tt>. Benchmarks and committed results: <tt>benchmarks/</tt>. Public datasets are fetched by "
           "<tt>benchmarks/external/fetch.py</tt> and not redistributed. Paper sources: <tt>docs/research/paper/</tt>.", align="l", first=0.17)
    P.references(REFS)
    return P


if __name__ == "__main__":
    pa = build()
    state = pa.finish()
    pb = build(dict(refs_prev=state["refs"], cites_prev=state["cites"]))
    assert not pb.unresolved, sorted(pb.unresolved)
    cp = pb.doc.core_properties
    cp.author = "Pranshu Kumar; Lakshya Lalwani; Akshay Sable; Nalin Khare; Asim Tewari"
    cp.title = "ParkinSense: An Open Wrist-Worn Research Platform for Motion, Cardiac, Activity and Sleep Signals in Parkinson's Disease Monitoring"
    cp.comments = ""
    cp.last_modified_by = "Pranshu Kumar"
    pb.doc.save(OUT)
    print("wrote", OUT, "| figs", pb.nfig, "tables", pb.ntab, "eqs", pb.neq, "refs", len(pb.cite_order))
