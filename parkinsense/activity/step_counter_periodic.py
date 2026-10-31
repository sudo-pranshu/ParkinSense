"""
EXPERIMENTAL periodicity-gated step counter -- NOT the default.

Status (docs/validation/RESULTS.md): on synthetic ground truth it cuts false
steps during tremor/purposeful movement from 23-80/min to ~4-12/min at a
similar walking-count error, but on the only real walking recording in the
repository it counted 13-43 steps where the legacy counter counted 75
(~86 expected from the recording's spectral cadence). It therefore fails the
acceptance rule and is kept for further work and comparison only. Select it
with `RuntimeEngine(step_counter="periodic")`.

Original design notes follow.

Streaming wrist step counter (v2.0).

Why it was replaced (benchmarks/results, synthetic ground truth):
the v1.0 counter under-counted walking by ~82 % and produced 23-46 false
steps/min during tremor and purposeful arm movement. Root causes:
  1. timing on host arrival time (`time.monotonic()` per sample): the 10
     samples of a BLE packet arrive together, so inter-step intervals were
     quantised to ~96 ms packet spacing;
  2. a single-pole high-pass (~0.8 Hz) left tremor-band energy in, and the
     adaptive threshold (mean + 0.7 sd of |x|) sat inside the gait signal;
  3. no periodicity requirement -- any threshold crossing in a moving state
     counted.

v2.0 design (each element from published wrist step-counting work):
  * signal time from device timestamps (deterministic, unquantised);
  * |a| band-pass 0.5-3.0 Hz, 4th-order Butterworth, causal biquads, run
    per sample (gait fundamental 1.4-2.2 Hz; Brajdic & Harle, UbiComp 2013,
    found band-limited magnitude + peak detection among the most robust);
  * peak = local maximum above max(MIN_PEAK_G, K_RMS * running RMS);
  * continuity/regularity gate in the style of the Verisense algorithm
    (Gu et al. 2017; Rowlands et al., J Sports Sci 2022; open-source,
    MIT-licensed reference in the `walking` R package): candidates count
    only once a run of BOUT_MIN_STEPS has regular intervals (CV <= BOUT_MAX_CV);
    on confirmation the whole run is counted retroactively, so bout onsets
    are not lost;
  * the historical motion-state gate (REST never counts) is retained.

Public API is unchanged: `StepCounter(sample_rate=...)`, `.update(ax, ay, az,
motion_state, now=None)` -> dict with the same keys, `.reset()`. New:
`.break_continuity()` after a data gap, and a `walking_state` key so the
runtime no longer derives it in two places (review P2-12).
"""

from __future__ import annotations

import math
import time
from collections import deque

from scipy.signal import butter

from parkinsense.config import MotionState

BAND_HZ = (0.5, 3.0)
MIN_PEAK_G = 0.05
K_RMS = 0.7
RMS_TAU_S = 2.0
MIN_STEP_INTERVAL_S = 0.30            # 200 steps/min upper bound
MAX_STEP_INTERVAL_S = 1.25            # 48 steps/min lower bound within a bout
BOUT_MIN_STEPS = 6
BOUT_MAX_CV = 0.30
IN_BOUT_REL_TOL = 0.5                 # interval may deviate +-50 % from bout median
WALKING_TIMEOUT_S = 2.0
# Gait is periodic: the band-limited magnitude's normalised autocorrelation
# at the step lag (step regularity) or the stride lag (stride regularity) is high, while random purposeful movement that happens to
# produce a few regular peaks is not (autocorrelation-based gait
# periodicity: Moe-Nilssen & Helbostad, J Biomech 37(1), 2004).
PERIODICITY_WINDOW_S = 4.0
MIN_PERIODICITY = 0.6


