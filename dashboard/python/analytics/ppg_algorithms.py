"""
ParkinSense — PPG Signal Processing Algorithms
================================================

Stateless, reusable signal-processing functions for photoplethysmography
(PPG) data acquired from a MAX30102-class pulse oximeter (IR + RED LEDs,
18-bit ADC, typically sampled at 25-100 Hz).

Scope & honesty notice
-----------------------
These are research/hobbyist-grade estimators for a DIY wearable platform.
Nothing here is clinically validated or FDA-cleared. The techniques mirror,
at a conceptual level, what consumer wearables (WHOOP, Fitbit, Garmin,
Apple Watch, Polar) publicly describe doing: band-limiting the PPG signal
to the cardiac band, adaptive peak detection with physiological bounds and
outlier rejection, and ratio-of-ratios SpO2 estimation with an empirical
calibration curve. Treat all outputs as estimates, not diagnoses.

Every function operates on 1-D array-like sample buffers (IR / RED channel
counts) and returns plain dicts/floats — no hidden state (except the
explicitly documented SpO2 smoothing state), easy to unit test.
"""

from __future__ import annotations

import numpy as np
from scipy.interpolate import CubicSpline
from scipy.ndimage import uniform_filter1d
from scipy.signal import butter, correlate as _sig_correlate, filtfilt, find_peaks

# ---------------------------------------------------------------------------
# Constants — every threshold below is explained rather than left "magic".
# ---------------------------------------------------------------------------

# --- Cardiac band-pass ---
# Resting-to-vigorous human heart rate spans ~40-200 BPM (0.67-3.3 Hz).
# We use a slightly wider pass-band (0.5-4.5 Hz) so the filter's transition
# band doesn't attenuate the fundamental near the edges, while still
# rejecting respiration-driven baseline wander (~0.15-0.4 Hz) and
# high-frequency motion/EMG noise above the highest plausible harmonic.
HR_BAND_LOW_HZ = 0.5
HR_BAND_HIGH_HZ = 4.5
BUTTER_ORDER = 3  # 3rd-order Butterworth: adequate roll-off, stays numerically stable with filtfilt

# --- Physiological bounds ---
MIN_BPM = 40.0
MAX_BPM = 200.0
MIN_RR_SEC = 60.0 / MAX_BPM  # shortest plausible beat-to-beat interval
MAX_RR_SEC = 60.0 / MIN_BPM  # longest plausible beat-to-beat interval

# --- Peak detection ---
# Rolling normalization window: converts the band-passed signal into local
# z-scores (subtract rolling mean, divide by rolling std) before peak
# detection. This is what actually implements the "adaptive threshold"
# (rolling_mean + k*rolling_std) approach common in PPG/ECG beat-detection
# literature — by normalizing first, a single fixed k works as the
# threshold at every point in time, rather than recomputing
# rolling_mean + k*rolling_std explicitly at every sample.
NORMALIZATION_WINDOW_SECONDS = 3.0
# k in "threshold = local_mean + k * local_std". 0.5-1.0 is the commonly
# cited range for adaptive PPG/ECG beat thresholds; 0.6 sits in the
# permissive half so beats aren't missed during lower-perfusion periods.
PEAK_ADAPTIVE_K = 0.6

# Refractory period: deliberately a *detection-time* floor, looser than the
# MIN_BPM/MAX_BPM bounds used later to judge whether a *reported* heart
# rate is plausible. 222 BPM / 270 ms sits just above the commonly-cited
# ~220 BPM absolute human max, so the detector can see genuinely fast beats
# without prematurely discarding them — the physiological-bounds and
# MAD-outlier stages further down are where we actually decide what's
# plausible to report.
PEAK_REFRACTORY_BPM_MAX = 222.0
PEAK_REFRACTORY_SEC = 60.0 / PEAK_REFRACTORY_BPM_MAX

# Typical PPG systolic pulse width (half-prominence width) reported in
# wearable-PPG literature sits roughly in the 80-350 ms range; outside
# that, a "peak" is more likely a motion spike (too narrow) or a slow
# baseline ripple that survived the band-pass (too wide).
MIN_PEAK_WIDTH_SEC = 0.08
MAX_PEAK_WIDTH_SEC = 0.35

# --- Local energy and adaptive prominence (Phase 2.1 improvements) ---
# Short-time energy (STE) is computed over a ~0.4 s Hamming-weighted window.
# 0.4 s is slightly longer than the shortest plausible PPG systolic upstroke
# (~80 ms) but shorter than the shortest full pulse (~270 ms at 222 BPM),
# so the STE reflects the instantaneous pulsatile amplitude rather than
# spanning multiple beats. Hamming rather than rectangular weighting reduces
# spectral leakage so energy estimates are smoother near burst boundaries.
LOCAL_ENERGY_WINDOW_SEC = 0.4

# Exponent for energy-scaled adaptive prominence. Required prominence is
# scaled as: k_adaptive = PEAK_ADAPTIVE_K × (local_energy / median_energy)^alpha.
# alpha = 0.5 (square-root) produces moderate adaptation: doubling local
# energy raises the bar by only ~41%, not 100%, preventing over-suppression
# of real beats in high-perfusion bursts without ignoring the energy context.
ADAPTIVE_PROMINENCE_ALPHA = 0.5

# Peaks whose local STE is below this fraction of the buffer-wide median STE
# are suppressed regardless of their z-score. Flat-line segments (sensor
# lift, zero-perfusion) can produce z-scores near 1 through normalization
# amplification of sub-noise-floor fluctuations; the energy gate rejects
# these before they enter the beat-confidence scoring pipeline.
MIN_LOCAL_ENERGY_FRACTION = 0.05

# --- Per-beat confidence scoring ---
# Reference scales (in local z-score units) a "strong, trustworthy" beat
# is expected to clear comfortably; used only to map raw prominence/height
# onto a 0-1 sub-score, not as hard accept/reject thresholds (those are
# PEAK_ADAPTIVE_K above, already applied at detection time).
BEAT_PROMINENCE_Z_REF = 1.5
BEAT_HEIGHT_Z_REF = 2.0

# A real PPG pulse has a fast systolic upstroke and a slower diastolic
# decay, so a healthy beat is *expected* to be asymmetric, not symmetric.
# shape_ratio = 2 * min(rise, fall) / (rise + fall) approaches 0 for a
# narrow, spike-like artifact and 1 for a perfectly even rise/fall; real
# pulses typically land around 0.4-0.7, so scoring against a reference of
# 0.6 gives full credit to plausible pulses without demanding symmetry.
BEAT_SHAPE_RATIO_REF = 0.6

# Optimal pulse width (center of 80-350 ms physiological band) for width
# scoring. Score peaks at this value and rolls off linearly toward the band
# edges. 150 ms corresponds to ~70 BPM — the population-mean resting HR —
# so a healthy resting pulse scores near 1.0.
BEAT_PULSE_WIDTH_OPTIMAL_SEC = 0.15

# Expected ratio of rise_time / total_pulse_width for a real PPG systolic
# peak. Elgendi (2016) reports the systolic upstroke occupies approximately
# one third of the total pulse duration; the diastolic downstroke ~two thirds.
# Scoring the upstroke/downstroke asymmetry against these references adds
# morphological specificity without requiring a template-matching approach.
BEAT_UPSTROKE_RATIO_REF = 0.35    # rise_samples / total_width ≈ 1/3
BEAT_DOWNSTROKE_RATIO_REF = 0.65  # fall_samples / total_width ≈ 2/3

# Local SNR reference: a peak z-score of 3.0 above the local noise floor
# qualifies as "excellent". Peaks barely above the detection threshold (~0.6)
# score near 0. Chosen so a clinical-grade signal (~20 dB SNR) scores > 0.9
# and an artifact-dominated signal (~5 dB) scores < 0.3.
BEAT_LOCAL_SNR_REF = 3.0

# --- MAX30102 ADC characteristics ---
ADC_MAX_VALUE = 262_143  # 2**18 - 1 (18-bit resolution)
SATURATION_FRACTION = 0.98  # counts above this fraction of full-scale are "clipped"

# --- Finger-presence thresholds ---
# Typical MAX30102 IR DC level with a finger resting on the sensor at
# default LED current sits in the tens-of-thousands to low-hundred-thousands
# range; "no finger" reads near the ADC floor (ambient light / dark noise).
FINGER_DC_MIN = 5_000
FINGER_DC_MAX = ADC_MAX_VALUE * SATURATION_FRACTION
FINGER_MIN_AC_COUNTS = 5.0  # minimum pulsatile std-dev to call it a real pulse, not noise
# The pulsatile (AC) fraction of the total (DC) signal for real tissue is
# small — commonly cited as roughly 0.05%-10% depending on perfusion and LED
# drive current. Ratios outside this band suggest noise or a non-tissue
# reflectance (e.g. a desk, a fingernail with poor contact).
FINGER_AC_DC_RATIO_MIN = 0.0005
FINGER_AC_DC_RATIO_MAX = 0.10
FINGER_MIN_STABLE_SECONDS = 2.0  # how long DC level must hold steady to trust a reading

# Perfusion index (PI = AC/DC × 100 %) thresholds for finger detection.
# PI < 0.02 % indicates extremely poor tissue perfusion or no contact.
# PI > 10 % is physiologically implausible and suggests a non-tissue
# reflector or severe LED over-drive. These are numerically equivalent to
# FINGER_AC_DC_RATIO bounds but expressed as percent (matching the clinical
# PI definition used in pulse-oximetry literature) for explicit clarity.
FINGER_PI_MIN_PCT = 0.02   # 0.02 % ≡ 0.0002 AC/DC
FINGER_PI_MAX_PCT = 10.0   # 10.0 % ≡ 0.10 AC/DC

# Pulse repeatability gate: coefficient of variation (CV) of beat-to-beat
# peak amplitude in the filtered signal. Real tissue generates pulses of
# consistent height (CV typically < 0.3); random noise or a hard surface
# produces wildly varying apparent "beats" (CV > 0.5).
FINGER_PULSE_REPEATABILITY_CV_MAX = 0.5

# Spectral concentration lower bound for finger detection. Fraction of total
# spectral power that must fall within ±0.2 Hz of the dominant cardiac
# frequency. A real pulsatile signal concentrates energy at a narrow peak;
# broad-band noise spreads it across all bins.
FINGER_SPECTRAL_CONCENTRATION_MIN = 0.15

# --- SpO2 calibration ---
# Empirical linear calibration kept as fallback; primary curve is the
# CubicSpline built from published knots below (_SPO2_SPLINE).
SPO2_CAL_A = 110.0
SPO2_CAL_B = 25.0
SPO2_PHYSIO_MIN = 70.0
SPO2_PHYSIO_MAX = 100.0
# R (ratio-of-ratios) values outside this range indicate the estimate is
# almost certainly driven by noise rather than real arterial pulsation.
SPO2_R_MIN = 0.2
SPO2_R_MAX = 2.0

# Piecewise calibration breakpoint: kept for backward compatibility with the
# _spo2_calibrate_linear fallback used when scipy is unavailable.
SPO2_CAL_BREAKPOINT_R = 0.9
SPO2_CAL_A2 = 108.0
SPO2_CAL_B2 = 20.0

# --- SpO2 cubic spline calibration (Improvement 4) ---
# Knot points derived from Severinghaus (1979) and Maxim AN6409 Table 2.
# The relationship between the ratio-of-ratios R and arterial SpO2 is
# monotonically decreasing and mildly nonlinear, especially in the hypoxic
# range (R > 0.9, SpO2 < ~86%). A cubic spline over 10 calibration points
# captures this nonlinearity more accurately than two linear segments while
# remaining fully deterministic and parameter-free at runtime.
# CAUTION: these knots are approximate literature values — accurate absolute
# calibration requires simultaneous co-oximeter reference measurements.
_SPO2_CAL_R_KNOTS = np.array(
    [0.40, 0.50, 0.60, 0.70, 0.80, 0.90, 1.00, 1.10, 1.20, 1.40]
)
_SPO2_CAL_SPO2_KNOTS = np.array(
    [100.0, 97.5, 95.0, 92.5, 89.5, 85.5, 81.0, 76.0, 72.0, 70.0]
)
# Built once at import time; evaluating the spline at runtime is O(log n).
# bc_type='natural' (zero second derivative at both endpoints) is used rather
# than the default 'not-a-knot' because the natural boundary condition
# guarantees monotonicity for this strictly-decreasing calibration data,
# whereas not-a-knot produces an overshoot near the last two knots that
# creates a positive derivative (SpO2 incorrectly rising with R) above R≈1.35.
_SPO2_SPLINE = CubicSpline(_SPO2_CAL_R_KNOTS, _SPO2_CAL_SPO2_KNOTS, bc_type="natural")
# Derivative of the spline — used for first-order uncertainty propagation
# (dSpO2/dR × sigma_R → sigma_SpO2) without re-fitting anything at runtime.
_SPO2_SPLINE_DERIV = _SPO2_SPLINE.derivative()

# --- SpO2 DC estimation (Improvement 1) ---
# Butterworth low-pass cutoff for the baseline (DC) tracker. 0.5 Hz is well
# above the lowest plausible breathing rate (~0.1 Hz at 6 BPM) but well
# below the cardiac fundamental (~0.67 Hz at 40 BPM), so it tracks slow
# finger-pressure, LED-ageing, and temperature drift without contaminating
# the pulsatile estimate. Matches the _lowpass_dc helper already in the file.
SPO2_DC_CUTOFF_HZ = 0.5

# --- SpO2 cross-correlation alignment (Improvement 2) ---
# Maximum plausible lag between the IR and RED channel pulses in ms. On a
# MAX30102-class sensor the two LEDs illuminate the same tissue volume;
# propagation-path differences are < 1 ms. We allow 20 ms to accommodate
# multipath reflectance differences and slight LED-drive timing offsets.
# Lags beyond this are treated as correlation noise, not real alignment.
SPO2_XCORR_MAX_LAG_MS = 20.0
# Minimum peak-to-mean power ratio of the cross-correlation function for the
# lag estimate to be trusted. Below this threshold the xcorr is too flat
# (channels not well correlated) and we fall back to argmax search.
SPO2_XCORR_MIN_PEAK_RATIO = 1.5

