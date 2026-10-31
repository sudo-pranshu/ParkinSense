"""
ParkinSense — PPG Signal Processing Algorithms  (Version C — merged, reviewed)
===============================================================================

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
explicitly documented SpO2 smoothing/lock state), easy to unit test.

Version history / merge notes
------------------------------
This module ("Version C") merges two prior implementations:

  * "Version A" contributed the advanced adaptive peak detector (rolling
    z-score normalization, local short-time-energy gating, adaptive
    prominence scaling, physical-domain pulse-width verification), the
    richer per-beat morphology scoring, the fuller Signal Quality Index
    (spectral entropy, spectral concentration, harmonic ratio, perfusion
    index, pulse repeatability, frequency stability), the adaptive-weight
    finger-presence detector, and the confidence-weighted heart-rate
    estimator.

  * "Version B" contributed the beat-by-beat SpO2 architecture: per-beat
    AC/DC extraction, per-beat R computation and quality scoring, weighted
    pulse selection, a low-pass DC tracker, and a SEARCHING/LOCKED/
    TRACKING/LOST signal-lock state machine with rate-limited output.

Version C keeps every public function name, signature, and returned
dictionary key from both predecessors (new fields are additive only) while
rebuilding `estimate_spo2` on top of Version A's peak detector/scorer,
adding RED/IR peak-alignment validation, R-value stability scoring, an
adaptive (non-fixed-percentage) pulse-selection rule, a hysteresis-based
lock state machine, and a pluggable calibration hook — all without
duplicating FFTs or filter passes beyond what each function strictly needs.
"""

from __future__ import annotations

import numpy as np
from scipy.ndimage import uniform_filter1d
from scipy.signal import butter, filtfilt, find_peaks, peak_widths

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

# --- Simplified HR estimator (research-pipeline revision) ---
# A separate, tighter set of bounds used only by `estimate_heart_rate`'s
# simplified pipeline below. Kept distinct from MIN_BPM/MAX_BPM above
# because those are still used by `_score_beats`, `compute_hrv_metrics`,
# and `_detect_peaks`'s refractory period, none of which this revision
# touches.
SIMPLE_HR_MIN_BPM = 45.0
SIMPLE_HR_MAX_BPM = 180.0
SIMPLE_HR_MIN_RR_SEC = 60.0 / SIMPLE_HR_MAX_BPM
SIMPLE_HR_MAX_RR_SEC = 60.0 / SIMPLE_HR_MIN_BPM
# Detection-time spacing: looser than SIMPLE_HR_MAX_BPM so a genuinely
# fast beat isn't discarded before the RR-bounds filter (step 3) gets to
# judge it; the 20 BPM margin mirrors the same headroom the previous
# detection-time refractory period used relative to its own reporting
# bounds.
SIMPLE_PEAK_MIN_DISTANCE_SEC = 60.0 / (SIMPLE_HR_MAX_BPM + 20.0)
# Prominence floor expressed as a multiple of the filtered buffer's own
# standard deviation, so the threshold scales with whatever amplitude a
# given buffer happens to have (fingertip vs. wrist, good vs. poor
# contact) rather than a fixed ADC-count constant.
SIMPLE_PEAK_PROMINENCE_STD = 0.5
# A dicrotic notch (the small secondary bump on a PPG pulse's downslope)
# can still clear a plain distance+prominence peak-pick, since it often
# sits well past SIMPLE_PEAK_MIN_DISTANCE_SEC after the systolic peak.
# This is a confirmed, previously-diagnosed cause of ~2x HR readings, so
# one narrow check for it is kept even in the simplified pipeline: a
# candidate peak within this many seconds of the prior one is only kept
# if its prominence is at least this fraction of the prior peak's
# prominence (a real second beat is comparable in size; a notch is not).
SIMPLE_NOTCH_WINDOW_SEC = 0.5
SIMPLE_NOTCH_PROMINENCE_RATIO = 0.6

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
# Calibration model: a single smooth quadratic
#     SpO2 = SPO2_CAL_A + SPO2_CAL_B * R + SPO2_CAL_C * R^2
# replacing the two-segment linear "Maxim app-note" family (SpO2 = A - B*R,
# A/B = 110/25 below a breakpoint, 108/20 above it) that this module used
# previously.
#
# Root-cause note (why the piecewise-linear defaults were replaced, not
# just offset): those constants are the standard *transmission-mode*
# fingertip-clip calibration published in Maxim/Analog app notes for the
# MAX30100/30102 evaluation kit. This device is a *reflectance*-geometry
# sensor (LED and photodiode on the same side, sensor lying flat against
# the skin) — a fundamentally different optical path than a transmission
# clip. Reflectance PPG picks up more scattered/venous signal and a longer
# effective path length, so for the *same true SpO2* it produces a
# systematically higher R than a transmission probe does. Feeding that
# higher R through a transmission-calibrated curve therefore reads low by
# a roughly constant amount for any resting, well-perfused signal — a
# systematic calibration-curve mismatch, not measurement noise, which is
# exactly the "stuck ~9 points low regardless of signal quality" symptom
# (a genuine per-sample computation bug would instead track signal quality
# and jump around; a curve mismatch produces a stable, wrong number).
#
# The AC/DC extraction, DC tracking, peak alignment, and R computation
# upstream of this curve were reviewed against the standard ratio-of-ratios
# derivation (R = (AC_red/DC_red) / (AC_ir/DC_ir), peak-to-trough AC over a
# shared/aligned window, low-pass DC tracked at each channel's own peak
# sample) and found to already match the literature approach correctly —
# heart rate (which shares the same peak detector) reading accurately is
# consistent with that. The defect is isolated to the calibration mapping.
#
# Default coefficients below replace the flat literature default with a
# quadratic anchored at three points instead of an unexplained pair of
# constants:
#   (R=0.40, SpO2=100)  — low-R ceiling: near-fully-saturated blood produces
#                         only a small further change in R, so real SpO2/R
#                         curves plateau near 100% rather than climbing
#                         without bound as R falls (well documented in
#                         pulse-oximetry calibration literature).
#   (R=0.81, SpO2=98.7) — a single verified reference point: a simultaneous
#                         medical pulse-oximeter reading taken on this exact
#                         sensor at rest. This is real calibration data, the
#                         same kind `fit_spo2_calibration`/
#                         `calibrate_spo2_baseline` are designed to consume
#                         — not a hardcoded output. The curve is NOT locked
#                         to always return 98.7; a different R still maps to
#                         a different SpO2 through this same equation.
#   (R=1.80, SpO2=80)   — a literature-informed desaturation-range anchor,
#                         giving the curve a physiologically plausible slope
#                         away from the single reference point instead of
#                         guessing a slope from one point alone.
# This is still a *starting* calibration, not a clinically validated one —
# treat it exactly like the old defaults: replace it with a proper
# `fit_spo2_calibration` fit (ideally ≥5 points spanning a wide R range,
# e.g. resting + a brief breath-hold) as soon as that data is available.
SPO2_CAL_A = 97.601
SPO2_CAL_B = 10.503
SPO2_CAL_C = -11.266
SPO2_PHYSIO_MIN = 70.0
SPO2_PHYSIO_MAX = 100.0
# R (ratio-of-ratios) values outside this range indicate the estimate is
# almost certainly driven by noise rather than real arterial pulsation.
SPO2_R_MIN = 0.2
SPO2_R_MAX = 2.0

# Beat-level quality gates for SpO2 R estimation. Only beats with confidence
# ≥ SPO2_BEAT_CONFIDENCE_MIN contribute to the weighted median R. A threshold
# of 0.4 accepts beats that are "somewhat plausible" rather than demanding
# near-perfect morphology; this preserves more beats in low-perfusion states
# while still rejecting the noisiest artifact-like detections.
SPO2_BEAT_CONFIDENCE_MIN = 0.4

# Motion freeze: when the motion score is below this threshold, SpO2 cannot
# be reliably estimated because large-amplitude motion transients dominate the
# AC amplitude estimate. We return the last trusted estimate (with halved
# confidence) rather than a noise-driven measurement. 0.3 corresponds to
# ~30 % of the motion-free score — visible but not violent motion.
SPO2_MOTION_FREEZE_THRESHOLD = 0.3

# Exponential moving average weight for the new SpO2 measurement. Lower
# alpha produces a smoother output that changes more slowly. Tuned so that,
# at a typical ~1 update/second cadence, the effective smoothing time
# constant tau = -1/ln(1 - alpha) lands in the ~3-8 s range consumer
# wearables use (alpha=0.28 -> tau~3.3s at high confidence, alpha=0.05 ->
# tau~19.5s when confidence is low) rather than the previous 0.3-0.6 range
# (tau~0.9-2.8s), which reacted implausibly fast for a physiological signal
# that genuinely changes over tens of seconds to minutes.
SPO2_SMOOTHING_ALPHA = 0.15

# Maximum plausible SpO2 change between consecutive update calls. Real
# oxygen saturation changes are physiologically slow (tens of seconds to
# minutes); a jump of > 4 % per update window is almost certainly measurement
# noise rather than a genuine desaturation event, so we clamp it before the
# EMA smoother sees it.
SPO2_MAX_JUMP_PER_UPDATE = 4.0  # percent

# Rate-of-change ceiling expressed per *second* (rather than per arbitrary
# update window) so the clamp scales correctly regardless of buffer length.
# 1.0 %/s is well above any physiologically real desaturation rate (which
# unfolds over tens of seconds) but well below the jump a single noisy
# window can otherwise produce, so it is a safety clamp, not a physiological
# model of desaturation kinetics.
SPO2_MAX_ROC_PCT_PER_SEC = 1.0

# --- SpO2 signal-lock hysteresis state machine ---
# Two different thresholds for entering vs. leaving a trusted "lock" state
# (hysteresis) prevent the state machine from chattering back and forth
# across a single confidence value when confidence is noisy near the
# boundary. The gap between ON (0.75) and OFF (0.45) is chosen to be wider
# than the typical update-to-update confidence noise observed in bench
# testing, which is the standard rationale for hysteretic thresholds in
# embedded state machines (Schmitt-trigger-style debouncing).
SPO2_LOCK_CONFIDENCE_ON = 0.75
SPO2_LOCK_CONFIDENCE_OFF = 0.45
# Sustained high confidence required before *first* transitioning into a
# trusted lock, so a single lucky noisy window can't lock in a bad estimate.
SPO2_LOCK_DURATION_REQUIRED_SEC = 3.0
# Minimum sustained recovery time from LOST before re-attempting SEARCHING;
# mirrors the lock-acquisition duration so recovery is not easier to trigger
# than the initial lock (asymmetric leniency would let noise re-lock too fast).
SPO2_LOST_RECOVERY_SEC = 2.0

