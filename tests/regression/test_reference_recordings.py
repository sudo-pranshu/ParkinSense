"""
Golden-output regression on the real recordings committed under data/reference.

Values were produced by pipeline 3.0.0 (tests/regression/golden.json). A change
that moves them must be intentional: regenerate with
    python -m tests.regression.make_golden
and explain the change in the PR. Tolerances absorb floating-point noise only.
"""
import json
from pathlib import Path

import pytest

from parkinsense.replay import replay as R

GOLDEN = json.loads((Path(__file__).parent / "golden.json").read_text())


@pytest.mark.parametrize("name", sorted(GOLDEN))
def test_matches_golden(name):
    g = GOLDEN[name]
    out = R.replay(g["path"], resample=g["resample"])["summary"]["outputs"]
    for k, v in g["outputs"].items():
        if isinstance(v, float):
            assert out[k] == pytest.approx(v, abs=1e-6), k
        else:
            assert out[k] == v, k


def test_known_facts_about_reference_data():
    s = {n: g["outputs"] for n, g in GOLDEN.items()}
    assert s["stationary_60s"]["tremor_fraction"] == 0.0
    assert s["stationary_60s"]["motion_state_fraction"].get("REST", 0) > 0.95
    assert s["walking_60s"]["final_steps"] >= 60          # ~86 expected from spectral cadence
    assert s["parkinsense_20260630_123551"]["tremor_fraction"] == 0.0
