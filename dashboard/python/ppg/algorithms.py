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
counts) and returns plain dicts/floats — no hidden state, easy to unit test.
"""

from __future__ import annotations

import numpy as np
from scipy.signal import butter, filtfilt, find_peaks

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

# --- SpO2 calibration ---
# Empirical linear calibration of the form SpO2 = A - B * R, in the same
# family as calibration curves published by Maxim/Analog Devices app notes
# for the MAX30100/30102. This is NOT clinically calibrated against a
# co-oximeter reference — treat as a rough, honest estimate only.
SPO2_CAL_A = 110.0
SPO2_CAL_B = 25.0
SPO2_PHYSIO_MIN = 70.0
SPO2_PHYSIO_MAX = 100.0
# R (ratio-of-ratios) values outside this range indicate the estimate is
# almost certainly driven by noise rather than real arterial pulsation.
SPO2_R_MIN = 0.2
SPO2_R_MAX = 2.0

# --- Dominant cardiac frequency check (Phase 3) ---
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

# --- Sensor status classification (Phase 4) ---
# DC bands used to flag a weak-but-valid signal or an over-driven one
# before it actually clips, giving early warning of a poor sensor fit.
SENSOR_STATUS_LOW_DC = FINGER_DC_MIN
SENSOR_STATUS_HIGH_DC = ADC_MAX_VALUE * 0.85
SENSOR_STATUS_CLIPPING_FRACTION = 0.01  # >1% of samples pinned at the rail


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
    """
    ir = _as_float_array(ir)
    if ir.size < int(fs * 3):  # need a few seconds to resolve ~1 Hz components
        return None, 0.0

    filtered = bandpass_filter(ir, fs)
    windowed = filtered * np.hanning(filtered.size)
    spectrum = np.abs(np.fft.rfft(windowed))
    freqs = np.fft.rfftfreq(filtered.size, d=1.0 / fs)
    power = spectrum ** 2
    total_power = float(np.sum(power)) + 1e-12

    cardiac_mask = (freqs >= CARDIAC_FREQ_MIN_HZ) & (freqs <= CARDIAC_FREQ_MAX_HZ)
    if not np.any(cardiac_mask):
        return None, 0.0

    cardiac_power = power[cardiac_mask]
    cardiac_freqs = freqs[cardiac_mask]
    dominant_freq = float(cardiac_freqs[int(np.argmax(cardiac_power))])
    cardiac_power_ratio = float(np.sum(cardiac_power) / total_power)
    return dominant_freq, cardiac_power_ratio


# ---------------------------------------------------------------------------
# Finger detection
# ---------------------------------------------------------------------------