# --- SpO2 AC method (Improvement 3) ---
# String constant documenting that we use area-under-curve (AUC) rather than
# peak-to-trough amplitude for AC estimation. AUC is 3-5x more stable under
# motion because motion transients shift the peak but preserve waveform area
# (Motin et al. 2019, "Pulse Oximetry Signal Processing").
SPO2_AC_METHOD = "area"   # "area" | "peak_trough" for documentation only

# --- SpO2 adaptive window (Improvement 6) ---
# Expansion multipliers tried in order when beat-level mode yields fewer than
# SPO2_MIN_BEATS accepted beats. The sub-window grows from the caller-supplied
# sub_window_seconds × 1.0 up to × 3.0, giving the detector more signal to
# work with in low-perfusion or low-HR states before falling back to the
# window-std method.
SPO2_ADAPTIVE_WINDOW_MULTS: tuple = (1.0, 1.5, 2.0, 3.0)
SPO2_MIN_BEATS = 2  # minimum accepted beats to use beat-level mode

# --- SpO2 Kalman filter (Improvement 7, replaces EMA) ---
# 1-D scalar Kalman filter state stored in _spo2_state.
#
# Process noise Q: variance of the SpO2 random walk per update step.
# A real desaturation event (98% → 92%) unfolds over 20-40 s. At a
# 2 s update cadence that is ~3 updates, implying ~2%/update max change.
# Q = 0.25 corresponds to a process std of 0.5%/update — permissive enough
# to track real desaturation while resisting single-sample noise jumps.
SPO2_KALMAN_Q = 0.25
#
# Measurement noise R_base: the variance of the SpO2 estimate at confidence=1.
# 4.0 → measurement std ≈ 2% at full confidence, matching the typical ±2%
# accuracy specification of consumer reflectance pulse oximeters (ISO 80601-2-61).
# At confidence=c, R_meas = R_base / max(c, 0.1)^2, so low-quality
# measurements are treated with proportionally less trust.
SPO2_KALMAN_R_BASE = 4.0
#
# Initial Kalman error variance P₀ = 25 → initial std = 5%, reflecting
# complete uncertainty before the first measurement is collected.
SPO2_KALMAN_P_INIT = 25.0

# Beat-level quality gates for SpO2 R estimation. Only beats with confidence
# >= SPO2_BEAT_CONFIDENCE_MIN contribute to the weighted median R.
SPO2_BEAT_CONFIDENCE_MIN = 0.4

# --- SpO2 motion handling (Improvements 7b + 9) ---
# Below SPO2_MOTION_FREEZE_THRESHOLD the Kalman filter still updates but at
# very low weight (effectively frozen), returning the last trusted estimate
# with halved confidence instead of a noise-driven measurement.
SPO2_MOTION_FREEZE_THRESHOLD = 0.3
# Differential motion compensation (ANC approach) is applied only in the
# moderate-motion regime where it contributes most. Above the HIGH threshold
# motion is negligible and compensation is skipped (no benefit, slight cost).
# Below the LOW threshold we are already in the freeze regime.
SPO2_MOTION_COMP_THRESHOLD_LOW  = 0.3   # = SPO2_MOTION_FREEZE_THRESHOLD
SPO2_MOTION_COMP_THRESHOLD_HIGH = 0.7

# Kept for any external code that reads the EMA constant; smoothing is now
# done via the Kalman filter but the name is preserved for compatibility.
SPO2_SMOOTHING_ALPHA = 0.3
SPO2_MAX_JUMP_PER_UPDATE = 4.0  # percent — used as Kalman innovation clamp

# --- Respiratory suppression (Improvement 10) ---
# Human respiration rate spans 0.15-0.4 Hz (9-24 BPM); we set the low-pass
# cutoff at 0.5 Hz to include a small margin above the highest plausible rate.
RESP_BAND_HIGH_HZ = 0.5
# 2nd-order Butterworth for envelope extraction: gentle roll-off so it does
# not distort the very-low-frequency respiratory rhythm it is meant to track.
RESP_LP_ORDER = 2

# --- Dominant cardiac frequency check ---
# A true pulse concentrates most of its spectral energy in a narrow band
# around the fundamental heart rate. Periodic non-physiological noise
# (e.g. mains-coupled interference, a rhythmic mechanical tap) can pass
# the amplitude/ratio checks above but will not show a clear peak inside
# this narrower physiological range, so it's a useful independent check.
CARDIAC_FREQ_MIN_HZ = 0.8   # 48 BPM
CARDIAC_FREQ_MAX_HZ = 3.0   # 180 BPM
# Minimum fraction of in-band spectral power that must sit inside the
# cardiac frequency window for us to trust that a real pulse is present.
CARDIAC_POWER_RATIO_MIN = 0.15

# Spectral concentration bandwidth: fraction of total power within ±BW Hz
# of the dominant cardiac frequency. 0.2 Hz spans the natural beat-to-beat
# HR variability of a resting individual (±12 BPM / Hz at 1 Hz), so a real
# pulse contributes nearly all of its fundamental power within this band.
SQI_SPECTRAL_CONCENTRATION_BW_HZ = 0.2

# Harmonic integration bandwidth: ±BW Hz around 2f₀ and 3f₀.
# A real PPG waveform produces strong 2nd and 3rd harmonics; motion artifacts
# produce a broader, less harmonic spectrum. 0.15 Hz is wide enough to capture
# the harmonic even when HR drifts slightly during the analysis window.
SQI_HARMONIC_BW_HZ = 0.15

# --- Sensor status classification ---
SENSOR_STATUS_LOW_DC = FINGER_DC_MIN
SENSOR_STATUS_HIGH_DC = ADC_MAX_VALUE * 0.85
SENSOR_STATUS_CLIPPING_FRACTION = 0.01  # >1 % of samples pinned at the rail

# --- HRV quality gates ---
# Minimum number of clean (artifact-free) RR intervals required before
# computing HRV metrics. Below this threshold, RMSSD and SDNN estimates
# are unreliable. Clinical HRV guidelines (Task Force 1996) suggest ≥ 5
# intervals for short-term frequency-domain analysis; we require 4 as a
# practical minimum for time-domain metrics, accepting the reduced statistical
# stability in exchange for producing some output from short capture windows.
HRV_MIN_CLEAN_INTERVALS = 4

# RR intervals deviating more than this fraction from the local median are
# flagged as artifacts before HRV computation. 25 % is slightly more
# conservative than the commonly-cited 20 % ectopic-beat threshold
# (Clifford et al. 2006) to account for additional noise in a PPG-derived
# RR series vs. an ECG-derived one.
HRV_ARTIFACT_RR_TOLERANCE = 0.25


# ---------------------------------------------------------------------------
# Module-level optional state — SpO2 Kalman smoother
# ---------------------------------------------------------------------------
# This module is designed stateless: every public function accepts an explicit
# buffer argument with no reliance on call order. The one exception is SpO2
# physiological smoothing, which requires memory of the previous trusted
# estimate. We store it in a module-level dict so the function signature
# remains unchanged and the state can be inspected or reset externally.
#
# Kalman state (Improvement 7):
#   kalman_x : current SpO2 state estimate (None until first measurement)
#   kalman_P : current error covariance (variance in % units)
# The Kalman filter replaces the previous EMA smoother because it is
# confidence-weighted (low-quality measurements barely move the estimate),
# self-adapting (Kalman gain K shrinks as the estimate matures), and produces
# a principled uncertainty output (P_k) used for 95% CI computation (§8).
_spo2_state: dict = {
    "last_spo2": None,
    "last_confidence": 0.0,
    "kalman_x": None,           # state estimate (% SpO2)
    "kalman_P": SPO2_KALMAN_P_INIT,  # error variance (%²)
}


def reset_spo2_state() -> None:
    """
    Reset the SpO2 physiological smoothing / Kalman filter state.

    Call this when starting a new recording session, when the finger is
    removed (detected → not-detected transition), or after a gap in
    measurements longer than ~30 seconds, to prevent the smoother from
    carrying a stale baseline into a fresh measurement window.
    """
    _spo2_state["last_spo2"] = None
    _spo2_state["last_confidence"] = 0.0
    _spo2_state["kalman_x"] = None
    _spo2_state["kalman_P"] = SPO2_KALMAN_P_INIT


# ---------------------------------------------------------------------------
# Small internal helpers
# ---------------------------------------------------------------------------

def _as_float_array(x) -> np.ndarray:
    """Convert deque/list/array input to a contiguous float64 numpy array."""
    return np.asarray(x, dtype=np.float64)


def _min_filtfilt_len(order: int) -> int:
    """
    Minimum sample count filtfilt needs to apply its default edge padding
    for a Butterworth filter of the given order (padlen = 3 * max(len(a),
    len(b) - 1), and len(a) == len(b) == 2*order + 1 for a band-pass).
    """
    return 3 * (2 * order)


def _motion_artifact_score(raw_signal: np.ndarray) -> float:
    """
    Shared motion-artifact sub-score (0-1, higher = less motion) used by
    both `compute_signal_quality` and `estimate_heart_rate`, so the same
    robust-statistics logic isn't duplicated in two places.

    Sample-to-sample jumps far larger than the typical pulsatile
    derivative indicate hand/arm motion rather than a heartbeat. Each
    |diff| is compared against a robust (median + MAD-based) scale rather
    than a fixed count threshold, so it adapts to different perfusion
    levels and LED drive currents.
    """
    if raw_signal.size < 3:
        return 1.0
    diffs = np.abs(np.diff(raw_signal))
    median_diff = float(np.median(diffs)) + 1e-9
    mad = float(np.median(np.abs(diffs - median_diff))) + 1e-9
    outlier_fraction = float(np.mean(diffs > median_diff + 10 * mad))
    return float(np.clip(1.0 - outlier_fraction * 10.0, 0.0, 1.0))


def _rolling_mean_std(x: np.ndarray, window: int) -> tuple[np.ndarray, np.ndarray]:
    """
    Rolling mean and standard deviation via a uniform (box) filter — O(n),
    no explicit Python loop. `var = E[x^2] - E[x]^2`, clipped at 0 to guard
    against tiny negative values from floating-point cancellation.
    """
    window = max(min(window, x.size), 3)
    mean = uniform_filter1d(x, size=window, mode="nearest")
    mean_sq = uniform_filter1d(x * x, size=window, mode="nearest")
    var = np.clip(mean_sq - mean * mean, 0.0, None)
    return mean, np.sqrt(var)


def _normalize_signal(filtered: np.ndarray, fs: float) -> np.ndarray:
    """
    Rolling z-score normalization: subtract the local (rolling) mean and
    divide by the local (rolling) standard deviation. This is what lets a
    single fixed constant (`PEAK_ADAPTIVE_K`) act as an adaptive
    "rolling_mean + k*rolling_std" threshold at every point in the signal,
    without recomputing that expression by hand at each sample — and it
    makes peak detection robust to perfusion/LED-current changes that
    would otherwise require re-tuning a fixed-count threshold.

    A floor on the local std (based on the buffer's *global* std) prevents
    near-flat segments (e.g. a genuinely weak-perfusion stretch) from
    amplifying tiny fluctuations into spurious full-height "peaks".
    """
    if filtered.size < 3:
        return filtered - np.mean(filtered) if filtered.size else filtered

    window = int(fs * NORMALIZATION_WINDOW_SECONDS)
    local_mean, local_std = _rolling_mean_std(filtered, window)
    global_std = float(np.std(filtered))
    std_floor = np.maximum(local_std, global_std * 0.1 + 1e-9)
    return (filtered - local_mean) / std_floor


def _local_energy_envelope(signal: np.ndarray, fs: float) -> np.ndarray:
    """
    Short-time energy (STE) envelope computed with a Hamming-weighted sliding
    window of length `LOCAL_ENERGY_WINDOW_SEC`.

    STE = sum_k( w[k] * x[n-k]^2 ) where w is a Hamming window normalized
    to sum to 1.0. Captures instantaneous squared amplitude in a perceptually
    smooth, spectrally well-behaved way. The squared signal (not RMS) is
    used because we compare energy *ratios* when computing the adaptive
    prominence floor — the units cancel and the ratio is the same.

    Implemented via `np.convolve` with 'same' mode so the output is the same
    length as the input with no index offset to manage. Edge samples are
    zero-padded (conservative underestimate of energy) which is acceptable
    because edge samples are already less reliable for peak detection.
    """
    win_len = max(int(fs * LOCAL_ENERGY_WINDOW_SEC), 3)
    win_len = min(win_len, signal.size)
    hamming = np.hamming(win_len)
    hamming /= hamming.sum()  # normalize: energy in amplitude² units per sample
    return np.convolve(signal ** 2, hamming, mode="same")


def _weighted_median(values: np.ndarray, weights: np.ndarray) -> float:
    """
    Weighted median of `values` with non-negative `weights`.

    A weighted median x* satisfies: the cumulative weight of all values ≤ x*
    is ≥ W/2 and the cumulative weight of all values ≥ x* is ≥ W/2, where
    W = sum(weights). Unlike the weighted mean, it is resistant to outliers
    — a single large weight on an outlying value does not pull x* toward it
    unless that outlier's weight exceeds half the total weight.

    This property is why we use it for RR-interval aggregation: an occasional
    missed-beat interval (2× true RR) with a low confidence weight does not
    bias the resulting BPM the way it would in a weighted mean.

    Falls back to standard median if all weights are zero or `values` has
    only one element, to maintain a valid return under degenerate inputs.
    """
    if values.size == 0:
        return 0.0
    total_weight = float(np.sum(weights))
    if total_weight <= 0.0 or values.size == 1:
        return float(np.median(values))
    sort_idx = np.argsort(values)
    cumulative = np.cumsum(weights[sort_idx])
    idx = int(np.searchsorted(cumulative, total_weight / 2.0))
    idx = min(idx, values.size - 1)
    return float(values[sort_idx[idx]])


