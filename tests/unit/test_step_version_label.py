"""Step-counter version label (ADR-0013): new recordings are truthful, old ones stay interpretable."""
import json

import numpy as np
import pytest

from parkinsense import config as C
from parkinsense.protocol import packet as P
from parkinsense.runtime.engine import CAPTURE_COLUMNS, RuntimeEngine
from parkinsense.runtime.recorder import SessionRecorder


def _packet(seq=0):
    rows = [(0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 100_000, 80_000)] * 10
    return P.encode(rows, seq * 96150, version=2, seq=seq)


@pytest.mark.parametrize("algo,expected", [("default", "1.1"), ("periodic", "2.0"), ("gated", "3.0-dev")])
def test_rows_and_metadata_name_the_algorithm_that_ran(algo, expected, tmp_path):
    e = RuntimeEngine(step_counter=algo)
    rows = []
    for k in range(60):
        rows += e.process_packet(_packet(k)).rows
    assert {r["step_counter_version"] for r in rows} == {expected}
    md = SessionRecorder(e, tmp_path).metadata("COMPLETE")
    assert md["step_counter_version"] == expected == md["step_algorithm_version"]
    assert md["metadata_revision"] == C.METADATA_REVISION == 2


def test_capture_schema_unchanged():
    assert len(CAPTURE_COLUMNS) == 79 and C.CAPTURE_SCHEMA_VERSION == "3"
    assert "step_counter_version" in CAPTURE_COLUMNS and "metadata_revision" not in CAPTURE_COLUMNS


def test_deprecated_alias_is_the_default_counters_version():
    assert C.STEP_COUNTER_VERSION == C.STEP_ALGORITHM_VERSIONS["default"] == "1.1"


def test_legacy_recordings_are_reinterpreted_not_rewritten():
    f = C.step_algorithm_version_of
    assert f("2.0") == "1.1"                                    # pre-Phase-7 recording: label was wrong
    assert f("2.0", None, 1) == "1.1"
    assert f("2.0", "periodic") == "2.0"                        # Phase-7 metadata names the algorithm
    assert f("2.0", "default") == "1.1"
    assert f("1.1", None, 2) == "1.1" and f("3.0-dev", None, 2) == "3.0-dev"
    assert f(None) is None and f("") is None
    assert f("9.9") == "9.9"                                    # unknown labels pass through untouched


def test_metadata_is_json_serialisable(tmp_path):
    e = RuntimeEngine()
    e.process_packet(_packet())
    json.dumps(SessionRecorder(e, tmp_path).metadata("COMPLETE"))
    assert np  # keep numpy import used for parity with sibling tests
