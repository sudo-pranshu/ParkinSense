"""Wear-state monitor tests. All inputs are SIMULATED; nothing here is hardware evidence."""

import numpy as np
import pytest

from parkinsense.wear import (
    ImuState, PowerState, PpgState, WearConfig, WearMonitor, WearState, analyze_arrays,
)

FS = 104.0
NO_FINGER, FINGER = 1_600.0, 109_000.0            # IR levels recorded in the v4 firmware source


class Sim:
    """Concatenate motion / contact segments into one stream, then run it through the monitor."""

    def __init__(self, seed=0, cfg=None):
        self.rng = np.random.default_rng(seed)
        self.cfg = cfg or WearConfig(expected_rate_hz=FS)
        self.t0 = 0.0
        self.parts = []

    def seg(self, seconds, motion="table", ir=NO_FINGER, imu_ok=True, ppg_ok=True):
        n = int(seconds * FS)
        t = self.t0 + np.arange(n) / FS
        sd = {"table": 0.0007, "sleep": 0.012, "moving": 0.15}[motion]
        acc = np.tile([0.0, 0.0, 1.0], (n, 1)) + self.rng.normal(0, sd, (n, 3))
        if motion == "moving":                              # slow orientation changes as well
            acc += 0.4 * np.sin(2 * np.pi * 0.3 * t)[:, None] * np.array([1.0, 0.5, 0.0])
        gyro = self.rng.normal(0, 0.1 if motion == "table" else 5.0, (n, 3))
        if not imu_ok:
            acc[:] = 0.0
            gyro[:] = 0.0
        irv = np.full(n, ir) + self.rng.normal(0, 30, n)
        self.parts.append((t, acc, gyro, irv, np.full(n, imu_ok), np.full(n, ppg_ok)))
        self.t0 = t[-1] + 1 / FS
        return self

    def gap(self, seconds):
        self.t0 += seconds
        return self

    def run(self):
        cat = [np.concatenate(x) for x in zip(*self.parts)]
        return analyze_arrays(cat[0], cat[1], cat[2], cat[3], cat[4], cat[5], config=self.cfg, fs=FS)


def states(m):
    return [e[1] for e in m.epoch_log]


def first(m, state):
    return next((e[0] for e in m.epoch_log if e[1] == state.value), None)


def test_worn_with_contact():
    m = Sim().seg(60, "moving", FINGER).run()
    assert m.state == WearState.WORN and m.status.physiology_allowed
    assert m.status.ppg_state == PpgState.CONTACT and m.status.imu_state == ImuState.STREAMING
    assert m.status.power_state == PowerState.UNKNOWN and m.status.inferred


def test_still_alone_is_never_removal_with_contact():
    """Motionless sleeper with optical contact for an hour: stays WORN."""
    m = Sim().seg(3600, "table", FINGER).run()
    assert set(states(m)) <= {"UNKNOWN", "WORN"} and m.state == WearState.WORN


def test_contact_loss_alone_is_never_removal():
    """Moving wrist, finger off the sensor for an hour: WORN_PPG_UNAVAILABLE, never removed."""
    m = Sim().seg(60, "moving", FINGER).seg(3600, "moving", NO_FINGER).run()
    assert m.state == WearState.WORN_PPG_UNAVAILABLE
    assert not {"POSSIBLY_REMOVED", "REMOVED"} & set(states(m))
    assert m.status.activity_allowed and not m.status.physiology_allowed


def test_sleeping_without_contact_is_not_removal():
    """Worn, no PPG contact, micro-movements of a sleeper (above bench noise): never removed."""
    m = Sim().seg(60, "moving", FINGER).seg(4 * 3600, "sleep", NO_FINGER).run()
    assert not {"POSSIBLY_REMOVED", "REMOVED"} & set(states(m))
    assert m.state == WearState.WORN_PPG_UNAVAILABLE


def test_table_removal_needs_both_conditions_and_hysteresis():
    m = Sim().seg(60, "moving", FINGER).seg(1200, "table", NO_FINGER).run()
    t_remove = 60.0
    t_possible = first(m, WearState.POSSIBLY_REMOVED)
    t_removed = first(m, WearState.REMOVED)
    cfg = m.cfg
    # the removal clock starts once contact loss is established; never earlier than the configured durations
    assert t_possible - t_remove >= cfg.possibly_removed_s
    assert t_removed - t_possible > 0 and t_removed - t_remove >= cfg.removed_s
    assert t_removed - t_remove < cfg.removed_s + 60            # and it does arrive
    assert m.state == WearState.REMOVED and not m.status.activity_allowed and not m.status.physiology_allowed
    assert m.transition_count <= 4


