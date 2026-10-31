import json

import pandas as pd

from helpers import packets
from parkinsense.datasets import builder
from parkinsense.replay import replay as R
from parkinsense.runtime.engine import RuntimeEngine
from parkinsense.runtime.recorder import SessionRecorder
from parkinsense.synthetic import signals as S

REF_V1 = "data/reference/ble_v1_104hz/parkinsense_20260630_123551.csv"


def _live_session(tmp_path):
    sig, _ = S.concatenate([S.rest(seconds=8, seed=1), S.rest_tremor(seconds=12, seed=1, amp=30)])
    p = S.ppg(seconds=20, seed=1)
    ir, red = S.ppg_to_slots(p, path="v2")
    eng = RuntimeEngine(session_id="live")
    with SessionRecorder(eng, root=tmp_path) as rec:
        for d in packets(sig, ir, red, version=2):
            rec.write_rows(eng.process_packet(d).rows)
    return rec.dir, eng


def test_recorder_lifecycle(tmp_path):
    d, eng = _live_session(tmp_path)
    meta = json.loads((d / "metadata.json").read_text())
    assert meta["status"] == "COMPLETE" and meta["pipeline_version"] == "3.0.0"
    assert meta["measured"]["rows_written"] > 0 and meta["integrity"]["bad_packets"] == 0
    assert (tmp_path / "latest.json").exists()


def test_live_and_replay_are_identical(tmp_path):
    """The replay engine exercises the real implementation: same packets -> same outputs."""
    d, _ = _live_session(tmp_path)
    live = pd.read_csv(d / "capture.csv")
    rp = pd.DataFrame(R.replay(d / "capture.csv")["rows"])
    live_a = live[live.is_analysis_row].reset_index(drop=True)
    rp_a = rp[rp.is_analysis_row].reset_index(drop=True)
    # replay starts from the first *recorded* row (after the live window filled),
    # so align on device time
    m = live_a.merge(rp_a, on="device_time_us", suffixes=("_l", "_r"))
    assert len(m) > 10
    late = m[m.device_time_us >= m.device_time_us.min() + 5_000_000]
    assert (late.classification_l == late.classification_r).all()
    assert (late.dominant_frequency_l - late.dominant_frequency_r).abs().max() < 1e-9


def test_replay_is_deterministic():
    a = R.replay(REF_V1)["analyses"]
    b = R.replay(REF_V1)["analyses"]
    keys = ("classification", "tremor_probability", "heart_rate", "steps", "dominant_frequency")
    assert [[x[k] for k in keys] for x in a] == [[x[k] for k in keys] for x in b]


def test_dataset_builder_one_row_per_window(tmp_path):
    meta = builder.build([REF_V1], tmp_path / "ds", "0.0.1-test")
    w = pd.read_csv(tmp_path / "ds" / "windows.csv")
    assert meta["windows"] == len(w) and w["analysis_seq"].is_unique
    rec = next(iter(meta["recordings"].values()))
    assert rec["accepted"] and abs(rec["rate_hz"] - 104) < 1
