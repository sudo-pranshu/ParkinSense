"""
EXPERIMENTAL step counter v3.0-dev ("gated"): opt-in via RuntimeEngine(step_counter="gated").
Not the default; see docs/algorithms/STEP_ACCEPTANCE.md for the rule it must meet first.

Design (each element chosen for a measured reason, see docs/research/STEPS.md):

  1. |a| -> causal Butterworth band-pass (BAND_HZ), signal-time clock.
  2. Candidate steps = local maxima of the band-passed signal above
     max(MIN_PEAK_G, PEAK_K * running RMS), refractory MIN_STEP_INTERVAL_S.
     Candidates are NOT counted yet.
  3. Walking gate, evaluated every HOP_S on the last WINDOW_S of band-passed signal:
        rms >= MIN_RMS_G   and   max normalised autocorrelation over lags
        [LAG_MIN_S, LAG_MAX_S] >= MIN_PERIODICITY.
     Autocorrelation (not interval CV) is used because arm-swing makes consecutive
     step intervals/amplitudes alternate (stride vs step), which a CV rule rejects;
     the autocorrelation peak at the stride lag is still high.
  4. When the gate opens, candidates of the preceding CREDIT_S are credited
     retroactively (with their true times); while open, candidates count live; the gate
     closes HOLD_S after the last passing evaluation.
  5. The historical motion-state gate (REST never counts) is retained, so the runtime's
     tremor guard still applies.

Latency: up to WINDOW_S/2 before the first steps of a bout are credited; totals are
correct once the bout is confirmed. `step_event_times` keeps the true time of the most recent
`max_event_history` counted steps (used by the benchmark for event matching).
"""

from __future__ import annotations

import math
import time
from collections import deque

import numpy as np
from scipy.signal import butter

from parkinsense.activity.step_counter import StepCounter
from parkinsense.activity.step_counter_periodic import _Biquads
from parkinsense.config import MotionState

BAND_HZ = (0.5, 3.5)
MIN_PEAK_G = 0.03
PEAK_K = 0.5
RMS_TAU_S = 2.0
MIN_STEP_INTERVAL_S = 0.28
HOP_S = 0.5
WINDOW_S = 4.0
LAG_MIN_S = 0.30
LAG_MAX_S = 1.40
MIN_PERIODICITY = 0.65
MIN_RMS_G = 0.12
CREDIT_S = 3.0
HOLD_S = 2.0
ALLOWED_STATES = ("ACTIVE", "WALKING", "MOVING", "LOW MOTION")


