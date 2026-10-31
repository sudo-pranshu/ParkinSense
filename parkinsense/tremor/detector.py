"""
Per-window tremor evidence (algorithm v3).

Replaces the v2 additive point score (35 + 30 + 20 + 20 points for
hand-picked gates). Each window now yields a bounded *evidence* value in
[0, 1] built from quantities with physical meaning:

  * spectral peak SNR in the 3.5-7.5 Hz band (peak PSD vs the 2-12 Hz
    median floor) -- is there a narrow-band oscillation at all?
  * tremor amplitude, RMS angular velocity within +-0.625 Hz of the peak
    (deg/s) -- is it above the sensor/postural noise floor?
    Physical-unit amplitude follows Elble & McNames, "Using portable
    transducers to measure tremor severity", Tremor Other Hyperkinet Mov
    2016;6:375.
  * peak location -- a maximum sitting on the band edge is the skirt of an
    out-of-band oscillation (e.g. 9 Hz physiological tremor, 15 Hz
    vibration), not an in-band peak.
  * harmonic check -- during purposeful movement, a peak at an integer
    multiple (>= 2) of the dominant 0.5-3 Hz movement frequency is treated
    as a movement harmonic (arm swing while walking), not tremor.

The logistic midpoints/widths below are engineering settings chosen from
the synthetic suite and checked against the in-repo real recordings; they
are NOT trained on labelled patient data (none exists in this repository).
They are therefore not a calibrated probability of tremor. Temporal
integration lives in `temporal.py`.

No clinical severity is produced. The v2 "severity" labels (VERY MILD ...
SEVERE) were mapped from an uncalibrated point score and had no clinical
basis; the field is kept in the schema as "NOT_ASSESSED" / "NONE" and the
measured `tremor_amplitude_dps` is published instead.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from parkinsense.config import TREMOR_BAND_HZ, MotionState
from parkinsense.motion.features import SpectralFeatures

SNR_MID_DB = 10.0
SNR_WIDTH_DB = 2.0
AMP_MID_DPS = 1.0
AMP_WIDTH_DPS = 0.25
EDGE_GUARD_HZ = 0.15
HARMONIC_TOL_HZ = 0.15
HARMONIC_MAX_ORDER = 4
HARMONIC_MIN_ARM_DPS = 10.0
HARMONIC_PENALTY = 0.15
DETECT_EVIDENCE = 0.5


def _sig(x):
    return float(1.0 / (1.0 + np.exp(-x)))


@dataclass
class TremorEvidence:
    evidence: float
    detected_window: bool
    frequency_hz: float
    amplitude_dps: float
    snr_db: float
    at_band_edge: bool
    movement_harmonic: bool
    tremor_type: str            # REST | ACTION | NONE


def evaluate(f: SpectralFeatures, motion_state: str) -> TremorEvidence:
    lo, hi = TREMOR_BAND_HZ
    edge = f.peak_frequency_hz <= lo + EDGE_GUARD_HZ or f.peak_frequency_hz >= hi - EDGE_GUARD_HZ

    harmonic = False
    if f.arm_rms_dps >= HARMONIC_MIN_ARM_DPS and f.arm_peak_frequency_hz > 0.3:
        k = f.peak_frequency_hz / f.arm_peak_frequency_hz
        kr = round(k)
        if 2 <= kr <= HARMONIC_MAX_ORDER and abs(f.peak_frequency_hz - kr * f.arm_peak_frequency_hz) <= HARMONIC_TOL_HZ:
            harmonic = True

    e = _sig((f.peak_snr_db - SNR_MID_DB) / SNR_WIDTH_DB) * _sig((f.tremor_rms_dps - AMP_MID_DPS) / AMP_WIDTH_DPS)
    if edge:
        e *= 0.0
    if harmonic:
        e *= HARMONIC_PENALTY

    det = e >= DETECT_EVIDENCE
    state = MotionState.parse(motion_state)
    ttype = "NONE" if not det else ("ACTION" if state == MotionState.ACTIVE else "REST")
    return TremorEvidence(e, det, f.peak_frequency_hz, f.tremor_rms_dps, f.peak_snr_db,
                          edge, harmonic, ttype)
