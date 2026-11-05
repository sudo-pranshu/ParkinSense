"""
Sleep/wake classification: context features -> logistic regression (-> optional 2-state HMM).

Why this design (docs/research/SLEEP_ALGORITHMS.md, ADR-0010):

* The published evidence says simple, interpretable methods are competitive with machine and
  deep learning on PSG (Patterson et al., npj Digit Med 2023, as read for this work).
* A logistic regression over a handful of movement-context features keeps the model a weight
  vector (identical on Python, Android, iOS), and lets the van Hees rule enter as one feature
  instead of being the whole method.
* The 2-state HMM below (transition probabilities estimated from PSG, tempered like the tremor
  HMM, ADR-0007) is kept for experiments but is NOT used in production: on leave-one-subject-out
  Walch data it lowered kappa (0.50 -> 0.47, untempered 0.39). `params.ACCEL["smooth"]` is False.

Every feature is computed from `EpochTable` columns; epochs without data
(coverage < 50 %) get NaN features and an uninformative emission.
"""

from __future__ import annotations

import numpy as np

from parkinsense.sleep.features import EPOCH_S, EpochTable

STILL_DEG = 5.0             # van Hees 2015: no angle change > 5 deg ...
STILL_MIN = 5.0             # ... for at least 5 minutes
CONTEXT_MIN = 5.0           # +/- window for density / intensity features
CAP_MIN = 60.0

ACCEL_FEATURES = ["log_dg", "move_density", "log_enmo_ctx", "still_bout", "log_since_move", "log_until_move"]
HR_FEATURES = ["hr_rel", "hr_sd_ctx"]


def _rolling_mean(x, half):
    """Centred mean over +/- half epochs, ignoring NaN."""
    v = np.where(np.isfinite(x), x, 0.0)
    n = np.isfinite(x).astype(float)
    k = np.ones(2 * half + 1)
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.convolve(v, k, "same") / np.convolve(n, k, "same")


def _run_lengths(mask):
    """Length of the True run each element belongs to (0 for False)."""
    out = np.zeros(len(mask), int)
    i = 0
    while i < len(mask):
        if mask[i]:
            j = i
            while j < len(mask) and mask[j]:
                j += 1
            out[i:j] = j - i
            i = j
        else:
            i += 1
    return out


def _minutes_since(event, cap):
    out = np.empty(len(event))
    last = -np.inf
    for i, e in enumerate(event):
        if e:
            last = i
        out[i] = min((i - last) * EPOCH_S / 60.0, cap)
    return out


def still_mask(tab: EpochTable, angle: str = "dg") -> np.ndarray:
    a = tab.dg_max if angle == "dg" else tab.dz_max
    return np.isfinite(a) & (a <= STILL_DEG)


def vanhees_sleep(tab: EpochTable, angle: str = "dz") -> np.ndarray:
    """
    van Hees et al. 2015 sustained inactivity at epoch resolution: an epoch is
    sleep if it lies in a run of >= 5 min with no 5 s angle change > 5 deg.
    angle="dz" is the published z-angle; "dg" the orientation-free variant.
    Returns 1/0, -1 where the epoch has no data.
    """
    still = still_mask(tab, angle)
    s = (_run_lengths(still) * EPOCH_S / 60.0 >= STILL_MIN).astype(int)
    s[~np.isfinite(tab.dg_max)] = -1
    return s


def context_features(tab: EpochTable, use_hr: bool = False) -> np.ndarray:
    half = int(CONTEXT_MIN * 60 / EPOCH_S)
    valid = np.isfinite(tab.dg_max)
    moved = valid & (tab.dg_max > STILL_DEG)
    still_run = _run_lengths(still_mask(tab)) * EPOCH_S / 60.0
    cols = [
        np.log10(tab.dg_max + 0.5),
        _rolling_mean(moved.astype(float) * np.where(valid, 1, np.nan), half),
        np.log10(_rolling_mean(tab.enmo, half) + 1e-3),
        (still_run >= STILL_MIN).astype(float),
        np.log1p(_minutes_since(moved, CAP_MIN)),
        np.log1p(_minutes_since(moved[::-1], CAP_MIN)[::-1]),
    ]
    if use_hr:
        hr = tab.hr
        med = np.nanmedian(hr) if np.isfinite(hr).any() else np.nan
        cols += [np.nan_to_num((hr - med) / 10.0, nan=0.0),
                 np.nan_to_num(np.sqrt(np.maximum(_rolling_mean(hr ** 2, half) - _rolling_mean(hr, half) ** 2, 0)),
                               nan=0.0)]
    X = np.stack(cols, axis=1)
    X[~valid] = np.nan
    return X


