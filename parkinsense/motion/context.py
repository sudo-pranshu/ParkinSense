"""
Motion context: REST / LOW MOTION / ACTIVE for one analysis window.

v3 change (ADR-0005): the context is computed from *non-tremor-band*
movement only -- linear acceleration band-limited to 0.2-3 Hz and gyroscope
power in 0.5-3 Hz -- so a tremor's own oscillation can no longer classify
the wrist as ACTIVE and veto its own detection. In the v2.2 baseline,
120-250 deg/s rest tremor was published as TREMOR in only 38 % of analyses
for exactly this reason (benchmarks/results).

Thresholds: accelerometer thresholds keep their historical values
(0.03 g / 0.20 g RMS) but now apply to the band-limited signal. Gyroscope
thresholds (10 / 30 deg/s RMS in 0.5-3 Hz) were set so that the synthetic
rest scenario (postural micro-motion ~1 deg/s) stays REST and purposeful
movement (25-140 deg/s) is ACTIVE; they are engineering settings, not
physiological constants, and are covered by regression tests.
"""

from __future__ import annotations

import numpy as np

from parkinsense.config import MotionState
from parkinsense.motion.filters import Bandlimit, GravityRemoval

ACC_REST_G = 0.03
ACC_ACTIVE_G = 0.20
GYRO_LOW_DPS = 10.0
GYRO_ACTIVE_DPS = 30.0
_ORDER = (MotionState.REST, MotionState.LOW_MOTION, MotionState.ACTIVE)


class MotionContext:
    def __init__(self, fs: float):
        self.fs = fs
        self._gravity = GravityRemoval(fs)
        self._band = Bandlimit(fs, low=0.2, high=3.0)

    def classify(self, accel: np.ndarray, arm_rms_dps: float | None = None) -> dict:
        """accel: (3, n) in g. arm_rms_dps: gyro RMS in 0.5-3 Hz from features."""
        lin = self._gravity.remove(np.asarray(accel, dtype=float))
        lin = self._band(lin)
        q = lin.shape[1] // 4          # central half: avoid filter edge transients
        lin = lin[:, q:-q] if q > 0 else lin
        mag = np.sqrt(np.sum(lin ** 2, axis=0))
        acc_rms = float(np.sqrt(np.mean(lin ** 2) * 3))   # RMS of the vector magnitude

        if acc_rms < ACC_REST_G:
            s_acc = MotionState.REST
        elif acc_rms < ACC_ACTIVE_G:
            s_acc = MotionState.LOW_MOTION
        else:
            s_acc = MotionState.ACTIVE

        s = s_acc
        if arm_rms_dps is not None:
            if arm_rms_dps >= GYRO_ACTIVE_DPS:
                s_g = MotionState.ACTIVE
            elif arm_rms_dps >= GYRO_LOW_DPS:
                s_g = MotionState.LOW_MOTION
            else:
                s_g = MotionState.REST
            s = max(s_acc, s_g, key=_ORDER.index)

        return {
            "state": s.value,
            "motion_rms": acc_rms,
            "arm_rms_dps": arm_rms_dps,
            "accel_magnitude_peak_g": float(mag.max()) if mag.size else 0.0,
        }
