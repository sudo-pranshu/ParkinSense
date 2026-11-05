"""
Epoch features for sleep/wake classification from wrist acceleration.

Input: raw tri-axial acceleration in g with its own (possibly irregular,
gappy) time base. Output: one row per 30 s epoch. Everything is computed
from 5 s sub-epochs, following van Hees et al. (PLoS ONE 2015):

    g_k        mean acceleration vector of sub-epoch k  (gravity estimate;
               the 5 s mean replaces the paper's rolling 5 s median, see
               docs/algorithms/SLEEP.md)
    z_k        = atan(g_z / sqrt(g_x^2 + g_y^2))          arm (z) angle, deg
    dz_k       = |z_k - z_{k-1}|                         z-angle change
    dg_k       = angle between g_k and g_{k-1}           orientation-free change
    enmo_k     = mean(max(|a| - 1, 0))                   movement intensity, g

Per epoch: max dz, max dg, mean ENMO, sample coverage, and optional heart
rate. `dg` does not depend on how the board is mounted, `dz` reproduces the
published method (z = axis perpendicular to the skin).

The same function serves the runtime (fed one epoch at a time from a
buffer), offline analysis and the benchmarks, so all three are identical.
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass

import numpy as np

EPOCH_S = 30.0
SUB_S = 5.0
SUBS_PER_EPOCH = int(EPOCH_S / SUB_S)
MIN_COVERAGE = 0.5          # an epoch with < 50 % of its expected samples is a data gap


@dataclass
class EpochTable:
    """Column arrays, one entry per epoch (NaN where an epoch has no data)."""
    t: np.ndarray            # epoch start, s
    coverage: np.ndarray     # fraction of expected samples present
    dz_max: np.ndarray       # deg
    dg_max: np.ndarray       # deg
    z_mean: np.ndarray       # deg
    enmo: np.ndarray         # g
    acc_sd: np.ndarray       # max over axes of the per-axis SD, g (non-wear check)
    hr: np.ndarray           # bpm, mean of valid HR samples in the epoch (NaN if none)

    def __len__(self):
        return len(self.t)

    def as_dict(self):
        return {k: getattr(self, k) for k in self.__dataclass_fields__}


def _angle_deg(u, v):
    nu = np.linalg.norm(u, axis=-1)
    nv = np.linalg.norm(v, axis=-1)
    c = np.einsum("...i,...i->...", u, v) / np.maximum(nu * nv, 1e-12)
    return np.degrees(np.arccos(np.clip(c, -1.0, 1.0)))


def epoch_features(t, acc, t0: float | None = None, n_epochs: int | None = None, fs: float | None = None,
                   hr_t=None, hr=None, prev_sub: np.ndarray | None = None) -> EpochTable:
    """
    t: (n,) seconds; acc: (n, 3) g. Epochs start at t0 (default: first sample)
    and are EPOCH_S long. `fs` (nominal rate) sets the expected sample count for
    coverage; default = median sampling interval. `prev_sub` is the last
    sub-epoch mean vector before t0 (streaming continuity across epochs).
    """
    t = np.asarray(t, float)
    acc = np.asarray(acc, float)
    if t0 is None:
        t0 = float(t[0]) if len(t) else 0.0
    if n_epochs is None:
        n_epochs = int(np.floor((t[-1] - t0) / EPOCH_S)) + 1 if len(t) else 0
    if fs is None:
        fs = 1.0 / float(np.median(np.diff(t))) if len(t) > 1 else 1.0
    n_sub = n_epochs * SUBS_PER_EPOCH
    k = np.floor((t - t0) / SUB_S).astype(np.int64)
    ok = (k >= 0) & (k < n_sub) & np.isfinite(acc).all(axis=1)
    k, a = k[ok], acc[ok]

    cnt = np.bincount(k, minlength=n_sub).astype(float)
    sums = np.stack([np.bincount(k, a[:, j], minlength=n_sub) for j in range(3)], axis=1)
    sq = np.stack([np.bincount(k, a[:, j] ** 2, minlength=n_sub) for j in range(3)], axis=1)
    enmo_s = np.bincount(k, np.maximum(np.linalg.norm(a, axis=1) - 1.0, 0.0), minlength=n_sub)
    with np.errstate(invalid="ignore", divide="ignore"):
        g = sums / cnt[:, None]
    has = cnt >= 0.25 * SUB_S * fs
    g[~has] = np.nan

    z = np.degrees(np.arctan2(g[:, 2], np.hypot(g[:, 0], g[:, 1])))
    prev = np.vstack([prev_sub if prev_sub is not None else np.full(3, np.nan), g[:-1]]) if n_sub else g
    zprev = np.degrees(np.arctan2(prev[:, 2], np.hypot(prev[:, 0], prev[:, 1])))
    dz = np.abs(z - zprev)
    dg = _angle_deg(g, prev)

    def per_epoch(x, how):                     # all-NaN epochs -> NaN without a warning
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            return how(x.reshape(n_epochs, SUBS_PER_EPOCH), axis=1)

    ecnt = cnt.reshape(n_epochs, SUBS_PER_EPOCH).sum(axis=1)
    with np.errstate(invalid="ignore", divide="ignore"):
        enmo = enmo_s.reshape(n_epochs, SUBS_PER_EPOCH).sum(axis=1) / ecnt
        esum = sums.reshape(n_epochs, SUBS_PER_EPOCH, 3).sum(axis=1)
        esq = sq.reshape(n_epochs, SUBS_PER_EPOCH, 3).sum(axis=1)
        sd = np.sqrt(np.maximum(esq / ecnt[:, None] - (esum / ecnt[:, None]) ** 2, 0.0)).max(axis=1)
    coverage = ecnt / (EPOCH_S * fs)

    hr_e = np.full(n_epochs, np.nan)
    if hr_t is not None and hr is not None and len(hr_t):
        hr_t = np.asarray(hr_t, float)
        hr = np.asarray(hr, float)
        e = np.floor((hr_t - t0) / EPOCH_S).astype(np.int64)
        v = (e >= 0) & (e < n_epochs) & np.isfinite(hr) & (hr > 25) & (hr < 220)
        c = np.bincount(e[v], minlength=n_epochs)
        s = np.bincount(e[v], hr[v], minlength=n_epochs)
        with np.errstate(invalid="ignore", divide="ignore"):
            hr_e = np.where(c > 0, s / c, np.nan)

    gap = coverage < MIN_COVERAGE
    out = EpochTable(
        t=t0 + EPOCH_S * np.arange(n_epochs),
        coverage=np.round(coverage, 4),
        dz_max=per_epoch(dz, np.nanmax), dg_max=per_epoch(dg, np.nanmax),
        z_mean=per_epoch(z, np.nanmean), enmo=enmo, acc_sd=sd, hr=hr_e)
    for name in ("dz_max", "dg_max", "z_mean", "enmo", "acc_sd"):
        getattr(out, name)[gap] = np.nan
    return out


def last_sub_vector(t, acc, t_end: float, fs: float) -> np.ndarray | None:
    """Mean vector of the last full sub-epoch before t_end (for streaming continuity)."""
    t = np.asarray(t, float)
    m = (t >= t_end - SUB_S) & (t < t_end)
    if m.sum() < 0.25 * SUB_S * fs:
        return None
    return np.asarray(acc, float)[m].mean(axis=0)