# --------------------------------------------------------------------------- logistic regression
def fit_logistic(X, y, l2=1.0, iters=50):
    """L2-regularised logistic regression by Newton's method (standardised inputs)."""
    X = np.asarray(X, float)
    y = np.asarray(y, float)
    mu, sd = X.mean(0), X.std(0)
    sd[sd == 0] = 1.0
    Z = np.c_[np.ones(len(X)), (X - mu) / sd]
    w = np.zeros(Z.shape[1])
    R = l2 * np.eye(Z.shape[1])
    R[0, 0] = 0.0
    for _ in range(iters):
        p = 1 / (1 + np.exp(-Z @ w))
        g = Z.T @ (p - y) + R @ w
        H = (Z * (p * (1 - p))[:, None]).T @ Z + R
        step = np.linalg.solve(H, g)
        w -= step
        if np.abs(step).max() < 1e-8:
            break
    return {"bias": float(w[0] - (w[1:] / sd) @ mu), "weights": (w[1:] / sd).tolist()}


def predict_proba(model: dict, X) -> np.ndarray:
    X = np.asarray(X, float)
    z = model["bias"] + X @ np.asarray(model["weights"])
    with np.errstate(over="ignore"):
        return 1 / (1 + np.exp(-z))


# --------------------------------------------------------------------------- HMM smoothing
def temper(p, beta):
    """p^b / (p^b + (1-p)^b): shrinks over-confident posteriors towards 0.5."""
    p = np.clip(np.asarray(p, float), 1e-6, 1 - 1e-6)
    a, b = p ** beta, (1 - p) ** beta
    return a / (a + b)


def hmm_smooth(p_sleep, p_stay_sleep, p_stay_wake, prior_sleep, causal=False, beta=1.0):
    """
    Posterior P(sleep) under a 2-state HMM whose emissions are the classifier's
    posteriors divided by the class prior (scaled likelihoods). The context
    features overlap across neighbouring epochs, so successive emissions are
    not independent; `beta` < 1 tempers them (posterior and prior alike) so
    the same evidence is not counted many times -- the overlap correction
    used for the tremor HMM (ADR-0007). NaN inputs are uninformative.
    causal=True -> forward filter only (live use).
    """
    p = np.asarray(p_sleep, float)
    if beta != 1.0:
        p = np.where(np.isfinite(p), temper(np.nan_to_num(p, nan=0.5), beta), np.nan)
        prior_sleep = float(temper(prior_sleep, beta))
    n = len(p)
    A = np.array([[p_stay_wake, 1 - p_stay_wake], [1 - p_stay_sleep, p_stay_sleep]])  # rows: from wake, sleep
    pri = np.array([1 - prior_sleep, prior_sleep])
    E = np.ones((n, 2))
    ok = np.isfinite(p)
    E[ok, 0] = (1 - np.clip(p[ok], 1e-6, 1 - 1e-6)) / pri[0]
    E[ok, 1] = np.clip(p[ok], 1e-6, 1 - 1e-6) / pri[1]
    a = np.empty((n, 2))
    prev = pri
    for i in range(n):
        v = (prev @ A if i else prev) * E[i]
        a[i] = v / v.sum()
        prev = a[i]
    if causal:
        return a[:, 1]
    b = np.ones(2)
    post = np.empty(n)
    for i in range(n - 1, -1, -1):
        g = a[i] * b
        post[i] = g[1] / g.sum()
        v = A @ (E[i] * b)
        b = v / v.sum()
    return post


def transitions_from_labels(seqs) -> tuple[float, float, float]:
    """Maximum-likelihood stay probabilities and sleep prior from labelled 0/1 sequences."""
    ss = sw = ws = ww = 0
    n1 = n = 0
    for y in seqs:
        y = np.asarray(y)
        y = y[y >= 0]
        a, b = y[:-1], y[1:]
        ss += np.sum((a == 1) & (b == 1))
        sw += np.sum((a == 1) & (b == 0))
        ww += np.sum((a == 0) & (b == 0))
        ws += np.sum((a == 0) & (b == 1))
        n1 += np.sum(y == 1)
        n += len(y)
    return (ss + 1) / (ss + sw + 2), (ww + 1) / (ww + ws + 2), n1 / max(n, 1)


def classify(tab: EpochTable, params: dict, use_hr: bool | None = None, causal=False) -> dict:
    """Run the full classifier with a parameter set (parkinsense.sleep.params)."""
    use_hr = params.get("use_hr", False) if use_hr is None else use_hr
    X = context_features(tab, use_hr=use_hr)
    p = predict_proba(params["logistic"], X)
    if params.get("smooth", True):
        post = hmm_smooth(p, params["p_stay_sleep"], params["p_stay_wake"], params["prior_sleep"], causal=causal,
                          beta=params.get("beta", 1.0))
    else:
        post = p
    state = np.where(np.isfinite(tab.dg_max), (post >= params.get("threshold", 0.5)).astype(int), -1)
    return {"p_classifier": p, "p_sleep": post, "state": state}