def assess_finger_presence(ir, fs: float = 50.0) -> dict:
    """
    Multi-criteria finger-on-sensor detector.

    A single DC threshold is easily fooled by ambient light leaking into
    the photodiode or by an object other than a finger resting on the
    sensor. Instead we combine several independent signals and require
    the majority to agree, producing a continuous confidence score rather
    than a brittle yes/no cutoff.

    Criteria (each contributes a weighted vote to `confidence`):
      - DC level within the plausible tissue-contact range
      - not saturating the ADC (motion/pressure can slam the signal to rail)
      - pulsatile AC amplitude is large enough to be a real pulse, not noise
      - AC/DC ratio falls within the physiological perfusion-index range
      - DC level is stable over the recent window (a finger being placed/
        removed, or ambient light flooding the sensor, causes large swings)

    Returns
    -------
    dict with keys: detected (bool), confidence (0-1 float), dc_level,
    ac_amplitude, ac_dc_ratio, saturated (bool), stability (0-1 float),
    reason (str, human-readable explanation when not detected).
    """
    ir = _as_float_array(ir)
    min_samples = max(int(FINGER_MIN_STABLE_SECONDS * fs), 20)
    if ir.size < min_samples:
        return {
            "detected": False, "confidence": 0.0, "dc_level": 0.0,
            "ac_amplitude": 0.0, "ac_dc_ratio": 0.0, "saturated": False,
            "stability": 0.0, "reason": "insufficient_samples",
        }

    dc_level = float(np.mean(ir))
    ac_amplitude = float(np.std(ir - dc_level))
    ac_dc_ratio = ac_amplitude / (dc_level + 1e-9)
    saturated = bool(np.max(ir) >= ADC_MAX_VALUE * SATURATION_FRACTION)

    # Stability: split the buffer into ~0.5 s sub-windows and look at how
    # much the sub-window means wander relative to the overall DC level.
    # A finger resting steadily on the sensor gives a near-flat DC trend;
    # ambient light changes or a finger sliding on/off cause large jumps.
    sub_window = max(int(fs * 0.5), 1)
    n_sub = ir.size // sub_window
    if n_sub >= 2:
        sub_means = ir[: n_sub * sub_window].reshape(n_sub, sub_window).mean(axis=1)
        relative_drift = float(np.std(sub_means) / (dc_level + 1e-9))
        stability = float(np.clip(1.0 - relative_drift * 20.0, 0.0, 1.0))
    else:
        stability = 0.5  # not enough sub-windows to judge; stay neutral

    # Dominant cardiac frequency (Phase 3): rejects periodic non-cardiac
    # noise (mains coupling, rhythmic taps) that could otherwise satisfy
    # the amplitude/ratio checks above without a real pulse behind it.
    dominant_freq, cardiac_power_ratio = dominant_cardiac_frequency(ir, fs)
    has_cardiac_frequency = (
        dominant_freq is not None and cardiac_power_ratio >= CARDIAC_POWER_RATIO_MIN
    )

    checks = {
        "dc_in_range": FINGER_DC_MIN <= dc_level <= FINGER_DC_MAX,
        "not_saturated": not saturated,
        "sufficient_ac": ac_amplitude >= FINGER_MIN_AC_COUNTS,
        "plausible_ratio": FINGER_AC_DC_RATIO_MIN <= ac_dc_ratio <= FINGER_AC_DC_RATIO_MAX,
        "stable": stability > 0.3,
        "has_cardiac_frequency": has_cardiac_frequency,
    }
    # Weights sum to 1.0. DC range/saturation confirm "something is on the
    # sensor"; AC/ratio/cardiac-frequency confirm "and it's pulsing like
    # real tissue", which is why the cardiac-frequency check carries as
    # much weight as DC range.
    weights = {
        "dc_in_range": 0.25, "not_saturated": 0.10, "sufficient_ac": 0.20,
        "plausible_ratio": 0.10, "stable": 0.10, "has_cardiac_frequency": 0.25,
    }
    confidence = sum(weights[k] for k, passed in checks.items() if passed)

    # Hard requirements even at high confidence: no tissue-range DC, an
    # outright saturated sensor, or the absence of any real cardiac-band
    # spectral peak should never be reported as "detected" — these three
    # are structural failures that no amount of amplitude/ratio agreement
    # should be able to outvote.
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
        # --- additive diagnostics (Phase 3) ---
        "dominant_frequency_hz": round(dominant_freq, 3) if dominant_freq is not None else None,
        "cardiac_power_ratio": round(cardiac_power_ratio, 3),
    }


# ---------------------------------------------------------------------------
# Signal Quality Index (SQI)
# ---------------------------------------------------------------------------

