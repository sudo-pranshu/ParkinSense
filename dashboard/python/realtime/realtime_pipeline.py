import numpy as np

from dashboard.python.calibration.gyro_calibration import GyroCalibration
from dashboard.python.filters.gravity import GravityRemoval
from dashboard.python.filters.bandpass import ButterworthBandpass
from dashboard.python.filters.notch import NotchFilter
from dashboard.python.fusion.sensor_fusion import SensorFusion
from dashboard.python.features.feature_extractor import FeatureExtractor


class RealtimePipeline:

    def __init__(self, fs=104):

        self.fs = fs

        self.calibration = GyroCalibration()

        self.gravity = GravityRemoval(fs)

        self.fusion = SensorFusion()

        self.bandpass = ButterworthBandpass(fs)

        self.notch = NotchFilter(fs)

        self.extractor = FeatureExtractor(fs)

    def process_window(
        self,
        ax,
        ay,
        az,
        gx,
        gy,
        gz
    ):

        gx = np.asarray(gx)
        gy = np.asarray(gy)
        gz = np.asarray(gz)

        ax = np.asarray(ax)
        ay = np.asarray(ay)
        az = np.asarray(az)

        gx_f = self.bandpass.filter(gx)
        gy_f = self.bandpass.filter(gy)
        gz_f = self.bandpass.filter(gz)

        gx_f = self.notch.filter(gx_f)
        gy_f = self.notch.filter(gy_f)
        gz_f = self.notch.filter(gz_f)

        features = {}

        features["gx"] = self.extractor.extract(gx_f)
        features["gy"] = self.extractor.extract(gy_f)
        features["gz"] = self.extractor.extract(gz_f)

        return features
