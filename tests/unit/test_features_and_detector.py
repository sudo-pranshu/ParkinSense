import numpy as np
import pytest

from parkinsense.motion import features as F
from parkinsense.motion.context import MotionContext
from parkinsense.tremor import detector as D

FS = 104.0


def _sine(f, amp, n=416, axis=1, noise=0.3, seed=0):
    rng = np.random.default_rng(seed)
    t = np.arange(n) / FS
    g = rng.normal(0, noise, (3, n))
    g[axis] += amp * np.sin(2 * np.pi * f * t + 0.7)
    return g


@pytest.mark.parametrize("f", [3.9, 4.37, 5.0, 5.63, 6.2, 6.9])
def test_frequency_interpolation_accuracy(f):
    feats = F.extract(_sine(f, 20.0), FS)
    assert abs(feats.peak_frequency_hz - f) < 0.06       # bin spacing is 0.10 Hz


def test_amplitude_in_physical_units():
    feats = F.extract(_sine(5.0, 20.0, noise=0.0), FS)
    assert abs(feats.tremor_rms_dps - 20.0 / np.sqrt(2)) / (20 / np.sqrt(2)) < 0.08
    assert feats.best_axis == "gy" and feats.axis_dominance > 0.95


def test_band_ratio_is_informative():
    # v2 computed band_ratio on band-passed data (~1 for almost anything).
    slow = F.extract(_sine(1.0, 50.0), FS).band_ratio
    trem = F.extract(_sine(5.0, 20.0), FS).band_ratio
    assert trem > 0.8 and slow < 0.05


def test_out_of_band_oscillation_is_not_tremor():
    for f in (9.0, 15.0):
        ev = D.evaluate(F.extract(_sine(f, 30.0), FS), "REST")
        assert not ev.detected_window and ev.evidence < 0.1


def test_noise_only_is_not_tremor():
    ev = D.evaluate(F.extract(_sine(5.0, 0.0), FS), "REST")
    assert not ev.detected_window


def test_tremor_does_not_make_context_active(synth):
    # The v2 veto: strong tremor's own acceleration classified the wrist ACTIVE.
    s = synth.strong_tremor(seconds=12, seed=3)
    ctx = MotionContext(FS)
    states = [ctx.classify(s.accel()[:, e - 416:e], F.extract(s.gyro()[:, e - 416:e], FS).arm_rms_dps)["state"]
              for e in range(416, s.n, 104)]
    assert states.count("ACTIVE") <= len(states) // 2