def compute_signal_quality(ir, fs: float = 50.0) -> dict:
    """
    Composite Signal Quality Index (SQI), 0-100.

    Combines several independent quality indicators used in PPG-quality
    literature (Elgendi 2016; Orphanidou et al. 2015):
      - SNR: cardiac-band power vs. out-of-band residual power
      - clipping: fraction of samples pinned near the ADC rail
      - motion artifacts: large sample-to-sample jumps (derivative outliers)
      - pulse consistency: coefficient of variation of detected RR intervals
      - amplitude: pulsatile AC amplitude relative to the minimum needed
        for reliable peak detection

    Returns a dict with the composite `score` plus the individual
    sub-scores (each 0-1) for debugging/telemetry.
    """
    ir = _as_float_array(ir)
    if ir.size < int(fs * 2):
        return {"score": 0.0, "snr_db": None, "clipping_fraction": None,
                "motion_score": None, "pulse_consistency": None, "amplitude_score": None}

    filtered = bandpass_filter(ir, fs)
    dc_level = float(np.mean(ir))

    # --- SNR: cardiac-band signal power vs. residual (out-of-band) power ---
    residual = (ir - dc_level) - filtered
    signal_power = float(np.var(filtered))
    noise_power = float(np.var(residual)) + 1e-9
    snr_db = 10.0 * np.log10(signal_power / noise_power) if signal_power > 0 else -60.0
    # Map ~0-20 dB onto a 0-1 quality sub-score (below 0 dB is unusable,
    # above 20 dB is excellent for a wrist/finger PPG).
    snr_score = float(np.clip(snr_db / 20.0, 0.0, 1.0))

    # --- Clipping: fraction of samples pinned at the ADC ceiling/floor ---
    clip_hi = ADC_MAX_VALUE * SATURATION_FRACTION
    clipping_fraction = float(np.mean((ir >= clip_hi) | (ir <= 0)))
    clipping_score = float(np.clip(1.0 - clipping_fraction * 5.0, 0.0, 1.0))

    # --- Motion artifacts (see `_motion_artifact_score` docstring) ---
    motion_score = _motion_artifact_score(ir)

    # --- Pulse consistency: regular RR intervals indicate a clean,
    # trustworthy pulsatile signal; irregular intervals usually mean the
    # peak detector is tracking noise rather than real beats.
    peaks = _detect_peaks(filtered, fs)
    if peaks.size >= 3:
        rr = np.diff(peaks) / fs
        valid_rr = rr[(rr >= MIN_RR_SEC) & (rr <= MAX_RR_SEC)]
        if valid_rr.size >= 2:
            cv = float(np.std(valid_rr) / (np.mean(valid_rr) + 1e-9))
            pulse_consistency = float(np.clip(1.0 - cv * 2.0, 0.0, 1.0))
        else:
            pulse_consistency = 0.0
    else:
        pulse_consistency = 0.0

    # --- Amplitude: pulsatile swing relative to the minimum we trust ---
    ac_amplitude = float(np.std(filtered))
    amplitude_score = float(np.clip(ac_amplitude / (FINGER_MIN_AC_COUNTS * 4.0), 0.0, 1.0))

    # Weighted composite. SNR and pulse consistency are the most direct
    # indicators of "can we trust a heart-rate estimate from this window".
    score = (
        0.30 * snr_score
        + 0.15 * clipping_score
        + 0.15 * motion_score
        + 0.25 * pulse_consistency
        + 0.15 * amplitude_score
    ) * 100.0

    return {
        "score": round(float(np.clip(score, 0.0, 100.0)), 1),
        "snr_db": round(snr_db, 1),
        "clipping_fraction": round(clipping_fraction, 4),
        "motion_score": round(motion_score, 3),
        "pulse_consistency": round(pulse_consistency, 3),
        "amplitude_score": round(amplitude_score, 3),
    }


# ---------------------------------------------------------------------------
# Heart rate
# ---------------------------------------------------------------------------

def _detect_peaks(filtered_signal: np.ndarray, fs: float) -> np.ndarray:
    """
    Adaptive systolic-peak detector shared by HR estimation and SQI.

    Uses scipy.find_peaks with:
      - a minimum distance enforcing the fastest plausible heart rate
        (prevents double-counting the dicrotic notch as a separate beat)
      - a prominence threshold scaled to the signal's own amplitude
        (adaptive rather than a fixed count value, so it works across
        different perfusion levels / LED currents)
    """
    if filtered_signal.size < int(fs * 1.5):
        return np.array([], dtype=int)
    min_distance = max(int(fs * MIN_RR_SEC), 1)
    adaptive_prominence = max(np.std(filtered_signal) * 0.35, 1e-6)
    peaks, _ = find_peaks(filtered_signal, distance=min_distance, prominence=adaptive_prominence)
    return peaks


