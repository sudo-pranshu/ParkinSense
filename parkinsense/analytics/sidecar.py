"""
Biomarker sidecar: `biomarkers.jsonl`, one JSON object per analysis window (schema `biomarkers/1.0`).

Why a sidecar: the 79-column capture schema is additive-only and per-sample; biomarker *states* (why a value is or is
not trustworthy) need structure that does not fit it. The sidecar is a pure function of the engine's per-analysis
metrics, so a replay of a capture produces a byte-identical file (deterministic, tested). It is versioned
independently (`config.BIOMARKER_VERSION`) of the pipeline.

State vocabulary and rules (value is null unless the state is VALID or LOW_CONFIDENCE):
  VALID, LOW_CONFIDENCE, INVALID (measurement attempted, rejected), INSUFFICIENT_DATA (not enough clean signal yet),
  SENSOR_UNAVAILABLE (hardware reports the sensor as faulty), NOT_ASSESSED (no method / not applicable).

Evidence class: automated tests only. No state here is hardware- or clinically validated. In particular:
  * 10 s HRV is EXPLORATORY: capped at LOW_CONFIDENCE, flagged `UNVALIDATED_PPG_HRV`, `include_in_summaries: false`.
  * SpO2 is an uncalibrated estimate: never VALID.
"""

from __future__ import annotations

import json
from enum import Enum
from pathlib import Path

from parkinsense import config as C
from parkinsense.protocol import packet as P


class BState(str, Enum):
    VALID = "VALID"
    LOW_CONFIDENCE = "LOW_CONFIDENCE"
    INVALID = "INVALID"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    SENSOR_UNAVAILABLE = "SENSOR_UNAVAILABLE"
    NOT_ASSESSED = "NOT_ASSESSED"


_HAS_VALUE = (BState.VALID, BState.LOW_CONFIDENCE)

# engine quality -> (sidecar state, reason)
_MAP = {
    "VALID": (BState.VALID, None),
    "LOW_CONFIDENCE": (BState.LOW_CONFIDENCE, None),
    "MOTION_ARTIFACT": (BState.INVALID, "MOTION_ARTIFACT"),
    "NO_CONTACT": (BState.INVALID, "NO_FINGER_CONTACT"),
    "INSUFFICIENT_DATA": (BState.INSUFFICIENT_DATA, None),
    "DATA_GAP": (BState.INVALID, "DATA_GAP"),
    "SENSOR_FAULT": (BState.INVALID, "SENSOR_FAULT"),
    "RATE_INVALID": (BState.INVALID, "RATE_INVALID"),
}


def _entry(state: BState, value, unit, reasons, **extra) -> dict:
    return {"value": value if state in _HAS_VALUE else None, "unit": unit, "state": state.value,
            "reasons": reasons, **extra}


def _base_state(quality, has_value: bool, ppg_fault: bool, noise_rejected: bool):
    reasons: list[str] = []
    if ppg_fault:
        return BState.SENSOR_UNAVAILABLE, ["PPG_FAULT_FLAG"]
    state, why = _MAP.get(quality, (BState.INSUFFICIENT_DATA, None))
    if why:
        reasons.append(why)
    if noise_rejected:
        state, reasons = BState.INVALID, ["NO_PULSE_PERIODICITY"]
    if state in _HAS_VALUE and not has_value:
        state, reasons = BState.INSUFFICIENT_DATA, reasons + ["NO_VALUE"]
    return state, reasons


def biomarker_record(m: dict) -> dict:
    """One analysis' metrics dict -> one sidecar record."""
    flags = int(m.get("flags") or 0)
    ppg_fault = bool(flags & P.PacketFlags.PPG_FAULT)
    noise = bool(m.get("ppg_noise_rejected"))
    q = m.get("hr_quality_state")

    st, rs = _base_state(q, m.get("heart_rate") is not None, ppg_fault, noise)
    hr = _entry(st, m.get("heart_rate"), "bpm", rs, confidence=m.get("hr_confidence"))

    # 10 s HRV: exploratory, never VALID
    st, rs = _base_state(q, m.get("rmssd") is not None, ppg_fault, noise)
    if st in _HAS_VALUE:
        st, rs = BState.LOW_CONFIDENCE, rs + ["UNVALIDATED_PPG_HRV", "EXPLORATORY_10S_WINDOW"]
    elif st == BState.INSUFFICIENT_DATA and m.get("hrv_withheld_reason"):
        rs = rs + ["HRV_WITHHELD"]
    hrv = _entry(
        st, {"rmssd_ms": m.get("rmssd"), "sdnn_ms": m.get("sdnn"), "pnn50_pct": m.get("pnn50"),
             "mean_rr_ms": m.get("mean_rr")}, "ms", rs,
        window_s=C.PPG_WINDOW_SECONDS, n_nn_intervals=m.get("hrv_n_intervals"),
        artefact_pct=m.get("hrv_artifact_pct"), hrv_confidence=m.get("hrv_confidence"),
        withheld_reason=m.get("hrv_withheld_reason"), exploratory=True, include_in_summaries=False)

    # SpO2: uncalibrated estimate, never VALID
    st, rs = _base_state(q, m.get("spo2") is not None, ppg_fault, noise)
    if st in _HAS_VALUE:
        st, rs = BState.LOW_CONFIDENCE, rs + ["UNCALIBRATED_ESTIMATE"]
    spo2 = _entry(st, m.get("spo2"), "%", rs, calibrated=False)

    # Tremor: probability from the temporal model; unknown windows (IMU fault / gaps) are INVALID, not "no tremor"
    tq = m.get("tremor_quality")
    imu_fault = bool(flags & P.PacketFlags.IMU_FAULT)
    tst, why = _MAP.get(tq, (BState.INSUFFICIENT_DATA, None))
    trs = [why] if why else []
    if m.get("classification") == "UNKNOWN":
        tst, trs = BState.INVALID, trs or ["UNKNOWN_WINDOW"]
    if imu_fault and tst not in _HAS_VALUE:
        trs.append("IMU_FAULT_FLAG")
    if tst in _HAS_VALUE and m.get("tremor_probability") is None:
        tst, trs = BState.INSUFFICIENT_DATA, trs + ["NO_VALUE"]
    tremor = _entry(tst, m.get("tremor_probability"), "probability", trs,
                    tremor_state=m.get("tremor_state"), severity="NOT_ASSESSED")

    return {"schema": C.BIOMARKER_SCHEMA, "biomarker_version": C.BIOMARKER_VERSION,
            "analysis_seq": m.get("analysis_seq"), "signal_time_s": m.get("signal_time_s"),
            "biomarkers": {"heart_rate": hr, "hrv_10s": hrv, "spo2": spo2, "tremor": tremor}}


def dumps(rec: dict) -> str:
    return json.dumps(rec, sort_keys=True, separators=(",", ":"), allow_nan=False)


def write_sidecar(path, analyses) -> int:
    """Write a complete sidecar for `analyses` (replay). Returns the number of records."""
    n = 0
    with open(Path(path), "w", encoding="utf-8", newline="\n") as f:
        for m in analyses:
            f.write(dumps(biomarker_record(m)) + "\n")
            n += 1
    return n
