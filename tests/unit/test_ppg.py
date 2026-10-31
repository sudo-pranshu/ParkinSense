import numpy as np

from parkinsense.config import MotionState
from parkinsense.ppg import processor as PP
from parkinsense.synthetic import signals as S


def _feed(proc, ir, red, fs, hop_s=0.5, **kw):
    out = []
    step = int(hop_s * fs)
    for i in range(len(ir)):
        proc.ingest(int(ir[i]), int(red[i]))
        if i and i % step == 0:
            out.append(proc.analyze(now=i / fs, **kw))
    return out


def test_hr_accuracy_at_true_rate():
    p = S.ppg(seconds=40, seed=2, hr_bpm=72)
    ir, red = S.ppg_to_slots(p, path="v2")
    out = _feed(PP.PPGProcessor(sample_rate=104), ir, red, 104)
    hrs = [o["heart_rate"] for o in out[-20:] if o["heart_rate"]]
    assert hrs and abs(np.median(hrs) - p.true_hr_bpm) < 2.0
    assert out[-1]["hr_quality_state"] == "VALID"


def test_deterministic_with_signal_clock():
    p = S.ppg(seconds=25, seed=4)
    ir, red = S.ppg_to_slots(p, path="v2")
    a = _feed(PP.PPGProcessor(), ir, red, 104)
    b = _feed(PP.PPGProcessor(), ir, red, 104)
    assert [x["heart_rate"] for x in a] == [x["heart_rate"] for x in b]
    assert [x["spo2"] for x in a] == [x["spo2"] for x in b]


def test_hrv_withheld_at_10hz_effective_rate():
    p = S.ppg(seconds=30, seed=1)
    ir, red = S.ppg_to_slots(p, path="v1")
    out = _feed(PP.PPGProcessor(), ir, red, 104)
    assert out[-1]["ppg_effective_rate_hz"] < 15
    assert out[-1]["hrv"]["rmssd"] is None and "withheld_reason" in out[-1]["hrv"]


def test_motion_multipliers_keyed_by_enum_and_both_spellings():
    assert MotionState.parse("LOW_MOTION") is MotionState.LOW_MOTION
    assert MotionState.parse("LOW MOTION") is MotionState.LOW_MOTION
    assert PP.MOTION_CONFIDENCE_MULTIPLIERS[MotionState.parse("LOW_MOTION")] == 0.8


def test_motion_coupled_hr_is_flagged():
    p = S.ppg(seconds=40, seed=3, motion_g=0.4, motion_freq_hz=1.8)
    ir, red = S.ppg_to_slots(p, path="v2")
    out = _feed(PP.PPGProcessor(), ir, red, 104, motion_state="ACTIVE", motion_frequencies_hz=[0.9])
    late = out[-20:]
    assert all(o["hr_quality_state"] != "VALID" or not o["motion_coupled_hr"] for o in late)
    rest = _feed(PP.PPGProcessor(), *S.ppg_to_slots(S.ppg(seconds=40, seed=3), path="v2"), 104,
                 motion_state="REST")
    c_m = np.median([o["hr_quality"]["overall_confidence"] for o in late])
    c_r = np.median([o["hr_quality"]["overall_confidence"] for o in rest[-20:]])
    assert c_m < c_r                                   # v2 baseline had this inverted


def test_reset_clears_spo2_state():
    proc = PP.PPGProcessor()
    proc._spo2_prior["prior_spo2"] = 97.0
    proc.reset()
    assert proc._spo2_prior["prior_spo2"] is None
