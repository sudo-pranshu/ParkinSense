import numpy as np


class GyroCalibration:

    def __init__(self, samples_required=300):

        self.samples_required = samples_required

        self.samples = []

        self.bias = np.zeros(3)

        self.calibrated = False

    def add_sample(self, gx, gy, gz):

        if self.calibrated:
            return

        self.samples.append([gx, gy, gz])

        if len(self.samples) >= self.samples_required:

            self.bias = np.mean(self.samples, axis=0)

            self.calibrated = True

    def correct(self, gx, gy, gz):

        if not self.calibrated:

            return gx, gy, gz

        return (
            gx - self.bias[0],
            gy - self.bias[1],
            gz - self.bias[2],
        )

    def is_calibrated(self):

        return self.calibrated

    def get_bias(self):

        return self.bias