# --- RED/IR peak alignment (motion-robustness improvement) ---
# In a well-coupled reflectance sensor, the RED and IR systolic peaks for
# the same physical pulse should occur within a few milliseconds of each
# other (both channels observe the same arterial pulse wave through the
# same optical path). A larger offset indicates the "matched" RED peak is
# actually a different event — most commonly a motion transient that
# perturbed one channel more than the other — and the beat should be
# rejected from R-value estimation rather than silently biasing R.
IR_RED_PEAK_ALIGNMENT_MAX_SEC = 0.03  # 30 ms

# --- R-value stability scoring ---
# Reference coefficient of variation (CV) for beat-to-beat R values. Beat-
# level R has more idiosyncratic noise than a whole-window R estimate, so a
# looser reference than the window-level ratio_quality mapping is used here
# specifically for the explicit "R-value stability" sub-score requested for
# confidence blending. CV below ~0.05 is very stable (clean signal); above
# ~0.15 indicates the individual beats disagree enough to be suspicious.
SPO2_R_STABILITY_CV_REF = 0.15

# --- Adaptive pulse-selection (replaces any fixed "top N%" rule) ---
# Instead of always keeping a fixed percentile of beats, the accept
# threshold adapts to the actual quality distribution of the current
# window: a beat is kept if its quality clears the *higher* of the median
# quality or 65% of the best quality seen in this window. This tracks the
# window's own signal-to-noise regime — in a clean window nearly all beats
# clear both bars; in a noisy window with one or two excellent beats and a
# long tail of poor ones, the 0.65×max term still enforces a meaningful bar
# rather than admitting the whole noisy tail just because it's "above
# median of a bad population".
SPO2_ADAPTIVE_SELECTION_MAX_FRACTION = 0.65
SPO2_MIN_SELECTED_PULSES = 2

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

# Minimum Signal Quality Index (compute_signal_quality's 0-100 `score`) for a
# DC-plausible signal to still be reported as "GOOD". DC level alone (checked
# above) only rules out no-contact / saturation / over-drive; it says nothing
# about whether the waveform riding on that DC level is actually a usable
# pulse. Without this check, a finger resting still with a noisy, motion-
# corrupted, or otherwise unusable signal could be classified GOOD purely
# because its average light level looks like tissue. 40/100 is deliberately
# generous (roughly "somewhat usable"); callers wanting a precise numeric
# threshold should read the SQI score directly rather than relying on this
# coarse category.
SENSOR_STATUS_MIN_SQI = 40.0

# SQI score (0-100) at which estimate_heart_rate's confidence stops being
# discounted for signal quality at all (see the "SQI trust discount" in
# estimate_heart_rate). Deliberately a *different* number from
# SENSOR_STATUS_MIN_SQI above: that one gates a coarse status label, this one
# shapes a continuous confidence multiplier — and "usable" SQI varies by
# sensor placement (fingertip vs. wrist) in a way a single pass/fail cutoff
# can't capture, so HR is never unilaterally withheld by this factor alone.
SQI_FULL_TRUST_SCORE = 60.0

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
# Module-level optional state — SpO2 physiological smoothing + signal lock
# ---------------------------------------------------------------------------
# This module is designed stateless: every public function accepts an explicit
# buffer argument with no reliance on call order. The exceptions are SpO2
# physiological smoothing and the SpO2 signal-lock state machine, both of
# which require memory of the previous trusted estimate/state. We store them
# in a module-level dict so the `estimate_spo2` function signature can remain
# backward compatible (callers that only ever passed `ir, red, fs` keep
# working unmodified, with state tracked internally) while still allowing
# callers who want explicit, externally-owned state (as introduced by the
# newer beat-by-beat SpO2 pipeline) to pass it in and get it back out.
_spo2_state: dict = {
    "last_spo2": None,
    "last_confidence": 0.0,
    "state": "SEARCHING",
    "lock_duration_sec": 0.0,
}

# --- Interim single-point self-calibration offset (testing only) ---
# The built-in SPO2_CAL_A/B coefficients (110/25) are literature defaults
# derived from fingertip PPG geometry. Wrist placement has different
# reflectance geometry and lower perfusion, which commonly introduces a
# systematic *offset* in the raw ratio-of-ratios estimate relative to true
# SpO2 — not necessarily a wrong slope, just a shifted baseline for this
# specific sensor/wrist/skin combination. `SPO2_SELF_CAL_OFFSET` corrects
# that offset only; it is added to the calibrated value in `estimate_spo2`
# and otherwise changes nothing about how R is computed or how the signal
# responds to real changes (motion, perfusion, an actual desaturation
# still move the displayed value the same amount they would without the
# offset — this is deliberately NOT a clamp to a fixed "healthy" range).
# Set via `calibrate_spo2_baseline()` below. Defaults to 0.0 (no offset)
# so nothing changes until a caller explicitly sets a baseline. This is a
# stand-in for real calibration (see `fit_spo2_calibration` /
# `set_spo2_calibration_table`) and should be replaced once reference
# pulse-oximeter data is available.
SPO2_SELF_CAL_OFFSET = 0.0


def calibrate_spo2_baseline(known_spo2: float, ir, red, fs: float = 50.0) -> dict:
    """
    One-point offset calibration against a known SpO2 reference.

    Runs the ratio-of-ratios computation on a resting buffer (finger on,
    good contact, sitting still), compares the *uncalibrated-offset*
    result to `known_spo2` (a value already known to be true — from a
    reference pulse oximeter, or a self-identified healthy baseline while
    validating the device), and sets the module-level
    `SPO2_SELF_CAL_OFFSET` so future `estimate_spo2` calls land near that
    reference at this operating point.

    This corrects a systematic offset only — it does not touch the R ->
    SpO2 slope, the confidence machinery, or the signal-lock state
    machine, so a genuine within-session change (motion, perfusion shift,
    an actual desaturation) still moves the displayed value away from the
    anchor by the same amount it would have without this offset. It is
    not a substitute for `fit_spo2_calibration` against real reference
    data across a range of SpO2 levels — treat it as a temporary anchor
    for bench-testing on a single known-healthy subject, and replace it
    with a properly fitted calibration before drawing any conclusions
    from readings that aren't near that one reference point.

    Returns a dict with the computed offset and the raw (pre-offset)
    reading it was computed from, so the caller can sanity-check it
    before it takes effect (it takes effect immediately either way).
    """
    global SPO2_SELF_CAL_OFFSET
    ir = _as_float_array(ir)
    red = _as_float_array(red)
    # Compute a reading with any existing offset backed out, so repeated
    # calibration calls don't compound on top of each other.
    previous_offset = SPO2_SELF_CAL_OFFSET
    SPO2_SELF_CAL_OFFSET = 0.0
    try:
        raw_result = estimate_spo2(ir, red, fs)
    finally:
        SPO2_SELF_CAL_OFFSET = previous_offset

    if raw_result["spo2"] is None:
        return {
            "offset_applied": False,
            "reason": "no valid SpO2 reading in this buffer (check finger contact / signal quality)",
            "raw_spo2": None,
            "offset": previous_offset,
        }

    new_offset = float(known_spo2) - raw_result["spo2"]
    SPO2_SELF_CAL_OFFSET = new_offset
    return {
        "offset_applied": True,
        "raw_spo2": raw_result["spo2"],
        "known_spo2": float(known_spo2),
        "offset": round(new_offset, 2),
        "confidence": raw_result["confidence"],
    }


def reset_spo2_state() -> None:
    """
    Reset the SpO2 physiological smoothing and signal-lock state.

    Call this when starting a new recording session, when the finger is
    removed (detected → not-detected transition), or after a gap in
    measurements longer than ~30 seconds, to prevent the smoother/lock
    state machine from carrying a stale baseline into a fresh measurement
    window.
    """
    _spo2_state["last_spo2"] = None
    _spo2_state["last_confidence"] = 0.0
    _spo2_state["state"] = "SEARCHING"
    _spo2_state["lock_duration_sec"] = 0.0


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
    `compute_signal_quality`, `estimate_heart_rate`, and `estimate_spo2`, so
    the same robust-statistics logic isn't duplicated across the module.

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


def _local_robust_extremum(signal: np.ndarray, idx: int, half_width: int = 1) -> float:
    """
    Denoised value at `idx`: the mean of `signal[idx - half_width : idx + half_width + 1]`
    (clipped to valid bounds), rather than the single raw sample at `idx`.

    Rationale (new in Version C review): a systolic peak or pulse trough used
    directly for AC-amplitude estimation (in `_detect_peaks`'s `local_amplitudes`
    and in `estimate_spo2`'s per-beat AC/DC extraction) is a single sample drawn
    from a band-passed but still noisy signal (ADC quantization noise, residual
    shot noise, LED-driver ripple). A single noisy sample at exactly the
    extremum biases the AC estimate and, downstream, the R = (AC_red/DC_red) /
    (AC_ir/DC_ir) ratio used for SpO2. Averaging a small neighborhood around
    the extremum (a form of local smoothing restricted to the sample of
    interest, not a global filter that would blur timing) is a standard,
    literature-supported way to reduce this single-sample sensitivity without
    touching peak *location* (still detected on the un-averaged signal) or
    introducing any new free parameter beyond a fixed, small half-width.
    half_width = 1 (3-tap average) is deliberately small: a systolic peak's
    local curvature over 2 samples at typical fs (25-100 Hz) is negligible
    compared to the pulse width (80-350 ms), so this does not measurably
    flatten genuine peak/trough amplitude while still averaging out
    single-sample noise.
    """
    n = signal.size
    if n == 0:
        return 0.0
    lo = max(idx - half_width, 0)
    hi = min(idx + half_width + 1, n)
    if hi <= lo:
        return float(signal[max(min(idx, n - 1), 0)])
    return float(np.mean(signal[lo:hi]))