def _compute_spectrum(filtered: np.ndarray, fs: float) -> dict:
    """
    Compute a Hann-windowed power spectrum of the band-passed signal once
    and return all derived spectral features needed by both
    `compute_signal_quality` and `assess_finger_presence`.

    Sharing a single FFT call eliminates redundant computation when both
    functions are called in the same pipeline update step (the common case).

    Returns
    -------
    dict with keys:
      freqs                : FFT frequency bins (Hz), shape (N//2+1,)
      power                : periodogram power (amplitude²), same shape
      total_power          : scalar sum of all power bins
      cardiac_mask         : boolean mask selecting [CARDIAC_FREQ_MIN_HZ,
                             CARDIAC_FREQ_MAX_HZ] bins
      dominant_freq        : dominant frequency within cardiac band (Hz),
                             or None if the buffer is too short
      cardiac_power_ratio  : fraction of total power within cardiac band
      spectral_entropy     : normalized Shannon entropy of the cardiac-band
                             power spectrum; 1.0 = perfectly periodic (all
                             power in one bin), 0.0 = white noise
      spectral_concentration: fraction of *total* power within ±0.2 Hz of
                             the dominant cardiac frequency
      harmonic_ratio       : (P_2f₀ + P_3f₀) / P_f₀ — real PPG waveforms
                             have significant harmonic content; noise does not
    """
    n = filtered.size
    if n < int(fs * 3):  # need ≥ 3 s to resolve ~1 Hz components
        return {
            "freqs": np.array([]), "power": np.array([]),
            "total_power": 0.0, "cardiac_mask": np.array([], dtype=bool),
            "dominant_freq": None, "cardiac_power_ratio": 0.0,
            "spectral_entropy": 0.0, "spectral_concentration": 0.0,
            "harmonic_ratio": 0.0,
        }

    windowed = filtered * np.hanning(n)
    spectrum = np.abs(np.fft.rfft(windowed))
    freqs = np.fft.rfftfreq(n, d=1.0 / fs)
    power = spectrum ** 2
    total_power = float(np.sum(power)) + 1e-12

    cardiac_mask = (freqs >= CARDIAC_FREQ_MIN_HZ) & (freqs <= CARDIAC_FREQ_MAX_HZ)
    if not np.any(cardiac_mask):
        return {
            "freqs": freqs, "power": power, "total_power": total_power,
            "cardiac_mask": cardiac_mask, "dominant_freq": None,
            "cardiac_power_ratio": 0.0, "spectral_entropy": 0.0,
            "spectral_concentration": 0.0, "harmonic_ratio": 0.0,
        }

    cardiac_power = power[cardiac_mask]
    cardiac_freqs = freqs[cardiac_mask]
    dominant_freq = float(cardiac_freqs[int(np.argmax(cardiac_power))])
    cardiac_power_ratio = float(np.sum(cardiac_power) / total_power)

    # --- Spectral entropy (normalized Shannon entropy of cardiac-band PSD) ---
    # H = -sum( p_i * log(p_i) ) where p_i is the fraction of cardiac-band
    # power in bin i. Normalized by log(N_bins) so the result is in [0, 1]
    # regardless of FFT resolution. Score = 1 - H/H_max so that 1.0 means
    # perfectly periodic (all power in one bin) and 0.0 means white noise.
    # Used in SQI as a spectral-domain quality indicator independent of SNR.
    p_cardiac = cardiac_power / (float(np.sum(cardiac_power)) + 1e-12)
    h_max = np.log(max(p_cardiac.size, 2))
    h_raw = -float(np.sum(p_cardiac * np.log(p_cardiac + 1e-12)))
    spectral_entropy = float(np.clip(1.0 - h_raw / h_max, 0.0, 1.0))

    # --- Spectral concentration: power within ±BW Hz of dominant freq ---
    # Measures the "peakedness" of the cardiac-band spectrum. A clean PPG
    # signal concentrates most of its energy within ±0.2 Hz of the fundamental
    # (equivalent to ±12 BPM at 1 Hz); motion artifacts spread energy broadly.
    bw = SQI_SPECTRAL_CONCENTRATION_BW_HZ
    conc_mask = (freqs >= dominant_freq - bw) & (freqs <= dominant_freq + bw)
    spectral_concentration = float(np.sum(power[conc_mask]) / total_power)

    # --- Harmonic ratio: (P_2f₀ + P_3f₀) / P_f₀ ---
    # Real PPG waveforms are periodic non-sinusoidal signals and therefore have
    # substantial 2nd and 3rd harmonic content. White noise and most motion
    # artifacts have a flat spectrum; the harmonic ratio discriminates.
    # We integrate power within ±SQI_HARMONIC_BW_HZ around each harmonic
    # to capture the harmonic even when HR drifts slightly during the window.
    def _band_power(f_center: float) -> float:
        m = (freqs >= f_center - SQI_HARMONIC_BW_HZ) & (freqs <= f_center + SQI_HARMONIC_BW_HZ)
        return float(np.sum(power[m])) if np.any(m) else 0.0

    p_f0 = _band_power(dominant_freq) + 1e-12
    p_2f0 = _band_power(2.0 * dominant_freq)
    p_3f0 = _band_power(3.0 * dominant_freq)
    harmonic_ratio = float(np.clip((p_2f0 + p_3f0) / p_f0, 0.0, 5.0))

    return {
        "freqs": freqs, "power": power, "total_power": total_power,
        "cardiac_mask": cardiac_mask, "dominant_freq": dominant_freq,
        "cardiac_power_ratio": cardiac_power_ratio,
        "spectral_entropy": spectral_entropy,
        "spectral_concentration": spectral_concentration,
        "harmonic_ratio": harmonic_ratio,
    }


# ---------------------------------------------------------------------------
# Filtering
# ---------------------------------------------------------------------------

def bandpass_filter(
    signal,
    fs: float = 50.0,
    low_hz: float = HR_BAND_LOW_HZ,
    high_hz: float = HR_BAND_HIGH_HZ,
    order: int = BUTTER_ORDER,
) -> np.ndarray:
    """
    Zero-phase Butterworth band-pass filter isolating the cardiac band.

    Removes DC offset and slow baseline wander (below `low_hz`) and
    high-frequency motion/EMG noise (above `high_hz`) in one pass.
    Falls back to simple mean-removal if the buffer is too short for a
    stable filtfilt application (avoids raising on start-up buffers).
    """
    x = _as_float_array(signal)
    if x.size < _min_filtfilt_len(order):
        return x - np.mean(x) if x.size else x

    nyquist = fs / 2.0
    low = max(low_hz / nyquist, 1e-4)
    high = min(high_hz / nyquist, 0.999)
    if low >= high:
        return x - np.mean(x)

    b, a = butter(order, [low, high], btype="band")
    return filtfilt(b, a, x)


def _lowpass_dc(signal, fs: float, cutoff_hz: float = 0.5) -> np.ndarray:
    """
    Low-pass filter used to track the slowly varying DC (tissue baseline)
    component, e.g. for AC/DC ratio calculations that need a DC estimate
    aligned in time with the AC waveform rather than a single scalar mean.
    """
    x = _as_float_array(signal)
    if x.size < _min_filtfilt_len(2):
        return np.full_like(x, np.mean(x)) if x.size else x
    nyquist = fs / 2.0
    b, a = butter(2, min(cutoff_hz / nyquist, 0.999), btype="low")
    return filtfilt(b, a, x)


def dominant_cardiac_frequency(ir, fs: float = 50.0) -> tuple[float | None, float]:
    """
    Locate the dominant frequency in the cardiac band via FFT and report
    what fraction of spectral power it accounts for.

    A Hann window is applied before the FFT to reduce spectral leakage
    (energy smearing across neighbouring bins), which would otherwise make
    a real pulse look less "peaky" than it is. Power is the squared
    magnitude of the FFT, i.e. a periodogram-style power spectrum.

    Returns
    -------
    (dominant_freq_hz, cardiac_power_ratio):
        dominant_freq_hz is None if the buffer is too short to resolve
        anything meaningful in the cardiac band. cardiac_power_ratio is
        the fraction of the *total* spectral power that falls within
        [CARDIAC_FREQ_MIN_HZ, CARDIAC_FREQ_MAX_HZ] — low values mean the
        buffer is dominated by noise outside the physiological range.

    Note: internally delegates to `_compute_spectrum` to share the FFT
    result with `compute_signal_quality` and `assess_finger_presence` when
    called in the same pipeline step.
    """
    ir = _as_float_array(ir)
    filtered = bandpass_filter(ir, fs)
    spec = _compute_spectrum(filtered, fs)
    return spec["dominant_freq"], spec["cardiac_power_ratio"]


# ---------------------------------------------------------------------------
# Finger detection
# ---------------------------------------------------------------------------

def _adaptive_finger_weights(dc_level: float, ac_dc_ratio: float) -> dict[str, float]:
    """
    Compute per-criterion weights for finger confidence scoring, adapted
    to the current signal regime rather than using fixed values.

    Rationale for regime-based adaptation:
      - Very low DC (< 2× FINGER_DC_MIN): the sensor is barely illuminated.
        DC range is the most informative check; pulsatile checks have little
        signal to work with so they are down-weighted to avoid penalizing a
        weakly perfused but genuine contact.
      - Very high DC (> 0.9× FINGER_DC_MAX): saturation risk dominates.
        Up-weight not_saturated; DC check is less informative because we
        already know DC is "too high".
      - Normal regime: balanced weights with DC and cardiac-frequency checks
        sharing the most weight (they answer "is real tissue here?" and
        "is it pulsing physiologically?" respectively).

    All weights are normalized to sum to 1.0.
    """
    if dc_level < 2 * FINGER_DC_MIN:
        raw = {
            "dc_in_range": 0.40, "not_saturated": 0.10, "sufficient_ac": 0.15,
            "plausible_ratio": 0.08, "stable": 0.10,
            "has_cardiac_frequency": 0.12, "perfusion_index_ok": 0.05,
        }
    elif dc_level > 0.9 * FINGER_DC_MAX:
        raw = {
            "dc_in_range": 0.15, "not_saturated": 0.30, "sufficient_ac": 0.15,
            "plausible_ratio": 0.08, "stable": 0.10,
            "has_cardiac_frequency": 0.17, "perfusion_index_ok": 0.05,
        }
    else:
        # Normal regime. DC range and cardiac-frequency share the most weight.
        # perfusion_index_ok is a higher-specificity version of plausible_ratio
        # (expressed as percent rather than ratio) and adds independent
        # discriminative value even when plausible_ratio passes.
        raw = {
            "dc_in_range": 0.22, "not_saturated": 0.10, "sufficient_ac": 0.18,
            "plausible_ratio": 0.08, "stable": 0.10,
            "has_cardiac_frequency": 0.22, "perfusion_index_ok": 0.10,
        }
    total = sum(raw.values())
    return {k: v / total for k, v in raw.items()}


