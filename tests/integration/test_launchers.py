"""Launch scripts: help/usage, environment and port checks, duplicate
detection, and a full start → health → Ctrl+C → clean shutdown cycle."""

import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ["setup.sh", "start_runtime.sh", "start_dashboard.sh", "start_parkinsense.sh",
           "check.sh", "replay.sh", "clean.sh"]
pytestmark = pytest.mark.skipif(shutil.which("bash") is None or sys.platform == "win32", reason="needs bash")


def env(tmp_path, **extra):
    e = dict(os.environ, PARKINSENSE_PYTHON=sys.executable, PARKINSENSE_RUN_DIR=str(tmp_path / "run"),
             PARKINSENSE_LOG_DIR=str(tmp_path / "logs"))
    e.update(extra)
    return e


def run(args, tmp_path, timeout=30, **extra):
    return subprocess.run(["bash", *args], cwd=ROOT, env=env(tmp_path, **extra), capture_output=True,
                          text=True, timeout=timeout)


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.mark.parametrize("script", SCRIPTS)
def test_help_and_usage_errors(script, tmp_path):
    assert os.access(ROOT / script, os.X_OK), f"{script} is not executable"
    r = run([script, "--help"], tmp_path)
    assert r.returncode == 0 and "Usage:" in r.stdout
    r = run([script, "--definitely-not-an-option"], tmp_path)
    assert r.returncode == 2


def test_missing_environment_is_reported(tmp_path):
    e = {"PARKINSENSE_PYTHON": "", "VIRTUAL_ENV": ""}
    if (ROOT / ".venv").exists() or (ROOT / "venv").exists():
        pytest.skip("a project venv exists in this checkout")
    r = run(["start_dashboard.sh"], tmp_path, **e)
    assert r.returncode == 1 and "./setup.sh" in r.stderr


def test_port_conflict_is_detected(tmp_path):
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        s.listen()
        r = run(["start_dashboard.sh", "--port", str(s.getsockname()[1])], tmp_path)
    assert r.returncode == 3 and "in use" in r.stderr


def _wait(url, secs=30):
    end = time.time() + secs
    while time.time() < end:
        try:
            return urllib.request.urlopen(url, timeout=1).read()
        except OSError:
            time.sleep(0.3)
    raise AssertionError(f"{url} not reachable")


def test_unified_launcher_full_cycle(tmp_path):
    pytest.importorskip("uvicorn")
    pytest.importorskip("dash")
    api, dash_port = free_port(), free_port()
    out = tmp_path / "rec"
    p = subprocess.Popen(["bash", "start_parkinsense.sh", "--simulate", "--api-port", str(api),
                          "--dashboard-port", str(dash_port), "--quiet", "--",
                          "--out", str(out), "--metrics-file", str(tmp_path / "m.json"), "--speed", "4"],
                         cwd=ROOT, env=env(tmp_path), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                         text=True, start_new_session=True)
    try:
        health = json.loads(_wait(f"http://127.0.0.1:{api}/health"))
        assert "status" in health
        assert b"ParkinSense" in _wait(f"http://127.0.0.1:{dash_port}/")
        time.sleep(1.5)
        # a second runtime is refused while this one runs
        r = run(["start_runtime.sh", "--simulate", "--port", str(free_port())], tmp_path)
        assert r.returncode == 3 and "already running" in r.stderr
        live = json.loads(_wait(f"http://127.0.0.1:{api}/live"))
        assert live["source"] == "simulated" and live["last_sample_seq"] > 0
    finally:
        os.killpg(p.pid, signal.SIGINT)          # what Ctrl+C in the terminal does
        try:
            stdout, _ = p.communicate(timeout=30)
        except subprocess.TimeoutExpired:
            os.killpg(p.pid, signal.SIGKILL)
            raise
    assert p.returncode == 0, stdout
    assert "stopped" in stdout
    metas = list(out.glob("*/metadata.json"))
    assert len(metas) == 1 and json.loads(metas[0].read_text())["status"] == "COMPLETE"
    assert not list((tmp_path / "run").glob("*.pid"))
    for port in (api, dash_port):                # both processes are gone
        with socket.socket() as s:
            assert s.connect_ex(("127.0.0.1", port)) != 0


def test_clean_is_dry_run_by_default(tmp_path):
    r = run(["clean.sh"], tmp_path)
    assert r.returncode == 0 and ("dry run" in r.stdout or "nothing to clean" in r.stdout)
    assert (ROOT / "parkinsense").is_dir()
