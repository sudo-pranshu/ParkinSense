"""
ParkinSense — PPG Processing Pipeline
=======================================

Stateful wrapper around `algorithms.py` that maintains rolling sample
buffers for the IR/RED channels streamed from a MAX30102 sensor over BLE,
and turns each incoming sample pair into a single processed reading.

This module intentionally stays thin: buffer management, output smoothing,
the finger-presence hysteresis state machine, and SpO2 publish throttling
live here. All actual signal-processing math lives in `algorithms.py`.

Public API (unchanged across this revision): `PPGProcessor(sample_rate,
window_seconds)`, `.reset()`, `.process(ir, red)`. All previously existing
fields in the `process()` return dict are preserved; new fields are
additive only, so existing dashboard/consumer code keeps working.
"""

from __future__ import annotations

import time
from collections import deque

import numpy as np

from algorithms import (
    assess_finger_presence,
    classify_sensor_status,
    compute_hrv_metrics,
    compute_signal_quality,
    estimate_heart_rate,
    estimate_spo2,
)

# ---------------------------------------------------------------------------
# Constants (grouped here so tuning the pipeline doesn't require hunting
# through method bodies)
# ---------------------------------------------------------------------------

# Exponential Moving Average smoothing factor for the *displayed* heart
# rate: EMA_new = alpha * raw + (1 - alpha) * EMA_old. Higher alpha tracks
# the raw per-window estimate more closely (less smoothing, more jitter);
# lower alpha smooths harder but reacts more slowly to a real HR change.
# 0.25 is a common starting point for beat-to-beat wearable HR smoothing.
HR_EMA_ALPHA_DEFAULT = 0.25

# --- EMA outlier rejection ---
# A single corrupted analysis window (motion artifact, brief bad peak
# detection) can swing the raw per-window HR estimate by tens of BPM. If
# the estimator is also *unconfident* about that window, we hold the EMA
# steady rather than letting one bad window drag it off course. We do NOT
# gate on "how many calls in a row does this persist" — the rolling window
# only advances one sample per call, so a real artifact and a genuine HR
# change both "persist" across consecutive calls for the same structural
# reason (window overlap), and consecutive-call counting can't tell them
# apart. Confidence can, since it reflects peak/rhythm quality within the
# window itself, so we gate on that instead.
HR_EMA_OUTLIER_THRESHOLD_BPM = 30.0
HR_EMA_OUTLIER_CONFIDENCE_GATE = 0.5
# Safety valve: don't withhold updates forever if the signal stays noisy
# through a genuine sustained HR change (e.g. starting to exercise while
# motion also degrades signal quality). After this many seconds of
# continuous rejection, force the update through anyway.
HR_EMA_OUTLIER_MAX_REJECT_SECONDS = 8.0

# Finger-presence hysteresis: the per-sample detector in `algorithms.py`
# can flicker near its decision boundary (e.g. a finger shifting slightly).
# We only flip the *published* finger_detected state after this many
# seconds of continuous agreement, matching the persistence-filter pattern
# already used elsewhere in ParkinSense (e.g. tremor-event persistence).
# Asymmetric on purpose: users expect detection to appear quickly (short
# ON delay) but disappear slowly (longer OFF delay) so a brief wobble
# doesn't flash "no finger" — the same behaviour commercial wearables use.
FINGER_ON_HYSTERESIS_SECONDS = 1.0
FINGER_OFF_HYSTERESIS_SECONDS = 2.0

# A confirmed finger-off state (above) only affects what's *published*.
# Session-scoped smoothing state (the HR EMA, the cached SpO2 display) is
# deliberately kept alive longer than that — a finger briefly lifted and
# replaced within a few seconds is still the same physiological session,
# and restarting the EMA from scratch would cause a visible HR jump for
# no real reason. Only a genuinely sustained removal ends the session.
SESSION_RESET_SECONDS = 5.0

# SpO2 is recalculated every call (continuous processing) but only
# *published* to the dashboard at this interval. Real SpO2 doesn't change
# fast enough to justify a 1 Hz display refresh; consumer devices (Apple
# Watch, Garmin, WHOOP) typically average/refresh on an ~8-12 s cadence
# during continuous monitoring, so 10 s sits in the middle of that range.
# Gated on elapsed monotonic time rather than a sample count, so it stays
# correct even if the actual BLE sample rate drifts from the nominal `fs`.
SPO2_PUBLISH_INTERVAL_SECONDS = 10.0

