"""
Wear-state monitor (Phase 8). Pure, signal-time, no I/O, no firmware dependency.

It answers one question per second of signal: is this device being worn, and which of its data
sources can be trusted? It keeps five concepts SEPARATE (docs/architecture/WEAR_AWARE_ACQUISITION.md):

    wear state      WearState      WORN / WORN_PPG_UNAVAILABLE / POSSIBLY_REMOVED / REMOVED / RESUMING
    IMU state       ImuState       is acceleration/rotation data arriving and valid?
    PPG state       PpgState       optical contact: CONTACT / NO_CONTACT / FAULT / UNKNOWN
    link state      LinkState      is the stream continuous or has it gapped?
    power state     PowerState     always UNKNOWN: the current firmware reports no battery or power data

Evidence rules (hard requirements of the Phase 8 programme, enforced by tests):

  * Stillness alone is never evidence of removal: people sleep motionless.
  * Loss of PPG contact alone is never evidence of removal: a finger sensor loses contact when the
    finger moves, and the wrist-worn arrangement has no guaranteed optical contact.
  * A PPG FAULT (sensor not ready) is not "no contact" and counts as no evidence in either direction.
  * An IMU FAULT delivers zeros, which look perfectly still; faulted data never counts as stillness.
  * POSSIBLY_REMOVED / REMOVED require BOTH continuous NO_CONTACT AND continuous stillness at the
    bench noise level for the configured durations (hysteresis). All durations and thresholds are
    in WearConfig. The defaults are PROVISIONAL: they were chosen from public wrist data
    (benchmarks/wear_bench.py) and have not been measured on ParkinSense hardware; see
    docs/validation/PHASE_8_VALIDATION_PLAN.md (W1-W6).

What this cannot do: with the current hardware (no skin-contact, proximity or temperature sensor) a
device lying still on a table and a device on a motionless wrist whose finger left the sensor are
distinguished only by how quiet the accelerometer is. The monitor therefore labels REMOVED
"inferred", never "confirmed". See the hardware verdict in the architecture document.
"""

from __future__ import annotations

from collections import deque
from dataclasses import asdict, dataclass
from enum import Enum

import numpy as np

WEAR_MONITOR_VERSION = "1.0"


class WearState(str, Enum):
    UNKNOWN = "UNKNOWN"                              # before the first decision; behaves like WORN downstream
    WORN = "WORN"
    WORN_PPG_UNAVAILABLE = "WORN_PPG_UNAVAILABLE"
    POSSIBLY_REMOVED = "POSSIBLY_REMOVED"
    REMOVED = "REMOVED"
    RESUMING = "RESUMING"


class PpgState(str, Enum):
    UNKNOWN = "UNKNOWN"
    CONTACT = "CONTACT"
    NO_CONTACT = "NO_CONTACT"
    FAULT = "FAULT"


class ImuState(str, Enum):
    NO_DATA = "NO_DATA"
    STREAMING = "STREAMING"
    FAULT = "FAULT"


class LinkState(str, Enum):
    NO_DATA = "NO_DATA"
    STREAMING = "STREAMING"
    GAP = "GAP"


class PowerState(str, Enum):
    UNKNOWN = "UNKNOWN"                              # no battery/power telemetry exists in protocol v1/v2