def estimate_heart_rate(ir, fs: float = 50.0) -> dict:
    """
    Robust heart-rate estimator.

    Pipeline: band-pass filter -> adaptive peak detection -> RR interval
    validation against physiological bounds -> outlier rejection via a
    median-based (Hampel-style) filter -> median RR -> BPM.

    Using the median (rather than the mean) of the RR intervals makes the
    estimate resistant to the occasional missed or spurious peak that
    motion artifacts tend to introduce.

    Returns
    -------
    dict with: heart_rate (float | None), rr_intervals_ms (list[float]),
    confidence (0-1 float), beats_detected (int).
    """
    ir = _as_float_array(ir)
    empty = {"heart_rate": None, "rr_intervals_ms": [], "confidence": 0.0, "beats_detected": 0}
    if ir.size < int(fs * 5):  # need a handful of seconds to see multiple beats
        return empty

    filtered = bandpass_filter(ir, fs)
    peaks = _detect_peaks(filtered, fs)
    if peaks.size < 3:  # need >=2 RR intervals to judge consistency at all
        return empty

    rr = np.diff(peaks) / fs  # seconds

    # Stage 1: reject RR intervals outside physiologically possible bounds.
    physio_mask = (rr >= MIN_RR_SEC) & (rr <= MAX_RR_SEC)
    rr = rr[physio_mask]
    if rr.size < 2:
        return empty

    # Stage 2: Hampel-style outlier rejection on the remaining intervals —
    # drop any RR more than 3 median-absolute-deviations from the median.
    # This catches missed beats (RR ~= 2x true) and extra/spurious peaks
    # (RR ~= 0.5x true) that survive the physiological bound check.
    median_rr = float(np.median(rr))
    mad_rr = float(np.median(np.abs(rr - median_rr))) + 1e-9
    inlier_mask = np.abs(rr - median_rr) <= 3 * mad_rr
    clean_rr = rr[inlier_mask]
    if clean_rr.size == 0:
        clean_rr = rr  # fall back rather than reporting nothing

    bpm = 60.0 / float(np.median(clean_rr))
    if not (MIN_BPM <= bpm <= MAX_BPM):
        return empty

    # Confidence blends: fraction of RR intervals retained as inliers, and
    # how tight the retained intervals are (low CV = consistent rhythm).
    retained_fraction = clean_rr.size / rr.size
    cv = float(np.std(clean_rr) / (np.mean(clean_rr) + 1e-9))
    regularity = float(np.clip(1.0 - cv * 2.0, 0.0, 1.0))
    beat_count_factor = float(np.clip(clean_rr.size / 5.0, 0.0, 1.0))  # more beats seen = more trust
    confidence = float(np.clip(
        0.4 * retained_fraction + 0.4 * regularity + 0.2 * beat_count_factor, 0.0, 1.0
    ))

    return {
        "heart_rate": round(bpm, 1),
        "rr_intervals_ms": [round(x * 1000.0, 1) for x in clean_rr],
        "confidence": round(confidence, 3),
        "beats_detected": int(peaks.size),
        # --- additive sub-metrics, exposing values already computed above
        # so the processor can build a fuller HR-quality breakdown without
        # recomputing anything ---
        "peak_quality": round(retained_fraction, 3),   # fraction of detected peaks that survived outlier rejection
        "rhythm_quality": round(regularity, 3),         # 1 - RR coefficient of variation, clipped to [0, 1]
    }


# ---------------------------------------------------------------------------
# SpO2 (ratio-of-ratios)
# ---------------------------------------------------------------------------

