"""
Sleep/wake benchmark against polysomnography, subject-independent.

    python -m benchmarks.sleep_bench --walch data/external/walch [--out benchmarks/results/sleep_walch.json]
    python -m benchmarks.sleep_bench --walch ... --emit-params parkinsense/sleep/params.py

Data: Walch et al. 2019 (PhysioNet sleep-accel; wrist Apple Watch accel +
PPG heart rate, PSG 30 s epochs). Every subject whose acceleration file is
available is used; all scores are leave-one-subject-out (LOSO): the held-out
night never contributes to training, transition estimation or feature
scaling. These are public-dataset results, not ParkinSense hardware results.

Methods compared
  vanhees_dz      van Hees et al. 2015, z-angle, 5 deg / 5 min (published heuristic, no training)
  vanhees_dg      same rule on the orientation-free gravity-angle change
  lr_plain        logistic regression on 6 movement-context features, threshold 0.5
  hmm_untempered  lr_plain + 2-state HMM without the overlap correction (ablation)
  lr              logistic regression, decision threshold chosen by nested LOSO
  lr_hmm          lr + tempered 2-state HMM; (beta, threshold) chosen by nested LOSO   <- candidate
  lr_hr_hmm       lr_hmm + 2 heart-rate features
  rf_hmm_untempered  random forest on the same features + HMM (scikit-learn, reference only)

Hyperparameters (HMM temper beta, decision threshold) are chosen by an
inner leave-one-subject-out loop on the training subjects of each outer
fold, never on the held-out night.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np

from parkinsense import config as C
from parkinsense.datasets import reference as R
from parkinsense.sleep import features as F
from parkinsense.sleep import model as M
from parkinsense.sleep import night as N


def epoch_metrics(y_true, y_pred) -> dict:
    m = (y_true >= 0)
    t, p = y_true[m], np.where(y_pred[m] < 0, 0, y_pred[m])     # gap epochs scored as wake
    tp = np.sum((t == 1) & (p == 1)); tn = np.sum((t == 0) & (p == 0))
    fp = np.sum((t == 0) & (p == 1)); fn = np.sum((t == 1) & (p == 0))
    n = len(t)
    sens = tp / max(tp + fn, 1); spec = tn / max(tn + fp, 1)
    po = (tp + tn) / max(n, 1)
    pe = ((tp + fp) * (tp + fn) + (tn + fn) * (tn + fp)) / max(n * n, 1)
    return {"n": int(n), "accuracy": po, "sensitivity_sleep": sens, "specificity_wake": spec,
            "balanced_accuracy": (sens + spec) / 2,
            "f1_sleep": 2 * tp / max(2 * tp + fp + fn, 1), "f1_wake": 2 * tn / max(2 * tn + fn + fp, 1),
            "kappa": (po - pe) / (1 - pe) if pe < 1 else 0.0}


def night_errors(tab, y_true, y_pred) -> dict:
    ref = N.summarize(tab, np.where(y_true < 0, -1, y_true))
    est = N.summarize(tab, y_pred)
    out = {}
    for k in ("tst_min", "waso_min", "spt_min", "period_efficiency"):
        if k in ref and k in est:
            out[k] = (est[k], ref[k], est[k] - ref[k])
    if "onset_s" in ref and "onset_s" in est:
        out["onset_min"] = (est["onset_s"] / 60, ref["onset_s"] / 60, (est["onset_s"] - ref["onset_s"]) / 60)
        out["wake_min"] = (est["wake_s"] / 60, ref["wake_s"] / 60, (est["wake_s"] - ref["wake_s"]) / 60)
    # total sleep over the whole PSG record (independent of the SPT definition)
    m = y_true >= 0
    out["total_sleep_min"] = (float(np.sum(y_pred[m] == 1)) / 2, float(np.sum(y_true[m] == 1)) / 2,
                              float(np.sum(y_pred[m] == 1) - np.sum(y_true[m] == 1)) / 2)
    return out


MIN_SUBJECT_COVERAGE = 0.5      # nights with accel in < 50 % of PSG epochs are excluded (reported)


def prepare(root, excluded=None):
    data = []
    for s in R.walch_subjects(root):
        rec = R.load_walch(root, s)
        t0 = rec.sleep_epoch_t[0]
        tab = F.epoch_features(rec.t, rec.acc, t0=t0, n_epochs=len(rec.sleep_epochs), fs=None,
                               hr_t=rec.hr_t, hr=rec.hr)
        cov = float(np.mean(tab.coverage >= F.MIN_COVERAGE))
        if cov < MIN_SUBJECT_COVERAGE:
            if excluded is not None:
                excluded.append({"subject": s, "epochs_with_data": round(cov, 3)})
            continue
        data.append({"subject": s, "tab": tab, "y": rec.sleep_epochs.astype(int),
                     "X": M.context_features(tab), "Xhr": M.context_features(tab, use_hr=True)})
    return data


GRID_BETA = (1.0, 0.5, 0.25, 0.1)
GRID_THRESHOLD = (0.5, 0.6, 0.7)


def fit(train, key="X", rf=False, beta=1.0, threshold=0.5):
    X = np.concatenate([d[key] for d in train])
    y = np.concatenate([d["y"] for d in train])
    ok = np.isfinite(X).all(1) & (y >= 0)
    pss, psw, prior = M.transitions_from_labels([d["y"] for d in train])
    params = {"p_stay_sleep": pss, "p_stay_wake": psw, "prior_sleep": prior, "threshold": threshold,
              "beta": beta}
    if rf:
        from sklearn.ensemble import RandomForestClassifier
        clf = RandomForestClassifier(n_estimators=300, min_samples_leaf=20, n_jobs=-1, random_state=0)
        clf.fit(X[ok], y[ok])
        params["rf"] = clf
    else:
        params["logistic"] = M.fit_logistic(X[ok], y[ok], l2=1.0)
    return params


def predict(params, d, key="X", smooth=True):
    X = d[key]
    ok = np.isfinite(X).all(1)
    p = np.full(len(X), np.nan)
    if "rf" in params:
        p[ok] = params["rf"].predict_proba(X[ok])[:, 1]
    else:
        p[ok] = M.predict_proba(params["logistic"], X[ok])
    if smooth:
        p = M.hmm_smooth(p, params["p_stay_sleep"], params["p_stay_wake"], params["prior_sleep"],
                         beta=params["beta"])
    return np.where(np.isfinite(d["tab"].dg_max), (p >= params["threshold"]).astype(int), -1)


def select(train, key="X", smooth=True):
    """Inner leave-one-subject-out over the training subjects only: pick (beta, threshold) by mean kappa."""
    inner = [fit([e for j, e in enumerate(train) if j != i], key=key) for i in range(len(train))]
    best, best_k = None, -1
    for beta in (GRID_BETA if smooth else (1.0,)):
        for thr in GRID_THRESHOLD:
            k = np.mean([epoch_metrics(d["y"], predict(dict(inner[i], beta=beta, threshold=thr), d, key, smooth))["kappa"]
                         for i, d in enumerate(train)])
            if k > best_k:
                best, best_k = (beta, thr), k
    return fit(train, key=key, beta=best[0], threshold=best[1])


def summarize_results(per):
    keys = [k for k in per[0]["epoch"] if k != "n"]
    pooled = {k: float(np.mean([p["epoch"][k] for p in per])) for k in keys}
    pooled_sd = {k: float(np.std([p["epoch"][k] for p in per])) for k in keys}
    night = {}
    for k in per[0]["night"]:
        errs = np.array([p["night"][k][2] for p in per if k in p["night"]], float)
        night[k] = {"mean_error": float(errs.mean()), "mae": float(np.abs(errs).mean()),
                    "n": int(len(errs))}
    return {"epoch_mean_over_subjects": pooled, "epoch_sd_over_subjects": pooled_sd, "night": night}


def paired_bootstrap(methods, base, n_boot=10000, seed=0):
    """Subject-level paired bootstrap of (method - base): kappa, balanced accuracy, |TST error| (min)."""
    rng = np.random.default_rng(seed)
    def vec(m):
        per = methods[m]["per_subject"]
        return np.array([[p["epoch"]["kappa"], p["epoch"]["balanced_accuracy"], abs(p["night"]["tst_min"][2])
                          if "tst_min" in p["night"] else np.nan] for p in per])
    b = vec(base)
    out = {}
    for m in methods:
        if m == base:
            continue
        d = vec(m) - b
        idx = rng.integers(0, len(d), (n_boot, len(d)))
        res = {}
        for j, k in enumerate(("kappa", "balanced_accuracy", "abs_tst_error_min")):
            col = d[:, j]
            ok = ~np.isnan(col)
            bs = np.nanmean(np.where(ok[idx], col[idx], np.nan), axis=1)
            res[k] = {"mean_diff": float(np.nanmean(col)), "ci95": np.percentile(bs, [2.5, 97.5]).tolist(),
                      "subjects_better": int(np.sum(col[ok] > 0) if j < 2 else np.sum(col[ok] < 0)), "n": int(ok.sum())}
        out[m] = res
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--walch", default="data/external/walch")
    ap.add_argument("--out")
    ap.add_argument("--emit-params", help="write the production parameter module fitted on ALL subjects")
    ap.add_argument("--no-rf", action="store_true")
    a = ap.parse_args(argv)
    t_start = time.time()
    excluded = []
    data = prepare(a.walch, excluded)
    methods = {}

    def run(name, fn):
        per = []
        for i, d in enumerate(data):
            pred = fn(i, d)
            per.append({"subject": d["subject"], "epoch": M_epoch(d, pred), "night": night_errors(d["tab"], d["y"], pred)})
        methods[name] = {"per_subject": per, **summarize_results(per)}

    def M_epoch(d, pred):
        return epoch_metrics(d["y"], pred)

    run("vanhees_dz", lambda i, d: M.vanhees_sleep(d["tab"], "dz"))
    run("vanhees_dg", lambda i, d: M.vanhees_sleep(d["tab"], "dg"))
    others = lambda i: [e for j, e in enumerate(data) if j != i]  # noqa: E731
    plain = [fit(others(i)) for i in range(len(data))]
    run("lr_plain", lambda i, d: predict(plain[i], d, smooth=False))
    run("hmm_untempered", lambda i, d: predict(plain[i], d))
    nested_lr = [select(others(i), smooth=False) for i in range(len(data))]
    run("lr", lambda i, d: predict(nested_lr[i], d, smooth=False))
    nested = [select(others(i)) for i in range(len(data))]
    run("lr_hmm", lambda i, d: predict(nested[i], d))
    nested_hr = [select(others(i), key="Xhr") for i in range(len(data))]
    run("lr_hr_hmm", lambda i, d: predict(nested_hr[i], d, key="Xhr"))
    chosen = {name: [(p["beta"], p["threshold"]) for p in ps]
              for name, ps in (("lr", nested_lr), ("lr_hmm", nested), ("lr_hr_hmm", nested_hr))}
    if not a.no_rf:
        try:
            loso_rf = [fit([e for j, e in enumerate(data) if j != i], rf=True) for i in range(len(data))]
            run("rf_hmm_untempered", lambda i, d: predict(loso_rf[i], d))
        except ImportError:
            print("scikit-learn not installed: rf_hmm skipped")

    labels = np.concatenate([d["y"] for d in data])
    report = {
        "benchmark": "sleep_walch_loso", "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "sleep_algorithm_version": C.SLEEP_ALGORITHM_VERSION, "pipeline_version": C.PIPELINE_VERSION,
        "dataset": R.WALCH_PROVENANCE, "subjects": [d["subject"] for d in data], "excluded": excluded,
        "epochs_scored": int((labels >= 0).sum()), "sleep_fraction": float((labels == 1).sum() / (labels >= 0).sum()),
        "protocol": "leave-one-subject-out; gap epochs (< 50 % samples) scored as wake; night metrics use "
                    "parkinsense.sleep.night definitions applied to both PSG labels and predictions",
        "config": {"epoch_s": F.EPOCH_S, "still_deg": M.STILL_DEG, "still_min": M.STILL_MIN,
                   "context_min": M.CONTEXT_MIN, "spt_merge_gap_min": N.SPT_MERGE_GAP_MIN},
        "selected_hyperparameters_per_fold": chosen,
        "paired_vs_vanhees_dz": paired_bootstrap(methods, "vanhees_dz"),
        "methods": methods, "runtime_s": round(time.time() - t_start, 1),
    }
    for name, m in methods.items():
        e, n = m["epoch_mean_over_subjects"], m["night"]
        print(f"{name:12s} kappa {e['kappa']:.3f}  bal.acc {e['balanced_accuracy']:.3f}  sens {e['sensitivity_sleep']:.3f}"
              f"  spec {e['specificity_wake']:.3f}  F1s {e['f1_sleep']:.3f}  | TST MAE {n['tst_min']['mae']:.1f}"
              f" (bias {n['tst_min']['mean_error']:+.1f})  WASO MAE {n['waso_min']['mae']:.1f}"
              f"  onset MAE {n.get('onset_min', {}).get('mae', float('nan')):.1f}"
              f"  wake MAE {n.get('wake_min', {}).get('mae', float('nan')):.1f}")
    for name, r in report["paired_vs_vanhees_dz"].items():
        k, t = r["kappa"], r["abs_tst_error_min"]
        print(f"  {name:12s} vs vanhees_dz: dkappa {k['mean_diff']:+.3f} CI [{k['ci95'][0]:+.3f},{k['ci95'][1]:+.3f}]"
              f" ({k['subjects_better']}/{k['n']} subjects better) | d|TST err| {t['mean_diff']:+.1f} min"
              f" CI [{t['ci95'][0]:+.1f},{t['ci95'][1]:+.1f}]")
    if a.out:
        Path(a.out).write_text(json.dumps(report, indent=1, default=float) + "\n")
    if a.emit_params:
        full = dict(select(data, smooth=False), smooth=False)       # production model = "lr" (no HMM, no HR)
        Path(a.emit_params).write_text(
            '"""Production sleep parameters (generated by benchmarks/sleep_bench.py --emit-params; do not edit).\n\n'
            f'Model "lr": logistic regression on movement-context features, decision threshold chosen by nested LOSO,\n'
            f'no HMM, no heart rate (both were evaluated and did not improve held-out agreement).\n'
            f'Fitted on all {len(data)} Walch 2019 subjects; LOSO performance in benchmarks/results/sleep_walch.json.\n"""\n\n'
            f"SLEEP_ALGORITHM_VERSION = {C.SLEEP_ALGORITHM_VERSION!r}\n"
            f"FEATURES_ACCEL = {M.ACCEL_FEATURES!r}\n"
            f"ACCEL = {json.dumps(full, indent=4)}\n".replace("false", "False"))
        print("wrote", a.emit_params)


if __name__ == "__main__":
    main()
