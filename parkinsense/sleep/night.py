"""
Night-level sleep estimates from an epoch-state sequence.

Definitions (all ESTIMATES from wrist movement, not polysomnography):

    sleep period (SPT)   main block of sleep: runs of sleep epochs are merged
                         across wake gaps < SPT_MERGE_GAP_MIN (as in HDCZA,
                         van Hees et al. 2018); the longest merged block of
                         >= SPT_MIN_MIN is the sleep period
    onset / wake time    first / last epoch of that block
    TST                  sleep epochs inside the sleep period
    WASO                 wake epochs inside the sleep period
    period efficiency    TST / SPT duration (NOT classic sleep efficiency,
                         which needs time-in-bed; not available)
    awakenings           wake runs >= AWAKENING_MIN_EPOCHS inside the period
    fragmentation index  awakenings per hour of TST
    movement in sleep    fraction of sleep epochs with an angle change > 5 deg
    non-wear             >= 60 min with every axis SD < 13 mg (van Hees 2011);
                         such epochs are excluded, never scored as sleep

Sleep stages are not estimated: wrist movement cannot separate them reliably.
"""

from __future__ import annotations

import numpy as np

from parkinsense import config as C
from parkinsense.sleep.features import EPOCH_S, EpochTable

SPT_MERGE_GAP_MIN = 60.0
SPT_MIN_MIN = 30.0
AWAKENING_MIN_EPOCHS = 2
NONWEAR_SD_G = 0.013
NONWEAR_MIN = 60.0
MIN_ANALYSED_MIN = 120.0
MIN_COVERAGE_VALID = 0.8


def runs(mask):
    """[(start, end_exclusive)] of True runs."""
    m = np.r_[False, np.asarray(mask, bool), False]
    d = np.diff(m.astype(int))
    return list(zip(np.flatnonzero(d == 1), np.flatnonzero(d == -1)))


def nonwear_mask(tab: EpochTable) -> np.ndarray:
    low = np.isfinite(tab.acc_sd) & (tab.acc_sd < NONWEAR_SD_G)
    need = int(NONWEAR_MIN * 60 / EPOCH_S)
    out = np.zeros(len(tab), bool)
    for a, b in runs(low):
        if b - a >= need:
            out[a:b] = True
    return out


def sleep_period(state) -> tuple[int, int] | None:
    s = np.asarray(state) == 1
    blocks = runs(s)
    if not blocks:
        return None
    gap = int(SPT_MERGE_GAP_MIN * 60 / EPOCH_S)
    merged = [list(blocks[0])]
    for a, b in blocks[1:]:
        if a - merged[-1][1] < gap:
            merged[-1][1] = b
        else:
            merged.append([a, b])
    best = max(merged, key=lambda r: r[1] - r[0])
    if (best[1] - best[0]) * EPOCH_S / 60 < SPT_MIN_MIN:
        return None
    return best[0], best[1]


def summarize(tab: EpochTable, state, t_wall0: float | None = None) -> dict:
    """Night summary. `t_wall0`: wall-clock time of tab.t == 0 (for clock times), optional."""
    state = np.asarray(state).copy()
    nw = nonwear_mask(tab)
    state[nw] = -1
    analysed = state >= 0
    minutes = lambda n: round(float(n) * EPOCH_S / 60.0, 1)  # noqa: E731
    out = {
        "algorithm_version": C.SLEEP_ALGORITHM_VERSION, "estimate": True, "epoch_s": EPOCH_S,
        "recording_min": minutes(len(state)), "analysed_min": minutes(analysed.sum()),
        "nonwear_min": minutes(nw.sum()),
        "coverage": round(float(analysed.mean()) if len(state) else 0.0, 3),
    }
    spt = sleep_period(state)
    if spt is None or out["analysed_min"] < MIN_ANALYSED_MIN:
        out.update(quality=C.Quality.INSUFFICIENT_DATA.value,
                   reason="no sleep period >= 30 min" if spt is None else "< 2 h of analysable data")
        return out
    a, b = spt
    seg = state[a:b]
    sleep_n = int((seg == 1).sum())
    wake_n = int((seg == 0).sum())
    gaps_n = int((seg < 0).sum())
    wake_runs = [r for r in runs(seg == 0) if r[1] - r[0] >= AWAKENING_MIN_EPOCHS]
    moved = np.isfinite(tab.dg_max[a:b]) & (tab.dg_max[a:b] > 5.0) & (seg == 1)
    tst_h = sleep_n * EPOCH_S / 3600
    spt_cov = 1 - gaps_n / max(b - a, 1)
    out.update({
        "onset_s": float(tab.t[a]), "wake_s": float(tab.t[b - 1] + EPOCH_S),
        "spt_min": minutes(b - a), "tst_min": minutes(sleep_n), "waso_min": minutes(wake_n),
        "gap_in_spt_min": minutes(gaps_n),
        "period_efficiency": round(sleep_n / max(sleep_n + wake_n, 1), 3),
        "awakenings": len(wake_runs),
        "fragmentation_index_per_h": round(len(wake_runs) / tst_h, 2) if tst_h > 0 else None,
        "movement_in_sleep_fraction": round(float(moved.sum()) / max(sleep_n, 1), 3),
        "enmo_in_spt_mg": round(float(np.nanmean(tab.enmo[a:b])) * 1000, 2),
        "sleep_outside_spt_min": minutes(int((state == 1).sum()) - sleep_n),
        "quality": (C.Quality.VALID.value if spt_cov >= MIN_COVERAGE_VALID and out["coverage"] >= MIN_COVERAGE_VALID
                    else C.Quality.DATA_GAP.value),
    })
    if t_wall0 is not None:
        out["onset_wall"] = t_wall0 + out["onset_s"]
        out["wake_wall"] = t_wall0 + out["wake_s"]
    return out
