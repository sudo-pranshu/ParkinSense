#!/usr/bin/env python3
"""Generates every figure of the ParkinSense paper into docs/research/paper/figures/.

Data sources: the committed benchmark results (benchmarks/results/*.json), the repository's own pipeline run on its
synthetic generators (parkinsense.synthetic) and the repository's images. Nothing is hand-entered except the
architecture/protocol diagrams and the status matrix (status_data.py).
Run from the repository root:  python3 docs/research/paper/make_figures.py
"""
import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch  # noqa: E402

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).parent))
OUT = Path(__file__).parent / "figures"
OUT.mkdir(exist_ok=True)
RES = ROOT / "benchmarks" / "results"

from parkinsense.motion import features as F  # noqa: E402
from parkinsense.runtime.engine import RuntimeEngine  # noqa: E402
from parkinsense.synthetic import signals as S  # noqa: E402
from status_data import COLS, ROWS  # noqa: E402
from tests.helpers import run_engine  # noqa: E402

BLUE, ORANGE, GREEN, RED, PURPLE, GREY, SKY = "#0072B2", "#E69F00", "#009E73", "#D55E00", "#CC79A7", "#777777", "#56B4E9"
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 7, "axes.titlesize": 7.5, "axes.labelsize": 7,
                     "xtick.labelsize": 6.5, "ytick.labelsize": 6.5, "legend.fontsize": 6.3, "axes.spines.top": False,
                     "axes.spines.right": False, "axes.linewidth": 0.6, "lines.linewidth": 1.0, "figure.dpi": 100,
                     "legend.frameon": False})
COL, WIDE = 3.45, 7.1