# When the ParkinSense Motion Pipeline reports an activity state, PPG HR
# confidence is scaled by how much motion typically corrupts the signal at
# that intensity. Graduated rather than a single on/off penalty, since a
# harsh flat penalty (e.g. for any "ACTIVE" state) would make HR
# effectively unavailable during ordinary walking. Unrecognized or missing
# motion states default to no penalty (multiplier 1.0) so the pipeline
# degrades gracefully as MotionPipeline's vocabulary grows.
MOTION_CONFIDENCE_MULTIPLIERS = {
    "REST": 1.0,
    "LOW_MOTION": 0.8,
    "ACTIVE": 0.5,
    "RUNNING": 0.2,
}


class PPGProcessor:
    """
    Consumes streaming IR/RED samples and produces per-sample quality,
    heart-rate, SpO2, and HRV estimates from a rolling time window.

    Usage
    -----
        proc = PPGProcessor(sample_rate=50, window_seconds=10)
        for ir_sample, red_sample in ble_stream:
            result = proc.process(ir_sample, red_sample)

        # Optionally fuse with the Motion Pipeline's activity state:
        result = proc.process(ir_sample, red_sample, motion_state="ACTIVE")
    """

    def __init__(
        self,
        sample_rate: int = 50,
        window_seconds: int = 10,
        hr_ema_alpha: float = HR_EMA_ALPHA_DEFAULT,
    ):
        self.fs = sample_rate
        self.hr_ema_alpha = hr_ema_alpha
        window_size = sample_rate * window_seconds

        # Rolling raw-sample buffers. A deque(maxlen=...) gives O(1)
        # amortized append/evict; the O(n) conversion to a numpy array
        # happens at most once per `process()` call (not once per
        # algorithm), keeping CPU usage low.
        self._ir_buffer: deque[float] = deque(maxlen=window_size)
        self._red_buffer: deque[float] = deque(maxlen=window_size)

        # --- Heart-rate EMA state ---
        self._hr_ema: float | None = None
        self._hr_outlier_reject_streak = 0
        self._hr_outlier_max_reject_samples = max(
            int(HR_EMA_OUTLIER_MAX_REJECT_SECONDS * sample_rate), 1
        )

        # --- Finger-presence hysteresis state machine ---
        self._finger_on_samples_required = max(int(FINGER_ON_HYSTERESIS_SECONDS * sample_rate), 1)
        self._finger_off_samples_required = max(int(FINGER_OFF_HYSTERESIS_SECONDS * sample_rate), 1)
        self._session_reset_samples_required = max(int(SESSION_RESET_SECONDS * sample_rate), 1)
        self._finger_on_streak = 0
        self._finger_off_streak = 0
        self._finger_confirmed = False  # this is what gets published as finger_detected

        # --- SpO2 throttled-publish state ---
        # Gated on elapsed monotonic time (not sample count) so publish
        # cadence stays correct even if the real BLE sample rate drifts
        # from the nominal `fs` (e.g. 48-52 Hz instead of exactly 50 Hz).
        self._spo2_last_publish_monotonic: float | None = None
        self._latest_valid_spo2: float | None = None
        self._published_spo2: float | None = None

    def reset(self) -> None:
        """Clear all buffers and state, e.g. after a sensor reattachment event."""
        self._ir_buffer.clear()
        self._red_buffer.clear()
        self._hr_ema = None
        self._hr_outlier_reject_streak = 0
        self._finger_on_streak = 0
        self._finger_off_streak = 0
        self._finger_confirmed = False
        self._spo2_last_publish_monotonic = None
        self._latest_valid_spo2 = None
        self._published_spo2 = None

    def process(self, ir: int | None, red: int | None, motion_state: str | None = None) -> dict:
        """
        Feed one new IR/RED sample pair and return the current processed
        reading computed over the trailing rolling window.

        Parameters
        ----------
        ir, red : latest raw sample counts from the MAX30102. Either may be
            `None` if a sample was dropped over BLE; the buffers simply
            aren't updated for that channel on this call.
        motion_state : optional activity state from the ParkinSense Motion
            Pipeline ("REST" | "LOW_MOTION" | "ACTIVE" | "RUNNING", or any
            future state). Purely additive — omitting it (default `None`)
            reproduces the previous behaviour. HR confidence is scaled by
            `MOTION_CONFIDENCE_MULTIPLIERS`; unrecognized/missing states
            get a 1.0 (no-op) multiplier.

        Returns
        -------
        dict: {
            "finger_detected": bool,        # hysteresis-confirmed, debounced
            "signal_quality": float,        # 0-100
            "heart_rate": float | None,     # BPM, EMA-smoothed
            "spo2": float | None,           # %, published on a ~10 s cadence
            "confidence": float,            # 0-1, overall trust in this reading
            "ir": int,
            "red": int,
            "rr_intervals_ms": list[float],
            "finger_reason": str,
            "quality_breakdown": dict,
            "hr_confidence": float,         # raw HR-estimator confidence (unsmoothed)
            "spo2_confidence": float,
            "hr_quality": dict,             # {peak_quality, rhythm_quality, motion_quality,
                                             #  signal_quality, overall_confidence, confidence}
            "hrv": dict,                    # {rmssd, sdnn, mean_rr, pnn50, n_intervals}
            "sensor_status": str,           # NO_FINGER | LOW_SIGNAL | GOOD | HIGH_SIGNAL | SATURATED
            "timestamp": float,             # time.time() at the moment this reading was produced
            "monotonic_timestamp": float,   # time.monotonic() at the same moment; never jumps,
                                             #  unaffected by system clock changes — use this for
                                             #  sensor-to-sensor sync / elapsed-time math
            "motion_state": str | None,     # echoes the motion_state argument, for logging/replay
        }
        All fields present in earlier revisions are unchanged in name and
        meaning; `timestamp`, `monotonic_timestamp`, and `motion_state` are
        new in this revision.
        """
        now_monotonic = time.monotonic()

        if ir is not None:
            self._ir_buffer.append(ir)
        if red is not None:
            self._red_buffer.append(red)

        # Single conversion to numpy arrays per call — every downstream
        # algorithm reuses these instead of re-converting the deque itself.
        ir_arr = np.fromiter(self._ir_buffer, dtype=np.float64, count=len(self._ir_buffer))
        red_arr = np.fromiter(self._red_buffer, dtype=np.float64, count=len(self._red_buffer))

        raw_finger = assess_finger_presence(ir_arr, self.fs)
        quality = compute_signal_quality(ir_arr, self.fs)
        sensor_status = classify_sensor_status(ir_arr)

        # --- Finger-presence hysteresis ---
        # Track how many *consecutive* samples agree with the raw per-
        # sample detector before trusting a state change. This is the same
        # persistence-counter pattern used by the tremor-event detector
        # elsewhere in ParkinSense, just applied to finger contact instead
        # of tremor bursts.
        if raw_finger["detected"]:
            self._finger_on_streak += 1
            self._finger_off_streak = 0
        else:
            self._finger_off_streak += 1
            self._finger_on_streak = 0

        if not self._finger_confirmed and self._finger_on_streak >= self._finger_on_samples_required:
            self._finger_confirmed = True

        if self._finger_confirmed and self._finger_off_streak >= self._finger_off_samples_required:
            self._finger_confirmed = False

        # Session-scoped reset uses a longer, independent threshold than
        # the publish-state hysteresis above. A finger lifted and replaced
        # within SESSION_RESET_SECONDS still keeps its EMA/SpO2 cache; only
        # a sustained removal past this longer window is treated as the
        # start of a new physiological session.
        if self._finger_off_streak >= self._session_reset_samples_required:
            self._hr_ema = None
            self._hr_outlier_reject_streak = 0
            self._latest_valid_spo2 = None
            self._published_spo2 = None
            self._spo2_last_publish_monotonic = None

        finger_detected = self._finger_confirmed

        # NO_FINGER is more actionable for a dashboard than the raw
        # ADC-level LOW_SIGNAL classification once we already know, via
        # the debounced hysteresis state, that there's no finger at all.
        # `classify_sensor_status` stays a pure raw-signal classifier
        # (still useful standalone/for tests); this override only applies
        # to what gets published here.
        if not finger_detected:
            sensor_status = "NO_FINGER"

        # --- Defaults for the finger-off case ---
        heart_rate = None
        rr_intervals_ms: list[float] = []
        hr_estimator_confidence = 0.0
        spo2_confidence = 0.0
        hr_quality = {
            "peak_quality": 0.0, "rhythm_quality": 0.0, "motion_quality": 0.0,
            "signal_quality": 0.0, "overall_confidence": 0.0, "confidence": 0.0,
        }
        hrv = {"rmssd": None, "sdnn": None, "mean_rr": None, "pnn50": None, "n_intervals": 0}

        if finger_detected:
            # --- Heart rate: raw per-window estimate -> EMA smoothing ---
            hr_result = estimate_heart_rate(ir_arr, self.fs)
            raw_heart_rate = hr_result["heart_rate"]
            rr_intervals_ms = hr_result["rr_intervals_ms"]
            hr_estimator_confidence = hr_result["confidence"]

            if raw_heart_rate is not None:
                if self._hr_ema is None:
                    # First valid estimate of the session — nothing to
                    # smooth against yet, so it just becomes the baseline.
                    self._hr_ema = raw_heart_rate
                    self._hr_outlier_reject_streak = 0
                else:
                    jump = abs(raw_heart_rate - self._hr_ema)
                    is_low_confidence_jump = (
                        jump > HR_EMA_OUTLIER_THRESHOLD_BPM
                        and hr_estimator_confidence < HR_EMA_OUTLIER_CONFIDENCE_GATE
                    )
                    if (
                        is_low_confidence_jump
                        and self._hr_outlier_reject_streak < self._hr_outlier_max_reject_samples
                    ):
                        # Large jump + weak peak/rhythm confidence reads as
                        # a motion artifact riding through the analysis
                        # window rather than a real HR change. Hold the EMA
                        # steady this call instead of updating it.
                        self._hr_outlier_reject_streak += 1
                    else:
                        # Either a normal-sized update, or a confident big
                        # jump (real change), or we've been rejecting long
                        # enough that the safety valve forces it through.
                        self._hr_ema = (
                            self.hr_ema_alpha * raw_heart_rate
                            + (1.0 - self.hr_ema_alpha) * self._hr_ema
                        )
                        self._hr_outlier_reject_streak = 0
            heart_rate = round(self._hr_ema, 1) if self._hr_ema is not None else None

            # --- HR quality breakdown ---
            # peak_quality / rhythm_quality are exposed directly from the
            # HR estimator (fraction of detected peaks retained after
            # outlier rejection, and RR-interval regularity). motion_quality
            # / signal_quality reuse the SQI breakdown already computed
            # above rather than recomputing anything.
            peak_quality = hr_result.get("peak_quality", 0.0)
            rhythm_quality = hr_result.get("rhythm_quality", 0.0)
            motion_quality = quality["motion_score"]
            signal_quality_fraction = quality["score"] / 100.0

            overall_hr_confidence = float(np.clip(
                0.40 * signal_quality_fraction + 0.30 * rhythm_quality
                + 0.20 * peak_quality + 0.10 * motion_quality,
                0.0, 1.0,
            ))
            # Motion-aware discount: scale HR confidence by how much the
            # reported activity level typically corrupts PPG, rather than
            # a single harsh on/off penalty. Unrecognized/missing motion
            # states fall through to a 1.0 (no-op) multiplier, so this
            # stays a strict addition for existing callers.
            overall_hr_confidence *= MOTION_CONFIDENCE_MULTIPLIERS.get(motion_state, 1.0)

            hr_quality = {
                "peak_quality": round(peak_quality, 3),
                "rhythm_quality": round(rhythm_quality, 3),
                "motion_quality": round(motion_quality, 3),
                "signal_quality": round(signal_quality_fraction, 3),
                "overall_confidence": round(overall_hr_confidence, 3),
                "confidence": round(overall_hr_confidence, 3),  # backward-compat alias
            }

            # --- HRV, reusing the RR intervals already computed above ---
            hrv = compute_hrv_metrics(rr_intervals_ms)

            # --- SpO2: computed every call, published on a slower cadence ---
            spo2_result = estimate_spo2(ir_arr, red_arr, self.fs)
            spo2_confidence = spo2_result["confidence"]
            if spo2_result["spo2"] is not None:
                self._latest_valid_spo2 = spo2_result["spo2"]

            should_publish = (
                self._published_spo2 is None
                or self._spo2_last_publish_monotonic is None
                or (now_monotonic - self._spo2_last_publish_monotonic) >= SPO2_PUBLISH_INTERVAL_SECONDS
            )
            if should_publish and self._latest_valid_spo2 is not None:
                self._published_spo2 = self._latest_valid_spo2
                self._spo2_last_publish_monotonic = now_monotonic

        spo2 = self._published_spo2 if finger_detected else None

        # Top-level (whole-reading) confidence: a reading is only as
        # trustworthy as the weakest link — finger contact, general signal
        # quality, and HR-quality confidence (which already folds in the
        # motion-state discount) all have to be reasonable.
        overall_confidence = float(np.clip(
            raw_finger["confidence"] * (quality["score"] / 100.0) * max(hr_quality["overall_confidence"], 0.3)
            if finger_detected else 0.0,
            0.0, 1.0,
        ))

        return {
            "finger_detected": finger_detected,
            "signal_quality": quality["score"],
            "heart_rate": heart_rate,
            "spo2": spo2,
            "confidence": round(overall_confidence, 3),
            "ir": ir,
            "red": red,
            # --- diagnostics present since the previous revision ---
            "rr_intervals_ms": rr_intervals_ms,
            "finger_reason": raw_finger["reason"],
            "quality_breakdown": quality,
            "hr_confidence": hr_estimator_confidence,
            "spo2_confidence": spo2_confidence,
            "hr_quality": hr_quality,
            "hrv": hrv,
            "sensor_status": sensor_status,
            # --- new in this revision (additive only) ---
            "timestamp": time.time(),
            "monotonic_timestamp": now_monotonic,
            "motion_state": motion_state,
        }