def test_ppg_fault_is_not_contact_loss():
    """A faulted PPG sensor on a still device must not drive removal (fault is no evidence)."""
    m = Sim().seg(60, "moving", FINGER).seg(3600, "table", NO_FINGER, ppg_ok=False).run()
    assert not {"POSSIBLY_REMOVED", "REMOVED"} & set(states(m))
    assert m.state == WearState.WORN_PPG_UNAVAILABLE and m.status.ppg_state == PpgState.FAULT


def test_imu_fault_zeros_do_not_look_still():
    """IMU_FAULT packets carry zeros. They must not be read as the stillness of a removed device."""
    m = Sim().seg(60, "moving", FINGER).seg(3600, "table", NO_FINGER, imu_ok=False).run()
    assert not {"POSSIBLY_REMOVED", "REMOVED"} & set(states(m))
    assert m.status.imu_state == ImuState.FAULT


def test_possibly_removed_is_cancelled_by_motion():
    m = Sim().seg(60, "moving", FINGER).seg(420, "table", NO_FINGER).seg(60, "moving", NO_FINGER).run()
    assert "POSSIBLY_REMOVED" in states(m)
    assert m.state == WearState.WORN_PPG_UNAVAILABLE and "REMOVED" not in states(m)


def test_rewear_by_contact_goes_through_resuming():
    m = Sim().seg(60, "moving", FINGER).seg(1200, "table", NO_FINGER).seg(60, "moving", FINGER).run()
    s = states(m)
    assert "REMOVED" in s and "RESUMING" in s and s.index("RESUMING") > s.index("REMOVED")
    assert m.state == WearState.WORN
    assert [x["to"] for x in m.transitions][-2:] == ["RESUMING", "WORN"]


def test_table_bumps_are_not_rewear_but_sustained_motion_is():
    sim = Sim().seg(60, "moving", FINGER).seg(1200, "table", NO_FINGER)
    for _ in range(5):                                       # five 3 s bumps on the table
        sim.seg(3, "moving", NO_FINGER).seg(60, "table", NO_FINGER)
    m = sim.run()
    assert m.state == WearState.REMOVED
    m = sim.seg(90, "moving", NO_FINGER).run()                # picked up and carried for 90 s
    assert m.state == WearState.WORN_PPG_UNAVAILABLE
    assert m.status.evidence == "PPG_UNAVAILABLE_ASSUMED_WORN" or m.status.evidence == "MOTION_ASSUMED_WORN"


def test_gap_forces_resuming_but_not_from_removed():
    m = Sim().seg(120, "moving", FINGER).gap(30).seg(60, "moving", FINGER).run()
    assert "RESUMING" in states(m) and m.state == WearState.WORN and m.gaps == 1
    m = Sim().seg(60, "moving", FINGER).seg(1200, "table", NO_FINGER).gap(600).seg(120, "table", NO_FINGER).run()
    assert m.state == WearState.REMOVED


def test_contact_flicker_does_not_chatter():
    sim = Sim().seg(30, "moving", FINGER)
    for _ in range(60):                                      # finger on for 4 s, off for 4 s, for 8 minutes
        sim.seg(4, "moving", FINGER).seg(4, "moving", NO_FINGER)
    m = sim.run()
    assert m.transition_count <= 6


def test_config_validation():
    with pytest.raises(ValueError):
        WearConfig(possibly_removed_s=600, removed_s=300)
    with pytest.raises(ValueError):
        WearConfig(contact_on_s=5, contact_off_s=2)
    with pytest.raises(ValueError):
        WearConfig(still_acc_sd_g=0)


def test_thresholds_are_configurable():
    cfg = WearConfig(expected_rate_hz=FS, possibly_removed_s=60, removed_s=120)
    m = Sim(cfg=cfg).seg(30, "moving", FINGER).seg(300, "table", NO_FINGER).run()
    assert m.state == WearState.REMOVED
    assert first(m, WearState.REMOVED) < 30 + 160


def test_out_of_order_and_incomplete_epochs_are_counted_not_crashing():
    m = WearMonitor(WearConfig(expected_rate_hz=FS))
    t = np.arange(0, 10, 1 / FS)
    acc = np.tile([0, 0, 1.0], (len(t), 1))
    m.update_block(t, acc, None, np.full(len(t), FINGER))
    m.update_block(t[:50], acc[:50], None, np.full(50, FINGER))   # late data
    m.flush()
    assert m.out_of_order > 0 and m.state == WearState.WORN
    assert m.summary()["note"].startswith("wear state is INFERRED")


# ---------------------------------------------------------------- runtime integration (simulated packets)
FAST = WearConfig(expected_rate_hz=FS, possibly_removed_s=60, removed_s=120)


