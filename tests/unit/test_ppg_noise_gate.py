"""WP-09 Stage B / ADR-0017: noise-only PPG is rejected; low-perfusion pulses are protected."""
import numpy as np
import pytest

from helpers import packets
from parkinsense.ppg import algorithms as A
from parkinsense.ppg import processor as PP
from parkinsense.runtime import engine as E
from parkinsense.synthetic import signals as S

FS = 104.0


def _run(ir, red, tail=20):
    p = PP.PPGProcessor(sample_rate=FS)
    out, step = [], int(0.5 * FS)
    for i in range(len(ir)):
        p.ingest(int(ir[i]), int(red[i]))
        if i and i % step == 0 and i > 12 * FS:
            out.append(p.analyze(now=i / FS, motion_state="REST"))
    return out[-tail:]


def _noise(kind, seed, ac=50.0, n=int(40 * FS)):
    rng = np.random.default_rng(seed)
    if kind == "white":
        x = rng.normal(0, ac, n)
    else:                                              # band-limited to the cardiac-looking 0.7-3.5 Hz
        from scipy.signal import butter, filtfilt
        b, a = butter(2, [0.7, 3.5], btype="band", fs=FS)
        x = filtfilt(b, a, rng.normal(0, 1, n))
        x *= ac / x.std()
    return 110_000 + x, 88_000 + 0.8 * x


@pytest.mark.parametrize("kind", ["white", "bandlimited"])
@pytest.mark.parametrize("seed", [0, 1, 2])
def test_noise_only_is_rejected(kind, seed):
    ir, red = _noise(kind, seed)
    out = _run(ir, red)
    assert all(o["hr_quality_state"] != "VALID" for o in out)
    assert sum(o["ppg_noise_rejected"] for o in out) >= 0.9 * len(out)
    rejected = [o for o in out if o["ppg_noise_rejected"]]
    assert all(o["heart_rate"] is None and o["spo2"] is None and o["hrv"]["rmssd"] is None for o in rejected)
    assert all(o["hr_quality_state"] == "INSUFFICIENT_DATA" for o in rejected)


@pytest.mark.parametrize("ac,sd", [(20, 5), (50, 10), (100, 20), (300, 100)])
def test_low_perfusion_pulses_are_protected(ac, sd):
    # AC amplitude of 20-300 counts on a 110 000 DC (perfusion index 0.02-0.3 %), absolute noise floor sd
    p = S.ppg(fs=FS, seconds=40, seed=11, hr_bpm=72, perfusion=ac / 110_000, noise=0.0)
    rng = np.random.default_rng(3)
    out = _run(p.ir + rng.normal(0, sd, len(p.ir)), p.red + rng.normal(0, sd, len(p.red)))
    assert not any(o["ppg_noise_rejected"] for o in out)
    hr = [o["heart_rate"] for o in out]
    assert all(h is not None and abs(h - p.true_hr_bpm) < 4 for h in hr[-10:])
    assert out[-1]["hr_quality_state"] in ("VALID", "LOW_CONFIDENCE") and out[-1]["pulse_periodicity"] >= 0.45


def test_periodicity_is_amplitude_independent_and_short_window_is_none():
    p = S.ppg(fs=FS, seconds=20, seed=2, hr_bpm=72, noise=0.05)
    big = A.pulse_periodicity(p.ir[-1040:], FS)
    small = A.pulse_periodicity(110_000 + (p.ir[-1040:] - 110_000) * 0.01, FS)
    assert big > 0.6 and abs(big - small) < 0.02
    assert A.pulse_periodicity(p.ir[:300], FS) is None
    assert A.pulse_periodicity(np.full(1040, 5e4), FS) is None


def test_absent_finger_is_flagged_not_a_measurement():
    rng = np.random.default_rng(0)
    n = int(30 * FS)
    out = _run(rng.normal(800, 15, n), rng.normal(600, 15, n))          # LED on, nothing over the sensor
    assert all(o["hr_quality_state"] == "NO_CONTACT" and o["heart_rate"] is None and o["spo2"] is None for o in out)


def test_engine_profile_b_stream_without_finger_has_no_hr():
    rng = np.random.default_rng(0)
    imu = S.rest(seconds=20, seed=0)
    ir = rng.normal(800, 15, imu.n).astype(int)
    red = rng.normal(600, 15, imu.n).astype(int)
    eng = E.RuntimeEngine()
    for d in packets(imu, ir=ir, red=red, version=2):
        eng.process_packet(d, host_monotonic=0.0, host_wall=0.0)
    m = eng.metrics
    assert m["hr_quality_state"] == "NO_CONTACT" and m["heart_rate"] is None and m["finger_detected"] is False
