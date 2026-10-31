"""
Spectral features for tremor and movement analysis (algorithm v3).

One Welch PSD per axis on the *un-band-passed*, mean-removed gyroscope
window; the three axis PSDs are also summed, which makes the band powers
independent of how the device sits on the wrist (the approach used by
ParaDigMa, Timmermans et al., npj Parkinson's Dis 2025).

Why not the previous design: features were computed on a 3-8 Hz band-passed
signal, so `band_ratio` (tremor-band power / total power) was the ratio of
in-band power to *already band-limited* power -- close to 1 for almost any
input, and therefore nearly uninformative. Peak frequency came from a 0.41 Hz
FFT grid with no interpolation, and per-axis peaks of noise-only axes voted
in the agreement statistic (audit P1-8).

Frequency estimate: the tremor-band PSD maximum is refined by Gaussian
(log-parabolic) interpolation over the three bins around it, which for a
Hann window reduces the peak-location bias to a small fraction of a bin
(Gasior & Gonzalez, CERN-AB-2004-023; Jacobsen & Kootsookos, IEEE SP Mag
24(3), 2007). Zero-padding (nfft=1024) shrinks the bin spacing to 0.10 Hz.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.signal import butter, sosfiltfilt, welch

from parkinsense.config import ANALYSIS_BAND_HZ, ARM_MOVEMENT_BAND_HZ, TREMOR_BAND_HZ

NFFT = 1024
TREMOR_PEAK_HALF_WIDTH_HZ = 0.625     # +-0.625 Hz -> 1.25 Hz integration (ParaDigMa)
NOISE_FLOOR_BAND_HZ = (2.0, 12.0)
AXES = ("gx", "gy", "gz")


@dataclass
class SpectralFeatures:
    peak_frequency_hz: float          # interpolated, summed-axis PSD, tremor band
    tremor_power: float               # dps^2 within +-0.625 Hz of the peak (sum of axes)
    tremor_rms_dps: float             # sqrt(tremor_power)
    arm_power: float                  # dps^2 in 0.5-3 Hz (purposeful movement)
    arm_rms_dps: float
    total_power: float                # dps^2 in 0.5-15 Hz
    band_ratio: float                 # tremor_power / total_power
    peak_snr_db: float                # peak PSD vs median floor 2-12 Hz (excluding peak)
    spectral_entropy: float           # normalised 0..1 over 0.5-15 Hz
    spectral_centroid_hz: float
    arm_peak_frequency_hz: float      # dominant purposeful-movement frequency
    best_axis: str
    axis_dominance: float             # max per-axis tremor power / sum
    axis_frequencies: dict            # per-axis interpolated peak (Hz)
    frequency_std: float              # tremor-power-weighted std of axis peaks
    axis_agreement: float             # 1 - frequency_std/2, clipped to [0, 1]
    per_axis: dict                    # legacy-compatible per-axis dicts


def _interp_peak(freqs, psd, idx):
    """Gaussian (log-parabolic) interpolation around bin `idx`."""
    if idx <= 0 or idx >= len(psd) - 1:
        return float(freqs[idx])
    a, b, c = np.log(np.maximum(psd[idx - 1:idx + 2], 1e-30))
    denom = a - 2 * b + c
    if denom >= 0:
        return float(freqs[idx])
    delta = 0.5 * (a - c) / denom
    delta = float(np.clip(delta, -0.5, 0.5))
    return float(freqs[idx] + delta * (freqs[1] - freqs[0]))


def _band(freqs, lo, hi):
    return (freqs >= lo) & (freqs <= hi)


def _integrate(psd, freqs, mask):
    if not np.any(mask):
        return 0.0
    return float(np.sum(psd[..., mask], axis=-1) * (freqs[1] - freqs[0])) if psd.ndim == 1 \
        else np.sum(psd[..., mask], axis=-1) * (freqs[1] - freqs[0])


_ARM_SOS = {}


def _arm_power(gyro, fs):
    key = float(fs)
    if key not in _ARM_SOS:
        _ARM_SOS[key] = butter(4, ARM_MOVEMENT_BAND_HZ, btype="bandpass", fs=fs, output="sos")
    x = np.asarray(gyro, dtype=float)
    x = x - x.mean(axis=1, keepdims=True)
    if x.shape[1] < 60:
        return float(np.sum(np.var(x, axis=1)))
    y = sosfiltfilt(_ARM_SOS[key], x, axis=1)
    # Central half only: filter start-up transients at the window edges are
    # large when a strong out-of-band (tremor) carrier is present.
    q = x.shape[1] // 4
    return float(np.sum(np.mean(y[:, q:-q] ** 2, axis=1)))


def gyro_spectrum(gyro: np.ndarray, fs: float):
    """gyro: (3, n) deg/s. Returns freqs, per-axis PSD (3, F)."""
    x = np.asarray(gyro, dtype=float)
    x = x - x.mean(axis=1, keepdims=True)
    nper = int(min(x.shape[1], round(2.0 * fs)))
    freqs, psd = welch(x, fs=fs, window="hann", nperseg=nper, noverlap=nper // 2,
                       nfft=max(NFFT, nper), detrend="linear", axis=-1)
    return freqs, psd


def extract(gyro: np.ndarray, fs: float) -> SpectralFeatures:
    freqs, psd_axes = gyro_spectrum(gyro, fs)
    psd = psd_axes.sum(axis=0)
    df = freqs[1] - freqs[0]

    tb = _band(freqs, *TREMOR_BAND_HZ)
    idx_band = np.flatnonzero(tb)
    i_pk = int(idx_band[np.argmax(psd[tb])])
    f_pk = _interp_peak(freqs, psd, i_pk)

    win = _band(freqs, f_pk - TREMOR_PEAK_HALF_WIDTH_HZ, f_pk + TREMOR_PEAK_HALF_WIDTH_HZ)
    tremor_power = float(psd[win].sum() * df)
    arm_mask = _band(freqs, *ARM_MOVEMENT_BAND_HZ)
    # Arm-movement power is measured in the time domain (8th-order effective
    # zero-phase band-pass) rather than from the PSD: Hann-window leakage and
    # tremor amplitude-modulation sidebands from a strong 4-6 Hz peak would
    # otherwise masquerade as 0.5-3 Hz "movement".
    arm_power = _arm_power(gyro, fs)
    total_mask = _band(freqs, *ANALYSIS_BAND_HZ)
    total_power = float(psd[total_mask].sum() * df)

    nf = _band(freqs, *NOISE_FLOOR_BAND_HZ) & ~_band(freqs, f_pk - 1.0, f_pk + 1.0)
    floor = float(np.median(psd[nf])) if np.any(nf) else 1e-12
    snr_db = float(10 * np.log10(max(psd[i_pk], 1e-30) / max(floor, 1e-30)))

    p = psd[total_mask]
    pn = p / (p.sum() + 1e-30)
    entropy = float(-np.sum(pn * np.log(pn + 1e-30)) / np.log(len(pn)))
    centroid = float(np.sum(freqs[total_mask] * p) / (p.sum() + 1e-30))

    i_arm = int(np.flatnonzero(arm_mask)[np.argmax(psd[arm_mask])])
    f_arm = _interp_peak(freqs, psd, i_arm)

    axis_tp = psd_axes[:, win].sum(axis=1) * df
    best = int(np.argmax(axis_tp))
    dominance = float(axis_tp[best] / (axis_tp.sum() + 1e-30))
    axis_f = {}
    for k, name in enumerate(AXES):
        ik = int(idx_band[np.argmax(psd_axes[k, tb])])
        axis_f[name] = _interp_peak(freqs, psd_axes[k], ik)
    w = axis_tp / (axis_tp.sum() + 1e-30)
    fa = np.array([axis_f[a] for a in AXES])
    fmean = float(np.sum(w * fa))
    fstd = float(np.sqrt(np.sum(w * (fa - fmean) ** 2)))

    per_axis = {}
    for k, name in enumerate(AXES):
        pa = psd_axes[k]
        tot = float(pa[total_mask].sum() * df)
        per_axis[name] = {
            "dominant_frequency": axis_f[name],
            "tremor_power": float(axis_tp[k]),
            "total_power": tot,
            "band_ratio": float(axis_tp[k] / tot) if tot > 0 else 0.0,
            "rms": float(np.sqrt(tot)),
        }

    return SpectralFeatures(
        peak_frequency_hz=f_pk, tremor_power=tremor_power,
        tremor_rms_dps=float(np.sqrt(tremor_power)), arm_power=arm_power,
        arm_rms_dps=float(np.sqrt(arm_power)), total_power=total_power,
        band_ratio=tremor_power / total_power if total_power > 0 else 0.0,
        peak_snr_db=snr_db, spectral_entropy=entropy, spectral_centroid_hz=centroid,
        arm_peak_frequency_hz=f_arm, best_axis=AXES[best], axis_dominance=dominance,
        axis_frequencies=axis_f, frequency_std=fstd,
        axis_agreement=float(np.clip(1.0 - fstd / 2.0, 0.0, 1.0)), per_axis=per_axis,
    )
