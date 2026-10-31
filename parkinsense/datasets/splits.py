"""
Leakage-safe dataset splitting.

Consecutive analysis windows overlap by 87.5 % and windows from one person
share physiology, sensor placement and device. A random window-level split
puts near-identical windows on both sides and inflates every metric. Only
group-level splits are offered:

* group_split      -- each group (subject by default, else recording) lands
                      entirely in train or test;
* group_kfold      -- K folds over groups;
* leave_one_group_out -- the protocol used to validate ParaDigMa's tremor
                      classifier (leave-one-subject-out; Timmermans et al.,
                      npj Parkinson's Dis 2025).
* temporal_split   -- within a single recording only: train on the first part,
                      test on the last, with a guard gap of >= one window so no
                      window straddles the boundary.

`assert_no_leakage` is a hard check to run on any split before evaluating.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from parkinsense.config import WINDOW_SECONDS


def _groups(df, by):
    if by not in df.columns:
        raise KeyError(f"column {by!r} required for a group split")
    return df[by].astype(str)


def group_split(df: pd.DataFrame, test_fraction=0.25, by="subject_id", seed=0):
    g = _groups(df, by)
    uniq = np.array(sorted(g.unique()))
    if len(uniq) < 2:
        raise ValueError(f"need >= 2 distinct {by} values for a group split; got {len(uniq)}")
    rng = np.random.default_rng(seed)
    rng.shuffle(uniq)
    n_test = max(1, int(round(test_fraction * len(uniq))))
    test_g = set(uniq[:n_test])
    test = g.isin(test_g)
    return df[~test].copy(), df[test].copy()


def group_kfold(df: pd.DataFrame, k=5, by="subject_id", seed=0):
    g = _groups(df, by)
    uniq = np.array(sorted(g.unique()))
    if len(uniq) < k:
        raise ValueError(f"k={k} folds need >= {k} groups; got {len(uniq)}")
    rng = np.random.default_rng(seed)
    rng.shuffle(uniq)
    for fold in np.array_split(uniq, k):
        test = g.isin(set(fold))
        yield df[~test].copy(), df[test].copy()


def leave_one_group_out(df: pd.DataFrame, by="subject_id"):
    g = _groups(df, by)
    for grp in sorted(g.unique()):
        test = g == grp
        yield grp, df[~test].copy(), df[test].copy()


def temporal_split(df: pd.DataFrame, test_fraction=0.25, time_col="window_start_s",
                   guard_s=WINDOW_SECONDS):
    if df["recording_id"].nunique() != 1:
        raise ValueError("temporal_split is for a single recording; use group_split across recordings")
    t = df[time_col]
    cut = t.min() + (1 - test_fraction) * (t.max() - t.min())
    train = df[t + WINDOW_SECONDS <= cut]
    test = df[t >= cut + guard_s]
    return train.copy(), test.copy()


def assert_no_leakage(train: pd.DataFrame, test: pd.DataFrame, by="subject_id"):
    shared = set(train[by].astype(str)) & set(test[by].astype(str))
    if shared:
        raise AssertionError(f"{by} present in both train and test: {sorted(shared)[:5]}")
    if "source_sha256" in train and "source_sha256" in test:
        s = set(train["source_sha256"]) & set(test["source_sha256"])
        if s:
            raise AssertionError("same source recording in train and test")