class _Biquads:
    """Causal SOS cascade, Direct Form II transposed, pure Python (per-sample)."""

    def __init__(self, sos):
        self.sos = [tuple(map(float, s)) for s in sos]
        self.z = [[0.0, 0.0] for _ in self.sos]

    def reset(self):
        self.z = [[0.0, 0.0] for _ in self.sos]

    def __call__(self, x):
        for (b0, b1, b2, _a0, a1, a2), z in zip(self.sos, self.z):
            y = b0 * x + z[0]
            z[0] = b1 * x - a1 * y + z[1]
            z[1] = b2 * x - a2 * y
            x = y
        return x


class PeriodicStepCounter:
    def __init__(self, sample_rate, step_length_m=0.75, active_minute_min_duration_s=60.0,
                 active_minute_min_cadence_spm=60.0, **_legacy_kwargs):
        self.sample_rate = float(sample_rate)
        self.step_length_m = step_length_m
        self.active_minute_min_duration_s = active_minute_min_duration_s
        self.active_minute_min_cadence_spm = active_minute_min_cadence_spm
        self._sos = butter(4, BAND_HZ, btype="bandpass", fs=self.sample_rate, output="sos")
        self._rms_alpha = 1.0 - math.exp(-1.0 / (RMS_TAU_S * self.sample_rate))
        self.reset()

    # ------------------------------------------------------------------
    def reset(self):
        self.steps = 0
        self.distance_m = 0.0
        self.active_minutes = 0.0
        self._active_seconds = 0.0
        self._filt = _Biquads(self._sos)
        self._ms = 0.0
        self._y1 = self._y2 = 0.0
        self._t1 = None
        self._warm = 0
        self._last_candidate_t = None
        self._pending: list[float] = []
        self._bout: deque = deque(maxlen=12)
        self._in_bout = False
        self._last_step_t = None
        self._last_amp_margin = 0.0
        self._bout_start = None
        self._bout_qualified = False
        self._last_update_t = None
        self._cadence = 0.0
        self._ybuf = deque(maxlen=int(PERIODICITY_WINDOW_S * self.sample_rate))

    def break_continuity(self):
        """Call after a data gap: forget filter state and any open bout, keep totals."""
        self._filt.reset()
        self._y1 = self._y2 = 0.0
        self._t1 = None
        self._warm = 0
        self._pending.clear()
        self._bout.clear()
        self._in_bout = False
        self._last_candidate_t = None
        self._ybuf.clear()

    def _periodicity(self, lag_s):
        n = len(self._ybuf)
        lag = int(round(lag_s * self.sample_rate))
        if lag < 2 or n < 2 * lag + 10:
            return 0.0
        y = list(self._ybuf)
        m = sum(y) / n
        y = [v - m for v in y]
        den = sum(v * v for v in y)
        if den <= 0:
            return 0.0
        best = 0.0
        for L in (lag - 2, lag - 1, lag, lag + 1, lag + 2):
            num = sum(y[i] * y[i + L] for i in range(n - L))
            best = max(best, num / den * n / (n - L))
        return best

    # ------------------------------------------------------------------
    def _count(self, t):
        self.steps += 1
        self.distance_m += self.step_length_m
        self._last_step_t = t
        self._bout.append(t)

    @staticmethod
    def _cv(intervals):
        m = sum(intervals) / len(intervals)
        if m <= 0:
            return float("inf")
        return math.sqrt(sum((i - m) ** 2 for i in intervals) / len(intervals)) / m

    def _candidate(self, t, margin):
        self._last_amp_margin = margin
        if self._last_candidate_t is not None and t - self._last_candidate_t < MIN_STEP_INTERVAL_S:
            return
        prev = self._last_candidate_t
        self._last_candidate_t = t
        if self._in_bout:
            times = list(self._bout)
            ints = sorted(b - a for a, b in zip(times, times[1:]))
            med = ints[len(ints) // 2] if ints else t - times[-1]
            gap = t - times[-1]
            if gap <= MAX_STEP_INTERVAL_S and abs(gap - med) <= IN_BOUT_REL_TOL * med:
                self._count(t)
                return
            self._in_bout = False
            self._bout.clear()
            self._pending = [t]
            return
        if prev is not None and t - prev > MAX_STEP_INTERVAL_S:
            self._pending = []
        self._pending.append(t)
        self._pending = self._pending[-BOUT_MIN_STEPS:]
        if len(self._pending) >= BOUT_MIN_STEPS:
            ints = [b - a for a, b in zip(self._pending, self._pending[1:])]
            med = sorted(ints)[len(ints) // 2]
            if (all(MIN_STEP_INTERVAL_S <= i <= MAX_STEP_INTERVAL_S for i in ints)
                    and self._cv(ints) <= BOUT_MAX_CV
                    and max(self._periodicity(med), self._periodicity(2 * med)) >= MIN_PERIODICITY):
                self._in_bout = True
                self._bout.clear()
                for pt in self._pending:          # retroactive: count the whole run
                    self._count(pt)
                self._pending = []

    def _cadence_spm(self, now):
        if not self._in_bout or len(self._bout) < 2:
            return 0.0 if not self._walking(now) else self._cadence
        times = list(self._bout)
        span = times[-1] - times[0]
        if span <= 0:
            return self._cadence
        raw = 60.0 * (len(times) - 1) / span
        self._cadence = raw if self._cadence <= 0 else 0.3 * raw + 0.7 * self._cadence
        return self._cadence

    def _walking(self, now):
        return (self._in_bout and self._last_step_t is not None
                and now - self._last_step_t <= WALKING_TIMEOUT_S)

    # ------------------------------------------------------------------
    def update(self, ax, ay, az, motion_state, now=None, debug=False):
        now = time.monotonic() if now is None else float(now)
        y = self._filt(math.sqrt(ax * ax + ay * ay + az * az))
        self._ybuf.append(y)
        self._ms += self._rms_alpha * (y * y - self._ms)
        self._warm += 1

        state = MotionState.parse(motion_state)
        gate = state in (MotionState.ACTIVE, MotionState.LOW_MOTION)
        thr = max(MIN_PEAK_G, K_RMS * math.sqrt(self._ms))
        # y1 is a local maximum if y2 < y1 >= y
        if (gate and self._warm > self.sample_rate and self._t1 is not None
                and self._y1 > thr and self._y1 > self._y2 and self._y1 >= y):
            self._candidate(self._t1, (self._y1 - thr) / thr)
        self._y2, self._y1, self._t1 = self._y1, y, now

        if self._in_bout and self._last_step_t is not None and now - self._last_step_t > WALKING_TIMEOUT_S:
            self._in_bout = False
            self._bout.clear()

        walking = self._walking(now)
        cadence = self._cadence_spm(now) if walking else 0.0
        if not walking:
            self._cadence = 0.0
        if walking:
            if self._bout_start is None:
                self._bout_start = now
            dur = now - self._bout_start
            if not self._bout_qualified:
                if dur >= self.active_minute_min_duration_s and cadence > self.active_minute_min_cadence_spm:
                    self._active_seconds += dur
                    self._bout_qualified = True
            elif self._last_update_t is not None and 0 < now - self._last_update_t < 1.0:
                self._active_seconds += now - self._last_update_t
        else:
            self._bout_start = None
            self._bout_qualified = False
        self._last_update_t = now
        self.active_minutes = self._active_seconds / 60.0

        if walking and len(self._bout) >= 3:
            ints = [b - a for a, b in zip(list(self._bout), list(self._bout)[1:])]
            wconf = max(0.0, min(1.0, 1.0 - self._cv(ints)))
        else:
            wconf = 0.0
        return {
            "steps": self.steps,
            "cadence": round(cadence, 1),
            "step_rate_hz": round(cadence / 60.0, 3),
            "walking": walking,
            "walking_state": "WALKING" if walking else "NOT_WALKING",
            "distance_m": round(self.distance_m, 2),
            "active_minutes": round(self.active_minutes, 2),
            "step_confidence": round(max(0.0, min(1.0, self._last_amp_margin)), 3),
            "walking_confidence": round(wconf, 3),
            "activity_type": "walking" if walking else None,
        }
