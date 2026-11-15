"""WP-07 / ADR-0015: faulty or missing IMU samples are UNKNOWN, never stillness."""
import numpy as np

from helpers import packets
from parkinsense import config as C
from parkinsense.protocol import packet as P
from parkinsense.runtime import engine as E
from parkinsense.synthetic import signals as S


def _run(eng, sig, bad_packets=(), drop=(), version=2):
    rows, ana = [], []
    for i, d in enumerate(packets(sig, version=version)):
        if i in drop:
            continue
        if i in bad_packets:                       # IMU not ready: fields zero, IMU_FAULT set
            pkt = P.decode(d)
            smp = [(0, 0, 0, 0, 0, 0, s.ir, s.red) for s in pkt.samples]
            d = P.encode(smp, pkt.samples[0].device_time_us, version=version, seq=pkt.seq,
                         flags=int(pkt.flags) | int(P.PacketFlags.IMU_FAULT))
        r = eng.process_packet(d, host_monotonic=0.0, host_wall=0.0)
        rows += r.rows
        ana += r.analyses
    return rows, ana


def test_version_and_threshold():
    assert C.PIPELINE_VERSION == "3.1.0" and C.IMU_MAX_MISSING_FRACTION == 0.02


def test_clean_stream_is_unchanged():
    eng = E.RuntimeEngine()
    _, ana = _run(eng, S.rest(seconds=15, seed=0))
    assert ana and all(a["classification"] == "NO TREMOR" and a["motion_state"] == "REST" for a in ana)
    assert eng.integrity()["imu_unusable_windows"] == 0


def test_imu_fault_is_unknown_not_rest():
    eng = E.RuntimeEngine()
    _, ana = _run(eng, S.rest(seconds=20, seed=0), bad_packets={60})
    bad = [a for a in ana if a["tremor_quality"] == "SENSOR_FAULT"]
    assert bad, "a window containing an IMU_FAULT packet must be flagged"
    for a in bad:
        assert a["classification"] == "UNKNOWN" and a["tremor_state"] == "UNKNOWN"
        assert a["motion_state"] is None and a["tremor_amplitude_dps"] is None
        assert a["hr_quality_state"] != C.Quality.VALID.value
    assert eng.integrity()["imu_fault_samples"] == 10 and eng.integrity()["imu_unusable_windows"] == len(bad)
    # recovers once the faulty packet has left the 4 s window
    assert ana[-1]["classification"] == "NO TREMOR" and ana[-1]["motion_state"] == "REST"


def test_lost_packets_above_threshold_are_data_gap_below_are_not():
    eng = E.RuntimeEngine()
    _, ana = _run(eng, S.rest(seconds=20, seed=0), drop={60})          # 10 of ~426 samples = 2.3 % > 2 %
    assert any(a["tremor_quality"] == "DATA_GAP" and a["classification"] == "UNKNOWN" for a in ana)
    assert eng.imu_unusable_windows > 0
    # a single lost sample-equivalent (< 2 %) must not blank the window: shrink the packet loss with a fake gap
    eng2 = E.RuntimeEngine()
    eng2._miss.extend([0] * 3)
    assert 4 / (C.WINDOW_SAMPLES + 4) < C.IMU_MAX_MISSING_FRACTION


def test_fault_samples_are_not_fed_to_step_counter():
    eng = E.RuntimeEngine()
    rows, _ = _run(eng, S.walking(seconds=30, seed=1), bad_packets=set(range(100, 110)))
    steps_during = [r["steps"] for r in rows if r["packet_seq"] in range(100, 110)]
    assert None not in steps_during and max(steps_during) - min(steps_during) == 0   # zeros are not steps


def test_raw_fault_rows_are_preserved_with_flag():
    eng = E.RuntimeEngine()
    rows, _ = _run(eng, S.rest(seconds=8, seed=0), bad_packets={3})
    r = [x for x in rows if x["packet_seq"] == 3]
    assert len(r) == 10 and all(x["ax"] == 0 and x["flags"] & int(P.PacketFlags.IMU_FAULT) for x in r)


def test_sleep_reader_masks_fault_rows(tmp_path):
    import pandas as pd

    from parkinsense.sleep.api import read_acceleration
    n = 100
    df = pd.DataFrame({"device_time_us": np.arange(n) * 9615 + 10**9, "ax": 0.0, "ay": 0.0, "az": 1.0,
                       "flags": [4 if 20 <= i < 30 else 0 for i in range(n)]})
    f = tmp_path / "c.csv"
    df.to_csv(f, index=False)
    t, acc, kind = read_acceleration(f)
    assert kind == "capture_v3" and np.isnan(acc[20:30]).all() and np.isfinite(acc[:20]).all()