def estimate_spo2(ir, red, fs: float = 50.0, sub_window_seconds: float = 2.0) -> dict:
    """
    Ratio-of-ratios SpO2 estimator using rolling sub-windows.

    Classic pulse-oximetry theory: R = (AC_red / DC_red) / (AC_ir / DC_ir).
    R correlates near-linearly with arterial oxygen saturation over the
    clinically relevant range, and is conventionally mapped through an
    empirical calibration curve (SpO2 = A - B*R) rather than derived from
    first-principles optics, because real calibration requires a
    co-oximeter reference we don't have here.

    Rather than computing a single R from the whole buffer (sensitive to
    a single burst of motion), we compute R over several overlapping
    sub-windows and take the median, reporting confidence based on how
    consistent the sub-window estimates are with each other.
    """
    ir = _as_float_array(ir)
    red = _as_float_array(red)
    empty = {"spo2": None, "confidence": 0.0, "r_value": None, "windows_used": 0}

    min_len = int(fs * sub_window_seconds) * 2  # need at least 2 sub-windows
    if ir.size < min_len or red.size < min_len or ir.size != red.size:
        return empty

    window = int(fs * sub_window_seconds)
    step = window // 2  # 50% overlap for more sub-window estimates without needing a longer buffer
    r_values = []

    for start in range(0, ir.size - window + 1, step):
        ir_seg = ir[start:start + window]
        red_seg = red[start:start + window]

        dc_ir = float(np.mean(ir_seg))
        dc_red = float(np.mean(red_seg))
        if dc_ir <= 0 or dc_red <= 0:
            continue

        # AC amplitude via band-passed segment std (robust to baseline
        # wander within the sub-window); falls back to raw std if the
        # segment is too short for filtfilt.
        ac_ir = float(np.std(bandpass_filter(ir_seg, fs)))
        ac_red = float(np.std(bandpass_filter(red_seg, fs)))
        if ac_ir <= 0 or ac_red <= 0:
            continue

        r = (ac_red / dc_red) / (ac_ir / dc_ir)
        if SPO2_R_MIN <= r <= SPO2_R_MAX:
            r_values.append(r)

    if not r_values:
        return empty

    r_values = np.array(r_values)
    r_median = float(np.median(r_values))
    spo2 = SPO2_CAL_A - SPO2_CAL_B * r_median
    spo2 = float(np.clip(spo2, SPO2_PHYSIO_MIN, SPO2_PHYSIO_MAX))

    # Confidence: how tightly the sub-window R estimates agree, plus how
    # many sub-windows contributed (more windows -> more trustworthy median).
    r_cv = float(np.std(r_values) / (r_median + 1e-9)) if r_values.size > 1 else 1.0
    consistency = float(np.clip(1.0 - r_cv * 3.0, 0.0, 1.0))
    coverage = float(np.clip(r_values.size / 4.0, 0.0, 1.0))
    confidence = float(np.clip(0.7 * consistency + 0.3 * coverage, 0.0, 1.0))

    return {
        "spo2": round(spo2, 1),
        "confidence": round(confidence, 3),
        "r_value": round(r_median, 4),
        "windows_used": int(r_values.size),
    }


# ---------------------------------------------------------------------------
# Heart-rate variability (HRV) — Phase 2
# ---------------------------------------------------------------------------

def compute_hrv_metrics(rr_intervals_ms) -> dict:
    """
    Standard time-domain HRV metrics computed from beat-to-beat (RR)
    intervals, using the conventional definitions from HRV literature
    (Task Force of ESC/NASPE, 1996; Shaffer & Ginsberg, 2017):

      - mean_rr : mean RR interval (ms)
      - sdnn    : standard deviation of NN (normal-to-normal / RR) intervals
                  (ms) — overall variability across the window.
      - rmssd   : root mean square of successive RR differences (ms) —
                  sqrt(mean((RR[i+1] - RR[i])^2)) — reflects short-term,
                  parasympathetically-mediated variability and is the
                  metric least sensitive to trend/artifact.
      - pnn50   : percentage of successive RR differences that exceed
                  50 ms — another parasympathetic-activity proxy.

    Caveat: clinically-referenced HRV norms are usually computed over
    ~5 minute windows. Over our short (~10 s) rolling buffer these values
    are internally consistent and useful for relative/trend comparisons,
    but should not be compared directly to published 5-minute norms.

    Returns None for any metric that doesn't have enough RR intervals to
    be computed rather than a misleading placeholder value.
    """
    rr = np.asarray(rr_intervals_ms, dtype=np.float64)
    n = int(rr.size)

    if n < 2:
        return {"rmssd": None, "sdnn": None, "mean_rr": None, "pnn50": None, "n_intervals": n}

    mean_rr = float(np.mean(rr))
    sdnn = float(np.std(rr, ddof=1))  # ddof=1: sample (not population) standard deviation

    if n < 3:
        # Need at least 2 successive differences (3 RR intervals) for
        # RMSSD/pNN50 to mean anything.
        return {
            "rmssd": None, "sdnn": round(sdnn, 2), "mean_rr": round(mean_rr, 2),
            "pnn50": None, "n_intervals": n,
        }

    successive_diffs = np.diff(rr)
    rmssd = float(np.sqrt(np.mean(successive_diffs ** 2)))
    pnn50 = float(np.mean(np.abs(successive_diffs) > 50.0) * 100.0)

    return {
        "rmssd": round(rmssd, 2),
        "sdnn": round(sdnn, 2),
        "mean_rr": round(mean_rr, 2),
        "pnn50": round(pnn50, 2),
        "n_intervals": n,
    }


# ---------------------------------------------------------------------------
# Sensor diagnostics — Phase 4
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
