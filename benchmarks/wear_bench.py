"""
Public-data evaluation of motion-based wear inference. NOT hardware evidence.

    python -m benchmarks.wear_bench [--data data/external] [--out benchmarks/results/wear_public_data.json]

What it measures (and what it cannot):

  A. "How still is a WORN, sleeping wrist?"  Walch 2019 PSG nights (17 subjects, Apple Watch, 50 Hz):
     the whole PSG window is wear by construction. For several stillness thresholds, the share of the
     night that lies in continuous still runs of >= 5 / 15 min is exactly the share a MOTION-ONLY removal
     detector would mislabel as removal. (Apple Watch noise floor != LSM6DS3; thresholds do not transfer
     to ParkinSense hardware until bench test W1 is done.)

  B. The Phase 8 state machine run on those nights with PPG contact permanently ABSENT (worst case for
     a worn device: finger never on the sensor). Reported: share of the night spent in POSSIBLY_REMOVED
     and REMOVED = false-removal rate of the shipped configuration in the worst case.

  C. The same for 27 Karas daytime recordings restricted to labelled DRIVING (seated, hands on wheel).

  There is NO non-wear ground truth in these datasets, so sensitivity to true removal cannot be measured
  here; that needs the table / bench recordings of plan W1-W3 on real hardware.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np

from parkinsense.datasets import reference as R
from parkinsense.wear import WearConfig, analyze_arrays

NO_FINGER_IR = 1_600.0
THRESH_MG = (1.0, 2.0, 4.0, 8.0, 13.0)


MIN_RATE_HZ = 20.0
MIN_HOURS = 3.0


def usable(rec) -> str | None:
    """Reason a Walch night is excluded, or None. Low-rate files (10 Hz) have a different noise bandwidth."""
    dt = np.diff(rec.t)
    if len(dt) == 0 or 1.0 / float(np.median(dt)) < MIN_RATE_HZ:
        return "sampling rate < 20 Hz"
    if rec.duration_s < MIN_HOURS * 3600:
        return "recording < 3 h"
    return None


def epoch_sd_max(t: np.ndarray, acc: np.ndarray, epoch_s: float = 1.0, min_n: int = 20):
    """Max-axis SD of acceleration per `epoch_s` epoch, vectorised. Returns (epoch_ids, sd_g)."""
    ids = np.floor((t - t[0]) / epoch_s).astype(np.int64)
    edges = np.r_[0, np.flatnonzero(np.diff(ids)) + 1]
    n = np.diff(np.r_[edges, len(ids)]).astype(float)
    s1 = np.add.reduceat(acc, edges, axis=0)
    s2 = np.add.reduceat(acc * acc, edges, axis=0)
    var = np.maximum(s2 / n[:, None] - (s1 / n[:, None]) ** 2, 0.0)
    sd = np.sqrt(var).max(axis=1)
    keep = n >= min_n
    return ids[edges][keep], sd[keep]


def still_run_share(ids, still, min_run_epochs):
    """Share of epochs lying in consecutive-epoch still runs of at least `min_run_epochs`."""
    if len(ids) == 0:
        return 0.0
    contiguous = np.r_[True, np.diff(ids) == 1]
    run = 0
    inrun = np.zeros(len(still), bool)
    start = 0
    for i in range(len(still)):
        if still[i] and (run == 0 or contiguous[i]):
            if run == 0:
                start = i
            run += 1
        else:
            if run >= min_run_epochs:
                inrun[start:i] = True
            run = 1 if still[i] else 0
            start = i
    if run >= min_run_epochs:
        inrun[start:len(still)] = True
    return float(inrun.mean())


def section_a(root: Path, log=print):
    rows, pooled, excluded = [], [], []
    for s in R.walch_subjects(root):
        rec = R.load_walch(root, s)
        why = usable(rec)
        if why:
            excluded.append({"subject": s, "reason": why})
            continue
        ids, sd = epoch_sd_max(rec.t, rec.acc)
        pooled.append(sd)
        row = {"subject": s, "minutes": round(len(sd) / 60, 1),
               "sd_mg_quantiles_q01_q05_q25_q50": [round(float(x) * 1000, 2) for x in np.quantile(sd, [.01, .05, .25, .5])]}
        for th in THRESH_MG:
            st = sd < th / 1000.0
            row[f"{th:g}mg"] = {"epoch_fraction_still": round(float(st.mean()), 4),
                                "share_in_runs_ge_5min": round(still_run_share(ids, st, 300), 4),
                                "share_in_runs_ge_15min": round(still_run_share(ids, st, 900), 4)}
        rows.append(row)
        log(f"A {s} {row['minutes']:6.1f} min  SD q05/q50 {row['sd_mg_quantiles_q01_q05_q25_q50'][1]}/"
            f"{row['sd_mg_quantiles_q01_q05_q25_q50'][3]} mg  runs>=15min @4mg {row['4mg']['share_in_runs_ge_15min']:.3f}")
    al = np.concatenate(pooled)
    summ = {"subjects": len(rows), "excluded": excluded, "epochs": int(len(al)), "sd_mg_quantiles_q01_q05_q25_q50": [round(float(x) * 1000, 2) for x in np.quantile(al, [.01, .05, .25, .5])]}
    for th in THRESH_MG:
        summ[f"{th:g}mg"] = {
            "mean_share_in_runs_ge_5min": round(float(np.mean([r[f"{th:g}mg"]["share_in_runs_ge_5min"] for r in rows])), 4),
            "mean_share_in_runs_ge_15min": round(float(np.mean([r[f"{th:g}mg"]["share_in_runs_ge_15min"] for r in rows])), 4),
            "subjects_with_any_run_ge_15min": int(sum(r[f"{th:g}mg"]["share_in_runs_ge_15min"] > 0 for r in rows))}
    return rows, summ


def run_machine(t, acc, fs, still_sd_g):
    cfg = WearConfig(expected_rate_hz=fs, still_acc_sd_g=still_sd_g)
    ir = np.full(len(t), NO_FINGER_IR)
    m = analyze_arrays(t, acc, None, ir, None, None, config=cfg, fs=fs, chunk=5000, keep_epochs=True)
    return m


def section_b(root: Path, thresholds_g=(0.001, 0.002, 0.004), log=print):
    out = {f"{th * 1000:g}mg": [] for th in thresholds_g}
    for s in R.walch_subjects(root):
        rec = R.load_walch(root, s)
        if usable(rec):
            continue
        for th in thresholds_g:
            m = run_machine(rec.t, rec.acc, 50.0, th)
            tis = m.time_in_state
            tot = sum(tis.values()) or 1.0
            out[f"{th * 1000:g}mg"].append({
                "subject": s, "minutes": round(tot / 60, 1),
                "possibly_removed_frac": round(tis["POSSIBLY_REMOVED"] / tot, 4),
                "removed_frac": round(tis["REMOVED"] / tot, 4),
                "ever_removed": bool(tis["REMOVED"] > 0)})
        log(f"B {s} " + " ".join(f"{k}: rem {v[-1]['removed_frac']:.3f}" for k, v in out.items()))
    summ = {k: {"mean_possibly_removed_frac": round(float(np.mean([r["possibly_removed_frac"] for r in v])), 4),
                "mean_removed_frac": round(float(np.mean([r["removed_frac"] for r in v])), 4),
                "subjects_ever_removed": int(sum(r["ever_removed"] for r in v)), "subjects": len(v)}
            for k, v in out.items()}
    return out, summ


def section_c(root: Path, log=print):
    rows = []
    for s in R.karas_subjects(root):
        rec = R.load_karas(root, s)
        drive = rec.activity == 4
        if drive.sum() < 100 * 120:
            continue
        m = run_machine(rec.t, rec.acc, 100.0, WearConfig().still_acc_sd_g)
        ep = np.array([(e[0], e[1]) for e in m.epoch_log], dtype=object)
        tt = np.array([e[0] for e in m.epoch_log])
        idx = np.clip(np.searchsorted(rec.t - rec.t[0], tt), 0, len(rec.t) - 1)
        dmask = drive[idx]
        states = np.array([e[1] for e in m.epoch_log])
        n = int(dmask.sum())
        row = {"subject": s, "driving_min": round(n / 60, 1),
               "removed_frac": round(float((states[dmask] == "REMOVED").mean()), 4) if n else None,
               "possibly_removed_frac": round(float((states[dmask] == "POSSIBLY_REMOVED").mean()), 4) if n else None}
        rows.append(row)
        log(f"C {s} driving {row['driving_min']} min removed {row['removed_frac']} possibly {row['possibly_removed_frac']}")
        del ep
    summ = {"subjects": len(rows), "driving_minutes": round(sum(r["driving_min"] for r in rows), 1),
            "mean_removed_frac": round(float(np.mean([r["removed_frac"] for r in rows])), 4) if rows else None,
            "mean_possibly_removed_frac": round(float(np.mean([r["possibly_removed_frac"] for r in rows])), 4) if rows else None}
    return rows, summ


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--data", default="data/external")
    ap.add_argument("--out")
    ap.add_argument("--only", choices=["a", "b", "c"])
    a = ap.parse_args(argv)
    d = Path(a.data)
    t0 = time.time()
    rep = {"benchmark": "wear_public_data", "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
           "defaults": WearConfig().to_dict(),
           "caveats": ["public wrist data, not ParkinSense hardware", "no non-wear ground truth exists in these data",
                       "Apple Watch / ActiGraph noise floors differ from the LSM6DS3"],
           "datasets": {"walch": R.WALCH_PROVENANCE, "karas": R.KARAS_PROVENANCE}}
    if a.only in (None, "a"):
        rows, summ = section_a(d / "walch")
        rep["A_worn_sleep_stillness"] = {"per_subject": rows, "summary": summ}
    if a.only in (None, "b"):
        rows, summ = section_b(d / "walch")
        rep["B_state_machine_worst_case_no_ppg"] = {"per_subject": rows, "summary": summ}
    if a.only in (None, "c"):
        rows, summ = section_c(d / "karas")
        rep["C_driving_state_machine"] = {"per_subject": rows, "summary": summ}
    rep["runtime_s"] = round(time.time() - t0, 1)
    for k, v in rep.items():
        if isinstance(v, dict) and "summary" in v:
            print(k, json.dumps(v["summary"], indent=1))
    if a.out:
        Path(a.out).write_text(json.dumps(rep, indent=1, default=float) + "\n")


if __name__ == "__main__":
    main()
