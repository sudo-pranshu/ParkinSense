# External reference datasets

Used only by `benchmarks/sleep_bench.py` and `benchmarks/steps_bench.py`. Nothing is committed:
`python -m benchmarks.external.fetch walch|clemson|karas` downloads into `data/external/`
(git-ignored). These are **public wrist datasets from other devices**; results on them are not
ParkinSense hardware results.

| Dataset | Used for | Licence | Canonical source | What was actually fetched here |
|---|---|---|---|---|
| Walch 2019, *Motion and heart rate from a wrist-worn wearable and labeled sleep from polysomnography* (PhysioNet `sleep-accel` 1.0.0), doi 10.13026/hmhs-py35 | sleep/wake vs PSG | ODC-By 1.0 | physionet.org | Labels and heart rate from a GitHub mirror, **verified against the upstream `SHA256SUMS.txt`**. Acceleration files from two other mirrors (checked against the same sums where listed). 18 of 31 subjects available; one excluded for < 50 % accelerometer coverage, **17 scored**. |
| Karas 2021, *Labeled raw accelerometry data captured during walking, stair climbing and driving* (PhysioNet 1.0.0), doi 10.13026/51h0-a262 | walking-state sensitivity, false steps during driving/clapping | ODbL 1.0 | physionet.org | GitHub mirror, 27 of 32 subjects. No hash list available: integrity not independently verified. |
| Clemson pedometer evaluation, Mattfeld, Jesch, Hoover, IEEE BIBM 2017, doi 10.1109/BIBM.2017.8217769 | step count and event accuracy | upstream project terms; not redistributed | cecas.clemson.edu/~ahoover/pedometer | A **third-party prepared copy** (`ChaddBrenner/mattfeld_research_data`) in which channels are min-max normalised over all participants. We re-calibrate each channel to g by an affine fit on the least-variable 1 s windows pooled over all 90 files (`reference.autocalibrate`). 90 files = 30 participants x 3 conditions. Gyroscope unused. Calibration error is an unquantified source of step-count error. |

Not available from the build environment (network allow-list: GitHub and PyPI only): PhysioNet,
NSRR/MESA (the large external sleep test set used by Walch et al.), Zenodo, figshare,
Clemson, Oxford. **No MESA, no OxWalk, no Newcastle PSG results are claimed anywhere.**

Reference-label caveats, per dataset:

* Walch: single-scorer PSG; 90.5 % of scored epochs are sleep, so accuracy is inflated by prevalence. Report kappa and
  balanced accuracy; 17 subjects is a small sample, healthy adults, one night each.
* Clemson: foot contacts annotated on video; the wrist sensor runs at 15 Hz (ParkinSense: 104 Hz), so spectral content
  above 7.5 Hz is absent and counters are run on a linearly up-sampled signal.
* Karas: no step events. Activity labels only; `4` driving and `77` clapping are the "non-walking" class.
