"""
Step-counter benchmark on labelled real wrist recordings.

    python -m benchmarks.steps_bench [--counters production,periodic,gated] [--out FILE]

Data (benchmarks/external/MANIFEST.md; fetched by benchmarks.external.fetch):

  Clemson pedometer evaluation (Mattfeld et al. 2017): 30 participants x 3 gait
      conditions (Regular / SemiRegular / Irregular), wrist Shimmer3 at 15 Hz,
      annotated left/right foot contacts. The only real step-event ground truth used.
  Karas 2021 walk-climb-drive: left wrist ActiGraph at 100 Hz, per-sample activity
      labels (walking, stairs, driving, clapping). No step annotations: it is used for
      walking-bout detection and for FALSE steps during non-walking activity.

Every signal is linearly resampled to 104 Hz (the ParkinSense stream rate) before it
is fed to a counter, because the production counter's filters are per-sample. The
motion-state gate is held at ACTIVE (the gyroscope-based motion context is not available
in these datasets), so this measures each counter's own detection logic, not the
runtime's tremor guard. Results are public-dataset results, not ParkinSense hardware
results.

Metrics: per-recording absolute and signed percentage count error, precision / recall / F1
of step events (one-to-one matching within TOL_S after removing the per-recording median
lag, which absorbs the offset between foot contact and wrist peak), cadence error,
false steps per minute outside walking, walking-time sensitivity / specificity.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np

from parkinsense import config as C
from parkinsense.datasets import reference as R

FS = C.SAMPLE_RATE_HZ
TOL_S = 0.30


def make_counter(name: str, fs: float = FS):
    if name == "production":
        from parkinsense.activity.step_counter import StepCounter
        return StepCounter(sample_rate=fs)
    if name == "periodic":
        from parkinsense.activity.step_counter_periodic import PeriodicStepCounter
        return PeriodicStepCounter(sample_rate=fs)
    if name.startswith("gated"):
        from parkinsense.activity.step_counter_v2 import GatedStepCounter
        kw = {}
        if ":" in name:                                   # gated:min_periodicity=0.5/peak_k=0.4
            for item in name.split(":", 1)[1].split("/"):
                k, v = item.split("=")
                kw[k] = float(v)
        return GatedStepCounter(sample_rate=fs, **kw)
    raise ValueError(name)


def resample(t, acc, fs=FS):
    tu = np.arange(t[0], t[-1], 1.0 / fs)
    return tu, np.stack([np.interp(tu, t, acc[:, k]) for k in range(3)], axis=1)


def run_counter(name: str, t, acc, gate: str = "ACTIVE"):
    """Feed a signal; return (step times, walking flag per sample, steps_total)."""
    c = make_counter(name)
    n = len(t)
    walking = np.zeros(n, bool)
    times = []
    last = 0
    for i in range(n):
        r = c.update(acc[i, 0], acc[i, 1], acc[i, 2], gate, now=float(t[i]))
        s = r["steps"]
        if s > last:
            times.extend([float(t[i])] * (s - last))
            last = s
        walking[i] = r["walking_state"] == "WALKING"
    if hasattr(c, "step_event_times"):                     # retroactive credit keeps true step times
        times = c.step_event_times
    return np.asarray(times), walking, last


def match_events(est, ref, tol=TOL_S):
    """One-to-one greedy nearest matching after removing the median lag. Returns (tp, lag)."""
    est, ref = np.sort(est), np.sort(ref)
    if len(est) == 0 or len(ref) == 0:
        return 0, 0.0
    idx = np.clip(np.searchsorted(ref, est), 1, len(ref) - 1)
    near = np.where(np.abs(ref[idx] - est) < np.abs(ref[idx - 1] - est), ref[idx], ref[idx - 1])
    lag = float(np.median(est - near))
    used = np.zeros(len(ref), bool)
    tp = 0
    for e in est - lag:
        j = np.searchsorted(ref, e)
        for k in (j - 1, j):
            if 0 <= k < len(ref) and not used[k] and abs(ref[k] - e) <= tol:
                used[k] = True
                tp += 1
                break
    return tp, lag


def prf(tp, n_est, n_ref):
    p = tp / n_est if n_est else 0.0
    r = tp / n_ref if n_ref else 0.0
    return p, r, (2 * p * r / (p + r) if p + r else 0.0)


def clemson(counters, root, participants=range(1, 31), kinds=R.CLEMSON_KINDS, log=print):
    cal = R.clemson_calibration(Path(root))
    rows = []
    for p in participants:
        for kind in kinds:
            rec = R.load_clemson(Path(root), p, kind, cal)
            t, a = resample(rec.t, rec.acc)
            row = {"participant": p, "kind": kind, "duration_s": round(rec.duration_s, 1),
                   "ref_steps": int(len(rec.step_times_s))}
            for name in counters:
                est, walking, total = run_counter(name, t, a)
                tp, lag = match_events(est, rec.step_times_s)
                pr, rc, f1 = prf(tp, len(est), len(rec.step_times_s))
                row[name] = {"steps": int(total), "error": int(total - len(rec.step_times_s)),
                             "pct_error": 100.0 * (total - len(rec.step_times_s)) / max(len(rec.step_times_s), 1),
                             "precision": pr, "recall": rc, "f1": f1, "lag_s": lag,
                             "walking_fraction": float(walking.mean())}
            rows.append(row)
            log(f"clemson P{p:03d} {kind:11s} ref {row['ref_steps']:5d} " +
                " ".join(f"{n}={row[n]['steps']:5d}({row[n]['pct_error']:+6.1f}%)" for n in counters))
    return rows


def karas(counters, root, subjects=None, log=print):
    rows = []
    for s in subjects or R.karas_subjects(Path(root)):
        rec = R.load_karas(Path(root), s)
        t, a = resample(rec.t, rec.acc)
        act = np.interp(t, rec.t, rec.activity).round().astype(int)       # nearest label
        act = rec.activity[np.clip(np.searchsorted(rec.t, t), 0, len(rec.t) - 1)]
        walk = np.isin(act, [1, 2, 3])
        nonwalk = np.isin(act, [4, 77])                                    # driving, clapping (labelled non-walking)
        row = {"subject": s, "walk_min": float(walk.sum() / FS / 60), "nonwalk_min": float(nonwalk.sum() / FS / 60)}
        for name in counters:
            est, walking, total = run_counter(name, t, a)
            idx = np.clip(np.round((est - t[0]) * FS).astype(int), 0, len(t) - 1) if len(est) else np.array([], int)
            fs_nonwalk = int(nonwalk[idx].sum()) if len(idx) else 0
            fs_walk = int(walk[idx].sum()) if len(idx) else 0
            row[name] = {"steps_in_walking": fs_walk, "false_steps_nonwalking": fs_nonwalk,
                         "false_steps_per_min": fs_nonwalk / max(row["nonwalk_min"], 1e-9),
                         "walking_sensitivity": float(walking[walk].mean()) if walk.any() else None,
                         "walking_specificity_labelled": float((~walking[nonwalk]).mean()) if nonwalk.any() else None,
                         "steps_per_walking_min": fs_walk / max(row["walk_min"], 1e-9)}
        rows.append(row)
        log(f"karas {s} walk {row['walk_min']:.1f} min nonwalk {row['nonwalk_min']:.1f} min " +
            " ".join(f"{n}: {row[n]['steps_per_walking_min']:.0f} st/min walk, {row[n]['false_steps_per_min']:.1f} false/min"
                     for n in counters))
    return rows


def summarize_clemson(rows, counters):
    out = {}
    for name in counters:
        out[name] = {}
        for kind in list(R.CLEMSON_KINDS) + ["all"]:
            sel = [r for r in rows if kind in ("all", r["kind"])]
            if not sel:
                continue
            ref = sum(r["ref_steps"] for r in sel)
            est = sum(r[name]["steps"] for r in sel)
            pct = np.array([r[name]["pct_error"] for r in sel])
            out[name][kind] = {
                "recordings": len(sel), "ref_steps": ref, "est_steps": est,
                "pooled_bias_pct": 100.0 * (est - ref) / max(ref, 1),
                "mape_pct": float(np.abs(pct).mean()), "median_abs_pct": float(np.median(np.abs(pct))),
                "precision": float(np.mean([r[name]["precision"] for r in sel])),
                "recall": float(np.mean([r[name]["recall"] for r in sel])),
                "f1": float(np.mean([r[name]["f1"] for r in sel])),
            }
    return out


def summarize_karas(rows, counters):
    out = {}
    for name in counters:
        nw = sum(r["nonwalk_min"] for r in rows)
        sens = [r[name]["walking_sensitivity"] for r in rows if r[name]["walking_sensitivity"] is not None]
        spec = [r[name]["walking_specificity_labelled"] for r in rows if r[name]["walking_specificity_labelled"] is not None]
        out[name] = {"subjects": len(rows), "nonwalking_minutes": nw,
                     "false_steps_per_min": sum(r[name]["false_steps_nonwalking"] for r in rows) / max(nw, 1e-9),
                     "walking_state_sensitivity": float(np.mean(sens)), "walking_state_specificity": float(np.mean(spec)),
                     "steps_per_walking_min": float(np.mean([r[name]["steps_per_walking_min"] for r in rows]))}
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--counters", default="production,periodic")
    ap.add_argument("--data", default="data/external")
    ap.add_argument("--out")
    ap.add_argument("--only", choices=["clemson", "karas"])
    ap.add_argument("--participants", help="comma list (default all 30)")
    ap.add_argument("--subjects", help="comma list of karas ids (default all)")
    a = ap.parse_args(argv)
    counters = a.counters.split(",")
    t0 = time.time()
    rep = {"benchmark": "steps_real_wrist", "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
           "pipeline_version": C.PIPELINE_VERSION, "counters": counters, "tolerance_s": TOL_S,
           "gate": "ACTIVE (constant)", "resampled_to_hz": FS,
           "datasets": {"clemson": R.CLEMSON_PROVENANCE, "karas": R.KARAS_PROVENANCE}}
    if a.only != "karas":
        ps = [int(x) for x in a.participants.split(",")] if a.participants else range(1, 31)
        rows = clemson(counters, Path(a.data) / "clemson", ps)
        rep["clemson"] = {"per_recording": rows, "summary": summarize_clemson(rows, counters)}
    if a.only != "clemson":
        rows = karas(counters, Path(a.data) / "karas", a.subjects.split(",") if a.subjects else None)
        rep["karas"] = {"per_subject": rows, "summary": summarize_karas(rows, counters)}
    rep["runtime_s"] = round(time.time() - t0, 1)
    for k in ("clemson", "karas"):
        if k in rep:
            print(json.dumps(rep[k]["summary"], indent=1, default=float))
    if a.out:
        Path(a.out).write_text(json.dumps(rep, indent=1, default=float) + "\n")


if __name__ == "__main__":
    main()
