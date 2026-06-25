import numpy as np

from scipy.signal import butter
from scipy.signal import filtfilt


class GravityRemoval:

    def __init__(self,
                 fs,
                 cutoff=0.3,
                 order=2):

        self.fs = fs

        nyquist = fs / 2

        self.b, self.a = butter(
            order,
            cutoff / nyquist,
            btype="low"
        )

    def remove(self, signal):

        gravity = filtfilt(
            self.b,
            self.a,
            signal
        )

        linear = signal - gravity

        return linear