def _packets(seconds, motion, ir, seq0=0, ts0=0, version=2, flags=0, rng=None):
    from parkinsense.protocol import packet as P
    rng = rng or np.random.default_rng(1)
    out, n = [], int(seconds * FS / 10)
    for k in range(n):
        sd = {"table": 0.0007, "moving": 0.15}[motion]
        rows = [(rng.normal(0, sd), rng.normal(0, sd), 1.0 + rng.normal(0, sd),
                 rng.normal(0, 0.1 if motion == "table" else 20.0), rng.normal(0, 0.1), rng.normal(0, 0.1),
                 int(ir), int(ir * 0.8)) for _ in range(10)]
        out.append(P.encode(rows, (ts0 + int(k * 10 * 9615)) % 2**32, version=version, seq=(seq0 + k) % 65536,
                            flags=flags))
    return out, ts0 + n * 10 * 9615, seq0 + n


def test_engine_default_has_no_wear_monitor_and_metadata_unchanged():
    from parkinsense.runtime.engine import RuntimeEngine
    e = RuntimeEngine()
    assert e.wear is None
    pk, _, _ = _packets(20, "moving", FINGER)
    for d in pk:
        e.process_packet(d)
    assert e.wear is None


@pytest.mark.parametrize("version", [1, 2])
def test_engine_wear_monitor_both_protocol_versions(version):
    from parkinsense.runtime.engine import RuntimeEngine
    e = RuntimeEngine(wear_monitor=FAST)
    pk, ts, seq = _packets(60, "moving", FINGER, version=version)
    for d in pk:
        e.process_packet(d)
    assert e.wear.state == WearState.WORN
    pk, ts, seq = _packets(200, "table", NO_FINGER, seq0=seq, ts0=ts, version=version)
    for d in pk:
        e.process_packet(d)
    assert e.wear.state == WearState.REMOVED
    assert e.step_algorithm == "default" and e.integrity()["packets_lost_seq"] == 0


def test_engine_imu_and_ppg_fault_flags_reach_the_monitor():
    from parkinsense.protocol import packet as P
    from parkinsense.runtime.engine import RuntimeEngine
    e = RuntimeEngine(wear_monitor=FAST)
    pk, ts, seq = _packets(30, "moving", FINGER)
    for d in pk:
        e.process_packet(d)
    pk, ts, seq = _packets(200, "table", NO_FINGER, seq0=seq, ts0=ts, flags=int(P.PacketFlags.IMU_FAULT))
    for d in pk:
        e.process_packet(d)
    assert e.wear.state != WearState.REMOVED and e.wear.status.imu_state == ImuState.FAULT


def test_recorder_metadata_includes_wear_block_only_when_enabled(tmp_path):
    from parkinsense.runtime.engine import RuntimeEngine
    from parkinsense.runtime.recorder import SessionRecorder
    for flag in (False, True):
        e = RuntimeEngine(wear_monitor=flag)
        pk, _, _ = _packets(5, "moving", FINGER)
        for d in pk:
            e.process_packet(d)
        md = SessionRecorder(e, tmp_path / str(flag)).metadata("COMPLETE")
        assert ("wear" in md) is flag
        if flag:
            assert md["wear"]["wear_monitor_version"] and "config" in md["wear"]



def test_possibly_removed_lapses_when_evidence_disappears():
    """IMU faults for a minute remove the stillness evidence without being motion: POSSIBLY_REMOVED is cancelled."""
    m = Sim().seg(60, "moving", FINGER).seg(420, "table", NO_FINGER).seg(90, "table", NO_FINGER, imu_ok=False).run()
    s = states(m)
    assert "POSSIBLY_REMOVED" in s and "REMOVED" not in s
    assert m.state == WearState.WORN_PPG_UNAVAILABLE
    assert m.transitions[-1]["reason"] == "EVIDENCE_LAPSED"


def test_capture_file_roundtrip_and_cli(tmp_path, capsys):
    """Record simulated packets with the wear monitor on, then analyse the capture offline."""
    from parkinsense.runtime.engine import RuntimeEngine
    from parkinsense.runtime.recorder import SessionRecorder
    from parkinsense.wear.api import analyze_file, main
    e = RuntimeEngine(wear_monitor=FAST)
    pk, ts, seq = _packets(40, "moving", FINGER)
    pk2, _, _ = _packets(200, "table", NO_FINGER, seq0=seq, ts0=ts)
    with SessionRecorder(e, tmp_path) as rec:
        for d in pk + pk2:
            rec.write_rows(e.process_packet(d).rows)
    cap = rec.dir / "capture.csv"
    rep = analyze_file(cap, FAST)
    assert rep["final_state"] == "REMOVED" and rep["source"]["kind"] == "capture_v3" and len(rep["source"]["sha256"]) == 64
    assert rep["final_state"] == e.wear.state.value                      # offline and live agree
    main([str(cap), "--set", "possibly_removed_s=60", "--set", "removed_s=120", "--out", str(tmp_path / "w.json")])
    assert (tmp_path / "w.json").exists() and "REMOVED" in capsys.readouterr().out
    md = __import__("json").loads((rec.dir / "metadata.json").read_text())
    assert md["wear"]["final_state"] == "REMOVED" and md["metadata_revision"] == 2
