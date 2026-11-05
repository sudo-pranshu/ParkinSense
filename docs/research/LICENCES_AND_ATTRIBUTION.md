# Licences and attribution — sleep and step work

Rule applied: **no third-party code was copied.** The sleep and step implementations are written from the
published mathematics. Where a reference repository's licence forbids reuse, its code was not read into this
implementation. Licences below were read from the repositories' LICENSE files during this work (cloned for
inspection only); papers were read via their public text.

| Source | What we used | Licence (as read) | How it is used here |
|---|---|---|---|
| van Hees et al. 2015 (PLoS ONE) and GGIR (wadpac/GGIR) | sustained-inactivity rule (5°/5 min) as a published method | GGIR: Apache-2.0 | Re-implemented from the paper's description; attribution in `docs/research/SLEEP_ALGORITHMS.md` and `sleep/model.py` |
| van Hees et al. 2018 (Sci Rep) HDCZA | sleep-period merge idea (gap < 60 min, block ≥ 30 min) | GGIR: Apache-2.0 | Simplified re-implementation (`sleep/night.py`); not the full HDCZA |
| Walch et al. 2019, PhysioNet `sleep-accel` | validation data (labels, heart rate, acceleration) | ODC-By 1.0 | Downloaded at run time, not redistributed; cite doi 10.13026/hmhs-py35 |
| `ojwalch/sleep_classifiers` | compared against only in the literature | MIT | no code used |
| Karas et al. 2021, PhysioNet | validation data | ODbL 1.0 | Downloaded at run time, not redistributed; doi 10.13026/51h0-a262 |
| Clemson pedometer evaluation, Mattfeld et al. 2017 | validation data | upstream project terms | A third-party prepared copy, downloaded at run time, not redistributed |
| Verisense step algorithm (Shimmer / Rowlands et al. 2022) | design reference for the existing `step_counter_periodic.py` | MIT (repo file, copyright Shimmer 2020) | the repo's counter is an independent implementation; not copied |
| `OxWearables/asleep`, `OxWearables/stepcount` | literature only | **Oxford Academic Use Licence** | **not used**; code and weights excluded |
| `onnela-lab/forest` (oak) | literature only | BSD-3-Clause | not implemented, no code used |
| `pfizer-opensource/scikit-digital-health` | not used | MIT | none |
| `actigraph/Sleep-Wake-Classification` | literature (Patterson 2023) | MIT | none |

Software dependencies added by this work: none at runtime (NumPy/SciPy/pandas already required). `scikit-learn` is used
only optionally by `benchmarks/sleep_bench.py` for the random-forest reference and is not a dependency of the package.

A note on an earlier docstring: `step_counter_periodic.py` cites "an MIT-licensed reference in the `walking` R package";
the MIT licence verified here is that of Shimmer's `Verisense-Toolbox`. The `walking` package was not checked.
