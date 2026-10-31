"""
Motion Context Detection

Determines whether the wrist is

REST
LOW MOTION
ACTIVE

using acceleration magnitude.
"""

import numpy as np


class MotionContext:

    def __init__(self):

        self.rest_threshold = 0.03
        self.active_threshold = 0.20

    def classify(self, ax, ay, az):

        mag = np.sqrt(
            ax**2 +
            ay**2 +
            az**2
        )

        mag = mag - np.mean(mag)

        rms = np.sqrt(np.mean(mag**2))

        if rms < self.rest_threshold:

            state = "REST"

        elif rms < self.active_threshold:

            state = "LOW MOTION"

        else:

            state = "ACTIVE"

        return {

            "state": state,
            "motion_rms": float(rms)

        }