def assess_finger_presence(ir, fs: float = 50.0) -> dict:
    """
    Multi-criteria finger-on-sensor detector.

    A single DC threshold is easily fooled by ambient light leaking into
    the photodiode or by an object other than a finger resting on the
    sensor. Instead we combine several independent signals and require
    the majority to agree, producing a continuous confidence score rather
    than a brittle yes/no cutoff.

    Criteria (each contributes an adaptive weighted vote to `confidence`):
      - DC level within the plausible tissue-contact range
      - not saturating the ADC (motion/pressure can slam the signal to rail)
      - pulsatile AC amplitude is large enough to be a real pulse, not noise
      - AC/DC ratio falls within the physiological perfusion-index range
      - DC level is stable over the recent window (a finger being placed/
        removed, or ambient light flooding the sensor, causes large swings)
      - dominant cardiac frequency present (rejects periodic non-cardiac noise)
      - perfusion index (AC/DC × 100 %) in physiologically valid range
        (more specific than the AC/DC ratio check alone)

    The `_compute_spectrum` helper is called once and its output is shared
    with downstream SQI computation to avoid recomputing the FFT.

    Returns
    -------
    dict with keys: detected (bool), confidence (0-1 float), dc_level,
    ac_amplitude, ac_dc_ratio, saturated (bool), stability (0-1 float),
    reason (str), dominant_frequency_hz, cardiac_power_ratio (all existing),
    plus: perfusion_index (%), contact_quality (0-1 float),
    spectral_concentration (0-1 float), pulse_repeatability (0-1 float),
    frequency_quality (0-1 float, alias for cardiac_power_ratio).
    """
    ir = _as_float_array(ir)
    min_samples = max(int(FINGER_MIN_STABLE_SECONDS * fs), 20)
    if ir.size < min_samples:
        return {
            "detected": False, "confidence": 0.0, "dc_level": 0.0,
            "ac_amplitude": 0.0, "ac_dc_ratio": 0.0, "saturated": False,
            "stability": 0.0, "reason": "insufficient_samples",
            "dominant_frequency_hz": None, "cardiac_power_ratio": 0.0,
            # new fields
            "perfusion_index": 0.0, "contact_quality": 0.0,
            "spectral_concentration": 0.0, "pulse_repeatability": 0.0,
            "frequency_quality": 0.0,
        }

    dc_level = float(np.mean(ir))
    ac_amplitude = float(np.std(ir - dc_level))
    ac_dc_ratio = ac_amplitude / (dc_level + 1e-9)
    perfusion_index = ac_dc_ratio * 100.0  # percent
    saturated = bool(np.max(ir) >= ADC_MAX_VALUE * SATURATION_FRACTION)

    # --- DC stability across ~0.5 s sub-windows ---
    # A finger resting steadily on the sensor gives a near-flat DC trend;
    # ambient light changes or a finger sliding on/off cause large swings.
    sub_window = max(int(fs * 0.5), 1)
    n_sub = ir.size // sub_window
    if n_sub >= 2:
        sub_means = ir[: n_sub * sub_window].reshape(n_sub, sub_window).mean(axis=1)
        relative_drift = float(np.std(sub_means) / (dc_level + 1e-9))
        stability = float(np.clip(1.0 - relative_drift * 20.0, 0.0, 1.0))
    else:
        stability = 0.5  # not enough sub-windows to judge; stay neutral

    # --- Spectral features via shared _compute_spectrum (no duplicate FFT) ---
    filtered = bandpass_filter(ir, fs)
    spec = _compute_spectrum(filtered, fs)
    dominant_freq = spec["dominant_freq"]
    cardiac_power_ratio = spec["cardiac_power_ratio"]
    spectral_concentration = spec["spectral_concentration"]

    has_cardiac_frequency = (
        dominant_freq is not None and cardiac_power_ratio >= CARDIAC_POWER_RATIO_MIN
    )

    # --- Pulse repeatability: CV of beat-to-beat peak heights ---
    # Real tissue generates pulses of consistent amplitude; noise or a hard
    # surface produces randomly varying apparent "beats" with high CV.
    peaks_for_rep = _detect_peaks(filtered, fs, return_properties=False)
    if peaks_for_rep.size >= 3:
        peak_heights = filtered[peaks_for_rep]
        cv_peaks = float(np.std(peak_heights) / (np.abs(np.mean(peak_heights)) + 1e-9))
        pulse_repeatability = float(
            np.clip(1.0 - cv_peaks / FINGER_PULSE_REPEATABILITY_CV_MAX, 0.0, 1.0)
        )
    else:
        pulse_repeatability = 0.0

    # --- Contact quality: mechanical contact score independent of pulsatile
    # quality. Combines DC stability, non-saturation, and proportional DC level.
    # This is useful as a separate diagnostic from overall confidence; low
    # contact_quality with high pulsatile quality can indicate pressure artifact.
    dc_score = float(np.clip(
        (dc_level - FINGER_DC_MIN) / (FINGER_DC_MAX - FINGER_DC_MIN + 1.0),
        0.0, 1.0,
    ))
    contact_quality = float(np.clip(
        stability * (1.0 - float(saturated)) * dc_score, 0.0, 1.0
    ))

    checks = {
        "dc_in_range": FINGER_DC_MIN <= dc_level <= FINGER_DC_MAX,
        "not_saturated": not saturated,
        "sufficient_ac": ac_amplitude >= FINGER_MIN_AC_COUNTS,
        "plausible_ratio": FINGER_AC_DC_RATIO_MIN <= ac_dc_ratio <= FINGER_AC_DC_RATIO_MAX,
        "stable": stability > 0.3,
        "has_cardiac_frequency": has_cardiac_frequency,
        "perfusion_index_ok": FINGER_PI_MIN_PCT <= perfusion_index <= FINGER_PI_MAX_PCT,
    }

    # Adaptive weights based on the current signal regime
    weights = _adaptive_finger_weights(dc_level, ac_dc_ratio)
    confidence = sum(weights[k] for k, passed in checks.items() if passed)

    # Hard requirements: no tissue-range DC, an outright saturated sensor,
    # or the absence of any cardiac-band spectral peak should never be
    # reported as "detected" — these are structural failures that no amount
    # of amplitude/ratio agreement should be able to outvote.
    detected = (
        confidence >= 0.6
        and checks["dc_in_range"]
        and checks["not_saturated"]
        and checks["has_cardiac_frequency"]
    )

    failed = [k for k, passed in checks.items() if not passed]
    reason = "ok" if detected else ("; ".join(failed) if failed else "low_confidence")

    return {
        "detected": detected,
        "confidence": round(confidence, 3),
        "dc_level": round(dc_level, 1),
        "ac_amplitude": round(ac_amplitude, 2),
        "ac_dc_ratio": round(ac_dc_ratio, 5),
        "saturated": saturated,
        "stability": round(stability, 3),
        "reason": reason,
        # existing additive diagnostics
        "dominant_frequency_hz": round(dominant_freq, 3) if dominant_freq is not None else None,
        "cardiac_power_ratio": round(cardiac_power_ratio, 3),
        # new diagnostics
        "perfusion_index": round(perfusion_index, 4),
        "contact_quality": round(contact_quality, 3),
        "spectral_concentration": round(spectral_concentration, 3),
        "pulse_repeatability": round(pulse_repeatability, 3),
        "frequency_quality": round(cardiac_power_ratio, 3),  # explicit alias
    }


# ---------------------------------------------------------------------------
# Signal Quality Index (SQI)
# ---------------------------------------------------------------------------

def compute_signal_quality(ir, fs: float = 50.0) -> dict:
    """
    Composite Signal Quality Index (SQI), 0-100.

    Combines independent quality indicators drawn from PPG-quality
    literature (Elgendi 2016; Orphanidou et al. 2015; Temko 2017).

    Existing components (unchanged):
      - SNR: cardiac-band power vs. out-of-band residual power
      - clipping: fraction of samples pinned near the ADC rail
      - motion artifacts: large sample-to-sample derivative outliers
      - pulse consistency: coefficient of variation of detected RR intervals
      - amplitude: pulsatile AC amplitude relative to minimum trusted level

    New components:
      - spectral_entropy: 1 − normalized Shannon entropy of the cardiac-band
        PSD; 1.0 = perfectly periodic, 0.0 = white noise
      - spectral_concentration: fraction of total power within ±0.2 Hz of
        the dominant cardiac frequency; high = clean, narrow spectral peak
      - harmonic_ratio: (P_2f₀ + P_3f₀) / P_f₀; real PPG waveforms have
        significant harmonic content, broadband noise does not
      - perfusion_index: AC/DC × 100 %, scored logarithmically over the
        0.02-10 % physiological range
      - pulse_repeatability: 1 − CV of beat-to-beat peak amplitude; consistent
        pulse height indicates a stable reflectance surface
      - frequency_stability: 1 − CV of instantaneous frequency (successive
        RR); low CV = regular rhythm, high CV = arrhythmia or motion artifact

    The FFT is computed once via `_compute_spectrum` and its result is shared
    with `assess_finger_presence` when both are called in the same update step.

    Returns a dict with the composite `score` plus all sub-scores (each 0-1
    where defined, snr_db in dB) for debugging/telemetry.
    """
    ir = _as_float_array(ir)
    empty = {
        "score": 0.0, "snr_db": None, "clipping_fraction": None,
        "motion_score": None, "pulse_consistency": None, "amplitude_score": None,
        "spectral_entropy": None, "spectral_concentration": None,
        "harmonic_ratio": None, "perfusion_index": None,
        "pulse_repeatability": None, "frequency_stability": None,
    }
    if ir.size < int(fs * 2):
        return empty

    filtered = bandpass_filter(ir, fs)
    dc_level = float(np.mean(ir))

    # --- SNR: cardiac-band signal power vs. residual (out-of-band) power ---
    residual = (ir - dc_level) - filtered
    signal_power = float(np.var(filtered))
    noise_power = float(np.var(residual)) + 1e-9
    snr_db = 10.0 * np.log10(signal_power / noise_power) if signal_power > 0 else -60.0
    # Map ~0-20 dB onto 0-1; below 0 dB is unusable, above 20 dB is excellent.
    snr_score = float(np.clip(snr_db / 20.0, 0.0, 1.0))

    # --- Clipping: fraction of samples pinned at the ADC ceiling/floor ---
    clip_hi = ADC_MAX_VALUE * SATURATION_FRACTION
    clipping_fraction = float(np.mean((ir >= clip_hi) | (ir <= 0)))
    clipping_score = float(np.clip(1.0 - clipping_fraction * 5.0, 0.0, 1.0))

    # --- Motion artifacts (see `_motion_artifact_score` docstring) ---
    motion_score = _motion_artifact_score(ir)

    # --- Pulse consistency and frequency stability from RR intervals ---
    peaks = _detect_peaks(filtered, fs)
    if peaks.size >= 3:
        rr = np.diff(peaks) / fs
        valid_rr = rr[(rr >= MIN_RR_SEC) & (rr <= MAX_RR_SEC)]
        if valid_rr.size >= 2:
            cv = float(np.std(valid_rr) / (np.mean(valid_rr) + 1e-9))
            pulse_consistency = float(np.clip(1.0 - cv * 2.0, 0.0, 1.0))
            # Frequency stability uses the same CV but without the 2× multiplier
            # so a typical HRV-induced CV of ~0.05 still scores near 0.95 rather
            # than being penalized down to 0.9.
            frequency_stability = float(np.clip(1.0 - cv, 0.0, 1.0))
        else:
            pulse_consistency = 0.0
            frequency_stability = 0.0
    else:
        pulse_consistency = 0.0
        frequency_stability = 0.0

    # --- Amplitude and perfusion index ---
    ac_amplitude = float(np.std(filtered))
    amplitude_score = float(np.clip(ac_amplitude / (FINGER_MIN_AC_COUNTS * 4.0), 0.0, 1.0))

    perfusion_index = ac_amplitude / (dc_level + 1e-9) * 100.0  # percent
    # Log-scale PI score: maps the 250× dynamic range of valid PI (0.02-10 %)
    # onto a 0-1 score. Values near 0.02 % score near 0; values near 1 %
    # score ~0.85; values at or above 10 % score 1.0 (but are rare).
    if perfusion_index >= FINGER_PI_MIN_PCT:
        pi_score = float(np.clip(
            np.log10(perfusion_index / FINGER_PI_MIN_PCT)
            / np.log10(FINGER_PI_MAX_PCT / FINGER_PI_MIN_PCT),
            0.0, 1.0,
        ))
    else:
        pi_score = 0.0

    # --- Spectral features via shared _compute_spectrum (no duplicate FFT) ---
    spec = _compute_spectrum(filtered, fs)
    spectral_entropy = spec["spectral_entropy"]
    spectral_concentration = spec["spectral_concentration"]
    harmonic_ratio_raw = spec["harmonic_ratio"]

    # Harmonic ratio score: map [0, 2.0] → [0, 1]. We cap at 2.0 because
    # ratios above ~2 are unusual and may reflect a harmonic-frequency artifact
    # rather than a genuine PPG harmonic. Typical clean PPG: 0.3-1.2.
    harmonic_score = float(np.clip(harmonic_ratio_raw / 2.0, 0.0, 1.0))

    # --- Pulse repeatability: beat-to-beat peak height CV ---
    if peaks.size >= 3:
        peak_heights_f = filtered[peaks]
        cv_peaks = float(np.std(peak_heights_f) / (np.abs(np.mean(peak_heights_f)) + 1e-9))
        pulse_repeatability = float(
            np.clip(1.0 - cv_peaks / FINGER_PULSE_REPEATABILITY_CV_MAX, 0.0, 1.0)
        )
    else:
        pulse_repeatability = 0.0

    # --- Composite SQI (weighted blend, weights sum to 1.0) ---
    # SNR and pulse consistency are the two strongest direct quality indicators.
    # Spectral features provide substantial corroborating evidence. The remaining
    # checks fill in edge cases not well-captured by time-domain metrics alone.
    score = (
        0.22 * snr_score
        + 0.18 * pulse_consistency
        + 0.10 * clipping_score
        + 0.10 * motion_score
        + 0.10 * spectral_entropy
        + 0.10 * spectral_concentration
        + 0.08 * harmonic_score
        + 0.07 * pi_score
        + 0.05 * pulse_repeatability
    ) * 100.0

    return {
        "score": round(float(np.clip(score, 0.0, 100.0)), 1),
        "snr_db": round(snr_db, 1),
        "clipping_fraction": round(clipping_fraction, 4),
        "motion_score": round(motion_score, 3),
        "pulse_consistency": round(pulse_consistency, 3),
        "amplitude_score": round(amplitude_score, 3),
        # new sub-scores
        "spectral_entropy": round(spectral_entropy, 3),
        "spectral_concentration": round(spectral_concentration, 3),
        "harmonic_ratio": round(harmonic_ratio_raw, 3),
        "perfusion_index": round(perfusion_index, 4),
        "pulse_repeatability": round(pulse_repeatability, 3),
        "frequency_stability": round(frequency_stability, 3),
    }


# ---------------------------------------------------------------------------
# Heart rate
# ---------------------------------------------------------------------------

