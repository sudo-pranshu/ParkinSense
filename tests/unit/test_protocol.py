import struct

import pytest

from parkinsense.protocol import packet as P


def _rows(v=0.5):
    return [(0.1 * i, -0.2, 1.0, 10.0 * i, -100.0, v, 100000 + i, 80000 + i) for i in range(P.BATCH_SIZE)]


@pytest.mark.parametrize("version", [1, 2])
def test_roundtrip_exact(version):
    data = P.encode(_rows(), 123456, version=version, seq=7)
    assert len(data) == P.PACKET_SIZE == 208
    pkt = P.decode(data)
    assert pkt.version == version
    assert pkt.seq == (7 if version == 2 else None)
    s = pkt.samples[3]
    sc = P.SCALES[version]
    assert abs(s.gx - 30.0) <= 0.5 / sc.gyro_counts_per_dps
    assert s.ir == 100003 and s.red == 80003
    assert s.device_time_us == 123456 + 3 * P.SAMPLE_PERIOD_US
    # re-encoding decoded values reproduces identical bytes (replay fidelity)
    again = P.encode([(x.ax, x.ay, x.az, x.gx, x.gy, x.gz, x.ir, x.red) for x in pkt.samples],
                     123456, version=version, seq=7)
    assert again == data


def test_v1_wire_layout_unchanged():
    # header <BBHI, sample <hhhhhhII -- the v1 wire contract must never change
    assert struct.calcsize(P.HEADER_FORMAT) == 8 and struct.calcsize(P.SAMPLE_FORMAT) == 20
    assert P.SCALES[1].accel_counts_per_g == 8192.0 and P.SCALES[1].gyro_counts_per_dps == 131.0


def test_v2_range_exceeds_v1():
    big = [(0, 0, 1, 400.0, 0, 0, 0, 0)] * P.BATCH_SIZE
    assert abs(P.decode(P.encode(big, 0, version=2)).samples[0].gx - 400.0) < 0.02
    v1 = P.decode(P.encode(big, 0, version=1)).samples[0]
    assert v1.possibly_clipped and v1.gx < 251


def test_rejects_bad_size_and_version():
    with pytest.raises(P.ProtocolError):
        P.decode(b"\x00" * 100)
    bad = bytearray(P.encode(_rows(), 0))
    bad[0] = 9
    with pytest.raises(P.ProtocolError):
        P.decode(bytes(bad))


def test_timestamp_unwrap_across_2_32():
    u = P.TimestampUnwrapper()
    near = (1 << 32) - 50_000
    a = u.unwrap(near)
    b = u.unwrap(46_160)                 # wrapped
    assert b - a == 96_160 and u.wraps == 1
    u.unwrap(40_000)                     # small backwards step: reported, not "fixed"
    assert u.backward_steps == 1


def test_sequence_tracker_loss_and_wrap():
    t = P.SequenceTracker()
    for s in [65533, 65534, 65535, 0, 3, 3]:
        t.update(s)
    assert t.lost == 2 and t.duplicates_or_reordered == 1


def test_gap_detector():
    g = P.GapDetector()
    g.update(0, 9 * P.SAMPLE_PERIOD_US)
    assert g.update(10 * P.SAMPLE_PERIOD_US, 19 * P.SAMPLE_PERIOD_US) == 0.0
    gap = g.update(40 * P.SAMPLE_PERIOD_US, 49 * P.SAMPLE_PERIOD_US)
    assert gap > 0 and g.gaps == 1 and g.missing_samples_est == 20
