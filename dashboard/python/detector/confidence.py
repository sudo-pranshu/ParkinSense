"""
ParkinSense V2
Confidence Estimator
"""

import numpy as np


class ConfidenceEstimator:

    def estimate(

        self,

        frequency_std,

        band_ratio,

        axis_agreement,

        context,

    ):

        confidence = 0

        # Stable frequency

        if frequency_std < 0.3:
            confidence += 30

        elif frequency_std < 0.8:
            confidence += 20

        elif frequency_std < 1.5:
            confidence += 10

        # Tremor-band energy

        confidence += min(
            30,
            band_ratio * 120
        )

        # Agreement between axes

        confidence += axis_agreement * 25

        # Penalize movement

        if context["state"] == "ACTIVE":

            confidence *= 0.6

        confidence = max(
            0,
            min(
                confidence,
                100
            )
        )

        # Penalize weak band energy

        if band_ratio < 0.20:
            confidence *= 0.5

        # Penalize unstable frequency

        if frequency_std > 1.2:
            confidence *= 0.5

        return float(confidence)