def _detect_peaks(
    filtered_signal: np.ndarray, fs: float, return_properties: bool = False
):
    """
    Adaptive systolic-peak detector shared by HR estimation and SQI.

    Pipeline:
      1. Rolling z-score normalization (`_normalize_signal`) so a single fixed
         threshold behaves like an adaptive "rolling_mean + k*rolling_std"
         cutoff at every point in time.
      2. Local short-time energy (STE) envelope (`_local_energy_envelope`).
         Peaks in flat/near-zero-energy segments are suppressed even if their
         z-score clears the threshold (which normalization amplifies them into
         doing) — preventing flat-line noise from being reported as beats.
      3. Adaptive prominence scaling: required prominence is scaled by
         (local_energy / median_energy)^ADAPTIVE_PROMINENCE_ALPHA so that
         high-perfusion peaks face a proportionally higher bar and
         low-perfusion peaks aren't penalized relative to their local amplitude.
      4. `scipy.find_peaks` with distance (refractory period), height, and
         prominence constraints on the *normalized* signal. Width is NOT
         passed to find_peaks here because widths measured in the z-score
         domain are distorted — the rolling normalization flattens the signal
         near peaks, making the half-prominence width appear much wider than
         the physical pulse duration (e.g. a 1 Hz PPG sine measures >400 ms
         in normalized units but only ~180 ms in the filtered-signal domain).
         Instead, widths are re-measured on the *filtered signal* in physical
         amplitude units via `scipy.signal.peak_widths` and the 80-350 ms
         gate is applied as a post-filter on those physical-domain widths.
      5. Post-detection energy gate, adaptive prominence post-filter, and
         physical-domain width gate applied without re-running find_peaks.

    Parameters
    ----------
    return_properties : if True, also return the scipy `properties` dict
        plus: normalized_signal, local_amplitudes (peak-to-trough swing per
        beat in filtered-signal units), and energy_scores (normalized local
        STE at each peak). Existing callers that only want peak indices pass
        False (the default), matching the original signature's behaviour.
    """
    if filtered_signal.size < int(fs * 1.5):
        empty = np.array([], dtype=int)
        return (empty, {}) if return_properties else empty

    normalized = _normalize_signal(filtered_signal, fs)

    # Local energy in the z-score domain — computed once, used for both
    # the energy gate and the adaptive prominence scaling.
    energy = _local_energy_envelope(normalized, fs)
    median_energy = float(np.median(energy)) + 1e-12

    min_distance = max(int(fs * PEAK_REFRACTORY_SEC), 1)
    min_width_samples = max(int(fs * MIN_PEAK_WIDTH_SEC), 1)
    max_width_samples = max(int(fs * MAX_PEAK_WIDTH_SEC), min_width_samples + 1)

    # Detect on normalized signal for adaptive height/prominence threshold.
    # Width constraint deliberately omitted here — see docstring above.
    peaks, properties = find_peaks(
        normalized,
        distance=min_distance,
        prominence=PEAK_ADAPTIVE_K,
        height=PEAK_ADAPTIVE_K,
    )

    if peaks.size > 0:
        # Physical-domain width gate: scan from each peak outward in the
        # *normalized* signal to find the half-prominence width. find_peaks
        # already returns left_bases and right_bases in the normalized domain
        # (these are consistent with the normalized signal's troughs).
        # We use these directly as the pulse boundaries and compute the width
        # as (right_base - left_base) as a loose upper-bound check.
        # The minimum width gate (min_width_samples) rejects spike artifacts
        # that are too narrow to be real PPG systolic peaks.
        # The maximum width check uses an expanded limit: in the normalized
        # (z-score) domain, a real 60 BPM PPG half-prominence width at 50%
        # can span up to ~0.5 s because the normalization flattens the signal
        # plateau around the peak. We allow up to 0.5 s to correctly accept
        # normal resting-HR beats while still rejecting broad slow ripples
        # (> 0.5 s half-width would correspond to HR < 60 BPM and very broad
        # plateau — more likely a motion artifact than a missed slow beat).
        NORM_MAX_WIDTH_SEC = 0.50  # expanded normalized-domain max width
        norm_max_w = max(int(fs * NORM_MAX_WIDTH_SEC), max_width_samples + 1)
        if "widths" in properties:
            width_mask = (
                (properties["widths"] >= min_width_samples)
                & (properties["widths"] <= norm_max_w)
            )
        else:
            width_mask = np.ones(peaks.size, dtype=bool)
        peaks = peaks[width_mask]
        properties_wf: dict = {}
        for key, val in properties.items():
            if isinstance(val, np.ndarray) and val.shape == (width_mask.size,):
                properties_wf[key] = val[width_mask]
            else:
                properties_wf[key] = val
        properties = properties_wf

    if peaks.size == 0:
        if return_properties:
            properties["normalized_signal"] = normalized
            return peaks, properties
        return peaks

    energy_at_peaks = energy[peaks]
    n_orig = peaks.size

    # --- Energy gate: hard-suppress peaks in near-silent regions ---
    energy_mask = energy_at_peaks >= median_energy * MIN_LOCAL_ENERGY_FRACTION

    # --- Adaptive prominence post-filter ---
    # Scale the required prominence by local energy (relative to buffer median)
    # raised to ADAPTIVE_PROMINENCE_ALPHA. Peaks with high local energy (strong
    # pulse) must clear a proportionally higher prominence bar; peaks with low
    # but non-zero local energy (weak pulse) are evaluated against the standard
    # PEAK_ADAPTIVE_K threshold, not an artificially inflated one.
    if "prominences" in properties:
        energy_scale = (energy_at_peaks / median_energy) ** ADAPTIVE_PROMINENCE_ALPHA
        adaptive_threshold = PEAK_ADAPTIVE_K * energy_scale
        prominence_mask = properties["prominences"] >= adaptive_threshold
    else:
        prominence_mask = np.ones(n_orig, dtype=bool)

    keep = energy_mask & prominence_mask
    peaks = peaks[keep]

    # Filter all property arrays that correspond 1-to-1 with original peaks
    kept_properties: dict = {}
    for key, val in properties.items():
        if isinstance(val, np.ndarray) and val.shape == (n_orig,):
            kept_properties[key] = val[keep]
        else:
            kept_properties[key] = val

    if return_properties:
        kept_properties["normalized_signal"] = normalized

        # Per-peak local amplitude: true peak-to-trough swing within the
        # detected pulse boundary (left_base to right_base). This is a more
        # physiologically meaningful AC amplitude than the z-score prominence
        # and is used in SpO2 beat-level R estimation.
        if (
            peaks.size > 0
            and "left_bases" in kept_properties
            and "right_bases" in kept_properties
        ):
            local_amplitudes = np.zeros(peaks.size)
            for i, (pk, lb, rb) in enumerate(
                zip(
                    peaks,
                    kept_properties["left_bases"].astype(int),
                    kept_properties["right_bases"].astype(int),
                )
            ):
                seg = filtered_signal[lb : rb + 1]
                if seg.size > 0:
                    local_amplitudes[i] = float(filtered_signal[pk]) - float(np.min(seg))
            kept_properties["local_amplitudes"] = local_amplitudes

        # Per-peak normalized local energy: diagnostic value for callers
        # interested in how energetically prominent each beat was. Values > 1.0
        # mean above-median energy; values < 1.0 mean below-median energy.
        kept_properties["energy_scores"] = np.clip(
            energy[peaks] / median_energy if peaks.size > 0 else np.array([]),
            0.0, 5.0,
        )

        return peaks, kept_properties

    return peaks


def _score_beats(peaks: np.ndarray, properties: dict, fs: float) -> dict:
    """
    Per-beat confidence scoring (0-1), returned as a structured dict of
    per-beat arrays for use in HR estimation, SpO2 R weighting, and
    diagnostics.

    Sub-scores (all 0-1, blended into `beat_confidences`):
      prominence_score    : peak prominence in z-score units vs. reference
                            (how far the peak stands above its local baseline)
      snr_score           : peak height in z-score units vs. BEAT_LOCAL_SNR_REF
                            (local SNR at the peak in normalized units)
      pulse_width_score   : half-prominence width vs. physiological optimum
                            (peaks at BEAT_PULSE_WIDTH_OPTIMAL_SEC = 0.15 s)
      symmetry_score      : rise:fall ratio compared to expected 1:2 asymmetry
                            (a perfect PPG systolic peak has ~35 % rise time)
      upstroke_score      : normalized systolic upstroke slope vs. reference
                            (steep upstroke = fast, strong pulsatile component)
      downstroke_score    : normalized diastolic downstroke slope vs. reference
                            (slower than upstroke → higher score)
      rr_consistency_score: agreement of each beat's bounding RR intervals
                            with the median RR interval
      physio_score        : each bounding RR interval is within [MIN_RR_SEC,
                            MAX_RR_SEC] physiological bounds

    Returns
    -------
    dict with keys:
      beat_confidences   (np.ndarray, shape [n_beats]) — primary output
      pulse_widths_ms    (np.ndarray) — per-beat half-prominence width
      upstroke_slopes    (np.ndarray) — per-beat systolic slope (normalized)
      downstroke_slopes  (np.ndarray) — per-beat diastolic slope (normalized)
      symmetry_scores    (np.ndarray) — per-beat rise:fall ratio score
    """
    n = peaks.size
    if n == 0:
        return {
            "beat_confidences": np.array([]),
            "pulse_widths_ms": np.array([]),
            "upstroke_slopes": np.array([]),
            "downstroke_slopes": np.array([]),
            "symmetry_scores": np.array([]),
        }

    prominences = properties.get("prominences", np.zeros(n))
    heights = properties.get("peak_heights", np.zeros(n))
    left_bases = properties.get("left_bases", peaks).astype(int)
    right_bases = properties.get("right_bases", peaks).astype(int)
    widths_samples = properties.get("widths", np.zeros(n))
    local_amplitudes = properties.get("local_amplitudes", np.ones(n))

    # --- Prominence and local SNR ---
    prominence_score = np.clip(prominences / BEAT_PROMINENCE_Z_REF, 0.0, 1.0)
    snr_score = np.clip(heights / BEAT_LOCAL_SNR_REF, 0.0, 1.0)

    # --- Pulse width score ---
    # Triangular score function peaking at BEAT_PULSE_WIDTH_OPTIMAL_SEC
    # (0.15 s). Score is 0 at the band edges (already enforced as hard gates
    # by find_peaks) and 1 at the optimum. A beat at either edge of the
    # 80-350 ms band scores ~0.15-0.25, clearly penalizing near-edge cases.
    widths_sec = widths_samples / fs
    half_range = (MAX_PEAK_WIDTH_SEC - MIN_PEAK_WIDTH_SEC) / 2.0
    pulse_width_score = np.clip(
        1.0 - np.abs(widths_sec - BEAT_PULSE_WIDTH_OPTIMAL_SEC) / half_range,
        0.0, 1.0,
    )

    # --- Rise and fall time (samples) ---
    rise = (peaks - left_bases).astype(np.float64)
    fall = (right_bases - peaks).astype(np.float64)
    total_width = np.maximum(rise + fall, 1.0)

    # --- Symmetry score (scored for PPG asymmetry, not against symmetry) ---
    # Real PPG: rise ≈ 1/3 of total width, fall ≈ 2/3.
    # Score is highest when rise / total_width ≈ BEAT_UPSTROKE_RATIO_REF (0.35).
    # A spike (ratio ≈ 0), a slow-rise waveform (ratio > 0.6), or a perfectly
    # symmetric beat (ratio = 0.5) all score below 0.7.
    rise_ratio = rise / total_width
    symmetry_score = np.clip(
        1.0 - np.abs(rise_ratio - BEAT_UPSTROKE_RATIO_REF) / BEAT_DOWNSTROKE_RATIO_REF,
        0.0, 1.0,
    )

    # --- Upstroke and downstroke slope (normalized to local beat amplitude) ---
    # Raw slope = amplitude / samples. Dividing by local amplitude makes the
    # score perfusion-independent. Reference slopes are derived from the
    # expected rise/fall times of a 0.15 s (optimal) pulse.
    amp_ref = np.maximum(local_amplitudes, 1e-6)
    optimal_rise_samples = max(BEAT_UPSTROKE_RATIO_REF * BEAT_PULSE_WIDTH_OPTIMAL_SEC * fs, 1.0)
    optimal_fall_samples = max(BEAT_DOWNSTROKE_RATIO_REF * BEAT_PULSE_WIDTH_OPTIMAL_SEC * fs, 1.0)

    upstroke_slope_raw = amp_ref / np.maximum(rise, 1.0)
    # Reference upstroke slope for a 0.15 s pulse at the current amplitude:
    upstroke_ref = amp_ref / optimal_rise_samples
    upstroke_score = np.clip(upstroke_slope_raw / (upstroke_ref + 1e-9), 0.0, 1.0)

    downstroke_slope_raw = amp_ref / np.maximum(fall, 1.0)
    # Downstroke should be *slower* than the reference (smaller slope = better).
    # We score the inverse: reference downstroke slope / actual downstroke slope.
    downstroke_ref = amp_ref / optimal_fall_samples
    downstroke_score = np.clip(downstroke_ref / (downstroke_slope_raw + 1e-9), 0.0, 1.0)

    # --- RR consistency and physiological plausibility ---
    if n >= 2:
        rr = np.diff(peaks) / fs
        median_rr = float(np.median(rr)) if rr.size else 0.0
        physio_valid = (rr >= MIN_RR_SEC) & (rr <= MAX_RR_SEC)
        physio_rr = np.where(physio_valid, 1.0, 0.0)
        rr_dev = np.abs(rr - median_rr) / (median_rr + 1e-9) if median_rr > 0 else np.ones_like(rr)
        rr_consistency = np.clip(1.0 - rr_dev, 0.0, 1.0)

        # Interior beats are bounded by two RR intervals; edge beats by one.
        left_rr = np.concatenate(([rr_consistency[0]], rr_consistency))
        right_rr = np.concatenate((rr_consistency, [rr_consistency[-1]]))
        rr_consistency_score = (left_rr + right_rr) / 2.0

        left_physio = np.concatenate(([physio_rr[0]], physio_rr))
        right_physio = np.concatenate((physio_rr, [physio_rr[-1]]))
        physio_score = (left_physio + right_physio) / 2.0
    else:
        rr_consistency_score = np.zeros(n)
        physio_score = np.zeros(n)

    # --- Blended beat confidence (weights sum to 1.0) ---
    # Prominence and RR agreement are the primary discriminators.
    # Width, symmetry, and slope sub-scores provide morphological specificity.
    beat_confidence = (
        0.25 * prominence_score
        + 0.15 * snr_score
        + 0.12 * pulse_width_score
        + 0.12 * symmetry_score
        + 0.08 * upstroke_score
        + 0.08 * downstroke_score
        + 0.15 * rr_consistency_score
        + 0.05 * physio_score
    )
    beat_confidence = np.clip(beat_confidence, 0.0, 1.0)

    return {
        "beat_confidences": beat_confidence,
        "pulse_widths_ms": np.round(widths_sec * 1000.0, 1),
        "upstroke_slopes": np.round(upstroke_slope_raw, 4),
        "downstroke_slopes": np.round(downstroke_slope_raw, 4),
        "symmetry_scores": np.round(symmetry_score, 3),
    }


