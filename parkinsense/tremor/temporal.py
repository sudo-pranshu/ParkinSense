"""
Temporal tremor inference: two-state hidden Markov forward filter.

Replaces `TremorStateMachine` (count thresholds coupled to the analysis
hop, with a 55-75 dead band that could freeze the state indefinitely --
review P1-6) and the dead `TemporalSmoother`.

Model
-----
Hidden state  s_t in {no tremor, tremor}.
Transitions   expressed as *rates*, so behaviour is independent of the hop:
                P(enter | dt) = 1 - exp(-dt / ENTER_TAU_S)
                P(exit  | dt) = 1 - exp(-dt / EXIT_TAU_S)
Observation   per-window evidence e in [0, 1] -> likelihood ratio
                LR = clip((e + eps) / (1 - e + eps), 1/LR_MAX, LR_MAX)
              tempered by dt / WINDOW_SECONDS, because consecutive 4 s
              windows at a 0.5 s hop share 87.5 % of their samples and are
              not independent evidence (review P1-6 / ADR-0001). One fully
              independent window contributes at most LR_MAX = 60, so confirmation
              needs ~1.4 windows (~5-6 s) of consistent evidence: a single 4 s
              burst cannot confirm on its own.

Output: posterior P(tremor) plus a hysteresis decision
(enter >= 0.8, exit <= 0.2). The legacy state names are derived from the
posterior so existing consumers keep working:
  NO_TREMOR, POSSIBLE_TREMOR (rising, not yet confirmed),
  CONFIRMED_TREMOR, RECOVERY (confirmed but posterior falling below 0.8).

Time comes from the caller (signal/device time), so live and replay runs are
identical regardless of wall clock.

The structure follows standard HMM filtering (Rabiner, Proc IEEE 77(2),
1989). Rates are engineering priors -- tremor episodes in daily life last
seconds to many minutes -- not values fitted to data.
"""

from __future__ import annotations

import math

from parkinsense.config import WINDOW_SECONDS

ENTER_TAU_S = 120.0
EXIT_TAU_S = 60.0
LR_MAX = 60.0
EPS = 1e-3
CONFIRM_P = 0.8
RELEASE_P = 0.2
PRIOR_P = 0.02


class TremorHMM:
    NO_TREMOR = "NO_TREMOR"
    POSSIBLE = "POSSIBLE_TREMOR"
    CONFIRMED = "CONFIRMED_TREMOR"
    RECOVERY = "RECOVERY"

    def __init__(self):
        self.reset()

    def reset(self):
        self.p = PRIOR_P
        self.confirmed = False
        self._last_t: float | None = None

    def update(self, evidence: float | None, t: float) -> dict:
        dt = WINDOW_SECONDS if self._last_t is None else max(0.0, t - self._last_t)
        self._last_t = t
        q_in = 1.0 - math.exp(-dt / ENTER_TAU_S)
        q_out = 1.0 - math.exp(-dt / EXIT_TAU_S)
        prior = self.p * (1 - q_out) + (1 - self.p) * q_in

        if evidence is None:          # unusable window: predict only
            post = prior
        else:
            e = min(max(float(evidence), 0.0), 1.0)
            lr = (e + EPS) / (1 - e + EPS)
            lr = min(max(lr, 1 / LR_MAX), LR_MAX)
            lr = lr ** min(1.0, dt / WINDOW_SECONDS)
            post = lr * prior / (lr * prior + (1 - prior))
        self.p = min(max(post, 1e-6), 1 - 1e-6)

        if not self.confirmed and self.p >= CONFIRM_P:
            self.confirmed = True
        elif self.confirmed and self.p <= RELEASE_P:
            self.confirmed = False

        if self.confirmed:
            state = self.CONFIRMED if self.p >= CONFIRM_P else self.RECOVERY
        else:
            state = self.POSSIBLE if self.p > RELEASE_P else self.NO_TREMOR
        return {"state": state, "probability": self.p, "confirmed": self.confirmed}
