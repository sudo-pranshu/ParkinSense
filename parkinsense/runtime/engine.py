"""
RuntimeEngine -- the single processing core for live, replay and tests.

Design rules (docs/decisions/0006-runtime-engine.md):

* No I/O, no globals, no wall clock in the processing path. Importing this
  module has no side effects (the v2 runtime truncated its capture file on
  import -- review P0-1).
* All temporal logic runs on *signal time* derived from the device's
  unwrapped micros() timestamps, so a recording replayed at any speed
  produces identical outputs (deterministic replay, review P1-5).
* Two clocks (ADR-0001): per-sample consumers (PPG buffer, step counter, raw
  capture) see every sample; windowed analysis runs every ANALYSIS_HOP.
* Every capture row says whether it carries a fresh analysis
  (`is_analysis_row`, `analysis_seq`) -- review P0-2.
* Stream integrity is measured, not assumed: timestamp wrap (P1-10),
  sequence gaps (v2, P1-8), timestamp gaps (any version), measured device
  sample rate vs nominal (P0-4). Long gaps reset windowed state (P2-13).
* Analysis exceptions are counted and surfaced, never swallowed (P1-7).
"""

from __future__ import annotations

import logging
import time
import traceback
import uuid
from collections import deque
from dataclasses import dataclass, field

import numpy as np

from parkinsense import config as C
from parkinsense.activity.step_counter import StepCounter
from parkinsense.activity.step_counter_periodic import PeriodicStepCounter
from parkinsense.motion.pipeline import MotionPipeline
from parkinsense.ppg.processor import PPGProcessor
from parkinsense.protocol import packet as P

log = logging.getLogger("parkinsense.runtime")

MAX_CONSECUTIVE_ANALYSIS_ERRORS = 20
RATE_ESTIMATE_PACKETS = 100          # ~10 s of header timestamps

# Capture schema v3. The first 52 columns are the v2 schema in its original
# order (append-only evolution: name-based readers of v2 files keep working).
LEGACY_COLUMNS = [
    "timestamp", "sample_timestamp_us",
    "ax", "ay", "az", "gx", "gy", "gz", "ir", "red",
    "classification", "tremor_score", "confidence", "severity", "dominant_frequency",
    "frequency_std", "band_ratio", "best_axis", "axis_agreement", "axis_dominance", "rest_index",
    "motion_state", "motion_rms",
    "steps", "cadence", "step_rate_hz", "walking_state", "distance_m", "active_minutes",
    "step_confidence", "walking_confidence", "activity_type",
    "heart_rate", "spo2", "hr_confidence", "spo2_confidence", "signal_quality", "sensor_status",
    "finger_detected",
    "rmssd", "sdnn", "mean_rr", "pnn50",
    "sample_count", "packet_count", "sampling_rate",
    "packet_version", "flags",
    "pipeline_version", "firmware_version", "step_counter_version", "ppg_version",
]
V3_COLUMNS = [
    "session_id", "host_monotonic", "device_time_us", "packet_seq", "packets_lost",
    "gap_before_s", "possibly_clipped",
    "is_analysis_row", "analysis_seq",
    "tremor_state", "tremor_probability", "tremor_evidence", "tremor_type",
    "tremor_amplitude_dps", "tremor_power", "tremor_snr_db", "arm_movement_rms_dps",
    "tremor_quality",
    "hr_quality_state", "ppg_effective_rate_hz", "motion_coupled_hr",
    "device_rate_hz", "rate_status",
    "nominal_rate_hz", "analysis_hop_samples", "capture_schema_version",
    "tremor_algorithm_version",
]
CAPTURE_COLUMNS = LEGACY_COLUMNS + V3_COLUMNS
# Columns that hold per-analysis (window-level) values, forward-filled
# between analyses. Everything else is per-sample or per-packet.
ANALYSIS_COLUMNS = {
    "classification", "tremor_score", "confidence", "severity", "dominant_frequency",
    "frequency_std", "band_ratio", "best_axis", "axis_agreement", "axis_dominance", "rest_index",
    "motion_state", "motion_rms", "heart_rate", "spo2", "hr_confidence", "spo2_confidence",
    "signal_quality", "sensor_status", "finger_detected", "rmssd", "sdnn", "mean_rr", "pnn50",
    "tremor_state", "tremor_probability", "tremor_evidence", "tremor_type",
    "tremor_amplitude_dps", "tremor_power", "tremor_snr_db", "arm_movement_rms_dps",
    "tremor_quality", "hr_quality_state", "ppg_effective_rate_hz", "motion_coupled_hr",
}