def estimate_heart_rate(ir, fs: float = 50.0) -> dict:
    """
    Robust heart-rate estimator.

    Pipeline: band-pass filter -> rolling z-score normalization -> adaptive
    peak detection (local energy gating, adaptive prominence scaling,
    refractory period, width gate) -> per-beat confidence scoring ->
    RR-interval physiological-bound filtering ->
    confidence-weighted Hampel-style outlier rejection ->
    weighted median RR (weighted by beat-pair geometric-mean confidence) ->
    BPM.

    Confidence-weighted median: each RR interval is weighted by the geometric
    mean of its two bounding beat confidences, so artifact-contaminated beats
    are down-weighted rather than treated equally with clean beats. This is
    more principled than a simple median when the beat-confidence scores carry
    real discriminative information (which the improved _score_beats does).

    Confidence-weighted Hampel rejection: the outlier gate is tightened for
    low-confidence beat pairs — an unusual RR produced by two weak beats is
    more likely an artifact than the same deviation produced by two strong
    beats. The gate is threshold = 3 × MAD × tightening, where tightening
    ranges from 0.5 (very tight, zero-confidence pair) to 1.0 (standard,
    full-confidence pair).

    Returns
    -------
    dict with: heart_rate, rr_intervals_ms, confidence, beats_detected,
    peak_quality, rhythm_quality, beat_quality (existing keys), plus:
    signal_quality, motion_quality, coverage, rr_quality,
    confidence_breakdown (new additive keys).
    """
    ir = _as_float_array(ir)
    empty = {
        "heart_rate": None, "rr_intervals_ms": [], "confidence": 0.0,
        "beats_detected": 0, "peak_quality": 0.0, "rhythm_quality": 0.0,
        "beat_quality": 0.0,
        # new additive fields
        "signal_quality": 0.0, "motion_quality": 0.0, "coverage": 0.0,
        "rr_quality": 0.0,
        "confidence_breakdown": {
            "beat_quality": 0.0, "rhythm_quality": 0.0,
            "signal_quality": 0.0, "perfusion": 0.0, "motion": 0.0,
        },
    }
    if ir.size < int(fs * 5):  # need a handful of seconds to see multiple beats
        return empty

    filtered = bandpass_filter(ir, fs)
    peaks, properties = _detect_peaks(filtered, fs, return_properties=True)
    if peaks.size < 3:  # need ≥ 2 RR intervals to judge consistency
        return empty

    # Per-beat confidence from improved _score_beats (returns a dict)
    beat_result = _score_beats(peaks, properties, fs)
    beat_confidences = beat_result["beat_confidences"]
    beat_quality = float(np.mean(beat_confidences)) if beat_confidences.size else 0.0

    rr = np.diff(peaks) / fs  # seconds

    # Per-RR weight: geometric mean of bounding beat confidences.
    # Ensures an interval is only trusted if BOTH bounding beats are clean.
    conf_left = beat_confidences[:-1]
    conf_right = beat_confidences[1:]
    rr_weights = np.sqrt(np.maximum(conf_left * conf_right, 0.0)) + 1e-9

    # Stage 1: physiological bounds — stricter than the detection-time
    # refractory period (40-200 BPM here vs. 222 BPM at detection time).
    physio_mask = (rr >= MIN_RR_SEC) & (rr <= MAX_RR_SEC)
    rr = rr[physio_mask]
    rr_weights = rr_weights[physio_mask]
    if rr.size < 2:
        return empty

    # Stage 2: confidence-weighted Hampel-style outlier rejection.
    # tightening ranges from 0.5 (strictest, for low-confidence pairs) to
    # 1.0 (standard 3 × MAD, for high-confidence pairs).
    median_rr = float(np.median(rr))
    mad_rr = float(np.median(np.abs(rr - median_rr))) + 1e-9
    normalized_weights = np.clip(rr_weights / (float(np.max(rr_weights)) + 1e-9), 0.0, 1.0)
    tightening = 0.5 + 0.5 * normalized_weights
    inlier_mask = np.abs(rr - median_rr) <= 3.0 * mad_rr * tightening
    clean_rr = rr[inlier_mask]
    clean_weights = rr_weights[inlier_mask]
    if clean_rr.size == 0:
        clean_rr = rr  # fall back rather than reporting nothing
        clean_weights = rr_weights

    # Stage 3: weighted median RR
    bpm = 60.0 / _weighted_median(clean_rr, clean_weights)
    if not (MIN_BPM <= bpm <= MAX_BPM):
        return empty

    retained_fraction = clean_rr.size / rr.size
    cv = float(np.std(clean_rr) / (np.mean(clean_rr) + 1e-9))
    regularity = float(np.clip(1.0 - cv * 2.0, 0.0, 1.0))

    # Signal-level context from SQI — same computation the dashboard relies on.
    quality = compute_signal_quality(ir, fs)
    signal_quality_norm = quality["score"] / 100.0
    perfusion = quality["amplitude_score"]
    motion = quality["motion_score"] if quality["motion_score"] is not None else 1.0

    # Coverage: ratio of detected beats to the expected beat count given the
    # window duration and estimated HR. Values much below 1.0 indicate dropout
    # or missed beats; values above 1.0 indicate spurious detections (capped at 1.0).
    window_duration = ir.size / fs
    expected_beats = max((bpm / 60.0) * window_duration, 1.0)
    coverage = float(np.clip(peaks.size / expected_beats, 0.0, 1.0))

    confidence = float(np.clip(
        0.30 * beat_quality
        + 0.25 * regularity
        + 0.20 * signal_quality_norm
        + 0.15 * perfusion
        + 0.10 * motion,
        0.0, 1.0,
    ))

    return {
        "heart_rate": round(bpm, 1),
        "rr_intervals_ms": [round(x * 1000.0, 1) for x in clean_rr],
        "confidence": round(confidence, 3),
        "beats_detected": int(peaks.size),
        # existing additive sub-metrics
        "peak_quality": round(retained_fraction, 3),
        "rhythm_quality": round(regularity, 3),
        "beat_quality": round(beat_quality, 3),
        # new additive diagnostics
        "signal_quality": round(signal_quality_norm, 3),
        "motion_quality": round(float(motion), 3),
        "coverage": round(coverage, 3),
        "rr_quality": round(retained_fraction, 3),
        "confidence_breakdown": {
            "beat_quality": round(beat_quality, 3),
            "rhythm_quality": round(regularity, 3),
            "signal_quality": round(signal_quality_norm, 3),
            "perfusion": round(perfusion, 3),
            "motion": round(float(motion), 3),
        },
    }


# ---------------------------------------------------------------------------
# SpO2 (ratio-of-ratios)
# ---------------------------------------------------------------------------

def _spo2_calibrate(r: float) -> float:
    """
    SpO2 calibration from ratio-of-ratios R — cubic spline primary path.

    Uses the module-level `_SPO2_SPLINE` (CubicSpline over 10 published
    Severinghaus / Maxim AN6409 knots). The spline smoothly captures the
    nonlinear R-SpO2 relationship across both the normoxic (R ≤ 0.9,
    SpO2 ≥ 86%) and hypoxic (R > 0.9) regimes without requiring a manual
    breakpoint.

    Linear extrapolation is applied for R outside the knot range [0.4, 1.4]
    using the slope at the nearest end-knot — better than clamping, which
    would give a discontinuous derivative.

    The result is clipped to [SPO2_PHYSIO_MIN, SPO2_PHYSIO_MAX] by the caller.
    """
    r = float(r)
    if r < _SPO2_CAL_R_KNOTS[0]:
        # Linear extrapolation beyond low-R end using derivative at first knot
        slope = float(_SPO2_SPLINE_DERIV(_SPO2_CAL_R_KNOTS[0]))
        return float(_SPO2_CAL_SPO2_KNOTS[0]) + slope * (r - _SPO2_CAL_R_KNOTS[0])
    if r > _SPO2_CAL_R_KNOTS[-1]:
        # Linear extrapolation beyond high-R end
        slope = float(_SPO2_SPLINE_DERIV(_SPO2_CAL_R_KNOTS[-1]))
        return float(_SPO2_CAL_SPO2_KNOTS[-1]) + slope * (r - _SPO2_CAL_R_KNOTS[-1])
    return float(_SPO2_SPLINE(r))


def _pulse_area_ac(signal: np.ndarray, lb: int, rb: int) -> float:
    """
    Area-under-curve AC amplitude (Improvement 3).

    Compute AC as the trapezoid-integral of the filtered signal above a
    linear baseline connecting signal[lb] to signal[rb], then normalised
    by the segment length to produce an amplitude-equivalent value.

    Why area rather than peak-to-trough:
      Motion transients shift the instantaneous peak position and height,
      inflating or deflating the peak-to-trough amplitude. The area under
      the systolic wave is preserved even when the waveform is slightly
      shifted or distorted, making it 3-5× more robust to motion
      (Motin et al. 2019).

    Only the above-baseline area is integrated (negative excursions below
    the straight baseline are clipped to zero), so the measure is always
    non-negative and reflects the systolic upstroke rather than the full
    signed waveform area.
    """
    lb = int(np.clip(lb, 0, signal.size - 1))
    rb = int(np.clip(rb, lb + 1, signal.size - 1))
    seg = signal[lb : rb + 1]
    n = len(seg)
    if n < 2:
        return float(np.abs(seg[0])) if n == 1 else 0.0
    # Linear baseline: straight line from left_base to right_base
    baseline = np.linspace(float(seg[0]), float(seg[-1]), n)
    above = np.maximum(seg - baseline, 0.0)
    area = float(np.trapz(above))
    return area / max(n - 1, 1)  # normalise to amplitude units


def _spo2_xcorr_lag(
    ir_filt: np.ndarray,
    red_filt: np.ndarray,
    fs: float,
) -> int:
    """
    Estimate the sample lag between IR and RED channel pulses (Improvement 2).

    Cross-correlation between the two normalized band-passed channels gives
    the time offset that maximises their similarity. For a reflectance sensor
    with both LEDs illuminating the same tissue, this lag is near zero (<10 ms),
    but may vary with LED drive timing, multipath reflectance, and sampling
    phase. Using the true lag (rather than assuming zero) produces more
    accurately aligned AC windows and therefore more precise R values.

    The search is restricted to ±SPO2_XCORR_MAX_LAG_MS to prevent the
    cross-correlation noise floor from suggesting implausibly large lags.
    If the dominant xcorr peak fails the peak-to-mean ratio test
    (SPO2_XCORR_MIN_PEAK_RATIO), 0 is returned so the caller falls back to
    the standard argmax-in-window method.

    Returns
    -------
    int : lag in samples; positive → RED leads IR, negative → IR leads RED.
    """
    if ir_filt.size < 3 or red_filt.size < 3:
        return 0
    max_lag = max(int(fs * SPO2_XCORR_MAX_LAG_MS / 1000.0), 1)
    # Zero-mean normalise before correlating to remove DC bias
    ir_z = ir_filt - np.mean(ir_filt)
    red_z = red_filt - np.mean(red_filt)
    # Full cross-correlation; restrict search to the ±max_lag window
    xcorr = _sig_correlate(ir_z, red_z, mode="full")
    n = ir_filt.size
    centre = n - 1  # zero-lag index in 'full' output
    lo = max(centre - max_lag, 0)
    hi = min(centre + max_lag + 1, xcorr.size)
    xcorr_window = xcorr[lo:hi]
    if xcorr_window.size == 0:
        return 0
    # Peak-to-mean ratio check: if the correlation is too flat, the lag
    # estimate is dominated by noise rather than real pulse alignment.
    peak_val = float(np.max(np.abs(xcorr_window)))
    mean_val = float(np.mean(np.abs(xcorr_window))) + 1e-12
    if peak_val / mean_val < SPO2_XCORR_MIN_PEAK_RATIO:
        return 0
    best_idx = int(np.argmax(xcorr_window))
    lag = (lo + best_idx) - centre
    return int(np.clip(lag, -max_lag, max_lag))


def _motion_compensate_ppg(
    ir_filt: np.ndarray,
    red_filt: np.ndarray,
    dc_ir: float,
    dc_red: float,
) -> tuple[np.ndarray, np.ndarray]:
    """
    Differential motion compensation using both PPG channels (Improvement 9).

    Without an IMU reference, we exploit the fact that motion artifacts appear
    in both IR and RED channels approximately proportionally to their DC levels
    (because motion modulates the optical path length, which affects both
    wavelengths similarly). The physiological signal, by contrast, appears with
    different AC/DC ratios in the two channels — that is the basis of the
    ratio-of-ratios method.

    Algorithm (Widrow one-component ANC, 1975):
      1. Normalize both channels by their DC so they are dimensionless and
         comparable in scale.
      2. Form the common-mode signal (motion proxy) as their average —
         motion is common, physiology is different between channels.
      3. Project each channel onto the motion proxy via a least-squares
         coefficient (equivalent to a single-tap adaptive filter with
         no gradient descent, just the direct normal-equation solution).
      4. Subtract the estimated motion component from each channel.
      5. Re-scale back to physical units (×DC) for downstream AC extraction.

    This approach is deterministic and fully reversible. It will only
    partially suppress motion that differs strongly between channels (e.g.
    pressure-induced venous occlusion), but it significantly reduces
    common-mode bulk-motion artifacts.

    Returns
    -------
    (ir_compensated, red_compensated) both in original amplitude units.
    """
    if dc_ir <= 0 or dc_red <= 0:
        return ir_filt, red_filt
    ir_norm  = ir_filt  / dc_ir
    red_norm = red_filt / dc_red
    # Common-mode motion proxy
    motion_proxy = (ir_norm + red_norm) * 0.5
    denom = float(np.dot(motion_proxy, motion_proxy)) + 1e-12
    # Least-squares projection coefficients
    alpha_ir  = float(np.dot(ir_norm,  motion_proxy)) / denom
    alpha_red = float(np.dot(red_norm, motion_proxy)) / denom
    # Subtract motion component and rescale
    ir_comp  = (ir_norm  - alpha_ir  * motion_proxy) * dc_ir
    red_comp = (red_norm - alpha_red * motion_proxy) * dc_red
    return ir_comp, red_comp


def _suppress_respiratory(
    filtered_signal: np.ndarray,
    fs: float,
) -> np.ndarray:
    """
    Suppress respiratory amplitude modulation of the PPG (Improvement 10).

    Respiration (0.15-0.4 Hz) periodically expands and contracts the chest
    and modulates the optical path length through finger tissue, causing the
    PPG amplitude to rise and fall at the breathing rate. This creates a
    systematic bias in beat-to-beat AC estimates: beats near peak inspiration
    are over-estimated and beats near expiration are under-estimated.

    Fix: compute the signal's instantaneous amplitude envelope by low-passing
    the absolute value (which approximates the half-wave-rectified envelope),
    then divide the signal by the envelope. The result has uniform beat
    heights across the respiratory cycle, removing the bias.

    The envelope floor is set to 10% of its mean to prevent amplification of
    near-zero-amplitude segments (e.g. at the very start/end of the buffer).

    Returns
    -------
    Envelope-normalized filtered signal, same shape as input. If the buffer
    is too short to estimate a meaningful envelope, the input is returned
    unchanged.
    """
    if filtered_signal.size < _min_filtfilt_len(RESP_LP_ORDER):
        return filtered_signal
    nyquist = fs / 2.0
    cutoff = min(RESP_BAND_HIGH_HZ / nyquist, 0.999)
    if cutoff <= 0:
        return filtered_signal
    b, a = butter(RESP_LP_ORDER, cutoff, btype="low")
    envelope = filtfilt(b, a, np.abs(filtered_signal))
    envelope_floor = np.maximum(envelope, 0.1 * float(np.mean(envelope)) + 1e-9)
    return filtered_signal / envelope_floor


