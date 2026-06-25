"""
ParkinSense V2
Multi-axis Tremor Detector
"""

import numpy as np


class MultiAxisDetector:

    def __init__(self):

        self.score = 0

    def detect(self, features, context):

        gx = features["gx"]
        gy = features["gy"]
        gz = features["gz"]

        freqs = np.array([
            gx["dominant_frequency"],
            gy["dominant_frequency"],
            gz["dominant_frequency"]
        ])

        powers = np.array([
            gx["band_ratio"],
            gy["band_ratio"],
            gz["band_ratio"]
        ])

        rms = np.array([
            gx["rms"],
            gy["rms"],
            gz["rms"]
        ])

        mean_freq = np.mean(freqs)

        freq_std = np.std(freqs)

        band_ratio = np.max(powers)

        best_axis = ["gx", "gy", "gz"][np.argmax(powers)]

        axis_dominance = np.max(rms) / (np.sum(rms) + 1e-6)

        axis_agreement = max(
            0.0,
            1.0 - freq_std / 2.0
        )

        gyro_rms = np.sqrt(
            np.mean(rms ** 2)
        )
        if gyro_rms < 0.8:
            return {
                "tremor": False,
                "score": 0,
                "confidence": 0,
                "severity": "NONE",
                "frequency": float(mean_freq),
                "frequency_std": float(freq_std),
                "band_ratio": float(band_ratio),
                "axis_agreement": float(axis_agreement),
                "axis_dominance": float(axis_dominance),
                "best_axis": best_axis,
                "motion_state": context["state"],
                "motion_rms": context["motion_rms"],
                "rest_index": max(
                    0.0,
                    1.0 - context["motion_rms"] / 0.20
                )
            }

        score = 0

        if 4.0 <= mean_freq <= 6.5:
            score += 35

        if band_ratio > 0.18:
            score += 30

        if axis_agreement > 0.85:
            score += 20

        if axis_dominance > 0.50:
            score += 20

        if context["state"] == "ACTIVE":
            score -= 40

        score = max(0, min(score, 100))

        tremor = score >= 80

        if score < 20:
            severity = "NONE"

        elif score < 40:
            severity = "VERY MILD"

        elif score < 60:
            severity = "MILD"

        elif score < 80:
            severity = "MODERATE"

        elif score < 95:
            severity = "HIGH"

        else:
            severity = "SEVERE"

        confidence = int(
            score * axis_agreement
        )

        return {

            "tremor": tremor,

            "score": score,

            "confidence": confidence,

            "severity": severity,

            "frequency": mean_freq,

            "frequency_std": freq_std,

            "band_ratio": band_ratio,

            "axis_agreement": axis_agreement,

            "axis_dominance": axis_dominance,

            "best_axis": best_axis,

            "motion_state": context["state"],

            "motion_rms": context["motion_rms"],

            "rest_index": max(
                0.0,
                1.0 - context["motion_rms"] / 0.20
            )
        }
