# ParkinSense paper: revision report (2026-11-08)

Deliverables: `ParkinSense_Research_Paper_Revised.docx` and `.pdf` (7 pages, IEEE two-column, US Letter). Built by `paper/build_revised.py` from the repository evidence. The 16-page version (`ParkinSense_paper.docx/.pdf`) is kept as the extended manuscript.

## Removed or consolidated
- **Figure 1 and the status matrix removed**, with its caption, its explanatory paragraph and all references to it. The 20-row status table was dropped too, as it duplicated the matrix. Its content is kept as a short evidence-class table (Table I), hardware status (Table XII) and the Hardware/Limitations section. `docs/research/IMPLEMENTATION_STATUS_MATRIX.md` stays in the repository.
- Sections reduced from 21 to 8: Introduction; Related Work; System, Firmware and Data Integrity; Signal-Processing Algorithms (tremor, PPG, steps/sleep/wear/baselines); Evaluation Methodology; Results; Hardware Status, Limitations and Future Work; Conclusion.
- Related work condensed to one paragraph and one 4-row table. Hardware, firmware, protocol and integrity merged. Biomarker aggregation, wear and sleep descriptions shortened to implementation-specific details. The cross-pipeline table and the earlier 20-item limitation list were folded into text.
- Figures: 16 → 9 (architecture, spectra, HMM, wear states, tremor benchmark, false-step gating, PPG, step counters on public data, sleep). Removed: packet layout, scenarios, photographs, dashboard screenshots (illegible at column width), timeline, wear-data, status matrix. Tables: 18 → 13; equations: 14 → 10.
- Caption lengths cut. Every figure and table is cited in the text.

## Writing and originality
- Text rewritten from the repository's own implementation and decisions. Source-derived ideas stay cited (Welch, Gaussian peak interpolation, HMM, ParaDigMa aggregation, van Hees, TROIKA, HRV standards). No citation was removed to lower similarity.
- No similarity or AI-detection tool was available here, and no pass is claimed. Passages closest to the literature (ParaDigMa and ELENA descriptions) are paraphrased and cited; the authors should run their institutional checker.

## Layout fixes
- Tables are atomic (nested in a single non-splittable row), so none splits across columns or pages. All pages checked for bottom gaps (≤ 0.5 in on pages 1–6; page 7 is the reference list, which ends mid-column).
- Wide figures placed so they do not leave blank bands; equation (5)–(7) split to fit the column; figure legend that overlapped bars fixed; stray `{TABLE}` token fixed; figure and table order now matches first citation.
- Page count is rendered by LibreOffice. Word may shift line breaks slightly.

## Claims checked against evidence
All numbers are read from `benchmarks/results/*.json`, `tests/regression/golden.json` and `docs/research/evidence/test_run_20261108.txt`, or are recomputed and asserted in the build script (HMM worked example 0.0509 → 0.763 → 0.839, K = 3 Welch segments, 0.1016 Hz bin spacing, ≈ 0.83 Hz step high-pass, 10.4 packets/s). Test count 141 passed, 1 deselected. The board is stated as Seeed XIAO nRF52840 Sense throughout (photos are not used to identify it). Evidence classes (test, synthetic, public data, hardware, clinical) stay separate; every hardware test is marked NOT RUN; the owner-reported informal test is stated as not counted.

## Unresolved
- Hardware tests H, W and PPK2 have not been run; firmware 5.0.0 is not compiled for target or flashed.
- No patient data; no clinical claim. PD@Home and Daphnet access unconfirmed.
- Reference volume/page details without a DOI (e.g. Timmermans 2025 volume, Charlton 2022) should be re-confirmed before submission.
- Text and arithmetic were checked by script and by reading every rendered page; no separate reviewer has read the paper.