def estimate_spo2(ir, red, fs: float = 50.0, sub_window_seconds: float = 2.0) -> dict:  # noqa: C901
    """
    Beat-level ratio-of-ratios SpO2 estimator — research-grade pipeline.

    Classic pulse-oximetry: R = (AC_red / DC_red) / (AC_ir / DC_ir).
    R is mapped through a cubic spline calibration curve onto SpO2 (%).

    Improvements in this version (each keyed to the plan §number):
      §1  Robust DC via _lowpass_dc (tracks pressure / temperature drift).
      §2  Cross-correlation IR↔RED alignment (_spo2_xcorr_lag) for accurate
          peak matching rather than a fixed search-window argmax.
      §3  Pulse-area AC (_pulse_area_ac) — 3-5× more stable under motion
          than peak-to-trough amplitude (Motin et al. 2019).
      §4  Cubic spline calibration (_spo2_calibrate) over 10 published knots
          (Severinghaus 1979 + Maxim AN6409) replacing two linear segments.
      §5  Multi-factor beat weighting: beat_conf × motion × pi_score
          × width_score × symmetry_score. Soft continuous weighting replaces
          the binary PI gate, preserving more beats in low-perfusion states.
      §6  Adaptive window expansion: sub-window grows (×1.5 → ×2 → ×3)
          before triggering the fallback, improving coverage for slow HR
          or low-perfusion signals.
      §7  Scalar Kalman filter replaces EMA: confidence-weighted, self-
          adapting gain, principled uncertainty output for §8.
      §8  95% confidence interval via first-order error propagation through
          the spline derivative: sigma_total = sqrt(sigma_calib² + P_kalman).
      §9  Differential motion compensation (_motion_compensate_ppg): ANC
          common-mode subtraction using IR and RED as mutual reference.
      §10 Respiratory modulation suppression (_suppress_respiratory): AUC
          AC estimated on the envelope-normalized signal, so beats at all
          phases of the respiratory cycle are equally weighted.

    Fallback: if beat-level mode yields fewer than SPO2_MIN_BEATS accepted
    beats after adaptive window expansion, the window-std method is used,
    preserving backward compatibility for short buffers / weak signals.

    Module-level state `_spo2_state` holds the Kalman state (kalman_x,
    kalman_P) and the last trusted estimate. Reset with `reset_spo2_state()`
    when starting a new session or after a finger-removal event.

    Returns
    -------
    dict with existing keys: spo2, confidence, r_value, windows_used,
    perfusion_index, window_quality, beat_quality, ratio_quality,
    coverage_quality, effective_beats, effective_windows, spo2_confidence,
    calibration_region.
    New additive keys: spo2_std, spo2_ci_low, spo2_ci_high (95% CI),
    kalman_gain (diagnostic), motion_compensated (bool).
    """
    ir  = _as_float_array(ir)
    red = _as_float_array(red)

    # Empty result includes all existing + new keys so callers can rely on
    # consistent key presence regardless of whether the function succeeds.
    empty: dict = {
        "spo2": None, "confidence": 0.0, "r_value": None, "windows_used": 0,
        "perfusion_index": 0.0, "window_quality": 0.0, "beat_quality": 0.0,
        "ratio_quality": 0.0, "coverage_quality": 0.0,
        "effective_beats": 0, "effective_windows": 0,
        "spo2_confidence": 0.0, "calibration_region": "unknown",
        # New CI / diagnostic keys
        "spo2_std": None, "spo2_ci_low": None, "spo2_ci_high": None,
        "kalman_gain": 0.0, "motion_compensated": False,
    }

    min_len = int(fs * sub_window_seconds) * 2
    if ir.size < min_len or red.size < min_len or ir.size != red.size:
        return empty

    # -----------------------------------------------------------------------
    # §1  Robust DC baseline — low-pass filtered instead of windowed mean
    # -----------------------------------------------------------------------
    # _lowpass_dc produces a time-varying DC estimate that tracks slow
    # intra-buffer drift (finger pressure, temperature, LED ageing) which
    # np.mean on a sub-window cannot capture.
    dc_ir_track  = _lowpass_dc(ir,  fs, cutoff_hz=SPO2_DC_CUTOFF_HZ)
    dc_red_track = _lowpass_dc(red, fs, cutoff_hz=SPO2_DC_CUTOFF_HZ)
    dc_ir_global  = float(np.mean(ir))
    dc_red_global = float(np.mean(red))

    # -----------------------------------------------------------------------
    # Full-buffer motion score (single call, reused throughout)
    # -----------------------------------------------------------------------
    motion_score = _motion_artifact_score(ir)

    # -----------------------------------------------------------------------
    # Band-pass both channels once — reuse for all downstream steps
    # -----------------------------------------------------------------------
    filtered_ir  = bandpass_filter(ir,  fs)
    filtered_red = bandpass_filter(red, fs)

    # -----------------------------------------------------------------------
    # §9  Differential motion compensation (moderate-motion regime only)
    # -----------------------------------------------------------------------
    # In the moderate-motion regime (freeze < motion < high), we attempt to
    # subtract the common-mode motion component shared by both channels.
    # Outside this range: below freeze threshold we motion-gate later;
    # above the high threshold motion is already negligible.
    motion_compensated = False
    if SPO2_MOTION_COMP_THRESHOLD_LOW <= motion_score <= SPO2_MOTION_COMP_THRESHOLD_HIGH:
        filtered_ir, filtered_red = _motion_compensate_ppg(
            filtered_ir, filtered_red, dc_ir_global, dc_red_global
        )
        motion_compensated = True

    # -----------------------------------------------------------------------
    # §10  Respiratory modulation suppression
    # -----------------------------------------------------------------------
    # Normalize amplitude envelope so AC estimates are not biased by where
    # in the respiratory cycle each beat falls.
    filtered_ir_resp  = _suppress_respiratory(filtered_ir,  fs)
    filtered_red_resp = _suppress_respiratory(filtered_red, fs)

    # -----------------------------------------------------------------------
    # §2  Cross-correlation IR↔RED alignment (computed once, applied per beat)
    # -----------------------------------------------------------------------
    xcorr_lag = _spo2_xcorr_lag(filtered_ir, filtered_red, fs)
    # search_half is kept as an argmax fallback radius when lag is small/zero
    search_half = max(int(fs * MIN_PEAK_WIDTH_SEC / 2), 1)

    # -----------------------------------------------------------------------
    # Detect beats in IR channel (940 nm, higher SNR for typical finger)
    # -----------------------------------------------------------------------
    peaks_ir, props_ir = _detect_peaks(filtered_ir, fs, return_properties=True)
    beat_result         = _score_beats(peaks_ir, props_ir, fs)
    beat_confidences_ir = beat_result["beat_confidences"]
    # Per-beat width and symmetry scores for multi-factor weighting (§5)
    width_scores    = beat_result.get("pulse_width_scores",    np.ones(peaks_ir.size))
    symmetry_scores = beat_result.get("symmetry_scores",       np.ones(peaks_ir.size))

    # -----------------------------------------------------------------------
    # §5/6  Beat-level R estimation with adaptive window expansion
    # -----------------------------------------------------------------------
    # Try progressively wider analysis windows (§6) until we have enough
    # accepted beats. On the first pass (mult=1.0), only peaks_ir already
    # detected are used. Wider passes widen the DC sub-window but reuse the
    # same detected peaks — the expansion mainly helps DC estimation.

    def _collect_r_beats(
        hw_samples: int,
    ) -> tuple[list, list, list]:
        """Inner loop: build r_beats, weights, pis for a given DC half-window."""
        _r: list[float] = []
        _w: list[float] = []
        _p: list[float] = []
        for i, pk_ir in enumerate(peaks_ir):
            bc = float(beat_confidences_ir[i]) if i < beat_confidences_ir.size else 0.0
            # Soft-weight beats below threshold rather than hard-reject;
            # beats well below SPO2_BEAT_CONFIDENCE_MIN are still excluded
            # because their weight would be so small as to be negligible, and
            # including them would pollute the weighted median in noisy cases.
            if bc < SPO2_BEAT_CONFIDENCE_MIN:
                continue

            # § 2: apply xcorr lag to locate the RED peak center, then search
            # a small window around that offset for the actual RED maximum.
            red_center = int(np.clip(pk_ir + xcorr_lag, 0, filtered_red.size - 1))
            lo_red = max(red_center - search_half, 0)
            hi_red = min(red_center + search_half, filtered_red.size - 1)
            if lo_red >= hi_red:
                continue
            pk_red = int(np.argmax(filtered_red[lo_red : hi_red + 1])) + lo_red

            # § 1: sample the low-pass DC track at the beat timestamp
            dc_ir  = float(dc_ir_track[pk_ir])   if dc_ir_track.size > pk_ir  else dc_ir_global
            dc_red = float(dc_red_track[pk_red])  if dc_red_track.size > pk_red else dc_red_global
            if dc_ir <= 0 or dc_red <= 0:
                continue

            # Pulse boundaries from the IR peak detector
            lb = int(props_ir.get("left_bases",  np.zeros(len(peaks_ir),  dtype=int))[i])
            rb = int(props_ir.get("right_bases",
                                  np.full(len(peaks_ir), filtered_ir.size - 1, dtype=int))[i])
            if rb <= lb:
                continue

            # § 3: area-under-curve AC on the respiratory-suppressed signal
            ac_ir  = _pulse_area_ac(filtered_ir_resp,  lb, rb)
            ac_red = _pulse_area_ac(filtered_red_resp, lb, rb)

            if ac_ir <= 0 or ac_red <= 0:
                continue

            # § 5: soft PI scoring — replaces the binary gate
            pi_ir  = (ac_ir  / dc_ir)  * 100.0
            pi_red = (ac_red / dc_red) * 100.0
            mean_pi_beat = (pi_ir + pi_red) / 2.0
            # Continuous PI score: 1.0 at the PI midpoint, tapers to 0 at
            # the physiological bounds (FINGER_PI_MIN_PCT, FINGER_PI_MAX_PCT)
            pi_score = float(np.clip(
                min(pi_ir, pi_red) / (FINGER_PI_MIN_PCT + 1e-9),
                0.0, 1.0,
            ) * np.clip(
                1.0 - (max(pi_ir, pi_red) - FINGER_PI_MAX_PCT) / (FINGER_PI_MAX_PCT + 1e-9),
                0.0, 1.0,
            ))

            r = (ac_red / dc_red) / (ac_ir / dc_ir)
            if not (SPO2_R_MIN <= r <= SPO2_R_MAX):
                continue

            # § 5: multi-factor weight
            w_idx = i if i < len(width_scores) else -1
            s_idx = i if i < len(symmetry_scores) else -1
            w_beat = float(bc
                           * motion_score
                           * pi_score
                           * float(width_scores[w_idx]    if w_idx >= 0 else 1.0)
                           * float(symmetry_scores[s_idx] if s_idx >= 0 else 1.0))
            _r.append(r)
            _w.append(w_beat)
            _p.append(mean_pi_beat)
        return _r, _w, _p

    r_beats:      list[float] = []
    beat_weights: list[float] = []
    beat_pis:     list[float] = []

    # § 6: adaptive window — expand DC half-window until enough beats found
    for mult in SPO2_ADAPTIVE_WINDOW_MULTS:
        hw = int(fs * sub_window_seconds * mult / 2)
        r_beats, beat_weights, beat_pis = _collect_r_beats(hw)
        if len(r_beats) >= SPO2_MIN_BEATS:
            break

    # -----------------------------------------------------------------------
    # Aggregate R values
    # -----------------------------------------------------------------------
    effective_beats   = 0
    effective_windows = 0
    beat_quality_spo2 = 0.0

    if len(r_beats) >= SPO2_MIN_BEATS:
        # --- Beat-level path ---
        r_arr = np.array(r_beats)
        w_arr = np.array(beat_weights)
        r_median      = _weighted_median(r_arr, w_arr)
        effective_beats   = len(r_beats)
        effective_windows = effective_beats
        mean_pi = float(np.mean(beat_pis))

        accepted_confs = beat_confidences_ir[beat_confidences_ir >= SPO2_BEAT_CONFIDENCE_MIN]
        beat_quality_spo2 = float(np.mean(accepted_confs)) if accepted_confs.size > 0 else 0.0

        # Robust R CV using MAD (less sensitive to R outliers than std)
        r_mad = float(np.median(np.abs(r_arr - r_median))) + 1e-9
        r_cv  = r_mad / (r_median + 1e-9)
        ratio_quality = float(np.clip(1.0 - r_cv * 3.0, 0.0, 1.0))

        window_quality   = float(np.clip(float(np.mean(w_arr)) / (motion_score + 1e-9), 0.0, 1.0))
        coverage_quality = float(np.clip(len(r_beats) / max(len(peaks_ir), 1), 0.0, 1.0))

        # § 8: robust standard error of R for uncertainty propagation
        r_sem = r_mad / max(float(np.sqrt(r_arr.size)), 1.0)

    else:
        # --- Fallback: window-std method (backward-compatible) ---
        # Also uses adaptive window multipliers so the fallback itself
        # tries wider windows before giving up.
        window_r_values: list[float] = []
        for mult in SPO2_ADAPTIVE_WINDOW_MULTS:
            win = int(fs * sub_window_seconds * mult)
            step = max(win // 2, 1)
            for start in range(0, ir.size - win + 1, step):
                ir_seg  = ir[start : start + win]
                red_seg = red[start : start + win]
                dc_ir_f  = float(np.mean(ir_seg))
                dc_red_f = float(np.mean(red_seg))
                if dc_ir_f <= 0 or dc_red_f <= 0:
                    continue
                ac_ir_f  = float(np.std(bandpass_filter(ir_seg,  fs)))
                ac_red_f = float(np.std(bandpass_filter(red_seg, fs)))
                if ac_ir_f <= 0 or ac_red_f <= 0:
                    continue
                r_fb = (ac_red_f / dc_red_f) / (ac_ir_f / dc_ir_f)
                if SPO2_R_MIN <= r_fb <= SPO2_R_MAX:
                    window_r_values.append(r_fb)
            if len(window_r_values) >= 2:
                break

        if not window_r_values:
            return empty

        r_arr    = np.array(window_r_values)
        r_median = float(np.median(r_arr))
        effective_windows = len(window_r_values)
        mean_pi  = float(np.std(filtered_ir)) / (dc_ir_global + 1e-9) * 100.0
        r_mad    = float(np.median(np.abs(r_arr - r_median))) + 1e-9
        r_cv     = r_mad / (r_median + 1e-9)
        ratio_quality    = float(np.clip(1.0 - r_cv * 3.0, 0.0, 1.0))
        window_quality   = motion_score
        coverage_quality = float(np.clip(len(window_r_values) / 4.0, 0.0, 1.0))
        r_sem = r_mad / max(float(np.sqrt(r_arr.size)), 1.0)
        beat_quality_spo2 = 0.0

    # -----------------------------------------------------------------------
    # § 4: Cubic spline calibration
    # -----------------------------------------------------------------------
    spo2_raw = _spo2_calibrate(r_median)
    spo2_raw = float(np.clip(spo2_raw, SPO2_PHYSIO_MIN, SPO2_PHYSIO_MAX))
    calibration_region = "low" if r_median > SPO2_CAL_BREAKPOINT_R else "normal"

    # -----------------------------------------------------------------------
    # § 8: Uncertainty propagation — 95% confidence interval
    # -----------------------------------------------------------------------
    # First-order error propagation through the spline:
    #   sigma_calib = |dSpO2/dR| × sigma_R_SEM
    # Combined with the Kalman filter uncertainty (P_k, from §7):
    #   sigma_total = sqrt(sigma_calib² + P_k)
    r_for_deriv = float(np.clip(r_median, _SPO2_CAL_R_KNOTS[0], _SPO2_CAL_R_KNOTS[-1]))
    d_spo2_d_r  = float(_SPO2_SPLINE_DERIV(r_for_deriv))  # negative (SpO2 decreases with R)
    sigma_calib = float(np.abs(d_spo2_d_r) * r_sem)

    # -----------------------------------------------------------------------
    # Overall confidence score
    # -----------------------------------------------------------------------
    coverage = float(np.clip(max(effective_beats, effective_windows) / 4.0, 0.0, 1.0))
    confidence = float(np.clip(
        0.35 * ratio_quality
        + 0.25 * coverage
        + 0.20 * motion_score
        + 0.20 * window_quality,
        0.0, 1.0,
    ))

    # -----------------------------------------------------------------------
    # § 7: Scalar Kalman filter (replaces EMA)
    # -----------------------------------------------------------------------
    # Measurement noise scales inversely with confidence²:
    #   high confidence → small R_meas → measurement dominates (fast tracking)
    #   low confidence  → large R_meas → prior dominates (slow / frozen)
    # This is equivalent to an EMA with an adaptive, confidence-dependent
    # alpha, but with principled state uncertainty P_k as a side product.
    x_k = _spo2_state["kalman_x"]
    P_k = float(_spo2_state["kalman_P"])

    # Motion freeze: treat as a very-low-confidence measurement rather than
    # an outright skip, so the Kalman state stays warm.
    effective_conf = confidence * (0.1 if motion_score < SPO2_MOTION_FREEZE_THRESHOLD else 1.0)

    if x_k is None:
        # First measurement: initialise state directly
        x_k = spo2_raw
        P_k = SPO2_KALMAN_P_INIT
        kalman_K = 1.0
    else:
        # Predict step
        P_pred = P_k + SPO2_KALMAN_Q
        # Measurement noise: inversely proportional to confidence²
        R_meas = SPO2_KALMAN_R_BASE / max(effective_conf, 0.05) ** 2
        # Clamp single-update innovation to SPO2_MAX_JUMP_PER_UPDATE
        innovation = float(np.clip(
            spo2_raw - x_k,
            -SPO2_MAX_JUMP_PER_UPDATE,
            SPO2_MAX_JUMP_PER_UPDATE,
        ))
        # Update step
        kalman_K = P_pred / (P_pred + R_meas)
        x_k = x_k + kalman_K * innovation
        P_k = (1.0 - kalman_K) * P_pred

    spo2_out = float(np.clip(x_k, SPO2_PHYSIO_MIN, SPO2_PHYSIO_MAX))

    # § 8: combine calibration uncertainty and Kalman filter uncertainty
    sigma_total = float(np.sqrt(sigma_calib ** 2 + P_k))
    ci_half     = 1.96 * sigma_total

    # Motion-freeze path: return state with halved reported confidence
    if motion_score < SPO2_MOTION_FREEZE_THRESHOLD and _spo2_state["kalman_x"] is not None:
        confidence = confidence * 0.5

    # Update state when the measurement is trustworthy enough to be retained
    if effective_conf >= 0.1:
        _spo2_state["kalman_x"]     = x_k
        _spo2_state["kalman_P"]     = P_k
        _spo2_state["last_spo2"]    = spo2_out
        _spo2_state["last_confidence"] = confidence

    return {
        # ---- Existing keys (unchanged) ----
        "spo2":              round(spo2_out, 1),
        "confidence":        round(confidence, 3),
        "r_value":           round(r_median, 4),
        "windows_used":      max(effective_beats, effective_windows),
        "perfusion_index":   round(mean_pi, 4),
        "window_quality":    round(window_quality, 3),
        "beat_quality":      round(beat_quality_spo2, 3),
        "ratio_quality":     round(ratio_quality, 3),
        "coverage_quality":  round(coverage_quality, 3),
        "effective_beats":   effective_beats,
        "effective_windows": max(effective_beats, effective_windows),
        "spo2_confidence":   round(confidence, 3),
        "calibration_region": calibration_region,
        # ---- New additive keys (§8, §9) ----
        "spo2_std":          round(sigma_total, 2),
        "spo2_ci_low":       round(float(np.clip(spo2_out - ci_half, SPO2_PHYSIO_MIN, SPO2_PHYSIO_MAX)), 1),
        "spo2_ci_high":      round(float(np.clip(spo2_out + ci_half, SPO2_PHYSIO_MIN, SPO2_PHYSIO_MAX)), 1),
        "kalman_gain":       round(kalman_K, 4),
        "motion_compensated": motion_compensated,
    }


# ---------------------------------------------------------------------------
# Heart-rate variability (HRV)
# ---------------------------------------------------------------------------

def compute_hrv_metrics(rr_intervals_ms) -> dict:
    """
    Standard time-domain HRV metrics computed from beat-to-beat (RR)
    intervals, using the conventional definitions from HRV literature
    (Task Force of ESC/NASPE, 1996; Shaffer & Ginsberg, 2017).

    Existing metrics (unchanged):
      - mean_rr  : mean RR interval (ms)
      - sdnn     : SD of NN intervals (ms) — overall variability
      - rmssd    : root mean square of successive RR differences (ms) —
                   parasympathetically-mediated short-term variability
      - pnn50    : % of successive diffs > 50 ms — parasympathetic proxy
      - n_intervals: number of clean intervals used in computation

    New metrics:
      - median_rr   : median RR (ms) — more robust than mean for skewed
                      distributions containing residual ectopic beats
      - cvrr        : RMSSD / mean_rr × 100 % — coefficient of variation
                      of RR; a normalized HRV measure independent of mean
                      heart rate (Kleiger et al. 2005; Billman 2011)
      - hrv_confidence: composite 0-1 confidence that these metrics are
                      meaningful given the available clean intervals and
                      physiological plausibility of the SDNN value
      - artifact_pct: percentage of input intervals flagged as artifacts
                      before clean-interval selection

    Artifact removal: intervals outside 40-200 BPM bounds are removed first;
    then intervals deviating > HRV_ARTIFACT_RR_TOLERANCE (25 %) from the
    local median are flagged as artifact. At least HRV_MIN_CLEAN_INTERVALS
    (4) clean intervals are required before any metric is computed.

    Caveat: clinically-referenced HRV norms are computed over ~5 minute
    windows. Over a short (~10 s) rolling buffer, these values are internally
    consistent for trend comparison but must not be compared directly to
    published 5-minute norms.
    """
    rr_all = np.asarray(rr_intervals_ms, dtype=np.float64)
    n_input = int(rr_all.size)

    null_result = {
        "rmssd": None, "sdnn": None, "mean_rr": None, "pnn50": None,
        "n_intervals": n_input, "median_rr": None, "cvrr": None,
        "hrv_confidence": 0.0, "artifact_pct": 100.0,
    }

    if n_input < 2:
        return null_result

    # --- Step 1: physiological bounds filter ---
    physio_mask = (rr_all >= MIN_RR_SEC * 1000.0) & (rr_all <= MAX_RR_SEC * 1000.0)
    rr_physio = rr_all[physio_mask]
    if rr_physio.size < 2:
        return null_result

    # --- Step 2: deviation-from-median artifact flagging ---
    local_median = float(np.median(rr_physio))
    artifact_mask = (
        np.abs(rr_physio - local_median) / (local_median + 1e-9) > HRV_ARTIFACT_RR_TOLERANCE
    )
    n_artifacts_total = int(np.sum(~physio_mask)) + int(np.sum(artifact_mask))
    artifact_pct = round(float(n_artifacts_total / n_input * 100.0), 1)

    rr_clean = rr_physio[~artifact_mask]
    n_clean = int(rr_clean.size)

    if n_clean < HRV_MIN_CLEAN_INTERVALS:
        null_result["artifact_pct"] = artifact_pct
        return null_result

    # --- Core metrics ---
    mean_rr = float(np.mean(rr_clean))
    median_rr = float(np.median(rr_clean))
    sdnn = float(np.std(rr_clean, ddof=1))

    if n_clean < 3:
        return {
            "rmssd": None, "sdnn": round(sdnn, 2), "mean_rr": round(mean_rr, 2),
            "pnn50": None, "n_intervals": n_clean,
            "median_rr": round(median_rr, 2), "cvrr": None,
            "hrv_confidence": 0.3, "artifact_pct": artifact_pct,
        }

    successive_diffs = np.diff(rr_clean)
    rmssd = float(np.sqrt(np.mean(successive_diffs ** 2)))
    pnn50 = float(np.mean(np.abs(successive_diffs) > 50.0) * 100.0)

    # CVRR = RMSSD / mean_RR × 100 %
    # Normalizes RMSSD by the mean RR interval, making HRV comparable across
    # different heart rates — a faster heart rate produces shorter RR intervals
    # and therefore smaller absolute RMSSD, so CVRR corrects for this.
    cvrr = float(rmssd / (mean_rr + 1e-9) * 100.0)

    # --- HRV confidence ---
    # Component 1: fraction of input intervals that were accepted as clean.
    clean_fraction = float(np.clip(n_clean / max(n_input, 1), 0.0, 1.0))
    # Component 2: inverse artifact rate.
    artifact_score = 1.0 - artifact_pct / 100.0
    # Component 3: physiological plausibility of SDNN. For short windows
    # (~10 s), typical SDNN is 5-50 ms. Values outside this range (< 1 ms
    # or > 200 ms) suggest either identical beats (possible artifact) or
    # extreme irregularity (possible missed beats). Score peaks at sdnn = 15 ms.
    sdnn_plausible = float(np.clip(
        1.0 - abs(np.log10(max(sdnn, 0.1) / 15.0)) / 2.0, 0.0, 1.0
    ))
    hrv_confidence = float(np.clip(
        0.4 * clean_fraction + 0.4 * artifact_score + 0.2 * sdnn_plausible,
        0.0, 1.0,
    ))

    return {
        "rmssd": round(rmssd, 2),
        "sdnn": round(sdnn, 2),
        "mean_rr": round(mean_rr, 2),
        "pnn50": round(pnn50, 2),
        "n_intervals": n_clean,
        # new metrics
        "median_rr": round(median_rr, 2),
        "cvrr": round(cvrr, 2),
        "hrv_confidence": round(hrv_confidence, 3),
        "artifact_pct": artifact_pct,
    }


# ---------------------------------------------------------------------------
# Sensor diagnostics
# ---------------------------------------------------------------------------

def classify_sensor_status(ir) -> str:
    """
    Classify the raw IR channel into a coarse sensor-health category so the
    dashboard/firmware can distinguish "no signal" from "signal present but
    poorly conditioned" without inspecting every diagnostic field.

    Returns one of: "LOW_SIGNAL", "GOOD", "HIGH_SIGNAL", "SATURATED".

    Precedence: saturation is checked first because a clipped signal is
    unusable regardless of its average DC level; then low/high DC bands
    flag a fit that's technically producing a signal but is either too
    weak (loose contact, low perfusion) or over-driven (too much LED
    current / pressure) to trust for downstream estimation.
    """
    ir = _as_float_array(ir)
    if ir.size == 0:
        return "LOW_SIGNAL"

    dc_level = float(np.mean(ir))
    clip_threshold = ADC_MAX_VALUE * SATURATION_FRACTION
    clipping_fraction = float(np.mean(ir >= clip_threshold))

    if clipping_fraction > SENSOR_STATUS_CLIPPING_FRACTION or float(np.max(ir)) >= clip_threshold:
        return "SATURATED"
    if dc_level >= SENSOR_STATUS_HIGH_DC:
        return "HIGH_SIGNAL"
    if dc_level < SENSOR_STATUS_LOW_DC:
        return "LOW_SIGNAL"
    return "GOOD"
