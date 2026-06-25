import numpy as np

from dashboard.python.filters.bandpass import ButterworthBandpass
from dashboard.python.filters.notch import NotchFilter

from dashboard.python.features.feature_extractor import FeatureExtractor


class SignalPipeline:

    def __init__(self, fs=104):

        self.fs = fs

        self.bandpass = ButterworthBandpass(fs)

        self.notch = NotchFilter(fs)

        self.extractor = FeatureExtractor(fs)

    def process(self, signal):

        signal = np.asarray(signal)

        filtered = self.bandpass.filter(signal)

        filtered = self.notch.filter(filtered)

        features = self.extractor.extract(filtered)

        return {

            "raw": signal,

            "filtered": filtered,

            "features": features

        }