@dataclass(frozen=True)
class WearConfig:
    """Every threshold the state machine uses. Defaults are provisional (see module docstring)."""
    epoch_s: float = 1.0
    expected_rate_hz: float = 104.0
    min_epoch_fraction: float = 0.5        # epoch with fewer samples than this fraction is treated as missing
    imu_valid_fraction: float = 0.9        # fraction of samples without IMU_FAULT for an epoch to count

    # optical contact (same level as firmware FINGER_THRESHOLD_IR; v4 recorded ~1.6k without, ~109k with a finger)
    contact_ir_min: float = 50_000.0
    ppg_valid_fraction: float = 0.5        # below this fraction of fault-free samples the epoch is a PPG FAULT
    contact_on_s: float = 3.0              # sustained contact before PpgState becomes CONTACT
    contact_off_s: float = 10.0            # sustained NO_CONTACT/FAULT before it is published

    # stillness: an epoch is "still" only if ALL available criteria hold (bench-noise level, not "resting")
    still_acc_sd_g: float = 0.001          # max-axis SD of acceleration within the epoch (provisional: benchmarks/wear_bench.py)
    still_gyro_dps: float = 0.5            # RMS of per-axis gyro SD (ignored when no gyro is supplied)
    still_angle_deg: float = 2.0           # change of mean gravity direction versus the previous epoch

    # removal hysteresis (joint evidence: continuous NO_CONTACT and continuous stillness)
    possibly_removed_s: float = 300.0
    removed_s: float = 900.0
    motion_return_s: float = 20.0          # sustained non-still run that cancels POSSIBLY_REMOVED
    evidence_lapse_s: float = 60.0         # POSSIBLY_REMOVED is also cancelled after this long without removal evidence

    # re-wear
    rewear_contact_s: float = 10.0
    rewear_motion_s: float = 60.0
    rewear_motion_fraction: float = 0.7    # share of non-still epochs in the last rewear_motion_s

    # continuity
    gap_s: float = 5.0                     # missing stream at least this long forces RESUMING (unless REMOVED)
    resume_s: float = 10.0
    max_transitions_kept: int = 1000

    def __post_init__(self):
        checks = [
            (self.epoch_s > 0, "epoch_s must be > 0"),
            (self.expected_rate_hz > 0, "expected_rate_hz must be > 0"),
            (0 < self.removed_s and self.possibly_removed_s < self.removed_s,
             "possibly_removed_s must be < removed_s (hysteresis)"),
            (self.contact_off_s >= self.contact_on_s, "contact_off_s must be >= contact_on_s"),
            (self.possibly_removed_s > 0, "possibly_removed_s must be > 0"),
            (self.still_acc_sd_g > 0 and self.still_angle_deg > 0 and self.still_gyro_dps > 0,
             "stillness thresholds must be > 0"),
            (0 < self.rewear_motion_fraction <= 1, "rewear_motion_fraction must be in (0, 1]"),
        ]
        for ok, msg in checks:
            if not ok:
                raise ValueError(msg)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class WearStatus:
    t: float
    wear_state: WearState
    imu_state: ImuState
    ppg_state: PpgState
    link_state: LinkState
    power_state: PowerState
    evidence: str                    # why the current state holds (documented strings, see _EVIDENCE)
    inferred: bool                   # True when no direct wear sensor backs the state (always, on current hardware)
    activity_allowed: bool           # step/activity counting permitted
    tremor_allowed: bool
    physiology_allowed: bool         # HR / HRV / SpO2 only with optical contact in a settled WORN state

    def to_dict(self) -> dict:
        d = asdict(self)
        return {k: (v.value if isinstance(v, Enum) else v) for k, v in d.items()}


def _unit(v):
    n = float(np.linalg.norm(v))
    return v / n if n > 1e-9 else None


@dataclass
class _Epoch:
    t: float
    complete: bool
    imu_valid: bool
    still: bool | None
    acc_sd: float | None
    ppg: PpgState


