# ParkinSense paper: final revision report

Files: `ParkinSense_Research_Paper_Revised.docx` / `.pdf` (10 pages, two-column IEEE layout), built by `paper/build_revised.py`. Figures: `paper/make_figures.py` (existing) and `paper/make_figures_v2.py` (new). Every PDF page was rendered and inspected; the largest blank band at a page bottom is 0.8 in (the last page ends with the reference list).

## What changed
- Figure 1 (status matrix), its caption and references removed; its content stays in Sections III, VII and VIII (firmware status, hardware tests, evidence classes). `IMPLEMENTATION_STATUS_MATRIX.md` stays in the repository.
- 7 pages → 10 pages. Added 9 figures, 3 tables and a comparison section; every earlier chart and plot is kept (spectra, HMM, tremor benchmark, step gating, PPG, public step data, sleep, wear states).
- Equations, parameters and all numbers are unchanged and were taken from `benchmarks/results/*.json`, `tests/regression/golden.json` and the 2026-11-08 test run (141 passed, 1 deselected).

## Figures (source of each)
| Fig. | Content | Source |
|---|---|---|
| 1 | System architecture | existing diagram, label overlaps fixed |
| 2 | Wrist photo, strap + enclosure + electronics | `docs/images/prototype_hand.jpg`, `prototype_only.jpg` (uncropped) |
| 3 | Dashboard, no tremor (overview) and tremor analytics | `docs/images/dashboard2_overview.png`, `dashboard2_tremor.png` (current dashboard; cropped to remove the sidebar) |
| 4 | Acquisition, BLE streaming, decoding, packet layout | redrawn from firmware and protocol code |
| 5 | Dashboard and logging architecture | redrawn from `runtime/` |
| 6 | Live-monitoring page | `docs/images/dashboard2_live.png` |
| 7 | Motion, PPG and step pipelines | redrawn from code and parameters |
| 8–9 | Spectra, HMM posterior | existing, from repo code |
| 10 | Cross-pipeline gating and fusion | redrawn from `runtime/engine.py` |
| 11 | Wear-state model | existing |
| 12 | Reference BLE capture: sample intervals, packet-start drift, IR and acceleration, motion-context fractions | `data/reference/ble_v1_104hz/*.csv`, `tests/regression/golden.json` |
| 13–17 | Tremor benchmark, step gating, PPG, public steps, sleep | existing |

Older dashboard screenshots (`dashboard_normal.jpg`, `dashboard_tremor.jpg`) are not used, as instructed.

## Comparison section (VII)
Two tables align ELENA, PERFORM, the Apple Watch pipeline (MM4PD and the Movement Disorder API), ParaDigMa and ParkinSense over: hardware and sensing, communication, processing architecture, algorithm, context and confidence, real-time behaviour, validation method, reported evidence, limitations. Published figures are kept apart from ParkinSense's own; no ranking or superiority claim is made. Sources added: Powers et al., Sci. Transl. Med. 2021 (doi 10.1126/scitranslmed.abd7865) and Apple's CMMovementDisorderManager documentation; ELENA (Sensors 2025, doi 10.3390/s25092763; LACCEI 2024), PERFORM (Sensors 2014), ParaDigMa were already cited.

## Items requested but not available (stated in the paper, not invented)
- **Clinical-style dashboard:** none exists; the paper says the pages are engineering views.
- **Dashboard screenshots are from the built-in simulated stream** (the SIMULATED banner is visible) and are captioned as such; no screenshot of live wearable data exists in the repository.
- **Photographs:** only two exist (worn; strap, enclosure and electronics). No internal-electronics close-up or sensor-placement photograph exists. The board visible in the open-enclosure photo is a sizing stand-in (silkscreen reads a different board); the caption says so, and the documented target is the XIAO nRF52840 Sense.
- **Power and battery plots:** no measurement exists (hardware tests S1–S7 NOT RUN); none is plotted.
- **BLE streaming performance:** the only evidence is one 87 s firmware-v4 capture with device timestamps (104.004 Hz, no interval above 13.1 ms, packet-start timestamps within ±7.2 ms of an ideal clock). Protocol v1 has no sequence number, so host-side loss and BLE latency are not measured.
- **Motion-context plot:** shows context fractions of the six regression recordings, which have no per-window ground truth; labelled regression outputs, not accuracy.
- **Tremor, PPG and step plots:** synthetic and public-data results only; no patient data.

## Verification
- Every number was checked against the result JSONs and golden file by the builder's assertions; unresolved cross-reference tokens fail the build.
- Figure and table references all resolve (17 figures, 13 tables, 37 references). No mention of other projects or ventures.
- Statements about other systems follow their papers or manufacturer documentation. The Apple figures (r = 0.80; 94 % treatment-response agreement; 343 participants, 118-person pilot, 225 followed ≤ 6 months; median tremor false-positive rate 0.25 % in controls) come from the published abstract and journal-press coverage of it; re-check against the full text before submission.
- Reference volume and page details for ParaDigMa (npj Parkinson's Disease, 2025) should be re-confirmed before submission.

## Risks
- LibreOffice renders the PDF; Word may paginate slightly differently, and equations render with LibreOffice's OMML engine.
- Screenshot text is small at column and full-page width; the captions describe the content.
