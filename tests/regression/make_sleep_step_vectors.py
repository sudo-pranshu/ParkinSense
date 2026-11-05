"""
Generate cross-platform parity vectors for the sleep and step algorithms.

    python -m tests.regression.make_sleep_step_vectors

The Python implementation is the reference. Android / iOS ports must reproduce `expected` from `input`
within the stated tolerances (docs/software/SLEEP_STEP_MOBILE_SPEC.md). Inputs are synthetic and exist only to
pin down numerical behaviour; they say nothing about accuracy.
"""
import json
from pathlib import Path

import numpy as np

from parkinsense.activity.step_counter import StepCounter
from parkinsense.activity.step_counter_v2 import GatedStepCounter
from parkinsense.sleep import features as F
from parkinsense.sleep import model as M
from parkinsense.sleep import night as N
from parkinsense.sleep import params as P

OUT = Path(__file__).parent / "sleep_step_vectors.json"


def sleep_input():
    """40 min at 4 Hz: 5 min restless, 30 min still with two twitches, 5 min restless."""
    fs, rng = 4.0, np.random.default_rng(7)
    parts = []
    for minutes, active in ((5, True), (30, False), (5, True)):
        n = int(minutes * 60 * fs)
        if active:
            seg = int(3 * fs)
            th = rng.uniform(0, np.pi / 2, n // seg + 1)
            ph = rng.uniform(0, 2 * np.pi, n // seg + 1)
            g = np.stack([np.sin(th) * np.cos(ph), np.sin(th) * np.sin(ph), np.cos(th)], 1)
            a = np.repeat(g, seg, axis=0)[:n] + rng.normal(0, 0.05, (n, 3))
        else:
            a = np.tile([0.0, 0.0, 1.0], (n, 1)) + rng.normal(0, 0.004, (n, 3))
            for k in (int(600 * fs), int(1300 * fs)):
                a[k:k + int(2 * fs), 0] += 0.12
        parts.append(a)
    acc = np.round(np.vstack(parts), 4)
    return fs, np.round(np.arange(len(acc)) / fs, 3), acc


def step_input():
    fs, rng = 104.0, np.random.default_rng(3)
    t = np.arange(int(40 * fs)) / fs
    z = 1 + 0.4 * np.sin(2 * np.pi * 1.8 * t) + 0.24 * np.sin(2 * np.pi * 0.9 * t + 1)
    a = np.stack([0.08 * np.sin(2 * np.pi * 0.9 * t), 0 * t, z], 1) + rng.normal(0, 0.01, (len(t), 3))
    return fs, np.round(a, 4)


def night_input():
    """Epoch-level table, 5 h: wake 20 min, sleep with two wake bouts, last 80 min flat (non-wear)."""
    n = 600
    state = np.ones(n, int)
    state[:40] = 0
    state[240:260] = 0
    state[400:430] = 0
    dg = np.where(state == 0, 25.0, 1.5)
    enmo = np.where(state == 0, 0.05, 0.002)
    sd = np.where(state == 0, 0.08, 0.02)
    sd[440:] = 0.004
    return {"dg_max": dg, "enmo": enmo, "acc_sd": sd, "state": state}


def build():
    fs, t, acc = sleep_input()
    tab = F.epoch_features(t, acc, t0=0.0, fs=fs)
    out = M.classify(tab, P.ACCEL)
    X = M.context_features(tab)
    night = N.summarize(tab, out["state"])
    sfs, sacc = step_input()
    steps = {}
    for name, cls in (("default", StepCounter), ("gated", GatedStepCounter)):
        c = cls(sfs)
        for i, r in enumerate(sacc):
            c.update(r[0], r[1], r[2], "ACTIVE", now=i / sfs)
        steps[name] = {"steps": c.steps, "event_times_s": [round(x, 4) for x in getattr(c, "step_event_times", [])]}
    ni = night_input()
    ntab = F.EpochTable(t=30.0 * np.arange(len(ni["state"])), coverage=np.ones(len(ni["state"])), dz_max=ni["dg_max"],
                        dg_max=ni["dg_max"], z_mean=np.zeros(len(ni["state"])), enmo=ni["enmo"], acc_sd=ni["acc_sd"],
                        hr=np.full(len(ni["state"]), np.nan))
    nsum = N.summarize(ntab, ni["state"])
    nz = lambda v: [None if not np.isfinite(x) else float(round(x, 6)) for x in np.ravel(v)]  # noqa: E731
    return {
        "note": "Python is the reference; tolerances in docs/software/SLEEP_STEP_MOBILE_SPEC.md",
        "sleep_algorithm_version": P.SLEEP_ALGORITHM_VERSION,
        "sleep": {"input": {"fs_hz": fs, "t_s": t.tolist(), "acc_g": acc.tolist()},
                  "expected": {"dg_max": nz(tab.dg_max), "dz_max": nz(tab.dz_max), "enmo": nz(tab.enmo),
                               "features": [nz(r) for r in X], "p_sleep": nz(out["p_sleep"]),
                               "state": [int(s) for s in out["state"]],
                               "night": {k: v for k, v in night.items() if isinstance(v, (int, float, str, bool))}}},
        "night": {"input": {k: np.asarray(v).tolist() for k, v in ni.items()},
                  "expected": {k: v for k, v in nsum.items() if isinstance(v, (int, float, str, bool))}},
        "steps": {"input": {"fs_hz": sfs, "acc_g": sacc.tolist(), "motion_state": "ACTIVE"}, "expected": steps},
    }


if __name__ == "__main__":
    OUT.write_text(json.dumps(build(), separators=(",", ":")) + "\n")
    print("wrote", OUT, OUT.stat().st_size // 1024, "KiB")
