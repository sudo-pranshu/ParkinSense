"""WP-03 / ADR-0016: localhost default, token-authenticated POST, token-required reads when LAN-bound."""
import asyncio
import json
import os
import stat
import urllib.error
import urllib.request

import pytest

from parkinsense.runtime import auth
from parkinsense.runtime.app import Control, LiveState, build_api, parse_args
from test_dashboard import _free_port, _serve

TOKEN = "t" * 32


def _req(port, path, method="GET", token=None):
    h = {auth.HEADER: token} if token else {}
    r = urllib.request.Request(f"http://127.0.0.1:{port}{path}", method=method, headers=h)
    try:
        with urllib.request.urlopen(r, timeout=3) as resp:
            return resp.status, json.load(resp)
    except urllib.error.HTTPError as e:
        return e.code, None


@pytest.fixture
def served():
    pytest.importorskip("uvicorn")
    started = []

    def make(**kw):
        loop = asyncio.new_event_loop()
        control = Control(loop)
        port = _free_port()
        server, th = _serve(build_api(LiveState(), control, **kw), port)
        started.append((server, th, loop))
        return port, control

    yield make
    for server, th, loop in started:
        server.should_exit = True
        th.join(5)
        loop.close()


def test_default_bind_is_loopback():
    assert parse_args([]).host == "127.0.0.1"
    assert auth.is_loopback("127.0.0.1") and not auth.is_loopback("0.0.0.0")


def test_post_requires_token(served):
    port, _ = served(token=TOKEN)
    assert _req(port, "/session/stop", "POST")[0] == 401
    assert _req(port, "/session/stop", "POST", "wrong" * 8)[0] == 401
    code, body = _req(port, "/session/stop", "POST", TOKEN)
    assert code == 200 and body["ok"] is True


def test_no_token_configured_disables_post(served):
    port, _ = served()
    assert _req(port, "/session/start", "POST", TOKEN)[0] == 403


def test_reads_open_on_loopback_but_guarded_when_lan(served):
    port, _ = served(token=TOKEN)
    assert _req(port, "/metrics")[0] == 200 and _req(port, "/live")[0] == 200
    port, _ = served(token=TOKEN, require_read_token=True)
    assert _req(port, "/health")[0] == 200                       # liveness probe stays open
    for p in ("/metrics", "/live", "/session"):
        assert _req(port, p)[0] == 401 and _req(port, p, token=TOKEN)[0] == 200


def test_token_sources_and_file_mode(tmp_path, monkeypatch):
    monkeypatch.delenv(auth.ENV_TOKEN, raising=False)
    monkeypatch.setenv(auth.ENV_FILE, str(tmp_path / "sub" / "tok"))
    assert auth.read_token() is None                              # clients never create the file
    t = auth.load_or_create_token()
    assert len(t) >= 32 and auth.read_token() == t
    if os.name == "posix":
        assert stat.S_IMODE(os.stat(auth.token_path()).st_mode) == 0o600
    assert auth.load_or_create_token() == t                       # stable across restarts
    monkeypatch.setenv(auth.ENV_TOKEN, "e" * 20)
    assert auth.read_token() == "e" * 20 and auth.load_or_create_token("x" * 20) == "x" * 20
    with pytest.raises(ValueError):
        auth.load_or_create_token("short")


def test_dashboard_client_sends_token(served, tmp_path, monkeypatch):
    from parkinsense.visualization.datasource import LiveFeed
    monkeypatch.setenv(auth.ENV_TOKEN, TOKEN)
    port, control = served(token=TOKEN, require_read_token=True)
    feed = LiveFeed(f"http://127.0.0.1:{port}")
    assert feed.poll_once()                                       # authenticated read
    assert feed.post("/session/stop")["ok"] is True
    monkeypatch.setenv(auth.ENV_TOKEN, "z" * 32)
    assert feed.post("/session/stop")["ok"] is False and not feed.poll_once()
