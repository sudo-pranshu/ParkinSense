"""
Subject-independent threshold selection and held-out comparison for step counters.

    python -m benchmarks.steps_select GRID1.json [GRID2.json ...] --baseline steps_baseline.json

Inputs are per-recording results from benchmarks.steps_bench (each file holds one or more
counter configurations evaluated on all 90 Clemson recordings). Participants are split
into two folds (odd / even id). For each fold the configuration with the lowest mean
condition-wise MAPE on the OTHER fold is selected, and then evaluated on this fold. So
every reported held-out number comes from participants never used to choose its
thresholds. The configuration finally shipped is selected on all participants and is
labelled in-sample.

Paired comparison against production: participant-level bootstrap (resampling
participants, 5000 draws) of the difference in mean event F1 and in MAPE.
"""

from __future__ import annotations

import argparse
import json

import numpy as np

KINDS = ("Regular", "SemiRegular", "Irregular")


def load(paths):
    rows, names = {}, []
    for p in paths:
        r = json.load(open(p))
        for rec in r["clemson"]["per_recording"]:
            d = rows.setdefault((rec["participant"], rec["kind"]), {"ref": rec["ref_steps"]})
            for n in r["counters"]:
                d[n] = rec[n]
        names += [n for n in r["counters"] if n not in names]
    return rows, names


def score(rows, name, keep):
    """Mean over conditions of MAPE (equal weight per condition) for participants in `keep`."""
    m = []
    for k in KINDS:
        e = [abs(v[name]["pct_error"]) for (p, kk), v in rows.items() if kk == k and p in keep]
        m.append(np.mean(e))
    return float(np.mean(m))


def metrics(rows, name, keep):
    out = {}
    for k in KINDS + ("all",):
        sel = [v for (p, kk), v in rows.items() if p in keep and k in ("all", kk)]
        ref = sum(v["ref"] for v in sel)
        est = sum(v[name]["steps"] for v in sel)
        out[k] = {"n": len(sel), "bias_pct": 100 * (est - ref) / ref,
                  "mape_pct": float(np.mean([abs(v[name]["pct_error"]) for v in sel])),
                  "f1": float(np.mean([v[name]["f1"] for v in sel]))}
    return out


def boot(rows, a, b, parts, n=5000, seed=0):
    rng = np.random.default_rng(seed)
    parts = np.array(sorted(parts))
    d = {}
    for p in parts:
        sel = [v for (pp, _k), v in rows.items() if pp == p]
        d[p] = (np.mean([x[a]["f1"] - x[b]["f1"] for x in sel]),
                np.mean([abs(x[a]["pct_error"]) - abs(x[b]["pct_error"]) for x in sel]))
    arr = np.array([d[p] for p in parts])
    idx = rng.integers(0, len(parts), (n, len(parts)))
    bs = arr[idx].mean(axis=1)
    return {"f1_diff": float(arr[:, 0].mean()), "f1_ci95": np.percentile(bs[:, 0], [2.5, 97.5]).tolist(),
            "mape_diff": float(arr[:, 1].mean()), "mape_ci95": np.percentile(bs[:, 1], [2.5, 97.5]).tolist()}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("grids", nargs="+")
    ap.add_argument("--baseline", required=True)
    ap.add_argument("--out")
    a = ap.parse_args(argv)
    rows, names = load(a.grids)
    base = json.load(open(a.baseline))
    for rec in base["clemson"]["per_recording"]:
        rows[(rec["participant"], rec["kind"])]["production"] = rec["production"]
        rows[(rec["participant"], rec["kind"])]["periodic"] = rec["periodic"]
    cands = [n for n in names if n.startswith("gated")]
    parts = {p for p, _ in rows}
    odd = {p for p in parts if p % 2}
    even = parts - odd
    report = {"candidates": cands, "folds": []}
    held = {}                      # per-recording results of the held-out config, assembled across folds
    for test, train in ((even, odd), (odd, even)):
        sc = {c: score(rows, c, train) for c in cands}
        best = min(sc, key=sc.get)
        report["folds"].append({"test_participants": sorted(test), "selected": best, "train_scores": sc})
        for (p, k), v in rows.items():
            if p in test:
                held[(p, k)] = {"ref": v["ref"], "heldout": v[best], "production": v["production"],
                                "periodic": v["periodic"]}
    report["heldout"] = {n: metrics(held, n, parts) for n in ("heldout", "production", "periodic")}
    report["paired_vs_production"] = boot(held, "heldout", "production", parts)
    allsc = {c: score(rows, c, parts) for c in cands}
    shipped = min(allsc, key=allsc.get)
    report["all_participant_scores"] = allsc
    report["selected_on_all_insample"] = shipped
    report["insample"] = {n: metrics(rows, n, parts) for n in (shipped, "production")}
    print(json.dumps(report, indent=1, default=float))
    if a.out:
        open(a.out, "w").write(json.dumps(report, indent=1, default=float) + "\n")


if __name__ == "__main__":
    main()
