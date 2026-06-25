"""
ParkinSense V2
Temporal Tremor Smoother
"""

from collections import deque

import numpy as np


class TemporalSmoother:

    def __init__(self, window=10):

        self.window = window

        self.scores = deque(maxlen=window)
        self.freqs = deque(maxlen=window)
        self.confidences = deque(maxlen=window)

    def update(self, result):

        self.scores.append(result["score"])
        self.freqs.append(result["frequency"])
        self.confidences.append(result["confidence"])

        smooth_score = float(np.mean(self.scores))

        smooth_freq = float(np.mean(self.freqs))

        smooth_conf = float(np.mean(self.confidences))

        persistence = sum(
            s >= 80 for s in self.scores
        )

        tremor = persistence >= 5

        return {

            "score": smooth_score,

            "frequency": smooth_freq,

            "confidence": smooth_conf,

            "persistence": persistence,

            "tremor": tremor
        }
