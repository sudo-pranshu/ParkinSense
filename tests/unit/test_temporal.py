from parkinsense.tremor.temporal import TremorHMM


def _run(evidences, hop):
    h = TremorHMM()
    out = []
    for i, e in enumerate(evidences):
        out.append(h.update(e, (i + 1) * hop))
    return out


def test_confirms_and_releases():
    out = _run([1.0] * 30 + [0.0] * 40, 0.5)
    first = next(i for i, o in enumerate(out) if o["confirmed"])
    assert 1 <= first <= 14       # never on the first window alone; within 7 s
    assert not out[-1]["confirmed"] and out[-1]["state"] == "NO_TREMOR"


def test_hop_invariance():
    t_conf = []
    for hop in (0.25, 0.5, 1.0):
        n = int(40 / hop)
        out = _run([1.0] * n, hop)
        t_conf.append((next(i for i, o in enumerate(out) if o["confirmed"]) + 1) * hop)
    # v2 state machine: confirmation latency scaled linearly with the hop (0.25 s -> 1 s, 1 s -> 4 s)
    assert max(t_conf) - min(t_conf) <= 1.6, t_conf


def test_no_dead_band_lockup():
    # v2 froze in CONFIRMED forever for scores in 56..74. Ambiguous evidence must decay.
    out = _run([1.0] * 20 + [0.3] * 200, 0.5)
    assert not out[-1]["confirmed"]


def test_unusable_windows_only_predict():
    h = TremorHMM()
    p0 = h.update(None, 0.5)["probability"]
    assert p0 < 0.06
