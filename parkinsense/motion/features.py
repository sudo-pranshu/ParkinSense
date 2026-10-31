"""
ParkinSense V2
Feature Extraction Engine
"""

import numpy as np

from scipy.signal import find_peaks
from scipy.signal import welch
from scipy.stats import entropy

from dashboard.python.utils.signal_utils import (
    rms,
    signal_energy,
    zero_crossings
)


class FeatureExtractor:

    def __init__(self, fs):

        self.fs = fs

    def extract(self, signal):

        signal = np.asarray(signal)

        features = {}

        # -----------------------
        # Time-domain features
        # -----------------------

        features["mean"] = float(np.mean(signal))
        features["std"] = float(np.std(signal))
        features["variance"] = float(np.var(signal))
        features["rms"] = float(rms(signal))
        features["energy"] = float(signal_energy(signal))

        features["max"] = float(np.max(signal))
        features["min"] = float(np.min(signal))
        features["range"] = features["max"] - features["min"]

        features["zero_crossings"] = int(
            zero_crossings(signal)
        )

        features["sma"] = float(
            np.mean(np.abs(signal))
        )

        # -----------------------
        # Frequency-domain
        # -----------------------

        freq, psd = welch(
            signal,
            fs=self.fs,
            nperseg=min(len(signal), 256)
        )

        dominant_idx = np.argmax(psd)

        features["dominant_frequency"] = float(
            freq[dominant_idx]
        )

        features["peak_power"] = float(
            psd[dominant_idx]
        )

        tremor_band = (
            (freq >= 3.5) &
            (freq <= 7.5)
        )

        tremor_power = np.sum(
            psd[tremor_band]
        )

        total_power = np.sum(psd)

        features["tremor_power"] = float(
            tremor_power
        )

        features["total_power"] = float(
            total_power
        )

        if total_power > 0:

            features["band_ratio"] = float(
                tremor_power / total_power
            )

        else:

            features["band_ratio"] = 0.0

        # -----------------------
        # Spectral Entropy
        # -----------------------

        psd_norm = psd / (np.sum(psd) + 1e-12)

        features["spectral_entropy"] = float(
            entropy(psd_norm)
        )

        # -----------------------
        # Spectral Centroid
        # -----------------------

        centroid = np.sum(
            freq * psd
        ) / (np.sum(psd) + 1e-12)

        features["spectral_centroid"] = float(
            centroid
        )

        # -----------------------
        # Peak Analysis
        # -----------------------

        peaks, _ = find_peaks(psd)

        features["num_peaks"] = int(
            len(peaks)
        )

        if len(peaks):

            features["peak_prominence"] = float(
                np.max(psd[peaks])
            )

        else:

            features["peak_prominence"] = 0.0

        return features
