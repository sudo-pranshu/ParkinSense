"""
Background jobs started from the dashboard (replay, dataset generation).

Jobs run the project's own command-line tools in a *separate process*, so the
dashboard never executes processing code in its UI process and a long job
cannot freeze it. Outputs always go to new directories (`replays/`,
`datasets/`); source recordings are opened read-only by those tools.
"""

from __future__ import annotations

import subprocess
import sys
import threading
import time
import uuid
from collections import deque
from dataclasses import dataclass, field


@dataclass
class Job:
    id: str
    kind: str
    cmd: list
    started: float = field(default_factory=time.time)
    status: str = "RUNNING"
    returncode: int | None = None
    log: deque = field(default_factory=lambda: deque(maxlen=400))


_jobs: dict[str, Job] = {}
_lock = threading.Lock()


def start(kind: str, args: list) -> Job:
    cmd = [sys.executable, "-m", *args]
    job = Job(uuid.uuid4().hex[:8], kind, cmd)
    with _lock:
        _jobs[job.id] = job

    def run():
        try:
            p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            for line in p.stdout:
                job.log.append(line.rstrip())
            job.returncode = p.wait()
            job.status = "DONE" if job.returncode == 0 else "FAILED"
        except OSError as e:
            job.log.append(str(e))
            job.status = "FAILED"

    threading.Thread(target=run, daemon=True, name=f"job-{job.id}").start()
    return job


def replay(capture: str, out_dir: str, resample: bool = False) -> Job:
    args = ["parkinsense.replay.replay", capture, "--out", out_dir] + (["--resample"] if resample else [])
    return start("replay", args)


def dataset(captures: list, out_dir: str, version: str) -> Job:
    return start("dataset", ["parkinsense.datasets.builder", *captures, "--out", out_dir, "--version", version])


def all_jobs() -> list[Job]:
    with _lock:
        return sorted(_jobs.values(), key=lambda j: j.started, reverse=True)


def get(job_id: str) -> Job | None:
    with _lock:
        return _jobs.get(job_id)