@dataclass
class PacketResult:
    rows: list = field(default_factory=list)
    analyses: list = field(default_factory=list)
    rejected: str | None = None


class RuntimeEngine:
    def __init__(self, fs: float = C.SAMPLE_RATE_HZ, hop_samples: int = C.ANALYSIS_HOP_SAMPLES,
                 window_samples: int = C.WINDOW_SAMPLES, firmware_version: str = "unknown",
                 session_id: str | None = None, step_counter: str = "default"):
        self.fs = fs
        self.hop = hop_samples
        self.window = window_samples
        self.firmware_version = firmware_version
        self.session_id = session_id or uuid.uuid4().hex[:12]

        self.motion = MotionPipeline(fs)
        self.ppg = PPGProcessor(sample_rate=C.PPG_SLOT_RATE_HZ, window_seconds=C.PPG_WINDOW_SECONDS)
        self.steps = (PeriodicStepCounter if step_counter == "periodic" else StepCounter)(sample_rate=fs)
        self._step_gate: str | None = None

        self.unwrapper = P.TimestampUnwrapper()
        self.seq = P.SequenceTracker()
        self.gaps = P.GapDetector()

        self.packet_count = 0
        self.bad_packets = 0
        self.sample_count = 0
        self.analysis_seq = 0
        self.analysis_errors = 0
        self.consecutive_errors = 0
        self.last_error: str | None = None
        self.resets = 0

        self._t0_us: int | None = None
        self._hdr_ts: deque = deque(maxlen=RATE_ESTIMATE_PACKETS)
        self._host_t0: float | None = None
        self._buf = deque(maxlen=window_samples)      # (ax, ay, az, gx, gy, gz, clipped)
        self._since = 0
        self._motion_state: str | None = None
        self._step: dict | None = None
        self.metrics: dict = {}
        self.versions = set()

    # ------------------------------------------------------------------
    def reset_windows(self):
        """Discard windowed/streaming state after a discontinuity."""
        self._buf.clear()
        self._since = 0
        self.motion.reset()
        self.ppg.reset()
        self.steps.break_continuity()
        self.resets += 1

    def device_rate_hz(self) -> float | None:
        if len(self._hdr_ts) < 10:
            return None
        span = self._hdr_ts[-1] - self._hdr_ts[0]
        if span <= 0:
            return None
        return (len(self._hdr_ts) - 1) * P.BATCH_SIZE / (span / 1e6)

    def rate_status(self) -> str:
        r = self.device_rate_hz()
        if r is None:
            return "UNKNOWN"
        err = abs(r - self.fs) / self.fs
        if err > C.RATE_INVALID_FRACTION:
            return "INVALID"
        if err > C.RATE_WARN_FRACTION:
            return "WARN"
        return "OK"

    # ------------------------------------------------------------------
    def process_packet(self, data: bytes, host_monotonic: float | None = None,
                       host_wall: float | None = None) -> PacketResult:
        res = PacketResult()
        host_monotonic = time.monotonic() if host_monotonic is None else host_monotonic
        host_wall = time.time() if host_wall is None else host_wall
        try:
            pkt = P.decode(data, self.unwrapper)
        except P.ProtocolError as e:
            self.bad_packets += 1
            res.rejected = str(e)
            log.warning("rejected packet: %s", e)
            return res

        self.packet_count += 1
        self.versions.add(pkt.version)
        if self._host_t0 is None:
            self._host_t0 = host_monotonic
        lost = self.seq.update(pkt.seq)
        first_us = pkt.samples[0].device_time_us
        gap_s = self.gaps.update(first_us, pkt.samples[-1].device_time_us)
        if gap_s and gap_s > C.MAX_GAP_BEFORE_RESET_S:
            self.reset_windows()
            self._hdr_ts.clear()
        self._hdr_ts.append(first_us)
        if self._t0_us is None:
            self._t0_us = first_us

        for s in pkt.samples:
            self.sample_count += 1
            t = (s.device_time_us - self._t0_us) / 1e6
            self._buf.append((s.ax, s.ay, s.az, s.gx, s.gy, s.gz, s.possibly_clipped))
            self.ppg.ingest(s.ir, s.red)

            if self._step_gate is not None:
                self._step = self.steps.update(s.ax, s.ay, s.az, self._step_gate, now=t)

            fresh = False
            if len(self._buf) >= self.window:
                self._since += 1
                if self._since >= self.hop or not self.metrics or self._needs_first_analysis():
                    self._since = 0
                    fresh = self._analyse(t, pkt)
                    if fresh:
                        res.analyses.append(self.metrics)

            # Every sample is recorded, including the first window's fill
            # (v2 dropped the first 4 s of raw data of every capture);
            # analysis columns stay empty until the first analysis.
            if True:
                res.rows.append(self._row(s, pkt, t, host_monotonic, host_wall, fresh,
                                          lost if s.index_in_packet == 0 else 0,
                                          gap_s if s.index_in_packet == 0 else 0.0))
        return res

    def _needs_first_analysis(self):
        return self.metrics.get("_reset_marker") != self.resets

    # ------------------------------------------------------------------
    def _analyse(self, t: float, pkt: P.Packet) -> bool:
        try:
            arr = np.asarray(self._buf, dtype=float)
            accel, gyro = arr[:, 0:3].T, arr[:, 3:6].T
            clipped = float(arr[:, 6].mean())
            rate_ok = self.rate_status() != "INVALID"
            m = self.motion.process(accel, gyro, t, clipped_fraction=clipped, usable=rate_ok)
            self._motion_state = m["context"]["state"]
            # Tremor guard: a confirmed *rest* tremor (no purposeful movement)
            # is not walking. Withholding the moving gate stops the step
            # counter converting tremor oscillation into steps -- v1.0
            # produced ~23 false steps/min of rest tremor (benchmarks).
            r = m["result"]
            self._step_gate = ("REST" if r["tremor"] and r["tremor_type"] == "REST"
                               else self._motion_state)
            if self._step is None:
                self._step = self.steps.update(*accel[:, -1], self._step_gate, now=t)
            motion_freqs = [m["features"].arm_peak_frequency_hz] if m["features"].arm_rms_dps >= 10 else []
            ppg = self.ppg.analyze(now=t, motion_state=self._motion_state,
                                   motion_frequencies_hz=motion_freqs)
            self.analysis_seq += 1
            self.metrics = self._metrics(m, ppg, pkt, t)
            self.consecutive_errors = 0
            return True
        except Exception:                                    # surfaced, not swallowed
            self.analysis_errors += 1
            self.consecutive_errors += 1
            self.last_error = traceback.format_exc()
            if self.analysis_errors == 1:
                log.error("analysis failed:\n%s", self.last_error)
            if self.consecutive_errors >= MAX_CONSECUTIVE_ANALYSIS_ERRORS:
                raise RuntimeError(
                    f"{self.consecutive_errors} consecutive analysis failures; last:\n{self.last_error}")
            return False

    def _metrics(self, m, ppg, pkt, t) -> dict:
        r, ctx = m["result"], m["context"]
        step = self._step or {}
        hrv = ppg.get("hrv") or {}
        rate = self.device_rate_hz()
        return {
            "_reset_marker": self.resets,
            "classification": "TREMOR" if r["tremor"] else "NO TREMOR",
            "tremor_score": r["score"], "confidence": r["confidence"], "severity": r["severity"],
            "dominant_frequency": r["frequency"], "frequency_std": r["frequency_std"],
            "band_ratio": r["band_ratio"], "best_axis": r["best_axis"],
            "axis_agreement": r["axis_agreement"], "axis_dominance": r["axis_dominance"],
            "rest_index": r["rest_index"],
            "motion_state": ctx["state"], "motion_rms": round(ctx["motion_rms"], 4),
            "steps": step.get("steps"), "cadence": step.get("cadence"),
            "step_rate_hz": step.get("step_rate_hz"), "walking_state": step.get("walking_state"),
            "distance_m": step.get("distance_m"), "active_minutes": step.get("active_minutes"),
            "step_confidence": step.get("step_confidence"),
            "walking_confidence": step.get("walking_confidence"),
            "activity_type": step.get("activity_type"),
            "heart_rate": ppg.get("heart_rate"), "spo2": ppg.get("spo2"),
            "hr_confidence": ppg.get("hr_confidence"), "spo2_confidence": ppg.get("spo2_confidence"),
            "signal_quality": ppg.get("signal_quality"), "sensor_status": ppg.get("sensor_status"),
            "finger_detected": ppg.get("finger_detected"),
            "hr_quality": ppg.get("hr_quality", {}),
            "rmssd": hrv.get("rmssd"), "sdnn": hrv.get("sdnn"), "mean_rr": hrv.get("mean_rr"),
            "pnn50": hrv.get("pnn50"),
            "latest_ir": int(ppg["ir"]) if ppg.get("ir") is not None else 0,
            "latest_red": int(ppg["red"]) if ppg.get("red") is not None else 0,
            "sample_count": self.sample_count, "packet_count": self.packet_count,
            "sampling_rate": round(rate, 3) if rate else None,
            "packet_version": pkt.version, "flags": pkt.flags,
            "timestamp": t, "signal_time_s": round(t, 4),
            "motion_pipeline_state": ctx["state"],
            "pipeline_version": C.PIPELINE_VERSION, "firmware_version": self.firmware_version,
            "step_counter_version": C.STEP_COUNTER_VERSION, "ppg_version": C.PPG_VERSION,
            # v3
            "analysis_seq": self.analysis_seq,
            **{k: r[k] for k in ("tremor_state", "tremor_probability", "tremor_evidence", "tremor_type",
                                 "tremor_amplitude_dps", "tremor_power", "tremor_snr_db",
                                 "arm_movement_rms_dps", "tremor_quality")},
            "hr_quality_state": (C.Quality.RATE_INVALID.value if self.rate_status() == "INVALID"
                                 else ppg.get("hr_quality_state")),
            "ppg_effective_rate_hz": ppg.get("ppg_effective_rate_hz"),
            "motion_coupled_hr": ppg.get("motion_coupled_hr"),
            "device_rate_hz": round(rate, 3) if rate else None,
            "rate_status": self.rate_status(),
            "integrity": self.integrity(),
        }

    def integrity(self) -> dict:
        return {
            "packets": self.packet_count, "bad_packets": self.bad_packets,
            "packets_lost_seq": self.seq.lost, "loss_fraction_seq": round(self.seq.loss_fraction, 5),
            "timestamp_gaps": self.gaps.gaps, "missing_samples_est": self.gaps.missing_samples_est,
            "timestamp_wraps": self.unwrapper.wraps,
            "timestamp_backward_steps": self.unwrapper.backward_steps,
            "window_resets": self.resets, "analysis_errors": self.analysis_errors,
            "protocol_versions": sorted(self.versions),
        }

    def _row(self, s, pkt, t, host_mono, host_wall, fresh, lost, gap_s) -> dict:
        m = self.metrics
        step = self._step or {}
        row = {k: m.get(k) for k in ANALYSIS_COLUMNS}
        row.update({
            "timestamp": host_wall, "sample_timestamp_us": s.device_time_us % P.TIMESTAMP_MODULUS,
            "ax": s.ax, "ay": s.ay, "az": s.az, "gx": s.gx, "gy": s.gy, "gz": s.gz,
            "ir": s.ir, "red": s.red,
            # per-sample step fields (ADR-0003)
            "steps": step.get("steps"), "cadence": step.get("cadence"),
            "step_rate_hz": step.get("step_rate_hz"), "walking_state": step.get("walking_state"),
            "distance_m": step.get("distance_m"), "active_minutes": step.get("active_minutes"),
            "step_confidence": step.get("step_confidence"),
            "walking_confidence": step.get("walking_confidence"),
            "activity_type": step.get("activity_type"),
            "sample_count": self.sample_count, "packet_count": self.packet_count,
            "sampling_rate": m.get("sampling_rate"),
            "packet_version": pkt.version, "flags": pkt.flags,
            "pipeline_version": C.PIPELINE_VERSION, "firmware_version": self.firmware_version,
            "step_counter_version": C.STEP_COUNTER_VERSION, "ppg_version": C.PPG_VERSION,
            "session_id": self.session_id, "host_monotonic": host_mono,
            "device_time_us": s.device_time_us, "packet_seq": pkt.seq, "packets_lost": lost,
            "gap_before_s": gap_s, "possibly_clipped": s.possibly_clipped,
            "is_analysis_row": fresh, "analysis_seq": m.get("analysis_seq"),
            "device_rate_hz": m.get("device_rate_hz"), "rate_status": m.get("rate_status"),
            "nominal_rate_hz": self.fs, "analysis_hop_samples": self.hop,
            "capture_schema_version": C.CAPTURE_SCHEMA_VERSION,
            "tremor_algorithm_version": C.TREMOR_ALGORITHM_VERSION,
        })
        return row
