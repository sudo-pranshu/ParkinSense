"""
ParkinSense V2
Butterworth Band-pass Filter
"""

import numpy as np
from scipy.signal import butter
from scipy.signal import filtfilt


class ButterworthBandpass:

    def __init__(
        self,
        fs,
        lowcut=3.0,
        highcut=8.0,
        order=4,
    ):

        self.fs = fs

        nyquist = fs * 0.5

        low = lowcut / nyquist
        high = highcut / nyquist

        self.b, self.a = butter(
            order,
            [low, high],
            btype="bandpass"
        )

    def filter(self, signal):

        signal = np.asarray(signal)

        if len(signal) < 30:
            return signal

        return filtfilt(
            self.b,
            self.a,
            signal
        )