def save(fig, name):
    fig.savefig(OUT / f"{name}.png", dpi=300, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print("wrote", name)


def jload(n):
    return json.load(open(RES / n))


def panel(ax, s):
    ax.text(-0.02, 1.04, s, transform=ax.transAxes, fontsize=8, fontweight="bold", va="bottom", ha="right")


def box(ax, x, y, w, h, text, fc="#EEF3F8", ec="#44576B", fs=5.8, bold=False, tc="black"):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.01,rounding_size=0.012", fc=fc, ec=ec, lw=0.7))
    ax.text(x + w / 2, y + h / 2, text, ha="center", va="center", fontsize=fs, fontweight="bold" if bold else "normal", color=tc,
            linespacing=1.25)


def arrow(ax, p, q, color="#44576B", ls="-", lw=0.8, style="-|>", rad=0.0):
    ax.add_patch(FancyArrowPatch(p, q, arrowstyle=style, mutation_scale=7, color=color, lw=lw, ls=ls,
                                 connectionstyle=f"arc3,rad={rad}"))


# --------------------------------------------------------------------------------------------- 1. architecture
def fig_architecture():
    fig, ax = plt.subplots(figsize=(WIDE, 3.15))
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    ax.text(0.01, 0.975, "Wearable", fontsize=7, fontweight="bold", color=GREY)
    ax.text(0.30, 0.975, "Python host (parkinsense/)", fontsize=7, fontweight="bold", color=GREY)
    ax.text(0.80, 0.975, "Consumers", fontsize=7, fontweight="bold", color=GREY)
    box(ax, 0.01, 0.74, 0.17, 0.12, "LSM6DS3 IMU\n104 Hz accel + gyro", "#DCEBF7")
    box(ax, 0.01, 0.55, 0.17, 0.12, "MAX30102\nIR + RED, 100 SPS FIFO", "#F8E3E3")
    box(ax, 0.01, 0.30, 0.17, 0.17, "XIAO firmware\nacquire, timestamp, pack\nv4: hardware-verified\n5.0.0: host-tested only", "#EEEEEE")
    arrow(ax, (0.095, 0.74), (0.095, 0.47))
    arrow(ax, (0.095, 0.55), (0.095, 0.47))
    box(ax, 0.01, 0.07, 0.17, 0.14, "BLE 5 notify, 208 B\n8 B header + 10 x 20 B\n≈10.4 packets/s", "#FFF4D6")
    arrow(ax, (0.095, 0.30), (0.095, 0.21))
    arrow(ax, (0.18, 0.14), (0.27, 0.14))
    box(ax, 0.27, 0.07, 0.15, 0.14, "decode, integrity\nunwrap · seq · gap ·\nrate (±5 %)", "#EEEEEE")
    # pipelines
    box(ax, 0.27, 0.62, 0.20, 0.22, "Motion pipeline\n4 s window, hop 0.5 s\nWelch PSD, 3.5–7.5 Hz peak\ncontext, evidence, HMM", "#DCEBF7", bold=False)
    box(ax, 0.27, 0.36, 0.20, 0.18, "PPG pipeline\n10 s buffer\nfinger, SQI, HR, HRV, SpO2", "#F8E3E3")
    box(ax, 0.52, 0.62, 0.16, 0.22, "Step counter\nper-sample, 104 Hz\nhigh-pass, adaptive\nthreshold, refractory", "#E1F2EA")
    box(ax, 0.52, 0.36, 0.16, 0.18, "Wear monitor\n(opt-in, inferred)\nstill + contact evidence", "#EADFF0")
    arrow(ax, (0.345, 0.21), (0.345, 0.36))
    arrow(ax, (0.30, 0.21), (0.30, 0.62), rad=0.0)
    arrow(ax, (0.42, 0.21), (0.55, 0.62), rad=0.0)
    arrow(ax, (0.42, 0.18), (0.58, 0.36), rad=0.0)
    # cross-pipeline gating
    arrow(ax, (0.37, 0.62), (0.37, 0.54), color=RED, ls="--")
    ax.text(0.385, 0.575, "motion state, f_arm", fontsize=5.4, color=RED, va="center", bbox=dict(fc="white", ec="none", pad=0.4))
    arrow(ax, (0.47, 0.73), (0.52, 0.73), color=RED, ls="--")
    arrow(ax, (0.60, 0.54), (0.60, 0.62), color=RED, ls="--")
    ax.text(0.612, 0.58, "REMOVED→REST", fontsize=5.4, color=RED, va="center", bbox=dict(fc="white", ec="none", pad=0.4))
    # engine/outputs
    box(ax, 0.27, 0.01, 0.41, 0.045, "RuntimeEngine: device-clock signal time; live = replay", "#FFFFFF", fs=5.4)
    box(ax, 0.74, 0.70, 0.25, 0.14, "capture.csv (79 columns)\nmetadata.json\n(versions, loss, rate, wrap)", "#FFFFFF")
    box(ax, 0.74, 0.50, 0.25, 0.14, "FastAPI /live /metrics\nmetrics JSON", "#FFFFFF")
    box(ax, 0.74, 0.28, 0.25, 0.16, "Plotly Dash dashboard\nlive · history · replay\n(consumer only)", "#FFFFFF")
    box(ax, 0.74, 0.07, 0.25, 0.16, "Offline tools\nreplay · sleep (30 s epochs)\nanalytics · baselines · wear CLI", "#FFFFFF")
    arrow(ax, (0.68, 0.73), (0.74, 0.77))
    arrow(ax, (0.68, 0.50), (0.74, 0.57))
    arrow(ax, (0.80, 0.50), (0.80, 0.44))
    arrow(ax, (0.865, 0.70), (0.865, 0.23), ls=":", color=GREY)
    ax.text(0.42, 0.88, "Red dashed: cross-pipeline gating and confidence coupling", fontsize=5.8, color=RED)
    save(fig, "p_architecture")


# --------------------------------------------------------------------------------------------- 2. packet
def fig_packet():
    fig, ax = plt.subplots(figsize=(COL, 1.9))
    ax.set_xlim(0, 28)
    ax.set_ylim(-0.2, 4.2)
    ax.axis("off")
    cols = {"h": "#DCEBF7", "a": "#E1F2EA", "g": "#FFF4D6", "p": "#F8E3E3"}

    def row(y, fields, label):
        x = 0
        for name, w, c in fields:
            ax.add_patch(plt.Rectangle((x, y), w, 0.8, fc=cols[c], ec="#44576B", lw=0.6))
            ax.text(x + w / 2, y + 0.4, name, ha="center", va="center", fontsize=5.4)
            x += w
        ax.text(-0.3, y + 0.4, label, ha="right", va="center", fontsize=6)

    row(3.2, [("ver", 1, "h"), ("flags", 1, "h"), ("seq / 0", 2, "h"), ("timestamp_us", 4, "h")], "header 8 B")
    row(1.9, [("ax", 2, "a"), ("ay", 2, "a"), ("az", 2, "a"), ("gx", 2, "g"), ("gy", 2, "g"), ("gz", 2, "g"), ("ir", 4, "p"), ("red", 4, "p")],
        "sample 20 B")
    ax.text(14, 1.45, "x 10 samples, device time = timestamp + i·9615 µs", ha="center", fontsize=5.8)
    ax.text(-0.3, 0.55, "scales", ha="right", va="center", fontsize=6)
    ax.text(0.2, 0.55, "accel 8192/g · gyro v1 131/dps (±250) · v2 64/dps (±512) · IR/RED 18-bit counts (u32)", fontsize=5.6, va="center")
    ax.text(0.2, 0.0, "v2 flags: accel/gyro clipped, IMU/PPG fault, PPG stale, notify failed, time discontinuity", fontsize=5.6, va="center")
    ax.text(0.2, 4.05, "208 B = 8 + 10 x 20 (v1 and v2); seq is reserved (0) in v1", fontsize=6)
    save(fig, "p_packet")


# --------------------------------------------------------------------------------------------- 3. PSD per scenario
def scenario_window(sig, seed_t0=10.0, fs=104.0):
    n0 = int(seed_t0 * fs)
    sl = slice(n0, n0 + int(4 * fs))
    return sig.gyro()[:, sl], sig.accel()[:, sl]


def fig_psd():
    fs = 104.0
    sc = [("rest tremor, 5.0 Hz, 20°/s peak", S.rest_tremor(seconds=30, seed=2, freq=5.0, amp=20.0), BLUE),
          ("purposeful arm movement", S.voluntary(seconds=30, seed=3), GREEN),
          ("walking", S.walking(seconds=30, seed=4), ORANGE),
          ("non-PD oscillation (8.5–11 Hz)", S.non_pd_oscillation(seconds=30, seed=5), RED)]
    fig, axs = plt.subplots(1, 4, figsize=(WIDE, 2.05), sharey=False)
    from parkinsense.motion.context import MotionContext
    from parkinsense.tremor import detector as D
    ctx = MotionContext(fs)
    info = []
    for ax, (name, sig, c) in zip(axs, sc):
        g, a = scenario_window(sig)
        fr, psd = F.gyro_spectrum(g, fs)
        s = psd.sum(axis=0)
        ft = F.extract(g, fs)
        cl = ctx.classify(a, ft.arm_rms_dps)
        ev = D.evaluate(ft, cl["state"])
        m = (fr >= 0.5) & (fr <= 15)
        ax.semilogy(fr[m], s[m], color=c)
        ax.axvspan(3.5, 7.5, color="#DDDDDD", alpha=0.55, lw=0)
        ax.axvline(ft.peak_frequency_hz, color="k", lw=0.6, ls=":")
        ax.set_xlabel("frequency (Hz)")
        ax.set_title(f"{name}\nf̂ = {ft.peak_frequency_hz:.2f} Hz · SNR {ev.snr_db:.1f} dB\n{cl['state']} · e = {ev.evidence:.2f}", fontsize=5.6)
        info.append((name, ft.peak_frequency_hz, ev.snr_db, cl["state"], ev.evidence))
    axs[0].set_ylabel("summed-axis PSD ((°/s)²/Hz)")
    fig.tight_layout(w_pad=1.2)
    save(fig, "p_psd")
    json.dump(info, open(OUT / "psd_numbers.json", "w"), indent=1)
    return info


# --------------------------------------------------------------------------------------------- 4. HMM trace
def fig_hmm():
    segs = [S.rest(seconds=20, seed=11), S.rest_tremor(seconds=30, seed=12, freq=5.0, amp=25.0), S.rest(seconds=30, seed=13)]
    sig, _ = S.concatenate(segs)
    eng = RuntimeEngine()
    rows, an = run_engine(eng, sig, version=2)
    t = np.array([a["signal_time_s"] for a in an])
    t0 = t[0]
    t = t - 0.0
    ev = np.array([a["tremor_evidence"] for a in an])
    p = np.array([a["tremor_probability"] for a in an])
    pub = np.array([a["classification"] == "TREMOR" for a in an])
    fig, axs = plt.subplots(2, 1, figsize=(COL, 2.8), sharex=True, gridspec_kw={"height_ratios": [2, 1]})
    ax = axs[0]
    ax.plot(t, ev, color=GREY, lw=0.8, label="window evidence e")
    ax.plot(t, p, color=BLUE, lw=1.2, label="P(tremor), HMM")
    ax.axhline(0.8, color=BLUE, ls=":", lw=0.6)
    ax.axhline(0.2, color=BLUE, ls=":", lw=0.6)
    ax.axvspan(20, 50, color="#EEEEEE", lw=0)
    ax.set_ylabel("0–1")
    ax.legend(loc="center left", bbox_to_anchor=(0.02, 0.62))
    ax.text(35, 0.04, "true tremor", ha="center", fontsize=6, color=GREY)
    ax = axs[1]
    ax.fill_between(t, 0, pub.astype(float), step="post", color=BLUE, alpha=0.6, lw=0)
    ax.axvspan(20, 50, color="#EEEEEE", lw=0, zorder=0)
    ax.set_yticks([0, 1])
    ax.set_yticklabels(["no", "TREMOR"])
    ax.set_ylabel("published")
    ax.set_xlabel("signal time (s)")
    on = t[pub & (t >= 20)].min() - 20 if np.any(pub & (t >= 20)) else float("nan")
    off_idx = np.where((~pub) & (t > 50))[0]
    off = t[off_idx[0]] - 50 if len(off_idx) else float("nan")
    save(fig, "p_hmm")
    return {"onset_s": float(on), "offset_s": float(off), "n_analyses": len(an)}


# --------------------------------------------------------------------------------------------- 5. tremor benchmark
def fig_tremor_bench():
    b, c = jload("baseline_legacy.json"), jload("current.json")
    fig, axs = plt.subplots(1, 3, figsize=(WIDE, 2.0), gridspec_kw={"width_ratios": [1.1, 1.3, 1.2]})
    ax = axs[0]
    names = ["sensitivity", "specificity", "F1"]
    vb = [b["tremor"]["analysis_level"][k] for k in ("sensitivity", "specificity", "f1")]
    vc = [c["tremor"]["analysis_level"][k] for k in ("sensitivity", "specificity", "f1")]
    x = np.arange(3)
    ax.bar(x - 0.18, vb, 0.36, color=GREY, label="2.2.0 (baseline)")
    ax.bar(x + 0.18, vc, 0.36, color=BLUE, label="3.0.0 (current)")
    for i in range(3):
        ax.text(x[i] - 0.18, vb[i] + 0.01, f"{vb[i]:.3f}", ha="center", fontsize=5.4)
        ax.text(x[i] + 0.18, vc[i] + 0.01, f"{vc[i]:.3f}", ha="center", fontsize=5.4)
    ax.set_xticks(x)
    ax.set_xticklabels(names)
    ax.set_ylim(0, 1.32)
    ax.legend(loc="upper center", ncol=2, fontsize=5.6, frameon=False)
    ax.set_title("analysis-level, synthetic")
    panel(ax, "(a)")
    ax = axs[1]
    labs = list(b["tremor"]["sensitivity_by_amplitude"].keys())
    x = np.arange(len(labs))
    ax.bar(x - 0.18, [b["tremor"]["sensitivity_by_amplitude"][k] for k in labs], 0.36, color=GREY)
    ax.bar(x + 0.18, [c["tremor"]["sensitivity_by_amplitude"][k] for k in labs], 0.36, color=BLUE)
    ax.set_xticks(x)
    ax.set_xticklabels([l.replace(" dps", "") for l in labs], fontsize=5.8)
    ax.set_xlabel("peak tremor amplitude (°/s)")
    ax.set_ylim(0, 1.1)
    ax.set_title("sensitivity by amplitude")
    panel(ax, "(b)")
    ax = axs[2]
    m = ["onset", "offset"]
    lb = [b["latency"]["onset_latency_s_median"], b["latency"]["offset_latency_s_median"]]
    lc = [c["latency"]["onset_latency_s_median"], c["latency"]["offset_latency_s_median"]]
    x = np.arange(2)
    ax.bar(x - 0.18, lb, 0.36, color=GREY)
    ax.bar(x + 0.18, lc, 0.36, color=BLUE)
    for i in range(2):
        ax.text(x[i] - 0.18, lb[i] + 0.15, f"{lb[i]:.1f}", ha="center", fontsize=5.6)
        ax.text(x[i] + 0.18, lc[i] + 0.15, f"{lc[i]:.1f}", ha="center", fontsize=5.6)
    ax.set_xticks(x)
    ax.set_xticklabels(m)
    ax.set_ylabel("median latency (s)")
    ax.set_title("latency (deliberately longer)")
    ax.set_ylim(0, 9.8)
    panel(ax, "(c)")
    fig.tight_layout(w_pad=1.2)
    save(fig, "p_tremor_bench")


def fig_scenarios():
    b, c = jload("baseline_legacy.json"), jload("current.json")
    order = ["rest_tremor", "subtle_tremor", "strong_tremor", "action_tremor", "walking_with_tremor", "rest", "voluntary", "walking",
             "vibration", "non_pd_oscillation"]
    nice = {"rest_tremor": "rest tremor", "subtle_tremor": "subtle tremor", "strong_tremor": "strong tremor", "action_tremor": "action tremor",
            "walking_with_tremor": "walking+tremor", "rest": "rest", "voluntary": "voluntary", "walking": "walking", "vibration": "vibration",
            "non_pd_oscillation": "8.5–11 Hz osc."}
    vb = [b["tremor"]["per_scenario"][k]["mean_fraction_classified_tremor"] for k in order]
    vc = [c["tremor"]["per_scenario"][k]["mean_fraction_classified_tremor"] for k in order]
    fig, ax = plt.subplots(figsize=(COL, 2.2))
    y = np.arange(len(order))
    ax.barh(y + 0.18, vb, 0.36, color=GREY, label="2.2.0")
    ax.barh(y - 0.18, vc, 0.36, color=BLUE, label="3.0.0")
    ax.axhline(4.5, color="k", lw=0.5, ls=":")
    ax.set_yticks(y)
    ax.set_yticklabels([nice[k] for k in order], fontsize=6)
    ax.invert_yaxis()
    ax.set_xlabel("fraction of analysed windows published as tremor")
    ax.legend(loc="lower right")
    ax.text(0.5, 4.45, "above: tremor present · below: absent", fontsize=5.4, ha="center", va="bottom", color=GREY)
    save(fig, "p_scenarios")


# --------------------------------------------------------------------------------------------- 6. steps
def fig_step_gating():
    b, c = jload("baseline_legacy.json"), jload("current.json")
    ks = ["rest_tremor", "voluntary", "rest", "vibration"]
    nice = ["rest tremor", "purposeful\narm movement", "rest", "vibration"]
    fig, ax = plt.subplots(figsize=(COL, 1.9))
    x = np.arange(len(ks))
    vb = [b["steps"]["false_steps_per_minute"][k] for k in ks]
    vc = [c["steps"]["false_steps_per_minute"][k] for k in ks]
    ax.bar(x - 0.18, vb, 0.36, color=GREY, label="2.2.0")
    ax.bar(x + 0.18, vc, 0.36, color=BLUE, label="3.0.0")
    for i in range(len(ks)):
        ax.text(x[i] - 0.18, vb[i] + 0.8, f"{vb[i]:.1f}", ha="center", fontsize=5.6)
        ax.text(x[i] + 0.18, vc[i] + 0.8, f"{vc[i]:.1f}", ha="center", fontsize=5.6)
    ax.set_xticks(x)
    ax.set_xticklabels(nice, fontsize=6)
    ax.set_ylabel("false steps / min (synthetic)")
    ax.set_ylim(0, 58)
    ax.legend()
    save(fig, "p_step_gating")


def fig_steps_public():
    sel = jload("steps_selection.json")["heldout"]
    kar = {**jload("steps_baseline.json")["karas"]["summary"], **jload("steps_gated_karas.json")["karas"]["summary"]}
    fig, axs = plt.subplots(1, 3, figsize=(WIDE, 2.0), gridspec_kw={"width_ratios": [1.3, 1.3, 1.1]})
    conds = ["Regular", "SemiRegular", "Irregular", "all"]
    cs = {"production": GREY, "periodic": ORANGE, "gated": BLUE}
    labs = {"production": "production v1.1", "periodic": "periodic (exp.)", "gated": "gated 3.0-dev (held-out)"}
    x = np.arange(4)
    for j, k in enumerate(["production", "periodic", "gated"]):
        src = sel["heldout"] if k == "gated" else sel[k]
        axs[0].bar(x + (j - 1) * 0.26, [src[cn]["f1"] for cn in conds], 0.26, color=cs[k], label=labs[k])
        axs[1].bar(x + (j - 1) * 0.26, [src[cn]["mape_pct"] for cn in conds], 0.26, color=cs[k])
    axs[0].set_xticks(x)
    axs[0].set_xticklabels(["Reg.", "Semi", "Irreg.", "all"])
    axs[0].set_ylabel("event F1")
    axs[0].set_ylim(0, 1.05)
    axs[0].legend(loc="upper right", fontsize=5.3)
    axs[0].set_title("Clemson, 30 participants")
    panel(axs[0], "(a)")
    axs[1].set_yscale("log")
    axs[1].set_xticks(x)
    axs[1].set_xticklabels(["Reg.", "Semi", "Irreg.", "all"])
    axs[1].set_ylabel("MAPE (%, log)")
    axs[1].set_title("count error")
    panel(axs[1], "(b)")
    ks = ["production", "periodic", "gated"]
    fs_ = [kar[k]["false_steps_per_min"] for k in ks]
    se = [kar[k]["walking_state_sensitivity"] for k in ks]
    ax = axs[2]
    ax.bar(np.arange(3), fs_, 0.5, color=[cs[k] for k in ks])
    for i, v in enumerate(fs_):
        ax.text(i, v + 1, f"{v:.1f}\n(sens {se[i]:.2f})", ha="center", fontsize=5.3)
    ax.set_xticks(np.arange(3))
    ax.set_xticklabels(["prod.", "periodic", "gated"])
    ax.set_ylabel("false steps / min")
    ax.set_ylim(0, 68)
    ax.set_title("Karas driving/clapping")
    panel(ax, "(c)")
    fig.tight_layout(w_pad=1.0)
    save(fig, "p_steps_public")


# --------------------------------------------------------------------------------------------- 7. PPG
def fig_ppg():
    from parkinsense.ppg.algorithms import bandpass_filter
    fs = 104.0
    p_rest = S.ppg(fs=100.0, seconds=60, seed=5, hr_bpm=72.0, rmssd_ms=35.0)
    out = {}
    traces = {}
    for name, pp in (("rest", p_rest),):
        ir, red = S.ppg_to_slots(pp, path="v2")
        imu = S.rest(seconds=60, seed=21) if name == "rest" else S.voluntary(seconds=60, seed=22, rms=60.0)
        n = min(len(ir), imu.n)
        eng = RuntimeEngine()
        rows, an = run_engine(eng, imu, ir=ir[:n], red=red[:n], version=2)
        t = np.array([a["signal_time_s"] for a in an])
        hr = np.array([a["heart_rate"] if a["heart_rate"] else np.nan for a in an], dtype=float)
        cf = np.array([a["hr_confidence"] if a["hr_confidence"] is not None else np.nan for a in an], dtype=float)
        st = [a["hr_quality_state"] for a in an]
        traces[name] = (t, hr, cf, st, ir[:n])
        sel = t > 20
        out[name] = {"hr_mae": float(np.nanmean(np.abs(hr[sel] - pp.true_hr_bpm))), "conf_median": float(np.nanmedian(cf[sel])),
                     "states": {s: st.count(s) for s in set(st)}}
    fig, axs = plt.subplots(1, 3, figsize=(WIDE, 2.0), gridspec_kw={"width_ratios": [1.2, 1.2, 1.0]})
    t, hr, cf, st, ir = traces["rest"]
    seg = ir[int(20 * fs):int(26 * fs)].astype(float)
    ts = np.arange(len(seg)) / fs
    bp = bandpass_filter(seg, fs)
    axs[0].plot(ts, seg - seg.mean(), color=GREY, lw=0.7, label="raw IR − mean")
    axs[0].plot(ts, np.asarray(bp), color=RED, lw=1.0, label="0.5–4.5 Hz band-pass")
    axs[0].set_xlabel("time (s)")
    axs[0].set_ylabel("ADC counts")
    axs[0].legend(loc="upper right", fontsize=5.4)
    axs[0].set_title("synthetic IR pulse, 72 bpm")
    panel(axs[0], "(a)")
    tt, h, cfv, _, _ = traces["rest"]
    axs[1].plot(tt, h, color=BLUE, label="published HR (rest)")
    axs[1].axhline(72, color="k", ls=":", lw=0.6, label="true HR")
    axs[1].set_xlabel("signal time (s)")
    axs[1].set_ylabel("HR (bpm)")
    axs[1].set_ylim(50, 95)
    axs[1].legend(loc="upper right", fontsize=5.4)
    axs[1].set_title("HR vs truth, 60 s synthetic rest")
    panel(axs[1], "(b)")
    b, c = jload("baseline_legacy.json"), jload("current.json")
    v = [b["ppg_v2_path"]["rest_hr_confidence_median"], c["ppg_v2_path"]["rest_hr_confidence_median"],
         b["ppg_v2_path"]["motion_hr_confidence_median"], c["ppg_v2_path"]["motion_hr_confidence_median"]]
    axs[2].bar([0, 1, 3, 4], v, color=[GREY, BLUE, GREY, BLUE])
    for xx, vv in zip([0, 1, 3, 4], v):
        axs[2].text(xx, vv + 0.02, f"{vv:.2f}", ha="center", fontsize=5.6)
    axs[2].set_xticks([0.5, 3.5])
    axs[2].set_xticklabels(["rest", "motion artefact"])
    axs[2].set_ylabel("median HR confidence")
    axs[2].set_ylim(0, 1.0)
    axs[2].set_title("benchmark: 2.2.0 | 3.0.0")
    panel(axs[2], "(c)")
    fig.tight_layout(w_pad=1.0)
    save(fig, "p_ppg")
    return out


# --------------------------------------------------------------------------------------------- 8. sleep
def fig_sleep():
    d = jload("sleep_walch.json")
    m = d["methods"]
    order = ["vanhees_dz", "vanhees_dg", "lr_plain", "lr", "lr_hmm", "lr_hr_hmm", "hmm_untempered", "rf_hmm_untempered"]
    nice = ["van Hees\n2015", "van Hees\nangle", "LR\nθ=0.5", "LR nested\nLOSO (ship)", "LR+HMM", "LR+HR\n+HMM", "LR+HMM\nuntemp.", "RF+HMM\nuntemp."]
    kap = [m[k]["epoch_mean_over_subjects"]["kappa"] for k in order]
    fig, axs = plt.subplots(1, 2, figsize=(WIDE, 2.2), gridspec_kw={"width_ratios": [1.8, 1]})
    ax = axs[0]
    cols = [GREY, GREY, SKY, BLUE, SKY, SKY, SKY, SKY]
    ax.bar(np.arange(len(order)), kap, color=cols)
    for i, v in enumerate(kap):
        ax.text(i, v + 0.008, f"{v:.3f}", ha="center", fontsize=5.5)
    ax.set_xticks(np.arange(len(order)))
    ax.set_xticklabels(nice, fontsize=5.5)
    ax.set_ylabel("Cohen κ vs PSG (mean, 17 subj.)")
    ax.set_ylim(0, 0.58)
    panel(ax, "(a)")
    ax = axs[1]
    kv = {r["subject"]: r["epoch"]["kappa"] for r in m["vanhees_dz"]["per_subject"]}
    kl = {r["subject"]: r["epoch"]["kappa"] for r in m["lr"]["per_subject"]}
    xs = np.array([kv[s] for s in kv])
    ys = np.array([kl[s] for s in kv])
    ax.scatter(xs, ys, s=12, color=BLUE, zorder=3)
    ax.plot([0, 0.8], [0, 0.8], color="k", lw=0.6, ls=":")
    ax.set_xlabel("κ, van Hees 2015")
    ax.set_ylabel("κ, shipped LR")
    pr = d["paired_vs_vanhees_dz"]["lr"]["kappa"]
    ax.text(0.03, 0.97, f"Δκ = {pr['mean_diff']:+.3f}\n95 % CI [{pr['ci95'][0]:+.3f}, {pr['ci95'][1]:+.3f}]\n{pr['subjects_better']}/{pr['n']} better",
            transform=ax.transAxes, va="top", fontsize=5.8)
    ax.set_xlim(0, 0.8)
    ax.set_ylim(0, 0.8)
    panel(ax, "(b)")
    fig.tight_layout(w_pad=1.2)
    save(fig, "p_sleep")


# --------------------------------------------------------------------------------------------- 9. wear
def fig_wear_states():
    fig, ax = plt.subplots(figsize=(COL, 2.6))
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    w, h = 0.27, 0.13
    pos = {"UNKNOWN": (0.02, 0.84), "WORN": (0.02, 0.52), "WPU": (0.37, 0.52), "PR": (0.37, 0.18), "REM": (0.72, 0.18), "RES": (0.72, 0.52)}
    lab = {"UNKNOWN": "UNKNOWN", "WORN": "WORN", "WPU": "WORN_PPG_\nUNAVAILABLE", "PR": "POSSIBLY_\nREMOVED", "REM": "REMOVED", "RES": "RESUMING"}
    cols = {"UNKNOWN": "#EEEEEE", "WORN": "#E1F2EA", "WPU": "#FFF4D6", "PR": "#FBE5D6", "REM": "#F8CFCF", "RES": "#DCEBF7"}
    for k, (x, y) in pos.items():
        box(ax, x, y, w, h, lab[k], cols[k], fs=5.6)

    def c(k, side):
        x, y = pos[k]
        return {"r": (x + w, y + h / 2), "l": (x, y + h / 2), "t": (x + w / 2, y + h), "b": (x + w / 2, y)}[side]

    arrow(ax, c("UNKNOWN", "b"), c("WORN", "t"))
    arrow(ax, c("WORN", "r"), c("WPU", "l"), style="<|-|>")
    ax.text(0.325, 0.67, "contact ≥ 3 s ↔\nlost ≥ 10 s", fontsize=4.9, ha="center", va="bottom")
    arrow(ax, c("WPU", "b"), c("PR", "t"))
    ax.text(0.50, 0.42, "still AND no\ncontact ≥ 300 s", fontsize=4.9, ha="right", va="center")
    arrow(ax, c("PR", "r"), c("REM", "l"))
    ax.text(0.675, 0.17, "still AND no contact ≥ 900 s", fontsize=4.9, ha="center", va="top")
    arrow(ax, c("REM", "t"), c("RES", "b"))
    ax.text(0.845, 0.42, "contact ≥ 10 s or\n≥ 70 % moving (60 s)", fontsize=4.9, ha="right", va="center")
    arrow(ax, c("RES", "l"), c("WPU", "r"))
    ax.text(0.675, 0.67, "after 10 s", fontsize=4.9, ha="center", va="bottom")
    ax.text(0.02, 0.08, "Stillness alone, or contact loss alone, is never removal.\nFaults count as no evidence; a stream gap never creates a removal.", fontsize=5.0,
            va="top")
    save(fig, "p_wear_states")


def fig_wear_data():
    w = jload("wear_public_data.json")
    A = w["A_worn_sleep_stillness"]["summary"]
    B = w["B_state_machine_worst_case_no_ppg"]["summary"]
    th = ["1mg", "2mg", "4mg", "8mg", "13mg"]
    xl = [1, 2, 4, 8, 13]
    fig, axs = plt.subplots(1, 2, figsize=(COL * 2 + 0.1, 2.0))
    ax = axs[0]
    ax.plot(xl, [100 * A[t]["mean_share_in_runs_ge_15min"] for t in th], "o-", color=BLUE, label="still runs ≥ 15 min")
    ax.plot(xl, [100 * A[t]["mean_share_in_runs_ge_5min"] for t in th], "s--", color=GREY, label="still runs ≥ 5 min")
    ax.set_xscale("log")
    ax.set_xticks(xl)
    ax.set_xticklabels([str(v) for v in xl])
    ax.set_xlabel("stillness threshold, max-axis 1 s SD (mg)")
    ax.set_ylabel("share of worn night (%)")
    ax.legend(loc="upper left", fontsize=5.6)
    ax.set_title("worn sleeping wrists look still (15 Walch nights)", fontsize=6.8)
    panel(ax, "(a)")
    ax = axs[1]
    t3 = ["1mg", "2mg", "4mg"]
    x = np.arange(3)
    ax.bar(x - 0.2, [100 * B[t]["mean_removed_frac"] for t in t3], 0.4, color=RED, label="REMOVED")
    ax.bar(x + 0.2, [100 * B[t]["mean_possibly_removed_frac"] for t in t3], 0.4, color=ORANGE, label="POSSIBLY_REMOVED")
    for i, t in enumerate(t3):
        ax.text(i, max(100 * B[t]["mean_removed_frac"], 100 * B[t]["mean_possibly_removed_frac"]) + 1.5,
                f"{B[t]['subjects_ever_removed']}/15 ever REMOVED", ha="center", fontsize=5.4)
    ax.set_xticks(x)
    ax.set_xticklabels(["1 mg\n(default)", "2 mg", "4 mg"])
    ax.set_ylabel("mean share of night (%)")
    ax.set_ylim(0, 52)
    ax.legend(loc="upper left", fontsize=5.6)
    ax.set_title("false removal, PPG forced absent", fontsize=6.8)
    panel(ax, "(b)")
    fig.tight_layout(w_pad=1.5)
    save(fig, "p_wear_data")


# --------------------------------------------------------------------------------------------- 10. status heat-map
def fig_status():
    from status_data import STATUSES
    fig, ax = plt.subplots(figsize=(WIDE, 3.9))
    n = len(ROWS)
    cmap = {2: "#4C9F70", 1: "#F2C14E", 0: "#F2F2F2"}
    sym = {2: "yes", 1: "part", 0: "–"}
    for i, r in enumerate(ROWS):
        for j, v in enumerate(r[3:]):
            ax.add_patch(plt.Rectangle((j, n - 1 - i), 0.96, 0.9, fc=cmap[v], ec="white"))
            ax.text(j + 0.48, n - 1 - i + 0.45, sym[v], ha="center", va="center", fontsize=5.4, color="black" if v else "#999999")
        ax.text(-0.1, n - 1 - i + 0.45, f"{r[0]}  {r[1]}", ha="right", va="center", fontsize=6)
        ax.text(5.15, n - 1 - i + 0.45, r[2], ha="left", va="center", fontsize=6, fontweight="bold")
    for j, cn in enumerate(COLS):
        ax.text(j + 0.48, n + 0.15, cn, ha="center", va="bottom", fontsize=6.3, fontweight="bold")
    ax.text(5.15, n + 0.15, "Status", ha="left", va="bottom", fontsize=6.3, fontweight="bold")
    ax.set_xlim(-3.4, 7.0)
    ax.set_ylim(-1.0, n + 0.9)
    ax.axis("off")
    ax.text(-3.35, -0.8, "yes = documented in the repository · part = one side only, owner-reported, or opt-in/failed criteria · – = none", fontsize=5.6,
            color=GREY)
    save(fig, "p_status")


# --------------------------------------------------------------------------------------------- 11. photos / screenshots
def fig_photos():
    from PIL import Image
    a = Image.open(ROOT / "docs/images/prototype_hand.jpg")
    b = Image.open(ROOT / "docs/images/prototype_only.jpg")
    fig, axs = plt.subplots(1, 2, figsize=(COL * 2 + 0.1, 2.7))
    for ax, im, t in ((axs[0], a, "(a) worn on the wrist"), (axs[1], b, "(b) open enclosure")):
        ax.imshow(im)
        ax.axis("off")
        ax.set_title(t, fontsize=6.8)
    fig.tight_layout(w_pad=0.5)
    save(fig, "p_photos")


def fig_dashboard():
    from PIL import Image
    a = Image.open(ROOT / "docs/images/dashboard2_overview.png")
    b = Image.open(ROOT / "docs/images/dashboard2_tremor.png")
    fig, axs = plt.subplots(1, 2, figsize=(COL * 2 + 0.1, 2.35))
    for ax, im, t in ((axs[0], a, "(a) overview page"), (axs[1], b, "(b) tremor analytics page")):
        ax.imshow(im)
        ax.axis("off")
        ax.set_title(t, fontsize=6.8)
    fig.tight_layout(w_pad=0.5)
    save(fig, "p_dashboard")


def fig_timeline():
    fig, ax = plt.subplots(figsize=(WIDE, 1.6))
    ax.set_xlim(0, 12)
    ax.set_ylim(0, 3)
    ax.axis("off")
    ph = [("Phase 8 (Nov 2026)", 0, 4, "wear-aware acquisition; software + docs done;\nhardware W0–W8, H1–H3, H5, PPK2 pending", "#FBE5D6"),
          ("Phase 9 (Nov–Dec 2026)", 4, 4, "public datasets: PD@Home tremor baseline, Daphnet FoG;\nbenchmark registry, pre-registered criteria", "#FFF4D6"),
          ("Phases 10–13 (Dec 2026 →)", 8, 4, "mobile app, product UI, cloud, pilot\n(deferred; not started)", "#EEEEEE")]
    for t, x, w, d, c in ph:
        ax.add_patch(plt.Rectangle((x + 0.05, 0.9), w - 0.1, 1.5, fc=c, ec="#44576B", lw=0.6))
        ax.text(x + w / 2, 2.15, t, ha="center", fontsize=6.6, fontweight="bold")
        ax.text(x + w / 2, 1.45, d, ha="center", va="center", fontsize=5.8)
    ax.text(0.1, 0.45, "A phase is complete only when its evidence and acceptance criteria are met, not when code exists.", fontsize=6, color=GREY)
    save(fig, "p_timeline")


if __name__ == "__main__":
    nums = {}
    fig_architecture()
    fig_packet()
    nums["psd"] = fig_psd()
    nums["hmm"] = fig_hmm()
    fig_tremor_bench()
    fig_scenarios()
    fig_step_gating()
    fig_steps_public()
    nums["ppg"] = fig_ppg()
    fig_sleep()
    fig_wear_states()
    fig_wear_data()
    fig_status()
    fig_photos()
    fig_dashboard()
    fig_timeline()
    json.dump(nums, open(OUT / "figure_numbers.json", "w"), indent=1)
    print(json.dumps(nums, indent=1))
