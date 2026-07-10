import math
import time
from collections import deque


class StepCounter:
    """
    Real-time pedestrian step counter driven by accelerometer magnitude.

    Design notes
    ------------
    - A high-pass filter removes gravity / slow drift, leaving only the
      oscillatory component of the acceleration signal.
    - An adaptive threshold (rolling mean + k * std of the filtered
      magnitude) tracks the current motion energy, so the detector works
      whether the device is on a wrist during a brisk walk or a gentle
      stroll, without hand-tuned constants per user.
    - Hysteresis (arm above threshold, re-arm only once well below it)
      prevents one physical step from being counted multiple times as
      the signal oscillates around the threshold.
    - A refractory period (derived from max_cadence_spm) rejects any
      "step" that arrives faster than a human could physically step,
      filtering out high-frequency noise/bounce.
    - motion_state gating: this module trusts MotionPipeline's motion
      classification and only counts steps when that state indicates
      real body movement (walking/active/moving). This is what prevents
      hand tremor, in-pocket fidgeting, or device handling from being
      miscounted as steps -- MotionPipeline already solved "is the body
      moving," so StepCounter doesn't need to re-solve it.
    - step_length_m is a constructor parameter, not a hardcoded constant,
      so distance can be calibrated per user (e.g. from height) later
      without touching detection logic. distance_m itself is kept at
      full float precision internally; rounding only happens in the
      dict returned from update(), which is for display/logging -- unit
      conversion to km etc. belongs in the dashboard layer, not here.
    - Cadence is EMA-smoothed rather than a raw instantaneous value, so
      the displayed number doesn't jitter step-to-step.
    - "walking" requires 3 consecutive steps at a plausible walking gap
      before it flips True, so a single stray/accidental movement isn't
      reported as the start of a walk. It still turns off quickly via
      walking_timeout_s once steps stop arriving.
    - "active minutes" is intentionally stricter than "walking": it only
      starts accruing once a walking bout has been sustained continuously
      for active_minute_min_duration_s AND cadence exceeds
      active_minute_min_cadence_spm. This is what keeps a 10-step trip to
      the kitchen from padding activity totals the way a real exercise
      bout would.
    - All internal timing uses time.monotonic(), which is immune to
      system clock adjustments (NTP sync, DST, manual changes) that
      would otherwise corrupt interval/cadence math.

    Usage
    -----
        step_counter = StepCounter(sample_rate=104, step_length_m=0.78)
        result = step_counter.update(ax, ay, az, motion_state)
        # result == {
        #     "steps": int,
        #     "cadence": float,            # steps per minute, EMA-smoothed
        #     "step_rate_hz": float,        # cadence expressed in Hz (cadence / 60),
        #                                   # since gait-analysis literature commonly
        #                                   # reports step rate in Hz rather than spm
        #     "walking": bool,              # confirmed walking right now
        #     "distance_m": float,
        #     "active_minutes": float,      # only sustained activity bouts
        #     "step_confidence": float,     # 0-1 heuristic, from threshold margin
        #     "walking_confidence": float,  # 0-1 heuristic, from interval regularity
        #     "activity_type": str | None,  # reserved, currently None
        # }

        # Call this on BLE disconnect/reconnect or "Start Workout" without
        # tearing down and recreating the object:
        step_counter.reset()
    """

    def __init__(
        self,
        sample_rate,
        step_length_m=0.75,
        min_cadence_spm=60,
        max_cadence_spm=200,
        adaptive_window_seconds=2.0,
        walking_timeout_s=2.0,
        active_minute_min_duration_s=60.0,
        active_minute_min_cadence_spm=60.0,
    ):
        # ---- Fixed configuration (untouched by reset()) ----
        self.sample_rate = sample_rate
        self.step_length_m = step_length_m

        self.min_cadence_spm = min_cadence_spm
        self.max_cadence_spm = max_cadence_spm

        # Refractory period: the shortest physically plausible gap
        # between two consecutive steps, derived from max cadence.
        self.min_step_interval_s = 60.0 / max_cadence_spm

        # If no step lands within this many seconds, we consider the
        # person to have stopped walking (used for the "walking" flag
        # and for closing out active-minute accumulation).
        self.walking_timeout_s = walking_timeout_s

        # A gap between steps looser than this isn't consistent with an
        # ongoing walking cadence, so it resets the consecutive-step run.
        self._max_consistent_step_gap_s = 60.0 / min_cadence_spm

        # Active-minute qualification thresholds.
        self.active_minute_min_duration_s = active_minute_min_duration_s
        self.active_minute_min_cadence_spm = active_minute_min_cadence_spm

        self._adaptive_window = max(10, int(sample_rate * adaptive_window_seconds))
        self._steps_required_to_confirm_walking = 3
        self._cadence_ema_alpha = 0.3  # smoothing factor: higher = more reactive
        self._min_threshold = 0.08
        self._max_threshold = 1.5
        self._threshold_k = 0.7  # std multiplier
        self._hp_alpha = 0.95

        self.reset()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def reset(self):
        """
        Reset all mutable/session state back to a fresh start, without
        losing the configuration this instance was constructed with.
        Call this on BLE reconnect, runtime restart-without-recreate, or
        a future "Start Workout" action -- anywhere you want step counts,
        distance, and active minutes to zero out but keep the same
        calibration (step length, cadence bounds, thresholds).
        """
        # Rolling buffer of filtered magnitudes for adaptive threshold.
        self._mag_buffer = deque(maxlen=self._adaptive_window)

        # First-order high-pass filter state.
        self._hp_prev_raw = 0.0
        self._hp_prev_out = 0.0

        # Adaptive threshold state.
        self._threshold = 0.15  # sensible starting floor, in g

        # Peak-detection / hysteresis state.
        self._above_threshold = False
        self._last_step_time = None

        # Cadence bookkeeping.
        self._recent_step_times = deque(maxlen=8)
        self._cadence_ema = 0.0

        # Walking-confirmation state.
        self._consecutive_step_count = 0
        self._walking_confirmed = False

        # Active-minutes / bout-tracking state.
        self._active_seconds = 0.0
        self.active_minutes = 0.0
        self._bout_start_time = None
        self._bout_qualified = False

        self._last_update_time = None

        # Output state.
        self.steps = 0
        self.distance_m = 0.0

        # Confidence heuristics (see _walking_confidence() and the
        # step-confidence calculation in update() for rationale).
        self._last_step_confidence = 0.0

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _high_pass(self, value):
        out = self._hp_alpha * (self._hp_prev_out + value - self._hp_prev_raw)
        self._hp_prev_raw = value
        self._hp_prev_out = out
        return out

    def _update_adaptive_threshold(self, filtered_abs):
        self._mag_buffer.append(filtered_abs)
        if len(self._mag_buffer) < self._adaptive_window // 2:
            return

        n = len(self._mag_buffer)
        mean = sum(self._mag_buffer) / n
        variance = sum((m - mean) ** 2 for m in self._mag_buffer) / n
        std = math.sqrt(variance)

        candidate = mean + self._threshold_k * std
        self._threshold = max(self._min_threshold, min(self._max_threshold, candidate))

    def _cadence_spm(self):
        """Compute EMA-smoothed cadence. Has a side effect of updating
        self._cadence_ema, so call this exactly once per update()."""
        times = list(self._recent_step_times)
        if len(times) < 2:
            return self._cadence_ema
        intervals = [b - a for a, b in zip(times, times[1:])]
        avg_interval = sum(intervals) / len(intervals)
        if avg_interval <= 0:
            return self._cadence_ema

        raw_cadence = 60.0 / avg_interval
        self._cadence_ema = (
            self._cadence_ema_alpha * raw_cadence
            + (1 - self._cadence_ema_alpha) * self._cadence_ema
            if self._cadence_ema > 0
            else raw_cadence
        )
        return self._cadence_ema

    def _is_walking_now(self, now):
        if not self._walking_confirmed or self._last_step_time is None:
            return False
        return (now - self._last_step_time) <= self.walking_timeout_s

    def _walking_confidence(self, walking_now):
        """
        Heuristic 0-1 confidence in the current walking_now flag, based on
        how regular the recent step-to-step intervals are. A steady human
        gait produces intervals clustered tightly around their mean (low
        coefficient of variation); an irregular sequence -- someone
        shuffling, or noise sporadically crossing the threshold -- produces
        higher variance, so confidence scales down accordingly. This is a
        heuristic, not a calibrated probability, but it's far more useful
        than a constant 1.0/0.0.
        """
        if not walking_now:
            return 0.0

        times = list(self._recent_step_times)
        if len(times) < 3:
            # walking_now already required 3 consecutive steps to become
            # True, so there IS a walking bout -- but not quite enough
            # intervals yet to judge regularity, hence a moderate default
            # rather than a hard 0 or 1.
            return 0.5

        intervals = [b - a for a, b in zip(times, times[1:])]
        mean_interval = sum(intervals) / len(intervals)
        if mean_interval <= 0:
            return 0.5

        variance = sum((i - mean_interval) ** 2 for i in intervals) / len(intervals)
        std = math.sqrt(variance)
        coefficient_of_variation = std / mean_interval

        return max(0.0, min(1.0, 1.0 - coefficient_of_variation))

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def update(self, ax, ay, az, motion_state, now=None):
        """
        Feed one accelerometer sample (in g) and the current motion_state
        string from MotionPipeline's context. Call this once per sample,
        at the same cadence as MotionPipeline.process().
        """
        now = now if now is not None else time.monotonic()

        magnitude = math.sqrt(ax * ax + ay * ay + az * az)
        filtered = self._high_pass(magnitude)
        filtered_abs = abs(filtered)

        self._update_adaptive_threshold(filtered_abs)

        # Only trust peaks while MotionPipeline says the body is
        # actually moving. This is the gate that keeps tremor and
        # device-handling from registering as steps.
        gating_ok = motion_state in ("active", "walking", "moving")

        if gating_ok:
            # Use the SIGNED filtered value so we only fire on the
            # positive-going excursion (the heel-strike impact), not
            # on both halves of the oscillation -- using abs() would
            # double-count every step.
            if not self._above_threshold and filtered > self._threshold:
                self._above_threshold = True

                interval_ok = True
                gap_from_last = None
                if self._last_step_time is not None:
                    gap_from_last = now - self._last_step_time
                    interval_ok = gap_from_last >= self.min_step_interval_s

                if interval_ok:
                    self.steps += 1
                    self.distance_m += self.step_length_m
                    self._last_step_time = now
                    self._recent_step_times.append(now)

                    # Step confidence: how far the triggering peak cleared
                    # the adaptive threshold, as a multiple of the
                    # threshold itself. A peak that barely ticks over the
                    # threshold is easily confused with noise sitting near
                    # the adaptive floor; a peak that clears it by a wide
                    # margin looks much more like a genuine heel-strike.
                    # Ratio of 1.0 (peak at 2x threshold) is treated as
                    # already-saturated confidence.
                    margin_ratio = (
                        (filtered - self._threshold) / self._threshold
                        if self._threshold > 0
                        else 0.0
                    )
                    self._last_step_confidence = max(0.0, min(1.0, margin_ratio))

                    # Consecutive-step run for the walking confirmation:
                    # a gap consistent with an ongoing gait extends the
                    # run; a looser gap (or the very first step) starts
                    # a fresh run of 1.
                    if (
                        gap_from_last is not None
                        and gap_from_last <= self._max_consistent_step_gap_s
                    ):
                        self._consecutive_step_count += 1
                    else:
                        self._consecutive_step_count = 1

                    if (
                        self._consecutive_step_count
                        >= self._steps_required_to_confirm_walking
                    ):
                        self._walking_confirmed = True

            elif self._above_threshold and filtered < self._threshold * 0.3:
                # Re-arm only once the signal has dropped well below
                # threshold (hysteresis band), so a single step doesn't
                # get double-counted as it decays back down.
                self._above_threshold = False
        else:
            self._above_threshold = False

        # Timeout: once too long has passed since the last step, drop
        # the walking confirmation and reset the consecutive-step run,
        # so the next steps have to re-earn "walking = True" again.
        if (
            self._last_step_time is not None
            and (now - self._last_step_time) > self.walking_timeout_s
        ):
            self._walking_confirmed = False
            self._consecutive_step_count = 0

        # Cadence is computed once here (it has a side effect on the EMA)
        # and reused below for both the active-minutes gate and the
        # returned dict.
        cadence_now = self._cadence_spm()
        walking_now = self._is_walking_now(now)

        # Active-minutes accounting: stricter than "walking". A bout has
        # to be sustained for active_minute_min_duration_s AND exceed
        # active_minute_min_cadence_spm before any of it counts, which is
        # what keeps a short walk to the kitchen from counting the same
        # as real sustained activity. Once a bout qualifies, the elapsed
        # bout time is credited in one catch-up addition, and the rest of
        # the bout accrues incrementally from then on.
        if walking_now:
            if self._bout_start_time is None:
                self._bout_start_time = now

            bout_duration = now - self._bout_start_time

            if not self._bout_qualified:
                if (
                    bout_duration >= self.active_minute_min_duration_s
                    and cadence_now > self.active_minute_min_cadence_spm
                ):
                    self._active_seconds += bout_duration
                    self._bout_qualified = True
            else:
                if self._last_update_time is not None:
                    dt = now - self._last_update_time
                    if 0 < dt < 1.0:
                        self._active_seconds += dt
        else:
            self._bout_start_time = None
            self._bout_qualified = False

        self._last_update_time = now
        self.active_minutes = self._active_seconds / 60.0

        return {
            "steps": self.steps,
            "cadence": round(cadence_now, 1),
            # Same cadence, expressed in Hz (cadence_now / 60) rather than
            # steps-per-minute. Costs nothing to compute since cadence_now
            # is already available, and several gait-analysis papers
            # report step rate in Hz instead of spm.
            "step_rate_hz": round(cadence_now / 60.0, 3),
            "walking": walking_now,
            "distance_m": round(self.distance_m, 2),
            "active_minutes": round(self.active_minutes, 2),
            # Heuristic 0-1 confidence scores (see _walking_confidence()
            # and the margin_ratio calculation above for rationale) --
            # not calibrated probabilities, but a useful signal beyond a
            # flat constant. activity_type stays reserved for now (e.g.
            # walk vs. run vs. climb classification).
            "step_confidence": round(self._last_step_confidence, 3),
            "walking_confidence": round(self._walking_confidence(walking_now), 3),
            "activity_type": "walking" if walking_now else None,
        }
