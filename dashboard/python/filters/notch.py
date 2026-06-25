"""
ParkinSense V2
Notch Filter
"""

import numpy as np

from scipy.signal import iirnotch
from scipy.signal import filtfilt


class NotchFilter:

    def __init__(
        self,
        fs,
        notch=50.0,
        q=30
    ):

        self.b, self.a = iirnotch(
            notch,
            q,
            fs
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
