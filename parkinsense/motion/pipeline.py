"""
Motion pipeline: one analysis window -> motion context + tremor biomarkers.

Owns only motion processing. PPG is owned by the runtime as a sibling
(review P2-11): the previous `MotionPipeline` constructed a `PPGProcessor`
with the wrong default sample rate (audit P0-2) and never passed it the
motion state (audit P1-5).

Window flow:
    gyro (3,n) --Welch per axis (raw, mean-removed)--> SpectralFeatures
    accel (3,n) + arm-band gyro RMS --> MotionContext (excludes tremor band)
    features + context --> TremorEvidence (per window)
    evidence + signal time --> TremorHMM (temporal posterior, published)
"""

from __future__ import annotations

import numpy as np

from parkinsense.config import SAMPLE_RATE_HZ, Quality
from parkinsense.motion import features as F
from parkinsense.motion.context import MotionContext
from parkinsense.tremor import detector as D
from parkinsense.tremor.temporal import TremorHMM

# A window with more than this fraction of (possibly) clipped samples cannot
# yield a trustworthy spectrum: clipping/wrap manufactures broadband energy.
MAX_CLIPPED_FRACTION = 0.02


class MotionPipeline:
    def __init__(self, fs: float = SAMPLE_RATE_HZ):
        self.fs = fs
        self.context = MotionContext(fs)
        self.hmm = TremorHMM()

    def reset(self):
        self.hmm.reset()

    def process(self, accel, gyro, t: float, clipped_fraction: float = 0.0,
                usable: bool = True) -> dict:
        """
        accel, gyro: (3, n) arrays in g and deg/s for one full window.
        t: signal time (s) of the window's last sample.
        usable: False when the window is known to be invalid (rate invalid,
            spans a gap); the HMM then only predicts and outputs are marked.
        """
        accel = np.asarray(accel, dtype=float)
        gyro = np.asarray(gyro, dtype=float)
        feats = F.extract(gyro, self.fs)
        ctx = self.context.classify(accel, feats.arm_rms_dps)
        ev = D.evaluate(feats, ctx["state"])

        quality = Quality.VALID
        if clipped_fraction > MAX_CLIPPED_FRACTION:
            quality = Quality.SENSOR_FAULT
        if not usable:
            quality = Quality.DATA_GAP
        use_ev = ev.evidence if quality == Quality.VALID else None
        temporal = self.hmm.update(use_ev, t)

        published = temporal["confirmed"]
        if published and quality == Quality.VALID and temporal["probability"] < 0.95:
            q_out = Quality.LOW_CONFIDENCE.value
        else:
            q_out = quality.value

        result = {
            # legacy-compatible keys (meanings documented in docs/validation/METRICS.md)
            "tremor": bool(published),
            "score": int(round(100 * ev.evidence)),
            "confidence": round(100 * temporal["probability"], 1),
            "severity": "NOT_ASSESSED" if published else "NONE",
            "frequency": round(ev.frequency_hz, 2),
            "frequency_std": round(feats.frequency_std, 3),
            "band_ratio": round(feats.band_ratio, 4),
            "best_axis": feats.best_axis,
            "axis_agreement": round(feats.axis_agreement, 3),
            "axis_dominance": round(feats.axis_dominance, 3),
            "rest_index": round(max(0.0, 1.0 - ctx["motion_rms"] / 0.20), 3),
            # v3 additions
            "tremor_state": temporal["state"],
            "tremor_probability": round(temporal["probability"], 4),
            "tremor_evidence": round(ev.evidence, 4),
            "tremor_window_detected": ev.detected_window,
            "tremor_type": ev.tremor_type if published else "NONE",
            "tremor_amplitude_dps": round(ev.amplitude_dps, 3),
            "tremor_power": round(feats.tremor_power, 4),
            "tremor_snr_db": round(ev.snr_db, 2),
            "arm_movement_rms_dps": round(feats.arm_rms_dps, 3),
            "spectral_entropy": round(feats.spectral_entropy, 4),
            "movement_harmonic": ev.movement_harmonic,
            "tremor_quality": q_out,
        }
        return {"result": result, "context": ctx, "features": feats}