class WearMonitor:
    """Feed blocks of samples with `update_block`; read `status`, `transitions`, `summary()`."""

    def __init__(self, config: WearConfig | None = None, keep_epochs: bool = False):
        self.cfg = config or WearConfig()
        self.keep_epochs = keep_epochs
        self.reset()

    # ------------------------------------------------------------------ lifecycle
    def reset(self):
        c = self.cfg
        self.state = WearState.UNKNOWN
        self._evidence = "NO_EVIDENCE_YET"
        self._ppg = PpgState.UNKNOWN
        self._imu = ImuState.NO_DATA
        self._link = LinkState.NO_DATA
        self._t_origin: float | None = None
        self._cur_id: int | None = None
        self._cur: list = []
        self._last_id: int | None = None
        self._last_unit_acc = None
        self._t_last = 0.0
        self._resume_start: float | None = None
        # run lengths in seconds
        self._contact_run = 0.0
        self._nocontact_run = 0.0
        self._fault_run = 0.0
        self._still_nocontact_run = 0.0
        self._moving_run = 0.0
        self._no_evidence_s = 0.0
        self._motion_window: deque = deque(maxlen=max(1, int(round(c.rewear_motion_s / c.epoch_s))))
        self.transitions: deque = deque(maxlen=c.max_transitions_kept)
        self.transition_count = 0
        self.time_in_state = {s.value: 0.0 for s in WearState}
        self.missing_s = 0.0
        self.gaps = 0
        self.out_of_order = 0
        self.epochs = 0
        self.epoch_log: list = []

    # ------------------------------------------------------------------ input
    def update_block(self, t, acc, gyro=None, ir=None, imu_ok=None, ppg_ok=None) -> None:
        """
        t: sample times in seconds (signal time, monotonic); acc: (n,3) g; gyro: (n,3) deg/s or None;
        ir: PPG infrared counts or None (no PPG data); imu_ok / ppg_ok: per-sample bool, False when the
        packet carried IMU_FAULT / PPG_FAULT. Samples with a False imu_ok are NOT used as motion evidence.
        """
        t = np.asarray(t, float)
        n = len(t)
        if n == 0:
            return
        acc = np.asarray(acc, float).reshape(n, 3)
        gyro = None if gyro is None else np.asarray(gyro, float).reshape(n, 3)
        ir = np.full(n, np.nan) if ir is None else np.asarray(ir, float)
        imu_ok = np.ones(n, bool) if imu_ok is None else np.asarray(imu_ok, bool)
        ppg_ok = np.isfinite(ir) if ppg_ok is None else np.asarray(ppg_ok, bool)
        if self._t_origin is None:
            self._t_origin = float(t[0])
        ids = np.floor((t - self._t_origin) / self.cfg.epoch_s).astype(np.int64)
        for k in np.unique(ids):
            sel = ids == k
            if self._cur_id is not None and k < self._cur_id:
                self.out_of_order += int(sel.sum())
                continue
            if self._cur_id is not None and k > self._cur_id:
                self._close_epoch()
            if self._cur_id is None:
                self._cur_id, self._cur = int(k), []
            self._cur.append((t[sel], acc[sel], None if gyro is None else gyro[sel], ir[sel], imu_ok[sel], ppg_ok[sel]))

    def flush(self) -> None:
        """Close the epoch in progress (offline analysis; live use leaves it open until the next second)."""
        if self._cur_id is not None:
            self._close_epoch()
            self._cur_id = None

    # ------------------------------------------------------------------ epoch processing
    def _close_epoch(self):
        c = self.cfg
        cid, parts = self._cur_id, self._cur
        self._cur_id, self._cur = None, []
        t_start = self._t_origin + cid * c.epoch_s
        if self._last_id is not None and cid > self._last_id + 1:
            self._on_missing((cid - self._last_id - 1) * c.epoch_s, t_start)
        self._last_id = cid

        t = np.concatenate([p[0] for p in parts])
        acc = np.concatenate([p[1] for p in parts])
        gyro = None if any(p[2] is None for p in parts) else np.concatenate([p[2] for p in parts])
        ir = np.concatenate([p[3] for p in parts])
        iok = np.concatenate([p[4] for p in parts])
        pok = np.concatenate([p[5] for p in parts])
        n = len(t)
        self._t_last = t_start + c.epoch_s
        if n < c.min_epoch_fraction * c.expected_rate_hz * c.epoch_s:
            self._on_missing(c.epoch_s, t_start)
            return

        self._link = LinkState.STREAMING
        # IMU evidence
        imu_valid = float(iok.mean()) >= c.imu_valid_fraction
        still = acc_sd = None
        if imu_valid:
            a = acc[iok]
            acc_sd = float(a.std(axis=0).max())
            ok = acc_sd < c.still_acc_sd_g
            if gyro is not None:
                gsd = float(np.sqrt(np.mean(gyro[iok].var(axis=0))))
                ok = ok and gsd < c.still_gyro_dps
            u = _unit(a.mean(axis=0))
            if u is not None and self._last_unit_acc is not None:
                ang = float(np.degrees(np.arccos(np.clip(float(u @ self._last_unit_acc), -1.0, 1.0))))
                ok = ok and ang < c.still_angle_deg
            self._last_unit_acc = u
            still = bool(ok)
            self._imu = ImuState.STREAMING
        else:
            self._imu = ImuState.FAULT
            self._last_unit_acc = None
        # PPG evidence (independent of the IMU)
        if np.isfinite(ir).any():
            valid = pok & np.isfinite(ir)
            if float(valid.mean()) < c.ppg_valid_fraction:
                ep_ppg = PpgState.FAULT
            else:
                ep_ppg = PpgState.CONTACT if float(np.median(ir[valid])) >= c.contact_ir_min else PpgState.NO_CONTACT
        else:
            ep_ppg = PpgState.UNKNOWN
        self._advance(_Epoch(t_start, True, imu_valid, still, acc_sd, ep_ppg))

    def _on_missing(self, dur_s: float, t: float):
        c = self.cfg
        self.missing_s += dur_s
        self._link = LinkState.GAP
        self._imu = ImuState.NO_DATA
        self._contact_run = self._nocontact_run = self._fault_run = 0.0
        self._still_nocontact_run = self._moving_run = 0.0
        self._no_evidence_s = 0.0
        self._motion_window.clear()
        self._last_unit_acc = None
        if dur_s >= c.gap_s:
            self.gaps += 1
            if self.state not in (WearState.REMOVED, WearState.RESUMING):
                self._go(WearState.RESUMING, t, "GAP", "STREAM_GAP")
                self._resume_start = t

    def _advance(self, e: _Epoch):
        c, d = self.cfg, self.cfg.epoch_s
        self.epochs += 1
        # --- run lengths (seconds). FAULT and UNKNOWN reset the removal evidence: no evidence either way.
        if e.ppg == PpgState.CONTACT:
            self._contact_run += d
            self._nocontact_run = self._fault_run = 0.0
        elif e.ppg == PpgState.NO_CONTACT:
            self._nocontact_run += d
            self._contact_run = self._fault_run = 0.0
        elif e.ppg == PpgState.FAULT:
            self._fault_run += d
            self._contact_run = self._nocontact_run = 0.0
        else:
            self._contact_run = self._nocontact_run = self._fault_run = 0.0
        if e.imu_valid and e.still is not None:
            self._moving_run = 0.0 if e.still else self._moving_run + d
            self._motion_window.append(0 if e.still else 1)
        else:
            self._moving_run = 0.0
            self._motion_window.clear()
        if e.ppg == PpgState.NO_CONTACT and e.imu_valid and e.still:
            self._still_nocontact_run += d
            self._no_evidence_s = 0.0
        else:
            self._still_nocontact_run = 0.0
            self._no_evidence_s += d
        # --- published (debounced) PPG state
        if self._contact_run >= c.contact_on_s:
            self._ppg = PpgState.CONTACT
        elif self._nocontact_run >= c.contact_off_s:
            self._ppg = PpgState.NO_CONTACT
        elif self._fault_run >= c.contact_off_s:
            self._ppg = PpgState.FAULT
        elif e.ppg == PpgState.UNKNOWN:
            self._ppg = PpgState.UNKNOWN
        t_end = e.t + d
        self._decide(t_end)
        self.time_in_state[self.state.value] += d
        if self.keep_epochs:
            self.epoch_log.append((e.t, self.state.value, self._ppg.value, e.still, e.acc_sd))

    # ------------------------------------------------------------------ the state machine
    def _go(self, new: WearState, t: float, reason: str, evidence: str):
        if new == self.state:
            self._evidence = evidence
            return
        self.transitions.append({"t": round(float(t), 3), "from": self.state.value, "to": new.value, "reason": reason})
        self.transition_count += 1
        self.state = new
        self._evidence = evidence

    def _decide(self, t: float):
        c, s = self.cfg, self.state
        contact = self._ppg == PpgState.CONTACT
        if s == WearState.UNKNOWN:
            if contact:
                self._go(WearState.WORN, t, "PPG_CONTACT", "PPG_CONTACT")
            elif self._ppg in (PpgState.NO_CONTACT, PpgState.FAULT) and self._moving_run >= c.motion_return_s:
                self._go(WearState.WORN_PPG_UNAVAILABLE, t, "MOTION_WITHOUT_CONTACT", "MOTION_ASSUMED_WORN")
            elif self._still_nocontact_run >= c.possibly_removed_s:
                self._go(WearState.POSSIBLY_REMOVED, t, "STILL_AND_NO_CONTACT", "STILL_NO_CONTACT")
        elif s == WearState.WORN:
            if self._ppg in (PpgState.NO_CONTACT, PpgState.FAULT):
                self._go(WearState.WORN_PPG_UNAVAILABLE, t,
                         "PPG_FAULT" if self._ppg == PpgState.FAULT else "PPG_CONTACT_LOST", "PPG_UNAVAILABLE_ASSUMED_WORN")
        elif s == WearState.WORN_PPG_UNAVAILABLE:
            if contact:
                self._go(WearState.WORN, t, "PPG_CONTACT", "PPG_CONTACT")
            elif self._still_nocontact_run >= c.possibly_removed_s:
                self._go(WearState.POSSIBLY_REMOVED, t, "STILL_AND_NO_CONTACT", "STILL_NO_CONTACT")
        elif s == WearState.POSSIBLY_REMOVED:
            if contact:
                self._go(WearState.WORN, t, "PPG_CONTACT", "PPG_CONTACT")
            elif self._moving_run >= c.motion_return_s:
                self._go(WearState.WORN_PPG_UNAVAILABLE, t, "SUSTAINED_MOTION", "MOTION_ASSUMED_WORN")
            elif self._no_evidence_s >= c.evidence_lapse_s:
                self._go(WearState.WORN_PPG_UNAVAILABLE, t, "EVIDENCE_LAPSED", "PPG_UNAVAILABLE_ASSUMED_WORN")
            elif self._still_nocontact_run >= c.removed_s:
                self._go(WearState.REMOVED, t, "STILL_AND_NO_CONTACT_SUSTAINED", "STILL_NO_CONTACT")
        elif s == WearState.REMOVED:
            motion_frac = (sum(self._motion_window) / len(self._motion_window)
                           if len(self._motion_window) == self._motion_window.maxlen else 0.0)
            if self._contact_run >= c.rewear_contact_s:
                self._go(WearState.RESUMING, t, "REWEAR_PPG_CONTACT", "PPG_CONTACT")
                self._resume_start = t
            elif motion_frac >= c.rewear_motion_fraction:
                self._go(WearState.RESUMING, t, "REWEAR_SUSTAINED_MOTION", "MOTION_ASSUMED_WORN")
                self._resume_start = t
        elif s == WearState.RESUMING:
            if self._resume_start is not None and t - self._resume_start >= c.resume_s:
                if contact:
                    self._go(WearState.WORN, t, "RESUMED_PPG_CONTACT", "PPG_CONTACT")
                else:
                    self._go(WearState.WORN_PPG_UNAVAILABLE, t, "RESUMED_NO_CONTACT", "PPG_UNAVAILABLE_ASSUMED_WORN")
                self._resume_start = None

    # ------------------------------------------------------------------ output
    @property
    def status(self) -> WearStatus:
        s = self.state
        removed = s == WearState.REMOVED
        return WearStatus(
            t=self._t_last, wear_state=s, imu_state=self._imu, ppg_state=self._ppg, link_state=self._link,
            power_state=PowerState.UNKNOWN, evidence=self._evidence, inferred=True,
            activity_allowed=not removed, tremor_allowed=not removed,
            physiology_allowed=(s == WearState.WORN and self._ppg == PpgState.CONTACT))

    def summary(self) -> dict:
        total = sum(self.time_in_state.values())
        return {
            "wear_monitor_version": WEAR_MONITOR_VERSION,
            "config": self.cfg.to_dict(),
            "final_state": self.state.value,
            "time_in_state_s": {k: round(v, 1) for k, v in self.time_in_state.items()},
            "fraction_removed": round(self.time_in_state["REMOVED"] / total, 4) if total else None,
            "missing_s": round(self.missing_s, 1), "gaps_ge_gap_s": self.gaps,
            "out_of_order_samples": self.out_of_order, "epochs": self.epochs,
            "transition_count": self.transition_count,
            "transitions": list(self.transitions),
            "note": "wear state is INFERRED (no skin-contact sensor on current hardware); thresholds provisional",
        }
