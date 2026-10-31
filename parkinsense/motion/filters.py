"""
Window filters for the motion pipeline.

All filters are second-order-section (SOS) Butterworth designs applied
zero-phase (`sosfiltfilt`) to one analysis window.

Why SOS: transfer-function (b, a) coefficients for band-pass designs lose
precision as order rises and the band narrows relative to fs; SOS cascades
do not (SciPy documentation, `scipy.signal.butter`: "output='sos' should be
used for general-purpose filtering"). The previous implementation used
`filtfilt(b, a)`.

Why zero-phase on a sliding window (audit P1-9): every motion output is a
*window-level* spectral statistic, not a per-sample value, so the phase
delay a causal filter would add is irrelevant, while edge transients are
diluted by Welch's tapered, averaged segments. `sosfiltfilt` pads by odd
reflection. The decision and the alternative (stateful causal `sosfilt`)
are recorded in docs/decisions/0005-motion-spectral-features.md.

Removed: the 50 Hz notch. With fs = 104 Hz it sits 2 Hz below Nyquist on a
battery-powered sensor with no mains coupling path, and its gain is
1.000 +- 0.001 across 0-15 Hz -- it was a no-op stage.
"""

from __future__ import annotations

import numpy as np
from scipy.signal import butter, sosfiltfilt

GRAVITY_CUTOFF_HZ = 0.3


def _min_len(sos) -> int:
    # sosfiltfilt default padlen = 3 * (2 * len(sos) + 1 - min(#zeros, #poles at 0))
    return 3 * (2 * len(sos) + 1) + 1


class ButterworthBandpass:
    """Zero-phase band-pass. Retained for the legacy 3-8 Hz display trace."""

    def __init__(self, fs, lowcut=3.0, highcut=8.0, order=4):
        self.fs = fs
        self.sos = butter(order, [lowcut, highcut], btype="bandpass", fs=fs, output="sos")

    def filter(self, signal):
        x = np.asarray(signal, dtype=float)
        if len(x) < _min_len(self.sos):
            return x
        return sosfiltfilt(self.sos, x)


class Bandlimit:
    """Generic zero-phase low/high/band filter."""

    def __init__(self, fs, low=None, high=None, order=4):
        if low and high:
            self.sos = butter(order, [low, high], btype="bandpass", fs=fs, output="sos")
        elif high:
            self.sos = butter(order, high, btype="low", fs=fs, output="sos")
        elif low:
            self.sos = butter(order, low, btype="high", fs=fs, output="sos")
        else:
            raise ValueError("need low and/or high")

    def __call__(self, x):
        x = np.asarray(x, dtype=float)
        if x.shape[-1] < _min_len(self.sos):
            return x - np.mean(x, axis=-1, keepdims=True)
        return sosfiltfilt(self.sos, x, axis=-1)


class GravityRemoval:
    """Linear acceleration = signal - low-passed (0.3 Hz) gravity estimate."""

    def __init__(self, fs, cutoff=GRAVITY_CUTOFF_HZ, order=2):
        self.sos = butter(order, cutoff, btype="low", fs=fs, output="sos")

    def remove(self, signal):
        x = np.asarray(signal, dtype=float)
        if x.shape[-1] < _min_len(self.sos):
            return x - np.mean(x, axis=-1, keepdims=True)
        return x - sosfiltfilt(self.sos, x, axis=-1)
