"""
Synthetic ground-truth benchmark suite (tremor, steps, PPG, runtime cost).

    python -m benchmarks.run_benchmarks --impl current --out benchmarks/results/current.json
    python -m benchmarks.run_benchmarks --impl legacy --worktree /path/to/baseline --out ...

Every number produced here is measured on *synthetic* signals with known
ground truth (parkinsense.synthetic.signals). It quantifies whether an
algorithm recovers an idealised, known quantity; it is not evidence of
clinical accuracy.

Protocol
--------
* Each segment runs on a fresh runtime (no state carried across segments).
* The first WARMUP_S seconds of each segment are excluded (window fill +
  temporal confirmation are reported separately as latency).
* A segment's per-analysis decisions are pooled; sensitivity/specificity are
  computed over analyses. Segment-level decisions (majority of analyses) are
  also reported, which is closer to how an "episode present" claim is made.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np

from benchmarks.harness import CurrentRuntimeAdapter, LegacyRuntimeAdapter, run
from parkinsense.synthetic import signals as S

WARMUP_S = 8.0
SEG_S = 30.0
N_SEEDS = 16


def _adapter(args):
    if args.impl == "legacy":
        return LegacyRuntimeAdapter(args.worktree)
    return CurrentRuntimeAdapter()


def _post(analyses, t_min=WARMUP_S):
    return [a for a in analyses if a["t"] >= t_min]


def confusion(pos_dec, neg_dec):
    tp = int(np.sum(pos_dec)); fn = len(pos_dec) - tp
    fp = int(np.sum(neg_dec)); tn = len(neg_dec) - fp
    sens = tp / (tp + fn) if tp + fn else float("nan")
    spec = tn / (tn + fp) if tn + fp else float("nan")
    prec = tp / (tp + fp) if tp + fp else float("nan")
    f1 = 2 * prec * sens / (prec + sens) if prec + sens and not np.isnan(prec) else float("nan")
    return {"tp": tp, "fn": fn, "fp": fp, "tn": tn, "sensitivity": sens,
            "specificity": spec, "precision": prec, "f1": f1,
            "false_positive_rate": 1 - spec if not np.isnan(spec) else float("nan")}


def bench_tremor(args):
    pos_scen = ["rest_tremor", "strong_tremor"]
    neg_scen = ["rest", "voluntary", "walking", "vibration", "non_pd_oscillation"]
    per = {}
    pos_dec, neg_dec, seg_pos, seg_neg, ferr = [], [], [], [], []
    amp_curve = []
    for scen in pos_scen + neg_scen + ["subtle_tremor", "action_tremor", "walking_with_tremor"]:
        decs = []
        for seed in range(N_SEEDS):
            sig = S.SCENARIOS[scen](seconds=SEG_S, seed=seed)
            an = _post(run(_adapter(args), sig))
            d = np.array([a["tremor"] for a in an], bool)
            decs.append(d.mean() if len(d) else 0.0)
            if scen in pos_scen:
                pos_dec.extend(d); seg_pos.append(d.mean() >= 0.5)
                amp_curve.append((sig.tremor_amp_dps, float(d.mean())))
                fr = [a["frequency"] for a in an if a["tremor"] and a["frequency"]]
                if fr:
                    ferr.append(abs(float(np.median(fr)) - sig.tremor_freq_hz))
            elif scen in neg_scen:
                neg_dec.extend(d); seg_neg.append(d.mean() >= 0.5)
        per[scen] = {"mean_fraction_classified_tremor": float(np.mean(decs))}
    amp_curve.sort()
    bins = [(8, 15), (15, 30), (30, 60), (60, 120), (120, 250)]
    sens_by_amp = {f"{lo}-{hi} dps": float(np.mean([f for a, f in amp_curve if lo <= a < hi] or [np.nan]))
                   for lo, hi in bins}
    return {
        "analysis_level": confusion(np.array(pos_dec), np.array(neg_dec)),
        "segment_level": confusion(np.array(seg_pos), np.array(seg_neg)),
        "per_scenario": per,
        "sensitivity_by_amplitude": sens_by_amp,
        "frequency_abs_error_hz": {"median": float(np.median(ferr)) if ferr else None,
                                   "p90": float(np.percentile(ferr, 90)) if ferr else None,
                                   "n": len(ferr)},
    }


def bench_latency(args):
    """rest(20s) -> tremor(30s) -> rest(30s); onset/offset latency of published classification."""
    on, off = [], []
    for seed in range(8):
        a = S.rest(seconds=20, seed=seed)
        b = S.rest_tremor(seconds=30, seed=seed, amp=40)
        c = S.rest(seconds=30, seed=seed + 99)
        sig, _ = S.concatenate([a, b, c])
        an = run(_adapter(args), sig)
        t_on = next((x["t"] for x in an if x["t"] >= 20 and x["tremor"]), None)
        t_off = next((x["t"] for x in an if x["t"] >= 50 and not x["tremor"]), None)

        on.append(None if t_on is None else t_on - 20)
        off.append(None if t_off is None else t_off - 50)
    f = [x for x in on if x is not None]
    g = [x for x in off if x is not None]
    return {"onset_latency_s_median": float(np.median(f)) if f else None,
            "onset_detected": f"{len(f)}/{len(on)}",
            "offset_latency_s_median": float(np.median(g)) if g else None,
            "offset_cleared": f"{len(g)}/{len(off)}"}


def bench_steps(args):
    errs, false_steps = [], {}
    for seed in range(N_SEEDS):
        sig = S.walking(seconds=60, seed=seed)
        an = run(_adapter(args), sig)
        steps = an[-1]["steps"] if an else 0
        errs.append(((steps or 0) - sig.true_steps) / sig.true_steps)
    for scen in ["rest_tremor", "voluntary", "rest", "vibration"]:
        fs_ = []
        for seed in range(6):
            an = run(_adapter(args), S.SCENARIOS[scen](seconds=60, seed=seed))
            fs_.append((an[-1]["steps"] or 0) if an else 0)
        false_steps[scen] = float(np.mean(fs_))
    e = np.array(errs)
    return {"walking_count_error_pct": {"mean": float(100 * e.mean()),
                                        "mean_abs": float(100 * np.abs(e).mean()),
                                        "worst": float(100 * e[np.argmax(np.abs(e))])},
            "false_steps_per_minute": false_steps}


def bench_ppg(args, path):
    hr_err, rmssd_err, cover, conf_rest = [], [], [], []
    for seed in range(10):
        p = S.ppg(seconds=60, seed=seed)
        ir, red = S.ppg_to_slots(p, path=path)
        imu = S.rest(seconds=60, seed=seed, micro_rms=0.5)
        an = run(_adapter(args), imu, ir, red, version=1)
        late = [a for a in an if a["t"] >= 20]
        hrs = [a["heart_rate"] for a in late if a["heart_rate"] is not None]
        cover.append(len(hrs) / max(len(late), 1))
        if hrs:
            hr_err.append(abs(float(np.median(hrs)) - p.true_hr_bpm))
        rm = [a["rmssd"] for a in late if a["rmssd"] is not None]
        if rm:
            rmssd_err.append(abs(float(np.median(rm)) - p.true_rmssd_ms))
        c = [a["hr_confidence"] for a in late if a["hr_confidence"] is not None]
        if c:
            conf_rest.append(float(np.median(c)))
    # motion artefact at step frequency, wrist moving
    mot_err, conf_mot = [], []
    for seed in range(6):
        p = S.ppg(seconds=60, seed=seed, motion_g=0.4, motion_freq_hz=1.8)
        ir, red = S.ppg_to_slots(p, path=path)
        imu = S.walking(seconds=60, seed=seed, cadence_spm=108)
        an = run(_adapter(args), imu, ir, red, version=1)
        late = [a for a in an if a["t"] >= 20]
        hrs = [a["heart_rate"] for a in late if a["heart_rate"] is not None]
        if hrs:
            mot_err.append(abs(float(np.median(hrs)) - p.true_hr_bpm))
        c = [a["hr_confidence"] for a in late if a["hr_confidence"] is not None]
        if c:
            conf_mot.append(float(np.median(c)))
    m = lambda x: float(np.mean(x)) if x else None
    return {"rest_hr_mae_bpm": m(hr_err), "rest_hr_reported_in": f"{len(hr_err)}/10",
            "rest_hr_coverage": m(cover), "rest_rmssd_mae_ms": m(rmssd_err),
            "rest_rmssd_reported_in": f"{len(rmssd_err)}/10",
            "rest_hr_confidence_median": m(conf_rest),
            "motion_hr_mae_bpm": m(mot_err), "motion_hr_reported_in": f"{len(mot_err)}/6",
            "motion_hr_confidence_median": m(conf_mot)}


def bench_cost(args):
    sig = S.rest_tremor(seconds=60, seed=1)
    p = S.ppg(seconds=60, seed=1)
    ir, red = S.ppg_to_slots(p, path="v2")
    t0 = time.perf_counter()
    an = run(_adapter(args), sig, ir, red)
    wall = time.perf_counter() - t0
    lat = [a["latency_s"] for a in an if a["latency_s"]]
    return {"wall_s_per_60s_signal": wall, "realtime_factor": 60.0 / wall,
            "analysis_packet_latency_ms_median": 1000 * float(np.median(lat)) if lat else None,
            "analysis_packet_latency_ms_p95": 1000 * float(np.percentile(lat, 95)) if lat else None,
            "analyses_per_minute": len(an)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--impl", choices=["legacy", "current"], default="current")
    ap.add_argument("--worktree")
    ap.add_argument("--out", required=True)
    ap.add_argument("--only", nargs="*")
    args = ap.parse_args()
    suites = {"tremor": bench_tremor, "latency": bench_latency, "steps": bench_steps,
              "ppg_v1_path": lambda a: bench_ppg(a, "v1"),
              "ppg_v2_path": lambda a: bench_ppg(a, "v2"), "cost": bench_cost}
    res = {"impl": args.impl, "synthetic_only": True}
    for k, fn in suites.items():
        if args.only and k not in args.only:
            continue
        t0 = time.time()
        res[k] = fn(args)
        print(f"[{k}] {time.time()-t0:.1f}s", json.dumps(res[k], default=str)[:600], flush=True)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(res, indent=2, default=str))


if __name__ == "__main__":
    main()