def _weighted_median(values: np.ndarray, weights: np.ndarray) -> float:
    """
    Weighted median of `values` with non-negative `weights`.

    A weighted median x* satisfies: the cumulative weight of all values ≤ x*
    is ≥ W/2 and the cumulative weight of all values ≥ x* is ≥ W/2, where
    W = sum(weights). Unlike the weighted mean, it is resistant to outliers
    — a single large weight on an outlying value does not pull x* toward it
    unless that outlier's weight exceeds half the total weight.

    This property is why we use it for RR-interval and SpO2 R-value
    aggregation: an occasional missed-beat interval, or a single artifact
    beat with a low confidence weight, does not bias the result the way it
    would in a weighted mean.

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

    This dynamic, time-aligned DC tracker (rather than a single scalar
    buffer-wide mean) is what `estimate_spo2` uses per-beat: LED drive
    current, ambient temperature, and light tissue-contact drift all shift
    the DC baseline slowly over the course of a multi-second buffer, and a
    single global mean would smear that drift into the AC/DC ratio for
    beats far from the buffer center.

    Review note: at the physiological floor (MIN_BPM = 40 BPM = 0.67 Hz),
    the 0.5 Hz default cutoff leaves only a ~0.17 Hz margin before this
    low-pass tracker starts to pass part of the cardiac fundamental into
    what is meant to be a pure DC/baseline estimate. That margin is
    workable in practice (the filter's roll-off means only a small fraction
    of cardiac energy leaks through at 0.67 Hz), but a caller processing a
    subject with resting HR at the very low end of the physiological range
    may see very slightly biased R values as a result. Rather than silently
    lowering the default (which would change existing behaviour for every
    caller relying on the current default), this is left as configurable
    via `cutoff_hz` and documented here so an integrator can tighten it
    (e.g. to 0.3 Hz) for subjects known to run bradycardic.
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

def _compute_signal_quality_impl(
    ir: np.ndarray,
    fs: float,
    filtered: np.ndarray | None = None,
    peaks: np.ndarray | None = None,
) -> dict:
    """
    Internal implementation shared by the public `compute_signal_quality`
    and by `estimate_heart_rate` / `estimate_spo2`.

    Review finding (performance): both `estimate_heart_rate` and
    `estimate_spo2` used to call the public `compute_signal_quality(ir, fs)`
    after already computing their own band-passed signal and peak set,
    causing `bandpass_filter` (a filtfilt call) and `_detect_peaks` (which
    itself does rolling normalization + an energy-envelope convolution +
    find_peaks) to run a second time on the same buffer. Accepting already-
    computed `filtered`/`peaks` here — while keeping the public
    `compute_signal_quality(ir, fs)` signature completely unchanged for
    external callers — removes that duplicate work.

    `ir` is still required (independent of `filtered`) because clipping and
    perfusion-index calculations need the raw ADC counts, not the band-passed
    signal.
    """
    empty = {
        "score": 0.0, "snr_db": None, "clipping_fraction": None,
        "motion_score": None, "pulse_consistency": None, "amplitude_score": None,
        "spectral_entropy": None, "spectral_concentration": None,
        "harmonic_ratio": None, "perfusion_index": None,
        "pulse_repeatability": None, "frequency_stability": None,
    }
    if ir.size < int(fs * 2):
        return empty

    if filtered is None:
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
    if peaks is None:
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
        # spectral / perfusion sub-scores
        "spectral_entropy": round(spectral_entropy, 3),
        "spectral_concentration": round(spectral_concentration, 3),
        "harmonic_ratio": round(harmonic_ratio_raw, 3),
        "perfusion_index": round(perfusion_index, 4),
        "pulse_repeatability": round(pulse_repeatability, 3),
        "frequency_stability": round(frequency_stability, 3),
    }


def compute_signal_quality(ir, fs: float = 50.0) -> dict:
    """
    Composite Signal Quality Index (SQI), 0-100.

    Combines independent quality indicators drawn from PPG-quality
    literature (Elgendi 2016; Orphanidou et al. 2015; Temko 2017).

    Components:
      - SNR: cardiac-band power vs. out-of-band residual power
      - clipping: fraction of samples pinned near the ADC rail
      - motion artifacts: large sample-to-sample derivative outliers
      - pulse consistency: coefficient of variation of detected RR intervals
      - amplitude: pulsatile AC amplitude relative to minimum trusted level
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

    Internally delegates to `_compute_signal_quality_impl`, which
    `estimate_heart_rate` and `estimate_spo2` also call directly with their
    already-computed filtered signal/peaks to avoid a duplicate filtfilt +
    peak-detection pass on the same buffer (see that function's docstring).
    This function's public signature and return keys are unchanged.

    Returns a dict with the composite `score` plus all sub-scores (each 0-1
    where defined, snr_db in dB) for debugging/telemetry.
    """
    ir = _as_float_array(ir)
    return _compute_signal_quality_impl(ir, fs)


# ---------------------------------------------------------------------------
# Heart rate — peak detection
# ---------------------------------------------------------------------------

def _detect_peaks(
    filtered_signal: np.ndarray, fs: float, return_properties: bool = False
):
    """
    Adaptive systolic-peak detector shared by HR estimation, SQI, finger
    detection, and SpO2.

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
         amplitude units and the 80-350 ms gate is applied as a post-filter on
         those physical-domain widths.
      5. Post-detection energy gate, adaptive prominence post-filter, and
         physical-domain width gate applied without re-running find_peaks.

    Parameters
    ----------
    return_properties : if True, also return the scipy `properties` dict
        plus: normalized_signal, local_amplitudes (peak-to-trough swing per
        beat in filtered-signal units, denoised via a small local average
        around the peak/trough samples — see `_local_robust_extremum` — to
        reduce single-sample ADC/quantization noise sensitivity), and
        energy_scores (normalized local STE at each peak). Existing callers
        that only want peak indices pass False (the default), matching the
        original signature's behaviour.
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
        # Measure the systolic pulse width in physical amplitude units.
        # We use the left_base and right_base sample indices that find_peaks
        # computed from the normalized signal as the pulse boundary landmarks
        # (they correctly locate the troughs on either side of each peak),
        # then scan inward from the peak to find the point where the filtered
        # signal drops to 50% of the local peak-to-trough amplitude. The
        # width = (right half-amp crossing - left half-amp crossing) in samples.
        # This is purely time-domain arithmetic and avoids calling peak_widths
        # with mismatched signal references.
        left_bases = properties.get("left_bases", np.zeros(peaks.size, dtype=int)).astype(int)
        right_bases = properties.get(
            "right_bases", np.full(peaks.size, filtered_signal.size - 1, dtype=int)
        ).astype(int)

        phys_widths = np.zeros(peaks.size)
        phys_lb_out = left_bases.copy()
        phys_rb_out = right_bases.copy()
        for i, pk in enumerate(peaks):
            lb = int(left_bases[i])
            rb = int(min(right_bases[i], filtered_signal.size - 1))
            pk_val = float(filtered_signal[pk])
            trough_val = min(
                float(np.min(filtered_signal[lb : pk + 1])),
                float(np.min(filtered_signal[pk : rb + 1])),
            )
            half_amp = trough_val + 0.5 * (pk_val - trough_val)
            # Scan left from peak to find where signal crosses half amplitude
            li = pk
            while li > lb and filtered_signal[li] > half_amp:
                li -= 1
            # Scan right from peak to find where signal crosses half amplitude
            ri = pk
            while ri < rb and filtered_signal[ri] > half_amp:
                ri += 1
            phys_widths[i] = float(ri - li)
            phys_lb_out[i] = li
            phys_rb_out[i] = ri

        width_mask = (
            (phys_widths >= min_width_samples)
            & (phys_widths <= max_width_samples)
        )
        peaks = peaks[width_mask]
        # Filter all property arrays and overwrite with physical-domain values
        properties_width_filtered: dict = {}
        for key, val in properties.items():
            if isinstance(val, np.ndarray) and val.shape == (width_mask.size,):
                properties_width_filtered[key] = val[width_mask]
            else:
                properties_width_filtered[key] = val
        properties_width_filtered["widths"] = phys_widths[width_mask]
        properties_width_filtered["left_bases"] = phys_lb_out[width_mask]
        properties_width_filtered["right_bases"] = phys_rb_out[width_mask]
        properties = properties_width_filtered

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
        #
        # Review improvement: the peak value and trough value are each read
        # as a small (3-tap) local average around their respective sample
        # (`_local_robust_extremum`) rather than the single raw sample. A
        # lone noisy ADC sample sitting exactly at the peak or trough would
        # otherwise directly bias this amplitude (and everything downstream
        # that consumes it: upstroke/downstroke slope scoring in
        # `_score_beats`). Peak/trough *location* is unaffected — only the
        # amplitude readout is denoised.
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
                    trough_idx = lb + int(np.argmin(seg))
                    peak_val = _local_robust_extremum(filtered_signal, int(pk), 1)
                    trough_val = _local_robust_extremum(filtered_signal, trough_idx, 1)
                    local_amplitudes[i] = peak_val - trough_val
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

    Weighting note (review): the blend weights below (0.25/0.15/0.12/0.12/
    0.08/0.08/0.15/0.05) were reviewed against the relative discriminative
    power documented in PPG beat-quality literature (Elgendi 2016;
    Orphanidou et al. 2015). Prominence and RR-agreement remain the two
    largest terms because they are the most direct, least assumption-laden
    indicators of "this is a real, well-separated pulse" — prominence
    is a direct measure of how far the candidate stands above the local
    noise floor, and RR-agreement flags beats that don't fit the local
    rhythm regardless of their individual morphology. The morphological
    sub-scores (width/symmetry/upstroke/downstroke) are corroborating,
    not primary, evidence: a real but atypical pulse (e.g. from a stiffer
    arterial wall) can fail one morphology check while still being a real
    beat, so no single morphology term is given more weight than the
    combination of prominence + RR-agreement. No empirical (regression-
    fitted) weight optimization has been done — that would require a
    labelled reference dataset this module does not have access to — so
    these remain literature-informed heuristic weights, not statistically
    fitted ones; this is stated plainly rather than dressed up as more
    rigorous than it is.

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


def estimate_heart_rate(ir, fs: float = 50.0, debug: bool = False) -> dict:
    """
    Heart-rate estimator — simplified research pipeline (this revision).

    Deliberately minimal, auditable six-step pipeline, replacing the
    earlier multi-stage adaptive detector (rolling z-score normalization,
    local-energy gating, adaptive prominence scaling, per-beat morphology
    scoring, confidence-weighted Hampel rejection, weighted median). That
    detector was more capable but harder to reason about end-to-end; the
    goal now is a stable, well-understood baseline first:

      1. Band-pass filter into the cardiac band (`bandpass_filter`,
         shared and unchanged).
      2. Peak detection: a single `scipy.find_peaks` pass with a
         physiologically-motivated minimum spacing and a prominence floor
         scaled to the buffer's own signal amplitude. One narrow
         exception is kept here (see `SIMPLE_NOTCH_WINDOW_SEC` /
         `SIMPLE_NOTCH_PROMINENCE_RATIO` above): a closely-following,
         much-weaker candidate peak is treated as a dicrotic notch rather
         than a second beat. This isn't reintroducing the old detector's
         complexity — it's a two-line guard against a specific,
         previously-confirmed failure mode (notch double-counting
         producing ~2x HR readings) that a plain peak-pick would
         otherwise reproduce.
      3. Reject RR intervals outside a physiologically plausible range.
      4. Take the median of what's left.
      5. Convert to BPM.
      6. Clamp/reject if the result still falls outside a plausible
         range — this discards an implausible computed value; it does
         not invent or force one into range.

    Per-update persistence (holding a single-window jump until it
    persists across several updates) intentionally lives in
    `PPGProcessor`'s existing EMA + outlier-hold logic in
    `ppg_processor.py`, not here. This function is stateless — one
    buffer in, one estimate out — and duplicating cross-call memory here
    would mean changing that file's contract, which is out of scope for
    this revision (per "don't touch the runtime architecture").

    Returns the same dict shape as the previous revision so
    `PPGProcessor` (and any other caller) needs no changes. The richer
    sub-metrics (`beat_quality`, `confidence_breakdown`, etc.) are now
    derived from this simpler pipeline's own signals — RR regularity and
    the fraction of intervals kept — rather than the old per-beat
    morphology scorer, so they're coarser but still meaningful 0-1 trust
    indicators. `compute_signal_quality` is called directly for
    perfusion/motion context rather than reusing an already-computed
    filtered/peaks pair (a small, deliberate trade of a bit of redundant
    computation for a simpler, more self-contained function body).

    Parameters
    ----------
    debug : if True, attach a `"_debug"` key with a stage-by-stage trace
        (peaks detected, RR intervals before/after filtering, counts
        rejected, and — on any early return — a plain-English `reason`).
    """
    ir = _as_float_array(ir)
    empty = {
        "heart_rate": None, "rr_intervals_ms": [], "confidence": 0.0,
        "beats_detected": 0, "peak_quality": 0.0, "rhythm_quality": 0.0,
        "beat_quality": 0.0,
        "signal_quality": 0.0, "motion_quality": 0.0, "coverage": 0.0,
        "rr_quality": 0.0,
        "confidence_breakdown": {
            "beat_quality": 0.0, "rhythm_quality": 0.0,
            "signal_quality": 0.0, "perfusion": 0.0, "motion": 0.0,
        },
    }

    dbg: dict = {"input_samples": int(ir.size), "fs": fs, "stage_reached": "input_length_check"}

    def _finish(result: dict) -> dict:
        if debug:
            result = dict(result)
            result["_debug"] = dbg
        return result

    if ir.size < int(fs * 5):  # need a handful of seconds to see multiple beats
        dbg["reason"] = f"buffer too short: {ir.size} samples < {int(fs * 5)} required (fs*5)"
        return _finish(empty)

    # --- Step 1: band-pass filter into the cardiac band ---
    filtered = bandpass_filter(ir, fs)

    # --- Step 2: peak detection (plain find_peaks + one notch guard) ---
    min_distance = max(int(fs * SIMPLE_PEAK_MIN_DISTANCE_SEC), 1)
    sig_std = float(np.std(filtered))
    prominence = max(sig_std * SIMPLE_PEAK_PROMINENCE_STD, 1e-6)
    raw_peaks, raw_props = find_peaks(filtered, distance=min_distance, prominence=prominence)

    # Notch guard: walk left to right, comparing each candidate to the
    # last *accepted* peak. A candidate within SIMPLE_NOTCH_WINDOW_SEC of
    # it is dropped if much weaker (a notch); comparable-or-stronger
    # candidates are kept as real beats (this is what a genuinely fast
    # heart rate looks like too, so it's deliberately not over-rejected).
    prominences = raw_props.get("prominences", np.ones(raw_peaks.size))
    max_notch_samples = SIMPLE_NOTCH_WINDOW_SEC * fs
    keep_mask = np.ones(raw_peaks.size, dtype=bool)
    last_kept = 0
    for i in range(1, raw_peaks.size):
        if raw_peaks[i] - raw_peaks[last_kept] <= max_notch_samples:
            if prominences[i] < SIMPLE_NOTCH_PROMINENCE_RATIO * prominences[last_kept]:
                keep_mask[i] = False
                continue
            if prominences[last_kept] < SIMPLE_NOTCH_PROMINENCE_RATIO * prominences[i]:
                keep_mask[last_kept] = False
                last_kept = i
                continue
        last_kept = i
    peaks = raw_peaks[keep_mask]

    dbg["stage_reached"] = "peak_detection"
    dbg["peaks_detected"] = int(peaks.size)
    dbg["peak_indices"] = peaks.tolist()
    if peaks.size < 3:  # need ≥ 2 RR intervals to judge consistency
        dbg["reason"] = f"only {peaks.size} peak(s) survived detection; need ≥3"
        return _finish(empty)

    # --- Step 3: reject physiologically impossible RR intervals ---
    rr_raw = np.diff(peaks) / fs  # seconds
    dbg["rr_ms_before_filtering"] = [round(x * 1000.0, 1) for x in rr_raw]
    physio_mask = (rr_raw >= SIMPLE_HR_MIN_RR_SEC) & (rr_raw <= SIMPLE_HR_MAX_RR_SEC)
    rr = rr_raw[physio_mask]
    dbg["stage_reached"] = "physiological_bounds_filter"
    dbg["rr_ms_after_physio_filter"] = [round(x * 1000.0, 1) for x in rr]
    dbg["rejected_rr_ms"] = [round(x * 1000.0, 1) for x in rr_raw[~physio_mask]]
    dbg["n_rejected_by_physio_bounds"] = int(rr_raw.size - rr.size)
    if rr.size < 2:
        dbg["reason"] = (
            f"only {rr.size} interval(s) left after physiological-bounds filter "
            f"({SIMPLE_HR_MIN_RR_SEC * 1000:.0f}-{SIMPLE_HR_MAX_RR_SEC * 1000:.0f} ms window); need ≥2"
        )
        return _finish(empty)

    # --- Steps 4-5: median RR -> BPM ---
    median_rr_sec = float(np.median(rr))
    bpm = 60.0 / median_rr_sec
    dbg["stage_reached"] = "bpm_computed"
    dbg["raw_bpm"] = round(bpm, 1)
    dbg["accepted_rr_ms"] = [round(x * 1000.0, 1) for x in rr]

    # --- Step 6: plausibility clamp (reject, don't invent) ---
    if not (SIMPLE_HR_MIN_BPM <= bpm <= SIMPLE_HR_MAX_BPM):
        dbg["reason"] = f"bpm {bpm:.1f} outside plausible range [{SIMPLE_HR_MIN_BPM}, {SIMPLE_HR_MAX_BPM}]"
        return _finish(empty)

    # --- Coarse trust sub-metrics, derived from this simpler pipeline ---
    retained_fraction = float(rr.size / rr_raw.size)
    cv = float(np.std(rr) / (np.mean(rr) + 1e-9))
    regularity = float(np.clip(1.0 - cv * 2.0, 0.0, 1.0))

    quality = compute_signal_quality(ir, fs)
    signal_quality_norm = quality["score"] / 100.0
    perfusion = quality.get("amplitude_score", signal_quality_norm)
    motion = quality.get("motion_score") if quality.get("motion_score") is not None else 1.0
    dbg["sqi_score"] = round(quality["score"], 1)

    confidence = float(np.clip(
        0.45 * retained_fraction + 0.35 * regularity + 0.20 * signal_quality_norm,
        0.0, 1.0,
    ))

    dbg["stage_reached"] = "complete"
    dbg["retained_fraction"] = round(retained_fraction, 3)

    return _finish({
        "heart_rate": round(bpm, 1),
        "rr_intervals_ms": [round(x * 1000.0, 1) for x in rr],
        "confidence": round(confidence, 3),
        "beats_detected": int(peaks.size),
        "peak_quality": round(retained_fraction, 3),
        "rhythm_quality": round(regularity, 3),
        "beat_quality": round(regularity, 3),  # coarse stand-in, see docstring
        "signal_quality": round(signal_quality_norm, 3),
        "motion_quality": round(float(motion), 3),
        "coverage": round(retained_fraction, 3),
        "rr_quality": round(retained_fraction, 3),
        "confidence_breakdown": {
            "beat_quality": round(regularity, 3),
            "rhythm_quality": round(regularity, 3),
            "signal_quality": round(signal_quality_norm, 3),
            "perfusion": round(float(perfusion), 3),
            "motion": round(float(motion), 3),
        },
    })


# ---------------------------------------------------------------------------
# SpO2 (ratio-of-ratios) — beat-by-beat pipeline with signal-lock tracking
# ---------------------------------------------------------------------------
#
# Algorithm summary (merges the Version-A peak/beat machinery with the
# Version-B beat-by-beat SpO2 architecture, plus new robustness features):
#
#   1. Band-pass both channels once; track each channel's slowly-varying DC
#      baseline with `_lowpass_dc` (time-aligned, not a single scalar mean).
#   2. Detect systolic beats on the IR channel with the shared adaptive
#      peak detector (`_detect_peaks`) and score them with the shared
#      morphology scorer (`_score_beats`) — the same machinery used by
#      `estimate_heart_rate`, so beat quality judgments are consistent
#      across HR and SpO2.
#   3. For each sufficiently-confident IR beat, locate the matching RED
#      peak in a small physiological search window and *validate RED/IR
#      temporal alignment* — a real arterial pulse produces near-simultaneous
#      systolic peaks in both wavelengths; a peak pair separated by more than
#      `IR_RED_PEAK_ALIGNMENT_MAX_SEC` is almost certainly two different
#      events (typically a motion transient hitting one channel harder than
#      the other) and is rejected rather than allowed to bias R.
#   4. Compute per-beat R = (AC_red/DC_red) / (AC_ir/DC_ir) using
#      peak-to-trough amplitudes over the *same* pulse-boundary window in
#      both channels (so asymmetric windowing can't bias R), with the peak
#      and trough samples each read as a small local average
#      (`_local_robust_extremum`) rather than a single raw ADC sample —
#      review improvement, see rationale below — gated by per-channel
#      perfusion-index plausibility and the physiological R range.
#   5. Hampel-reject outlying beat-level R values, then apply an *adaptive*
#      pulse-selection rule (no fixed "top-N%"): a beat is kept only if its
#      composite quality clears the higher of the window's median quality or
#      `SPO2_ADAPTIVE_SELECTION_MAX_FRACTION` of its best quality, so the bar
#      tracks the window's own SNR regime rather than always admitting a
#      fixed fraction of whatever beats happen to be present.
#   6. Aggregate with a confidence-weighted median R, and separately score
#      beat-to-beat R stability (its own sub-score, distinct from the
#      window-level ratio_quality) so a run of individually plausible but
#      mutually inconsistent R values is flagged rather than blindly averaged.
#   7. Map R through a calibration curve. The calibration step is exposed as
#      a small, swappable primitive (`_spo2_calibrate`, `set_spo2_calibration_table`)
#      so a future lookup-table or polynomial calibration can be installed
#      without touching `estimate_spo2`'s public signature.
#   8. Track a hysteresis-based signal-lock state machine
#      (SEARCHING -> LOCKED -> TRACKING -> LOST) so a brief, noisy dip in
#      confidence doesn't repeatedly flip the reported lock state — locking
#      requires *sustained* high confidence, unlocking requires confidence to
#      fall meaningfully below the locking bar (Schmitt-trigger-style
#      debouncing), which is the standard fix for state-machine chatter.
#   9. Only in LOCKED/TRACKING states (and outside severe motion) is a new
#      SpO2 value published; it is then rate-limited (physiologically
#      implausible desaturation speeds are clamped) and exponentially
#      smoothed, with the smoothing weight itself scaled by confidence so a
#      strong, stable beat set is trusted more than a marginal one.
#  10. During severe motion (`SPO2_MOTION_FREEZE_THRESHOLD`), the last
#      trusted value is held (with confidence halved) rather than reporting
#      a noise-driven measurement, regardless of lock state.
#
# Review note on the RED/IR alignment window (Section: "Beat pairing"):
# the RED-peak search window (`search_half`, derived from
# MIN_PEAK_WIDTH_SEC/2) and the accept tolerance (`IR_RED_PEAK_ALIGNMENT_MAX_SEC`
# = 30 ms) were checked against each other for consistency: at fs = 50 Hz,
# search_half is ~2 samples (40 ms) and the alignment tolerance is ~1.5
# samples (30 ms), so the search window is not so wide that it could find
# and then reject a RED peak that a wider search would have matched — the
# two are of comparable scale, which is the correct relationship (a search
# window much narrower than the tolerance would truncate legitimate matches;
# much wider would waste cycles scanning candidates that can never pass).
# No change was needed here.
#
# Review note on AC estimation ("AC estimation" section of the request):
# pulse *area/integral* (integrating the pulse waveform over its boundary
# window) was considered as an alternative to peak-to-trough amplitude.
# Area-based estimators are used in some research PPG pipelines because
# they average over more samples and are therefore less sensitive to a
# single noisy sample — but they also conflate amplitude with pulse *shape*
# (a wider, lower pulse and a narrower, taller pulse can integrate to the
# same area), which would make R less directly comparable across beats of
# differing morphology within the same buffer. Peak-to-trough amplitude is
# kept as the primary estimator (it is what the classical ratio-of-ratios
# derivation assumes), but its single-sample noise sensitivity is addressed
# directly and locally via `_local_robust_extremum` (a small fixed-width
# average around the peak and trough samples only) rather than switching
# estimators altogether — this captures most of the noise-robustness
# benefit of an area-based approach without its shape-conflation downside.
#
# Backward compatibility: callers that only ever passed `(ir, red, fs)` (the
# original stateless-per-call contract) get their lock/smoothing state
# tracked automatically in the module-level `_spo2_state` dict, exactly as
# before — call `reset_spo2_state()` on a new session or finger-removal
# event. Callers that want fully externally-owned state (no module-level
# mutation, e.g. for multi-sensor or multi-user deployments) may instead
# pass `prior_spo2` / `prior_confidence` / `prior_state` / `lock_duration_sec`
# explicitly and read the equivalent fields back out of the returned dict on
# every call; doing so bypasses `_spo2_state` entirely for that call.
# ---------------------------------------------------------------------------

# Module-level default calibration table hook. `None` means "use the built-in
# single quadratic calibration (SPO2_CAL_A/SPO2_CAL_B/SPO2_CAL_C)". Installing
# a table here lets every future `estimate_spo2` call (that doesn't pass its
# own `calibration_table` argument) pick up a new calibration — e.g. one
# derived from an actual co-oximeter calibration session — without changing
# `estimate_spo2`'s signature or breaking any existing caller.
_active_calibration_table: list[tuple[float, float, float, float]] | None = None


def set_spo2_calibration_table(
    table: list[tuple[float, float, float]] | list[tuple[float, float, float, float]] | None,
) -> None:
    """
    Install a custom piecewise SpO2 calibration table.

    `table` is a list of `(r_upper_bound, a, b)` or `(r_upper_bound, a, b, c)`
    tuples, sorted by ascending `r_upper_bound`, defining segments of the
    form `SpO2 = a + b*R + c*R^2` (c defaults to 0, i.e. a linear segment,
    for 3-tuples) valid for R up to `r_upper_bound` (the last entry's
    segment is used for any R above its bound). Passing `None` restores the
    built-in single quadratic default (`SPO2_CAL_A`/`SPO2_CAL_B`/`SPO2_CAL_C`).

    This indirection exists so that a future calibration derived from actual
    co-oximeter reference data (a `fit_spo2_calibration` fit, or a
    finer-grained piecewise table) can be installed without changing
    `estimate_spo2`'s public signature or any caller's code.
    """
    global _active_calibration_table
    _active_calibration_table = table


def fit_spo2_calibration(
    r_values, reference_spo2_values, install: bool = True
) -> dict:
    """
    Fit a SpO2 = a + b*R + c*R^2 calibration from paired reference
    measurements and (optionally) install it as the active calibration.

    Review context: the built-in `SPO2_CAL_A`/`SPO2_CAL_B`/`SPO2_CAL_C` are
    a documented *starting point* (see the SpO2-calibration constants block
    above), not a universal constant — actual R-to-SpO2 mapping shifts with
    optical geometry (reflectance vs. transmission), LED wavelength
    binning, photodiode responsivity, LED drive current, optical coupling,
    and skin tone. There is no responsible way to guess a replacement set
    of constants without reference measurements — doing so would just swap
    one unverified guess for another. This function does the honest
    version: collect `r_value` (from `estimate_spo2(...)["r_value"]`)
    alongside a simultaneous reading from a reference pulse oximeter across
    a range of conditions (ideally including some breath-holds or
    altitude/activity variation to get spread below ~97 %, since a
    calibration fit entirely from resting-normal data extrapolates poorly
    to the low-saturation region), then fit here.

    Fit degree
    ----------
    - >= 4 valid points spanning enough R range (`np.ptp(r) >= 0.15`):
      fits the full quadratic `a + b*R + c*R^2` via least squares.
    - 2-3 points, or a narrower R range: fits a straight line (`c=0`)
      instead — a quadratic from only a handful of closely-spaced points
      is typically just noise-fitting, not a genuine curvature estimate.

    Parameters
    ----------
    r_values : sequence of float — R values from `estimate_spo2(...)["r_value"]`
    reference_spo2_values : sequence of float — simultaneous reference SpO2 (%)
    install : if True (default), installs the fit via
        `set_spo2_calibration_table` so subsequent `estimate_spo2` calls
        (that don't pass their own `calibration_table`) use it immediately.

    Returns
    -------
    dict with: a, b, c (fitted SpO2 = a + b*R + c*R^2 coefficients,
    c=0.0 if a linear fit was used), r_squared (fit quality, 0-1), n (number
    of paired points used), degree ("linear" or "quadratic"), and a
    `warning` string if the fit is likely unreliable (too few points, or
    too narrow an R range to extrapolate from).
    """
    r = np.asarray(r_values, dtype=np.float64)
    y = np.asarray(reference_spo2_values, dtype=np.float64)
    if r.size != y.size:
        raise ValueError(
            f"r_values ({r.size}) and reference_spo2_values ({y.size}) must be the same length"
        )
    valid = np.isfinite(r) & np.isfinite(y)
    r, y = r[valid], y[valid]

    warning = None
    if r.size < 2:
        warning = f"Only {r.size} valid paired point(s); at least 5-10 across varied conditions is recommended for a trustworthy fit."
        return {
            "a": SPO2_CAL_A, "b": SPO2_CAL_B, "c": SPO2_CAL_C, "r_squared": 0.0,
            "n": int(r.size), "degree": "none",
            "warning": warning + " Falling back to built-in defaults; no fit was installed.",
        }
    if r.size < 5:
        warning = f"Only {r.size} valid paired point(s); at least 5-10 across varied conditions is recommended for a trustworthy fit."
    r_span = float(np.ptp(r))
    if r_span < 0.15:
        span_warning = f"R values span only {r_span:.3f}; a fit from such a narrow range extrapolates poorly outside it."
        warning = (warning + " " + span_warning) if warning else span_warning

    use_quadratic = r.size >= 4 and r_span >= 0.15

    if use_quadratic:
        design = np.stack([np.ones_like(r), r, r * r], axis=1)
        degree = "quadratic"
    else:
        design = np.stack([np.ones_like(r), r], axis=1)
        degree = "linear"

    coeffs, _, _, _ = np.linalg.lstsq(design, y, rcond=None)
    a = float(coeffs[0])
    b = float(coeffs[1])
    c = float(coeffs[2]) if use_quadratic else 0.0

    y_pred = a + b * r + c * r * r
    ss_res = float(np.sum((y - y_pred) ** 2))
    ss_tot = float(np.sum((y - np.mean(y)) ** 2)) + 1e-12
    r_squared = float(np.clip(1.0 - ss_res / ss_tot, 0.0, 1.0))

    result = {
        "a": round(a, 3), "b": round(b, 3), "c": round(c, 3),
        "r_squared": round(r_squared, 4), "n": int(r.size), "degree": degree,
    }
    if warning:
        result["warning"] = warning

    # Sanity check: over the observed R range, SpO2 must be non-increasing
    # as R increases (dSpO2/dR = b + 2c*R <= 0 across [min(r), max(r)]).
    # A fit that increases with R across the observed data almost always
    # means too few/too noisy points rather than a real physiological
    # finding — installing it would make estimates worse than the current
    # calibration, so refuse to install even if `install=True`.
    slope_at_min = b + 2.0 * c * float(np.min(r))
    slope_at_max = b + 2.0 * c * float(np.max(r))
    if slope_at_min > 0 or slope_at_max > 0:
        result["warning"] = (
            (result.get("warning", "") + " " if "warning" in result else "")
            + "Fitted curve increases with R somewhere in the observed range "
            "(SpO2 should decrease as R increases); this fit was NOT installed. "
            "Collect more paired points across a wider R range."
        )
        return result

    if install:
        r_upper = float(np.max(r)) + 1.0  # generous upper bound so the fit covers the observed range and a margin beyond it
        set_spo2_calibration_table([(r_upper, a, b, c)])
    return result


def _spo2_calibrate(
    r: float,
    cal_a: float = SPO2_CAL_A,
    cal_b: float = SPO2_CAL_B,
    cal_c: float = SPO2_CAL_C,
    calibration_table: list[tuple[float, float, float, float]] | None = None,
) -> float:
    """
    Empirical SpO2 calibration from the ratio-of-ratios R value.

    Resolution order:
      1. If `calibration_table` is given explicitly (per-call override), use it.
      2. Else if a table has been installed via `set_spo2_calibration_table`,
         use that.
      3. Else fall back to the built-in single quadratic calibration:
         SpO2 = cal_a + cal_b * R + cal_c * R^2 (see the SpO2-calibration
         constants block above for the root-cause rationale and anchor
         points behind the defaults). A single smooth quadratic covering the
         whole R range replaces the old two-segment linear approximation —
         it captures the same real nonlinearity (reduced vs. oxygenated
         hemoglobin have different absorption coefficients at 660/940 nm)
         without an artificial kink at a breakpoint.

    Table entries are `(r_upper, a, b, c)` 4-tuples evaluated as
    `a + b*r + c*r**2` (see `set_spo2_calibration_table`). 3-tuples
    `(r_upper, a, b)` are still accepted for backward compatibility and are
    treated as `c=0` (a plain linear segment).

    Constants are approximate in all cases; accurate clinical calibration
    requires simultaneous co-oximeter reference measurements across a range
    of SpO2.
    """
    table = calibration_table if calibration_table is not None else _active_calibration_table
    if table:
        for entry in table:
            r_upper, a, b = entry[0], entry[1], entry[2]
            c = entry[3] if len(entry) > 3 else 0.0
            if r <= r_upper:
                return a + b * r + c * r * r
        last = table[-1]
        a, b = last[1], last[2]
        c = last[3] if len(last) > 3 else 0.0
        return a + b * r + c * r * r

    return cal_a + cal_b * r + cal_c * r * r


def _spo2_fallback_window_method(
    ir: np.ndarray, red: np.ndarray, fs: float, sub_window_seconds: float,
    motion_score: float,
) -> dict:
    """
    Fallback window-std R estimation for buffers too short, or too sparse in
    detected beats, for the beat-by-beat pipeline. Preserved from the
    original window-based implementation for backward compatibility with
    short capture windows / very weak signals, where the adaptive peak
    detector may not reliably resolve individual beats but a coarse
    window-level AC/DC estimate is still informative.
    """
    window = int(fs * sub_window_seconds)
    step = max(window // 2, 1)  # 50 % overlap
    window_r_values: list[float] = []
    for start in range(0, max(ir.size - window + 1, 0), step):
        ir_seg = ir[start : start + window]
        red_seg = red[start : start + window]
        dc_ir = float(np.mean(ir_seg))
        dc_red = float(np.mean(red_seg))
        if dc_ir <= 0 or dc_red <= 0:
            continue
        ac_ir = float(np.std(bandpass_filter(ir_seg, fs)))
        ac_red = float(np.std(bandpass_filter(red_seg, fs)))
        if ac_ir <= 0 or ac_red <= 0:
            continue
        r = (ac_red / dc_red) / (ac_ir / dc_ir)
        if SPO2_R_MIN <= r <= SPO2_R_MAX:
            window_r_values.append(r)

    if not window_r_values:
        return {"ok": False}

    r_arr = np.array(window_r_values)
    r_median = float(np.median(r_arr))
    r_cv = float(np.std(r_arr) / (r_median + 1e-9)) if r_arr.size > 1 else 1.0
    ratio_quality = float(np.clip(1.0 - r_cv * 3.0, 0.0, 1.0))
    r_stability_score = float(np.clip(1.0 - r_cv / SPO2_R_STABILITY_CV_REF, 0.0, 1.0))
    mean_pi = float(np.std(bandpass_filter(ir, fs))) / (float(np.mean(ir)) + 1e-9) * 100.0

    return {
        "ok": True,
        "r_median": r_median,
        "mean_pi": mean_pi,
        "ratio_quality": ratio_quality,
        "r_stability_score": r_stability_score,
        "window_quality": motion_score,
        "beat_quality": 0.0,
        "coverage_quality": float(np.clip(len(window_r_values) / 4.0, 0.0, 1.0)),
        "effective_beats": 0,
        "effective_windows": len(window_r_values),
    }


def _spo2_empty_result(prior_spo2, prior_confidence, prior_state, lock_duration_sec) -> dict:
    """Shared "not enough information yet" result, passing prior state through unchanged."""
    return {
        "spo2": round(prior_spo2, 1) if prior_spo2 is not None else None,
        "confidence": 0.0,
        "r_value": None,
        "windows_used": 0,
        "perfusion_index": 0.0,
        "window_quality": 0.0,
        "beat_quality": 0.0,
        "ratio_quality": 0.0,
        "coverage_quality": 0.0,
        "effective_beats": 0,
        "effective_windows": 0,
        "spo2_confidence": 0.0,
        "calibration_region": "unknown",
        "r_stability_score": 0.0,
        "state": prior_state if prior_state is not None else "SEARCHING",
        "lock_duration_sec": round(lock_duration_sec, 2) if lock_duration_sec is not None else 0.0,
    }


def estimate_spo2(
    ir,
    red,
    fs: float = 50.0,
    sub_window_seconds: float = 2.0,
    prior_spo2: float | None = None,
    prior_confidence: float | None = None,
    prior_state: str | None = None,
    lock_duration_sec: float | None = None,
    cal_a: float = SPO2_CAL_A,
    cal_b: float = SPO2_CAL_B,
    cal_c: float = SPO2_CAL_C,
    calibration_table: list[tuple[float, float, float]] | None = None,
    max_roc_per_sec: float = SPO2_MAX_ROC_PCT_PER_SEC,
) -> dict:
    """
    Beat-by-beat ratio-of-ratios SpO2 estimator with RED/IR alignment
    validation, adaptive pulse selection, R-value stability scoring, and a
    hysteresis-based signal-lock state machine.

    Classic pulse-oximetry: R = (AC_red / DC_red) / (AC_ir / DC_ir). R
    correlates near-linearly with arterial oxygen saturation and is mapped
    through an empirical calibration curve (see `_spo2_calibrate`).

    Parameters
    ----------
    ir, red : array-like raw sample buffers, same length.
    fs : sampling rate in Hz.
    sub_window_seconds : sub-window length used only by the short-buffer
        fallback method and for the reported `effective_windows` estimate.
    prior_spo2, prior_confidence, prior_state, lock_duration_sec :
        Optional explicit state for callers that want to own SpO2/lock state
        themselves (e.g. multi-sensor deployments) instead of relying on the
        module-level `_spo2_state`. If **all** of these are left as `None`
        (the original calling convention), state is read from and written
        back to `_spo2_state` automatically, exactly as in the original
        stateless-per-call API — existing callers require no changes.
    cal_a, cal_b, cal_c : override the quadratic calibration coefficients
        (SpO2 = cal_a + cal_b * R + cal_c * R^2). Pass `cal_c=0.0` to
        recover a pure linear curve if desired.
    calibration_table : optional full override, see `_spo2_calibrate`.
    max_roc_per_sec : ceiling, in %/second, on how fast the published SpO2
        value may move once locked (a safety clamp, not a physiological
        desaturation-kinetics model — see `SPO2_MAX_ROC_PCT_PER_SEC`).

    Returns
    -------
    dict with (existing keys): spo2, confidence, r_value, windows_used,
    perfusion_index, window_quality, beat_quality, ratio_quality,
    coverage_quality, effective_beats, effective_windows, spo2_confidence,
    calibration_region; plus (new additive keys): r_stability_score, state,
    lock_duration_sec.
    """
    ir = _as_float_array(ir)
    red = _as_float_array(red)

    # Decide whether this call manages state internally (module-level) or
    # the caller is supplying/expecting to own it explicitly.
    use_internal_state = (
        prior_spo2 is None and prior_confidence is None
        and prior_state is None and lock_duration_sec is None
    )
    if use_internal_state:
        prior_spo2 = _spo2_state["last_spo2"]
        prior_confidence = _spo2_state["last_confidence"]
        prior_state = _spo2_state["state"]
        lock_duration_sec = _spo2_state["lock_duration_sec"]
    else:
        prior_state = prior_state if prior_state is not None else "SEARCHING"
        lock_duration_sec = lock_duration_sec if lock_duration_sec is not None else 0.0
        prior_confidence = prior_confidence if prior_confidence is not None else 0.0

    min_len = int(fs * sub_window_seconds) * 2
    if ir.size < min_len or red.size < min_len or ir.size != red.size:
        result = _spo2_empty_result(prior_spo2, prior_confidence, prior_state, lock_duration_sec)
        if use_internal_state:
            _spo2_state["state"] = result["state"]
            _spo2_state["lock_duration_sec"] = result["lock_duration_sec"]
        return result

    buffer_duration = ir.size / fs

    # --- Shared context: motion score and band-passed / DC-tracked channels ---
    motion_score = _motion_artifact_score(ir)
    filtered_ir = bandpass_filter(ir, fs)
    filtered_red = bandpass_filter(red, fs)
    dc_ir_signal = _lowpass_dc(ir, fs)
    dc_red_signal = _lowpass_dc(red, fs)

    # --- Beat detection & morphology scoring on the IR channel (shared with HR) ---
    peaks_ir, props_ir = _detect_peaks(filtered_ir, fs, return_properties=True)
    beat_confidences_ir = (
        _score_beats(peaks_ir, props_ir, fs)["beat_confidences"]
        if peaks_ir.size > 0 else np.array([])
    )

    search_half = max(int(fs * MIN_PEAK_WIDTH_SEC / 2), 1)
    align_max_samples = max(int(round(fs * IR_RED_PEAK_ALIGNMENT_MAX_SEC)), 1)
    left_bases_ir = props_ir.get("left_bases", peaks_ir).astype(int) if peaks_ir.size else peaks_ir
    right_bases_ir = props_ir.get("right_bases", peaks_ir).astype(int) if peaks_ir.size else peaks_ir

    raw_pulses: list[dict] = []
    n_alignment_rejected = 0

    for i, pk_ir in enumerate(peaks_ir):
        bc = float(beat_confidences_ir[i]) if i < beat_confidences_ir.size else 0.0
        if bc < SPO2_BEAT_CONFIDENCE_MIN:
            continue

        # Locate the matching RED peak within a physiologically small search
        # window around the IR peak.
        lo = max(pk_ir - search_half, 0)
        hi = min(pk_ir + search_half, filtered_red.size - 1)
        if lo >= hi:
            continue
        pk_red = int(np.argmax(filtered_red[lo : hi + 1])) + lo

        # --- RED/IR peak-alignment validation (motion-robustness improvement) ---
        # A genuine shared arterial pulse produces near-simultaneous systolic
        # peaks in both wavelengths; a larger offset means the "matched" RED
        # peak is likely a different event (commonly a motion artifact that
        # perturbed one channel more than the other) and would silently bias R.
        if abs(pk_red - pk_ir) > align_max_samples:
            n_alignment_rejected += 1
            continue

        lb = int(left_bases_ir[i])
        rb = int(min(right_bases_ir[i], filtered_ir.size - 1))
        if lb >= rb:
            continue

        ir_win = filtered_ir[lb : rb + 1]
        red_win = filtered_red[lb : rb + 1]
        if ir_win.size == 0 or red_win.size == 0:
            continue

        # Peak-to-trough AC amplitude over the *same* time window in both
        # channels (prevents asymmetric-window bias in R), and a time-aligned
        # low-pass DC estimate for each channel at its own peak location.
        #
        # Review improvement: the peak sample and trough sample are each read
        # via `_local_robust_extremum` (a small 3-tap local average) instead
        # of a single raw sample. R is a ratio of two such amplitudes, so a
        # single noisy ADC sample at either channel's peak or trough directly
        # perturbs the SpO2 estimate; averaging a couple of samples around
        # each extremum (without shifting *where* the extremum is taken from,
        # and without touching the DC tracker or peak timing at all) reduces
        # that sensitivity at negligible cost to genuine amplitude fidelity
        # (pulse curvature over 1-2 samples at 25-100 Hz is negligible next
        # to an 80-350 ms pulse width).
        ir_trough_idx = lb + int(np.argmin(ir_win))
        red_trough_idx = lb + int(np.argmin(red_win))
        ir_peak_val = _local_robust_extremum(filtered_ir, int(pk_ir), 1)
        ir_trough_val = _local_robust_extremum(filtered_ir, ir_trough_idx, 1)
        red_peak_val = _local_robust_extremum(filtered_red, int(pk_red), 1)
        red_trough_val = _local_robust_extremum(filtered_red, red_trough_idx, 1)
        ac_ir = float(ir_peak_val - ir_trough_val)
        ac_red = float(red_peak_val - red_trough_val)
        dc_ir = float(dc_ir_signal[pk_ir])
        dc_red = float(dc_red_signal[pk_red])

        if dc_ir <= 0 or dc_red <= 0 or ac_ir <= 0 or ac_red <= 0:
            continue

        pi_ir = (ac_ir / dc_ir) * 100.0
        pi_red = (ac_red / dc_red) * 100.0
        if not (FINGER_PI_MIN_PCT <= pi_ir <= FINGER_PI_MAX_PCT):
            continue
        if not (FINGER_PI_MIN_PCT <= pi_red <= FINGER_PI_MAX_PCT):
            continue

        r_beat = (ac_red / dc_red) / (ac_ir / dc_ir)
        if not (SPO2_R_MIN <= r_beat <= SPO2_R_MAX):
            continue

        raw_pulses.append({
            "r": r_beat,
            "pi": (pi_ir + pi_red) / 2.0,
            "beat_conf": bc,
            "alignment_offset_sec": abs(pk_red - pk_ir) / fs,
        })

    # --- Decide: beat-level pipeline, or fall back to window-std method ---
    if len(raw_pulses) < SPO2_MIN_SELECTED_PULSES:
        fb = _spo2_fallback_window_method(ir, red, fs, sub_window_seconds, motion_score)
        if not fb["ok"]:
            result = _spo2_empty_result(prior_spo2, prior_confidence, prior_state, lock_duration_sec)
            if use_internal_state:
                _spo2_state["state"] = result["state"]
                _spo2_state["lock_duration_sec"] = result["lock_duration_sec"]
            return result

        r_median = fb["r_median"]
        mean_pi = fb["mean_pi"]
        ratio_quality = fb["ratio_quality"]
        r_stability_score = fb["r_stability_score"]
        window_quality = fb["window_quality"]
        mean_beat_quality = fb["beat_quality"]
        coverage_quality = fb["coverage_quality"]
        effective_beats = fb["effective_beats"]
        effective_windows = fb["effective_windows"]
    else:
        # --- Hampel-style outlier rejection on beat-level R values ---
        r_arr = np.array([p["r"] for p in raw_pulses])
        r_median_raw = float(np.median(r_arr))
        r_mad = float(np.median(np.abs(r_arr - r_median_raw))) + 1e-9
        inlier_pulses = [p for p in raw_pulses if abs(p["r"] - r_median_raw) <= 3.0 * r_mad]
        if not inlier_pulses:
            inlier_pulses = raw_pulses

        # --- Adaptive pulse-selection (no fixed "top N%") ---
        # A composite per-pulse quality blends beat morphology confidence,
        # global motion score, and perfusion adequacy. The accept threshold
        # tracks the *current window's* quality distribution rather than
        # always keeping a fixed fraction, so a uniformly clean window keeps
        # nearly all beats while a mixed window still enforces a meaningful bar.
        for p in inlier_pulses:
            p["quality"] = p["beat_conf"] * motion_score * float(np.clip(p["pi"] / 2.0, 0.1, 1.0))

        qualities = np.array([p["quality"] for p in inlier_pulses])
        median_quality = float(np.median(qualities))
        max_quality = float(np.max(qualities))
        select_threshold = max(median_quality, SPO2_ADAPTIVE_SELECTION_MAX_FRACTION * max_quality)
        selected_pulses = [p for p in inlier_pulses if p["quality"] >= select_threshold]
        if len(selected_pulses) < SPO2_MIN_SELECTED_PULSES:
            # Not enough pulses clear the adaptive bar; fall back to keeping
            # the best SPO2_MIN_SELECTED_PULSES available rather than failing
            # outright on a marginal-but-not-empty window.
            selected_pulses = sorted(inlier_pulses, key=lambda p: p["quality"], reverse=True)
            selected_pulses = selected_pulses[: max(SPO2_MIN_SELECTED_PULSES, 1)]

        sel_r = np.array([p["r"] for p in selected_pulses])
        sel_w = np.array([p["quality"] for p in selected_pulses])
        sel_pi = np.array([p["pi"] for p in selected_pulses])
        sel_bc = np.array([p["beat_conf"] for p in selected_pulses])

        r_median = _weighted_median(sel_r, sel_w)
        mean_pi = float(np.mean(sel_pi))
        mean_beat_quality = float(np.mean(sel_bc))

        # --- R-value stability: beat-to-beat R agreement, its own sub-score ---
        r_cv = float(np.std(sel_r) / (r_median + 1e-9)) if sel_r.size > 1 else 1.0
        ratio_quality = float(np.clip(1.0 - r_cv * 3.0, 0.0, 1.0))
        r_stability_score = float(np.clip(1.0 - r_cv / SPO2_R_STABILITY_CV_REF, 0.0, 1.0))

        # Review improvement (performance): reuse the IR filtered signal and
        # peak set already computed above instead of calling the public
        # compute_signal_quality(ir, fs) (which would redo bandpass_filter,
        # _detect_peaks, and the spectral FFT on the same buffer). Output is
        # identical to the previous `compute_signal_quality(ir, fs)["score"]`.
        window_quality = (
            _compute_signal_quality_impl(ir, fs, filtered=filtered_ir, peaks=peaks_ir)["score"] / 100.0
        )
        coverage_quality = float(np.clip(len(selected_pulses) / max(peaks_ir.size, 1), 0.0, 1.0))
        effective_beats = len(selected_pulses)
        effective_windows = effective_beats

    # --- Calibration (pluggable; see _spo2_calibrate / set_spo2_calibration_table) ---
    spo2_raw = _spo2_calibrate(r_median, cal_a=cal_a, cal_b=cal_b, cal_c=cal_c, calibration_table=calibration_table)
    # Interim self-calibration offset (see `calibrate_spo2_baseline` /
    # `SPO2_SELF_CAL_OFFSET` above). Zero by default -- a no-op unless the
    # caller has explicitly anchored this sensor/wrist placement against a
    # known reference. Applied before the physiological clip so it can't
    # push a reading outside the plausible 70-100% band.
    spo2_raw += SPO2_SELF_CAL_OFFSET
    spo2_raw = float(np.clip(spo2_raw, SPO2_PHYSIO_MIN, SPO2_PHYSIO_MAX))
    active_table = calibration_table if calibration_table is not None else _active_calibration_table
    # Region is now classified from the calibrated *output* rather than an
    # R breakpoint, since the calibration curve is a single smooth quadratic
    # with no segment boundary — "low" simply flags outputs deep enough into
    # the desaturation range that they're extrapolating past where most
    # resting-subject calibration data lives.
    calibration_region = "table" if active_table else ("low" if spo2_raw < 90.0 else "normal")

    # --- Composite confidence ---
    # Weights are chosen so beat quality and R-ratio agreement (the two most
    # direct evidence signals that we're looking at a real, consistent
    # arterial pulse) dominate; R stability, window-level SQI, and motion
    # each contribute meaningfully; perfusion adequacy and beat coverage act
    # as smaller corroborating terms rather than primary discriminators.
    perfusion_subscore = float(np.clip(mean_pi / 2.0, 0.0, 1.0))
    confidence = float(np.clip(
        0.25 * mean_beat_quality
        + 0.20 * ratio_quality
        + 0.15 * r_stability_score
        + 0.15 * window_quality
        + 0.15 * motion_score
        + 0.05 * perfusion_subscore
        + 0.05 * coverage_quality,
        0.0, 1.0,
    ))

    # --- Hysteresis-based signal-lock state machine ---
    # Separate ON/OFF confidence thresholds (0.75 / 0.45) prevent chattering
    # across a single noisy boundary value; sustained confidence (not a
    # single good window) is required to transition into a trusted lock.
    if prior_state in (None, "SEARCHING"):
        if confidence >= SPO2_LOCK_CONFIDENCE_ON:
            lock_duration_sec += buffer_duration
        else:
            lock_duration_sec = 0.0
        new_state = "LOCKED" if lock_duration_sec >= SPO2_LOCK_DURATION_REQUIRED_SEC else "SEARCHING"
    elif prior_state in ("LOCKED", "TRACKING"):
        if confidence >= SPO2_LOCK_CONFIDENCE_OFF:
            new_state = "TRACKING"
            lock_duration_sec += buffer_duration
        else:
            new_state = "LOST"
            lock_duration_sec = 0.0
    elif prior_state == "LOST":
        if confidence >= SPO2_LOCK_CONFIDENCE_ON:
            lock_duration_sec += buffer_duration
        else:
            lock_duration_sec = 0.0
        new_state = "LOCKED" if lock_duration_sec >= SPO2_LOCK_DURATION_REQUIRED_SEC else "SEARCHING"
    else:
        new_state = "SEARCHING"
        lock_duration_sec = 0.0

    # --- Motion freeze: hold last trusted value during severe motion ---
    # This takes priority over the lock state — even a currently-TRACKING
    # estimate should not be updated with a measurement dominated by motion.
    if motion_score < SPO2_MOTION_FREEZE_THRESHOLD and prior_spo2 is not None:
        spo2_out = prior_spo2
        confidence_out = prior_confidence * 0.5
    elif new_state in ("LOCKED", "TRACKING") and prior_spo2 is not None:
        # Rate-limit (per-second ceiling, plus the original fixed per-update
        # jump clamp as an additional safety bound) and confidence-scaled
        # exponential smoothing.
        max_delta = max(max_roc_per_sec * buffer_duration, 1e-6)
        clamped = float(np.clip(spo2_raw, prior_spo2 - max_delta, prior_spo2 + max_delta))
        clamped = float(np.clip(
            clamped, prior_spo2 - SPO2_MAX_JUMP_PER_UPDATE, prior_spo2 + SPO2_MAX_JUMP_PER_UPDATE
        ))
        # Clip range (0.05-0.28) keeps the effective time constant inside the
        # ~3.3-19.5 s band described at SPO2_SMOOTHING_ALPHA's definition —
        # even a maximally-confident update can't snap the display to a new
        # value in one step, matching how commercial wearables visibly ease
        # into a new SpO2 reading rather than jumping to it.
        alpha = float(np.clip(SPO2_SMOOTHING_ALPHA * (confidence / 0.5), 0.05, 0.28))
        spo2_out = alpha * clamped + (1.0 - alpha) * prior_spo2
        confidence_out = confidence
    elif prior_spo2 is None:
        # No trusted prior yet — publish the raw estimate so the caller has
        # *something* to show, but confidence reflects that it is not yet locked.
        spo2_out = spo2_raw
        confidence_out = confidence
    else:
        # Not currently locked/tracking and a prior trusted value exists:
        # hold the prior rather than publishing an unlocked reading.
        spo2_out = prior_spo2
        confidence_out = confidence * 0.5

    spo2_out = float(np.clip(spo2_out, SPO2_PHYSIO_MIN, SPO2_PHYSIO_MAX))

    if use_internal_state:
        _spo2_state["state"] = new_state
        _spo2_state["lock_duration_sec"] = lock_duration_sec
        if new_state in ("LOCKED", "TRACKING") or prior_spo2 is None:
            _spo2_state["last_spo2"] = spo2_out
            _spo2_state["last_confidence"] = confidence_out

    return {
        "spo2": round(spo2_out, 1),
        "confidence": round(confidence_out, 3),
        "r_value": round(r_median, 4),
        "windows_used": effective_windows,
        "perfusion_index": round(mean_pi, 4),
        "window_quality": round(window_quality, 3),
        "beat_quality": round(mean_beat_quality, 3),
        "ratio_quality": round(ratio_quality, 3),
        "coverage_quality": round(coverage_quality, 3),
        "effective_beats": effective_beats,
        "effective_windows": effective_windows,
        "spo2_confidence": round(confidence_out, 3),
        "calibration_region": calibration_region,
        # new additive diagnostics
        "r_stability_score": round(r_stability_score, 3),
        "state": new_state,
        "lock_duration_sec": round(lock_duration_sec, 2),
    }


# ---------------------------------------------------------------------------
# Heart-rate variability (HRV)
# ---------------------------------------------------------------------------

def compute_hrv_metrics(rr_intervals_ms) -> dict:
    """
    Standard time-domain HRV metrics computed from beat-to-beat (RR)
    intervals, using the conventional definitions from HRV literature
    (Task Force of ESC/NASPE, 1996; Shaffer & Ginsberg, 2017).

    Metrics:
      - mean_rr  : mean RR interval (ms)
      - sdnn     : SD of NN intervals (ms) — overall variability
      - rmssd    : root mean square of successive RR differences (ms) —
                   parasympathetically-mediated short-term variability
      - pnn50    : % of successive diffs > 50 ms — parasympathetic proxy
      - n_intervals: number of intervals used in computation
      - median_rr   : median RR (ms) — more robust than mean for skewed
                      distributions containing residual ectopic beats
      - cvrr        : RMSSD / mean_rr × 100 % — coefficient of variation
                      of RR; a normalized HRV measure independent of mean
                      heart rate (Kleiger et al. 2005; Billman 2011)
      - hrv_confidence: composite 0-1 confidence that these metrics are
                      meaningful given the available interval count and
                      how much of it looked artifact-like
      - artifact_pct: percentage of input intervals either outside
                      physiological bounds or flagged as likely-artifact

    Acceptance policy (revised): only intervals outside hard
    physiological bounds (40-200 BPM) are discarded before computing
    anything. A previous revision additionally required each interval to
    be within 25% of the local median before it counted toward the
    metrics — a much stricter bar than the interval-count requirement,
    and one that could suppress every metric to `None` on a window with
    mostly-good beats plus a couple of genuinely irregular (but real)
    ones. HRV is expected to vary; "how many intervals do we have" and
    "how similar are they to each other" are different questions, and
    conflating them meant HRV was hidden far more often than the
    underlying signal actually warranted. Now: if at least
    HRV_MIN_CLEAN_INTERVALS physiologically-valid intervals are present,
    metrics are always computed and returned. The old deviation-from-
    median check still runs, but only to inform `hrv_confidence` /
    `artifact_pct` — a window with several off-median intervals gets
    lower confidence, not a `None` result.

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

    # --- Step 1: physiological bounds filter (the only hard exclusion) ---
    physio_mask = (rr_all >= MIN_RR_SEC * 1000.0) & (rr_all <= MAX_RR_SEC * 1000.0)
    rr_clean = rr_all[physio_mask]
    n_clean = int(rr_clean.size)

    # --- Step 2: deviation-from-median flagging (informational only) ---
    # No longer removes intervals from the metrics computation — see
    # "Acceptance policy" above. Feeds artifact_pct / hrv_confidence.
    if n_clean >= 2:
        local_median = float(np.median(rr_clean))
        artifact_mask = (
            np.abs(rr_clean - local_median) / (local_median + 1e-9) > HRV_ARTIFACT_RR_TOLERANCE
        )
        n_artifacts_total = int(np.sum(~physio_mask)) + int(np.sum(artifact_mask))
    else:
        n_artifacts_total = int(np.sum(~physio_mask))
    artifact_pct = round(float(n_artifacts_total / n_input * 100.0), 1) if n_input else 100.0

    if n_clean < HRV_MIN_CLEAN_INTERVALS:
        null_result["artifact_pct"] = artifact_pct
        return null_result

    # --- Core metrics (computed on all physio-valid intervals) ---
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
    # Component 1: fraction of input intervals that were physio-valid
    # (i.e. actually used).
    clean_fraction = float(np.clip(n_clean / max(n_input, 1), 0.0, 1.0))
    # Component 2: inverse artifact rate (now purely informational, per
    # the acceptance-policy change above, but still a meaningful quality
    # signal — a window with a high deviation-from-median rate is less
    # trustworthy even though its intervals weren't discarded).
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
        # additional metrics
        "median_rr": round(median_rr, 2),
        "cvrr": round(cvrr, 2),
        "hrv_confidence": round(hrv_confidence, 3),
        "artifact_pct": artifact_pct,
    }



# ---------------------------------------------------------------------------
# Sensor diagnostics
# ---------------------------------------------------------------------------

def classify_sensor_status(
    ir, fs: float | None = None, sqi_score: float | None = None
) -> str:
    """
    Classify the raw IR channel into a coarse sensor-health category so the
    dashboard/firmware can distinguish "no signal" from "signal present but
    poorly conditioned" without inspecting every diagnostic field.

    Returns one of: "LOW_SIGNAL", "GOOD", "HIGH_SIGNAL", "SATURATED",
    "POOR_SIGNAL".

    Precedence: saturation is checked first because a clipped signal is
    unusable regardless of its average DC level; then low/high DC bands
    flag a fit that's technically producing a signal but is either too
    weak (loose contact, low perfusion) or over-driven (too much LED
    current / pressure) to trust for downstream estimation.

    Review fix: DC level and clipping alone cannot tell "signal present"
    from "signal present *and usable*" — a DC-plausible, non-clipped signal
    can still be dominated by motion/noise and produce a low Signal Quality
    Index (SQI) while this function used to report it as "GOOD". To catch
    that case without forcing every caller to pay for an extra SQI
    computation, this now accepts an optional quality signal:

      - Pass `sqi_score` directly (0-100, e.g. `compute_signal_quality(ir,
        fs)["score"]`) if you already computed it — this is the cheap path
        and what `PPGProcessor` does, since it computes SQI every call anyway.
      - Pass `fs` (and omit `sqi_score`) to have this function compute SQI
        itself from `ir`.
      - Pass neither to get the original DC/clipping-only behavior exactly
        as before (fully backward compatible for existing callers/tests).

    When a DC-plausible, non-saturated signal's SQI falls below
    `SENSOR_STATUS_MIN_SQI`, "POOR_SIGNAL" is returned instead of "GOOD".
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

    # DC level looks like tissue and isn't saturated — but that alone
    # doesn't mean the waveform is usable. Check SQI if we have (or can get) it.
    if sqi_score is None and fs is not None:
        sqi_score = compute_signal_quality(ir, fs)["score"]
    if sqi_score is not None and sqi_score < SENSOR_STATUS_MIN_SQI:
        return "POOR_SIGNAL"

    return "GOOD"
