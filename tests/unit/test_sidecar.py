"""Biomarker sidecar (biomarkers.jsonl, schema biomarkers/1.0): state rules, replay determinism, recorder output."""
import json

import numpy as np
import pytest

from helpers import packets
from parkinsense import config as C
from parkinsense.analytics import sidecar as SC
from parkinsense.protocol import packet as P
from parkinsense.replay import replay as R
from parkinsense.runtime.engine import RuntimeEngine
from parkinsense.runtime.recorder import SessionRecorder
from parkinsense.synthetic import signals as S

REF_V1 = "data/reference/ble_v1_104hz/parkinsense_20260630_123551.csv"
HAS = ("VALID", "LOW_CONFIDENCE")


def _m(**kw):
    base = {"analysis_seq": 7, "signal_time_s": 12.5, "flags": 0, "hr_quality_state": "VALID", "heart_rate": 62.0,
            "hr_confidence": 0.9, "rmssd": 40.0, "sdnn": 50.0, "pnn50": 12.0, "mean_rr": 970.0, "spo2": 97.0,
            "tremor_quality": "VALID", "tremor_probability": 0.1, "tremor_state": "NO_TREMOR",
            "classification": "NO TREMOR", "hrv_n_intervals": 9, "hrv_artifact_pct": 0.0, "hrv_confidence": 0.8}
    return {**base, **kw}


def _b(m):
    return SC.biomarker_record(m)["biomarkers"]


def test_valid_inputs_state_rules():
    b = _b(_m())
    assert b["heart_rate"]["state"] == "VALID" and b["heart_rate"]["value"] == 62.0
    # 10 s HRV: never VALID, exploratory, excluded from summaries
    h = b["hrv_10s"]
    assert h["state"] == "LOW_CONFIDENCE" and h["exploratory"] and h["include_in_summaries"] is False
    assert {"UNVALIDATED_PPG_HRV", "EXPLORATORY_10S_WINDOW"} <= set(h["reasons"])
    assert h["window_s"] == 10.0 and h["n_nn_intervals"] == 9 and h["value"]["rmssd_ms"] == 40.0
    # SpO2: never VALID
    assert b["spo2"]["state"] == "LOW_CONFIDENCE" and "UNCALIBRATED_ESTIMATE" in b["spo2"]["reasons"]
    assert b["tremor"]["state"] == "VALID" and b["tremor"]["severity"] == "NOT_ASSESSED"


@pytest.mark.parametrize("q,expected", [("MOTION_ARTIFACT", "INVALID"), ("NO_CONTACT", "INVALID"),
                                        ("DATA_GAP", "INVALID"), ("SENSOR_FAULT", "INVALID"),
                                        ("RATE_INVALID", "INVALID"), ("INSUFFICIENT_DATA", "INSUFFICIENT_DATA")])
def test_value_is_null_unless_valid_or_low_confidence(q, expected):
    # numbers deliberately present in the metrics: the sidecar must still publish null
    b = _b(_m(hr_quality_state=q, tremor_quality=q))
    for name in ("heart_rate", "hrv_10s", "spo2", "tremor"):
        assert b[name]["state"] == expected and b[name]["value"] is None, name
    assert expected != "INVALID" or b["heart_rate"]["reasons"]


def test_absent_finger_is_flagged_invalid_with_reason():
    b = _b(_m(hr_quality_state="NO_CONTACT", heart_rate=None, rmssd=None, spo2=None))
    assert b["heart_rate"]["state"] == "INVALID" and "NO_FINGER_CONTACT" in b["heart_rate"]["reasons"]


def test_noise_rejected_window_is_invalid():
    b = _b(_m(hr_quality_state="INSUFFICIENT_DATA", ppg_noise_rejected=True, heart_rate=None, rmssd=None, spo2=None))
    assert b["heart_rate"]["state"] == "INVALID" and b["heart_rate"]["reasons"] == ["NO_PULSE_PERIODICITY"]


def test_hardware_fault_flags():
    b = _b(_m(flags=int(P.PacketFlags.PPG_FAULT)))
    assert all(b[k]["state"] == "SENSOR_UNAVAILABLE" and b[k]["value"] is None for k in ("heart_rate", "hrv_10s", "spo2"))
    assert b["tremor"]["state"] == "VALID"            # IMU unaffected
    b = _b(_m(flags=int(P.PacketFlags.IMU_FAULT), tremor_quality="SENSOR_FAULT", classification="UNKNOWN"))
    assert b["tremor"]["state"] == "INVALID" and "IMU_FAULT_FLAG" in b["tremor"]["reasons"]
    assert b["tremor"]["value"] is None


def test_missing_value_never_valid():
    b = _b(_m(heart_rate=None))
    assert b["heart_rate"]["state"] == "INSUFFICIENT_DATA" and b["heart_rate"]["value"] is None


def test_independent_version_and_strict_json():
    rec = SC.biomarker_record(_m())
    assert rec["schema"] == "biomarkers/1.0" and rec["biomarker_version"] == C.BIOMARKER_VERSION
    assert C.BIOMARKER_VERSION != C.PIPELINE_VERSION
    json.loads(SC.dumps(rec))                             # allow_nan=False -> raises on NaN


def test_replay_sidecar_is_deterministic_and_matches_analyses(tmp_path):
    for d in ("a", "b"):
        r = R.replay(REF_V1, out_dir=tmp_path / d)
    a = (tmp_path / "a" / "biomarkers.jsonl").read_bytes()
    assert a == (tmp_path / "b" / "biomarkers.jsonl").read_bytes()
    recs = [json.loads(x) for x in a.decode().splitlines()]
    assert len(recs) == len(r["analyses"]) and recs[0]["schema"] == "biomarkers/1.0"
    for rec in recs:
        for v in rec["biomarkers"].values():
            assert (v["value"] is None) == (v["state"] not in HAS)
            assert v["state"] != "VALID" or v["value"] is not None
    # the real recording's finger windows are all noise-rejected -> INVALID, never a number
    assert not any(r_["biomarkers"]["heart_rate"]["state"] in HAS for r_ in recs)


def test_recorder_writes_sidecar_and_metadata(tmp_path):
    sig, _ = S.concatenate([S.rest(seconds=8, seed=1), S.rest_tremor(seconds=12, seed=1, amp=30)])
    ir, red = S.ppg_to_slots(S.ppg(seconds=20, seed=1), path="v2")
    eng = RuntimeEngine(session_id="sc")
    with SessionRecorder(eng, root=tmp_path) as rec:
        for d in packets(sig, ir, red, version=2):
            res = eng.process_packet(d)
            rec.write_rows(res.rows)
            rec.write_analyses(res.analyses)
    lines = (rec.dir / "biomarkers.jsonl").read_text().splitlines()
    assert len(lines) == eng.analysis_seq > 0
    assert [json.loads(x)["analysis_seq"] for x in lines] == list(range(1, eng.analysis_seq + 1))
    meta = json.loads((rec.dir / "metadata.json").read_text())
    assert meta["biomarkers"] == {"file": "biomarkers.jsonl", "schema": "biomarkers/1.0",
                                  "version": C.BIOMARKER_VERSION}
    assert np.isfinite(meta["measured"]["samples"])
