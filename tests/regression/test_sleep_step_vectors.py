"""Parity vectors: the Python reference must reproduce the committed vectors (mobile ports test against the same file)."""
import json
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).parent))
import make_sleep_step_vectors as G  # noqa: E402

V = json.loads((Path(__file__).parent / "sleep_step_vectors.json").read_text())


@pytest.fixture(scope="module")
def fresh():
    return G.build()


def _close(a, b, tol):
    a = np.array([np.nan if x is None else x for x in a], float)
    b = np.array([np.nan if x is None else x for x in b], float)
    assert np.array_equal(np.isnan(a), np.isnan(b))
    np.testing.assert_allclose(a[~np.isnan(a)], b[~np.isnan(b)], atol=tol)


def test_sleep_vectors_unchanged(fresh):
    e, f = V["sleep"]["expected"], fresh["sleep"]["expected"]
    for k in ("dg_max", "dz_max", "enmo"):
        _close(e[k], f[k], 1e-5)
    _close(np.ravel(e["features"]), np.ravel(f["features"]), 1e-5)
    _close(e["p_sleep"], f["p_sleep"], 1e-5)
    assert e["state"] == f["state"]
    assert e["night"] == f["night"]


def test_night_vectors_unchanged(fresh):
    assert V["night"]["expected"] == fresh["night"]["expected"]
    assert V["night"]["expected"]["nonwear_min"] == 80.0 and V["night"]["expected"]["quality"] == "DATA_GAP"


def test_step_vectors_unchanged(fresh):
    for name in ("default", "gated"):
        assert V["steps"]["expected"][name]["steps"] == fresh["steps"]["expected"][name]["steps"]
        _close(V["steps"]["expected"][name]["event_times_s"], fresh["steps"]["expected"][name]["event_times_s"], 1e-3)


def test_vectors_exercise_both_classes():
    st = V["sleep"]["expected"]["state"]
    assert 0 in st and 1 in st
    assert V["steps"]["expected"]["default"]["steps"] > 20 and V["steps"]["expected"]["gated"]["steps"] > 20