class GatedStepCounter(StepCounter):
    """Same public API and output keys as StepCounter (cadence, walking, distance, ...)."""

    def __init__(self, sample_rate, step_length_m=0.75, min_peak_g=MIN_PEAK_G, peak_k=PEAK_K,
                 min_periodicity=MIN_PERIODICITY, min_rms_g=MIN_RMS_G, band_hz=BAND_HZ, window_s=WINDOW_S,
                 hold_s=HOLD_S, credit_s=CREDIT_S, max_event_history=100_000, **kw):
        self._max_events = max_event_history
        self._window_s, self._hold_s, self._credit_s = window_s, hold_s, credit_s
        self._min_peak_g, self._peak_k = min_peak_g, peak_k
        self._min_periodicity, self._min_rms_g = min_periodicity, min_rms_g
        self._sos = butter(4, band_hz, btype="bandpass", fs=float(sample_rate), output="sos")
        super().__init__(sample_rate=sample_rate, step_length_m=step_length_m, **kw)
        self._rms_alpha = 1.0 - math.exp(-1.0 / (RMS_TAU_S * self.sample_rate))
        self._win_n = int(self._window_s * self.sample_rate)
        self._hop_n = max(1, int(HOP_S * self.sample_rate))
        self._lag_lo = int(LAG_MIN_S * self.sample_rate)
        self._lag_hi = int(LAG_MAX_S * self.sample_rate)

    def reset(self):
        super().reset()
        self._filt = _Biquads(self._sos)
        self._ms = 0.0
        self._y1 = self._y2 = 0.0
        self._ybuf = deque(maxlen=int(self._window_s * self.sample_rate))
        self._n = 0
        self._warm = 0
        self._cand: deque = deque(maxlen=64)          # (time, amplitude), not yet credited
        self._last_cand_t = None
        self._gate_open = False
        self._gate_until = -1e18
        self.step_event_times: deque = deque(maxlen=self._max_events)   # bounded: true time of each counted step
        self.periodicity = 0.0
        self.band_rms_g = 0.0
        self._thr_now = MIN_PEAK_G
        self._last_cand_gap_ok = False

    def break_continuity(self):
        super().break_continuity()
        self._filt.reset()
        self._y1 = self._y2 = 0.0
        self._ybuf.clear()
        self._cand.clear()
        self._warm = 0
        self._last_cand_t = None
        self._gate_open = False

    # ------------------------------------------------------------------
    def _periodicity_and_rms(self):
        y = np.fromiter(self._ybuf, dtype=float, count=len(self._ybuf))
        rms = float(np.sqrt(np.mean(y[-int(2 * self.sample_rate):] ** 2)))
        n = len(y)
        if n < self._win_n * 3 // 4 or self._lag_hi >= n // 2:
            return 0.0, rms
        y = y - y.mean()
        f = np.fft.rfft(y, 2 * n)
        ac = np.fft.irfft(f * np.conj(f))[: self._lag_hi + 1]
        # unbiased, energy-normalised at each lag
        lags = np.arange(self._lag_lo, self._lag_hi + 1)
        e = np.cumsum(y * y)
        tot = e[-1]
        head = e[n - 1 - lags]                     # energy of y[0 : n-lag]
        tail = tot - e[lags - 1]                   # energy of y[lag : n]
        r = ac[lags] / np.sqrt(np.maximum(head * tail, 1e-18))
        return float(np.max(r)), rms

    def _count(self, t, amp):
        self.steps += 1
        self.distance_m += self.step_length_m
        self._last_step_time = t
        self._recent_step_times.append(t)
        self.step_event_times.append(t)
        self._last_step_confidence = max(0.0, min(1.0, amp / max(self._thr_now, 1e-9) - 1.0))
        if self._last_cand_gap_ok:
            self._consecutive_step_count += 1
        else:
            self._consecutive_step_count = 1
        if self._consecutive_step_count >= self._steps_required_to_confirm_walking:
            self._walking_confirmed = True

    def update(self, ax, ay, az, motion_state, now=None, debug=False):
        now = now if now is not None else time.monotonic()
        mag = math.sqrt(ax * ax + ay * ay + az * az)
        y = self._filt(mag)
        self._ms += self._rms_alpha * (y * y - self._ms)
        self._ybuf.append(y)
        self._n += 1
        self._warm += 1

        parsed = MotionState.parse(motion_state)
        state = parsed.value if parsed else (motion_state or "").strip().upper()
        gating_ok = state in ALLOWED_STATES

        thr = max(self._min_peak_g, self._peak_k * math.sqrt(self._ms))
        self._thr_now = thr
        # local maximum at the previous sample
        if self._warm > int(self.sample_rate):
            if self._y1 > self._y2 and self._y1 >= y and self._y1 > thr:
                t_pk = self._t1
                if self._last_cand_t is None or t_pk - self._last_cand_t >= MIN_STEP_INTERVAL_S:
                    if gating_ok:
                        self._cand.append((t_pk, self._y1))
                        self._last_cand_t = t_pk
                        if self._gate_open:
                            self._credit_pending(live=True)
        self._y2, self._y1, self._t1 = self._y1, y, now

        if self._n % self._hop_n == 0 and len(self._ybuf) >= self._win_n * 3 // 4:
            per, rms = self._periodicity_and_rms()
            self.periodicity, self.band_rms_g = per, rms
            if gating_ok and per >= self._min_periodicity and rms >= self._min_rms_g:
                self._gate_until = now + self._hold_s
                if not self._gate_open:
                    self._gate_open = True
                    self._credit_pending(live=False, now=now)
            if self._gate_open and now > self._gate_until:
                self._gate_open = False
        if not gating_ok:
            self._gate_open = False
            self._cand.clear()

        if self._last_step_time is not None and (now - self._last_step_time) > self.walking_timeout_s:
            self._walking_confirmed = False
            self._consecutive_step_count = 0

        return self._finish(now)

    # candidate crediting -----------------------------------------------
    def _credit_pending(self, live, now=None):
        horizon = (now - self._credit_s) if now is not None else -1e18
        prev = self._last_step_time
        while self._cand:
            t, amp = self._cand.popleft()
            if t < horizon:
                continue
            gap = None if prev is None else t - prev
            self._last_cand_gap_ok = gap is not None and gap <= self._max_consistent_step_gap_s
            self._count(t, amp)
            prev = t

    def _finish(self, now):
        cadence_now = self._cadence_spm()
        walking_now = self._is_walking_now(now)
        if walking_now:
            if self._bout_start_time is None:
                self._bout_start_time = now
            dur = now - self._bout_start_time
            if not self._bout_qualified:
                if dur >= self.active_minute_min_duration_s and cadence_now > self.active_minute_min_cadence_spm:
                    self._active_seconds += dur
                    self._bout_qualified = True
            elif self._last_update_time is not None and 0 < now - self._last_update_time < 1.0:
                self._active_seconds += now - self._last_update_time
        else:
            self._bout_start_time = None
            self._bout_qualified = False
        self._last_update_time = now
        self.active_minutes = self._active_seconds / 60.0
        return {
            "steps": self.steps, "cadence": round(cadence_now, 1), "step_rate_hz": round(cadence_now / 60.0, 3),
            "walking": walking_now, "distance_m": round(self.distance_m, 2),
            "active_minutes": round(self.active_minutes, 2),
            "step_confidence": round(self._last_step_confidence, 3),
            "walking_confidence": round(self._walking_confidence(walking_now), 3),
            "activity_type": "walking" if walking_now else None,
            "walking_state": "WALKING" if walking_now else "NOT_WALKING",
        }
