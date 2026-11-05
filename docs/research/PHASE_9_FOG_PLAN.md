# Phase 9 task 2: freezing of gait (Daphnet) — plan and pre-registered criteria

Status: **prepared, not run.** Daphnet has not been downloaded (the build environment reaches only GitHub and PyPI). FoG
stays **experimental** unless §4 is satisfied. Criteria are fixed here before any held-out evaluation; later changes go
in the amendment list with a reason.

## 1. Dataset

| Item | Verified from the UCI page | To verify on download |
|---|---|---|
| Source | <https://archive.ics.uci.edu/dataset/245/daphnet+freezing+of+gait>, doi 10.24432/C56K78, Roggen, Plotnik, Hausdorff (2010) | |
| Licence | **CC BY 4.0** (credit required) | |
| Access | open; 20.5 MB zip `https://archive.ics.uci.edu/static/public/245/daphnet+freezing+of+gait.zip`; also `ucimlrepo` id 245 | record SHA-256 of the zip |
| Files | 29 data files named like `S01R01` | subject count, runs per subject, which subjects have no freezes |
| Sensors, placement | 3 tri-axial accelerometers: ankle (shank), upper leg (thigh), trunk; units mg | axis/column order and **sampling rate** (not on the page; read the dataset readme before coding any filter) |
| Labels | `0` not part of the experiment, `1` experiment without freeze, `2` freeze | label timing resolution |
| Population | people with Parkinson's disease and freezing of gait, scripted walking tasks | no gyroscope, no wrist sensor |

**Owner action:** download the zip on a machine with normal internet, put it in `data/external/daphnet/` (not
committed), run `sha256sum`, and send the readme text plus the hash. I cannot fetch it here.

## 2. Transfer caveat

Daphnet sensors are at the shank, thigh and trunk. ParkinSense is a wrist device and the Daphnet data has no wrist or
gyroscope channel. A Daphnet result evaluates a **published method on Daphnet's placement**; it says nothing about wrist
FoG detection. It is a benchmark for the infrastructure and the published baseline, not evidence that ParkinSense
detects freezing. Any wrist-based FoG claim needs wrist data with FoG labels, which is not in hand.

## 3. Procedure

1. Loader and manifest: original files untouched, SHA-256 per file, subject/run IDs preserved, native rate recorded;
   unlabelled (`0`) segments excluded from scoring and counted, not silently dropped.
2. Baseline: the published threshold method of the dataset authors (Bächlin et al. 2010; freeze index as I recall it:
   power in a 3–8 Hz freeze band over a 0.5–3 Hz locomotor band, with a power threshold). **Recalled, not re-read:** the
   constants and the exact rule must be taken from the paper before coding; if they cannot be confirmed the report says
   "re-implementation, constants differ".
3. Subject-independent evaluation: leave-one-subject-out; thresholds/hyper-parameters fitted on training subjects only.
   Subjects without any freeze contribute false alarms only and are listed.
4. Candidates (classical features, small learned models) only after the baseline is reproduced; nested LOSO.

## 4. Pre-registered metrics and criteria

Windowing and event definitions are fixed before running: window labelled freeze if ≥ 50 % of its samples are `2`
(sensitivity of this rule is reported); an **event** is a maximal run of `2`; an event is detected if ≥ 1 detected window
overlaps it; latency = detection time − event onset. Metrics per subject, mean ± SD, participant-clustered bootstrap
95 % CI: window sensitivity, specificity, F1; event sensitivity; event detection latency; false alarms per hour of
walking (`1`) time.

| ID | Criterion | If not met |
|---|---|---|
| F1 | Baseline reproduced: LOSO event sensitivity and specificity reported next to the published figures with differences explained | report "not reproduced"; use own numbers |
| F2 | A candidate beats the baseline: paired CI of event-sensitivity difference lower bound > 0 and false alarms/hour not higher | no demonstrated difference |
| F3 | FoG leaves "experimental": F2, plus ≥ 1 independent FoG dataset or hardware recording with the **wrist** placement, plus end-to-end runtime integration | stays experimental, not shown as a biomarker |

## Amendments

(none)
