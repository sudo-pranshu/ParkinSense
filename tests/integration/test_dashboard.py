import json

import pytest

from helpers import packets

dash = pytest.importorskip("dash")


def test_dashboard_renders_from_live_session(tmp_path, monkeypatch):
    from parkinsense.runtime.engine import RuntimeEngine
    from parkinsense.runtime.recorder import SessionRecorder, _jsonable_metrics
    from parkinsense.synthetic import signals as S
    from parkinsense.visualization import dashboard as D

    eng = RuntimeEngine()
    with SessionRecorder(eng, root=tmp_path) as rec:
        for d in packets(S.rest_tremor(seconds=15, seed=1)):
            rec.write_rows(eng.process_packet(d).rows)
    m = _jsonable_metrics(eng.metrics)
    m["capture_path"] = str(rec.dir / "capture.csv")
    mf = tmp_path / "metrics.json"
    mf.write_text(json.dumps(m, default=str))
    monkeypatch.setattr(D, "METRICS_FILE", str(mf))
    out = D.update_dashboard(1)
    assert len(out) == 5
    tail = D.read_tail(m["capture_path"], nbytes=20_000)
    assert len(tail) > 10 and "is_analysis_row" in tail.columns
