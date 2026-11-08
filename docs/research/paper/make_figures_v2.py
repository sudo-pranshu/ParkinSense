#!/usr/bin/env python3
"""Additional figures for the 10-11 page revision (photos, current dashboard, redrawn diagrams, BLE capture plots).
Run from repo root: python3 docs/research/paper/make_figures_v2.py"""
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from PIL import Image

sys.path.insert(0, str(Path(__file__).parent))
import make_figures as M  # noqa: E402  (shared style, helpers)
from make_figures import BLUE, COL, GREEN, GREY, ORANGE, RED, WIDE, arrow, box, panel, save  # noqa: E402

ROOT = M.ROOT
IMG = ROOT / "docs/images"
C = {"imu": "#DCEBF7", "ppg": "#F8E3E3", "step": "#E1F2EA", "gen": "#EEEEEE", "ble": "#FFF4D6", "wear": "#EADFF0"}


def chain(ax, y, h, items, x0=0.0, x1=1.0, gap=0.032, fs=5.4):
    """Horizontal flow of boxes; items = [(text, colour)]. Returns box centres."""
    n = len(items)
    w = (x1 - x0 - gap * (n - 1)) / n
    xs = []
    for i, (t, c) in enumerate(items):
        x = x0 + i * (w + gap)
        box(ax, x, y, w, h, t, c, fs=fs)
        xs.append((x, w))
        if i:
            arrow(ax, (x - gap, y + h / 2), (x, y + h / 2))
    return xs


# ------------------------------------------------------------------------------------------ photos
def fig_prototype():
    a = Image.open(IMG / "prototype_hand.jpg")
    b = Image.open(IMG / "prototype_only.jpg")
    fig, axs = plt.subplots(1, 2, figsize=(WIDE, 3.0), gridspec_kw={"width_ratios": [a.width / a.height, b.width / b.height]})
    for ax, im, t in ((axs[0], a, "(a) assembled device worn on the wrist"), (axs[1], b, "(b) strap, 3D-printed enclosure and electronics (sizing and fit build)")):
        ax.imshow(im)
        ax.axis("off")
        ax.set_title(t, fontsize=6.8)
    fig.tight_layout(w_pad=0.6)
    save(fig, "p_prototype")


# ------------------------------------------------------------------------------------------ dashboards (current only)
def fig_dash():
    ov = Image.open(IMG / "dashboard2_overview.png").convert("RGB").crop((205, 0, 1440, 590))
    tr = Image.open(IMG / "dashboard2_tremor.png").convert("RGB").crop((205, 0, 1440, 590))
    fig, axs = plt.subplots(1, 2, figsize=(WIDE, 1.98))
    for ax, im, t in ((axs[0], ov, "(a) Overview: no tremor, session metrics"), (axs[1], tr, "(b) Tremor analytics: P(tremor), peak frequency, amplitude")):
        ax.imshow(im)
        ax.axis("off")
        ax.set_title(t, fontsize=6.8)
    fig.tight_layout(w_pad=0.4)
    save(fig, "p_dash")
    lv = Image.open(IMG / "dashboard2_live.png").convert("RGB").crop((205, 85, 1440, 900))
    fig, ax = plt.subplots(figsize=(COL, 2.1))
    ax.imshow(lv)
    ax.axis("off")
    save(fig, "p_dash_live")


# ------------------------------------------------------------------------------------------ pipelines
def fig_pipelines():
    fig, ax = plt.subplots(figsize=(WIDE, 3.35))
    ax.set_xlim(-0.01, 1.01)
    ax.set_ylim(0.07, 1)
    ax.axis("off")
    ax.text(0, 0.985, "Motion pipeline (every 0.5 s, 4 s window)", fontsize=6.6, fontweight="bold", color=GREY, va="top")
    chain(ax, 0.72, 0.2, [
        ("IMU buffer\n416 samples\n(4 s at 104 Hz)", C["imu"]),
        ("Hann segments 208,\nWelch K = 3,\nFFT 1024; sum of\naxes S(f)", C["imu"]),
        ("peak in 3.5–7.5 Hz,\nGaussian\ninterpolation", C["imu"]),
        ("power ±0.625 Hz,\nnoise floor 2–12 Hz\nSNR, amplitude A_T", C["imu"]),
        ("context REST / LOW /\nACTIVE; edge and\nharmonic checks", C["imu"]),
        ("evidence e →\ntwo-state tempered\nHMM, p(tremor)", "#DCEBF7")])
    ax.text(0, 0.655, "PPG pipeline (10 s buffer)", fontsize=6.6, fontweight="bold", color=GREY, va="top")
    chain(ax, 0.40, 0.2, [
        ("IR and RED FIFO\nsamples, 10 s\nbuffer", C["ppg"]),
        ("effective rate from\ntimestamps (HRV\nneeds ≥ 25 Hz)", C["ppg"]),
        ("Butterworth\nband-pass 0.5–4.5 Hz,\norder 3", C["ppg"]),
        ("peak detection,\nHR with EMA 0.25", C["ppg"]),
        ("finger contact, SQI,\nmotion-coupling flag\n(arm frequency)", C["ppg"]),
        ("HR + quality state,\nHRV (RMSSD),\nSpO2 uncalibrated", "#F8E3E3")])
    ax.text(0, 0.335, "Step pipeline (per sample, 104 Hz)", fontsize=6.6, fontweight="bold", color=GREY, va="top")
    chain(ax, 0.08, 0.2, [
        ("accelerometer\nmagnitude", C["step"]),
        ("high-pass\nα = 0.95", C["step"]),
        ("adaptive threshold\nμ + 0.7σ, refractory\ninterval", C["step"]),
        ("gate: motion state,\ntremor guard,\nwear monitor", C["step"]),
        ("opt-in gated 3.0-dev:\nautocorr. ≥ 0.65,\nRMS ≥ 0.12 g", "#FFFFFF"),
        ("steps, cadence", "#E1F2EA")])
    save(fig, "p_pipelines")


# ------------------------------------------------------------------------------------------ acquisition + BLE + decode
def fig_acq():
    fig, ax = plt.subplots(figsize=(WIDE, 2.55))
    ax.set_xlim(-0.01, 1.01)
    ax.set_ylim(-0.04, 1)
    ax.axis("off")
    box(ax, 0.0, 0.70, 0.12, 0.17, "LSM6DS3\nI²C 0x6A\n104 Hz", C["imu"])
    box(ax, 0.0, 0.44, 0.12, 0.17, "MAX30102\nI²C\nIR + RED FIFO", C["ppg"])
    box(ax, 0.18, 0.44, 0.20, 0.43, "XIAO nRF52840\nSense firmware:\n9 615 µs sample timer,\ntimestamp, pack 10\nsamples, BLE notify\nv4: hardware-verified\n5.0.0: flashed, no log", C["gen"], fs=5.2)
    box(ax, 0.44, 0.55, 0.14, 0.22, "BLE 5 notify\n208 B packets\n≈ 10.4 /s", C["ble"], fs=5.2)
    box(ax, 0.64, 0.44, 0.22, 0.43, "Host decoder\nversion, length, flags,\nsequence gaps,\ntimestamp unwrap,\nrate within ±5 %,\nclip and fault flags", C["gen"], fs=5.2)
    box(ax, 0.90, 0.55, 0.10, 0.22, "Runtime\nEngine", "#FFFFFF", fs=5.4)
    arrow(ax, (0.12, 0.785), (0.18, 0.72))
    arrow(ax, (0.12, 0.525), (0.18, 0.60))
    arrow(ax, (0.38, 0.66), (0.44, 0.66))
    arrow(ax, (0.58, 0.66), (0.64, 0.66))
    arrow(ax, (0.86, 0.66), (0.90, 0.66))
    # packet layout
    cols = {"h": "#DCEBF7", "a": "#E1F2EA", "g": "#FFF4D6", "p": "#F8E3E3"}
    ax.text(0.0, 0.36, "Packet (208 B = 8 B header + 10 × 20 B samples; little-endian)", fontsize=6.4, fontweight="bold", color=GREY)

    def row(y, fields, label, x0=0.1, unit=0.9 / 20):
        x = x0
        for name, w, c in fields:
            ax.add_patch(plt.Rectangle((x, y), w * unit, 0.1, fc=cols[c], ec="#44576B", lw=0.6))
            ax.text(x + w * unit / 2, y + 0.05, name, ha="center", va="center", fontsize=5.3)
            x += w * unit
        ax.text(x0 - 0.01, y + 0.05, label, ha="right", va="center", fontsize=5.8)

    row(0.25, [("ver", 1, "h"), ("flags", 1, "h"), ("seq", 2, "h"), ("timestamp_us (u32)", 4, "h")], "header 8 B")
    row(0.12, [("ax", 2, "a"), ("ay", 2, "a"), ("az", 2, "a"), ("gx", 2, "g"), ("gy", 2, "g"), ("gz", 2, "g"), ("IR (u32)", 4, "p"), ("RED (u32)", 4, "p")], "sample 20 B")
    ax.text(0.1, 0.045, "accel 8192 LSB/g; gyro v1 131 LSB/dps (±250), v2 64 LSB/dps (±512); sample i time = timestamp + i·9 615 µs; "
            "seq is 0 in v1.", fontsize=5.5, va="center")
    ax.text(0.1, -0.02, "v2 flags: accel/gyro clipped, IMU fault, PPG fault, PPG stale, notify failed, time discontinuity.", fontsize=5.5, va="center")
    save(fig, "p_acq")


# ------------------------------------------------------------------------------------------ gating + fusion
def fig_fusion():
    fig, ax = plt.subplots(figsize=(WIDE, 2.25))
    ax.set_xlim(-0.01, 1.01)
    ax.set_ylim(0, 1)
    ax.axis("off")
    box(ax, 0.0, 0.70, 0.20, 0.26, "Wear monitor (opt-in)\ninferred WORN / REMOVED\nstillness + optical contact", C["wear"])
    box(ax, 0.0, 0.04, 0.20, 0.50, "Motion pipeline\nstate REST / LOW / ACTIVE\ntremor type, evidence e,\nHMM p(tremor)\narm frequency f_arm,\narm RMS", C["imu"])
    box(ax, 0.43, 0.72, 0.24, 0.24, "Step counter\ngate = REST if confirmed rest\ntremor or REMOVED,\nelse the motion state", C["step"])
    box(ax, 0.43, 0.38, 0.24, 0.26, "PPG pipeline\nmotion state and f_arm\n(arm RMS ≥ 10 °/s) →\nmotion-coupled HR flag", C["ppg"])
    box(ax, 0.43, 0.04, 0.24, 0.26, "Tremor result\nusable only if sample rate\nwithin ±5 % (else INVALID);\nclipping lowers confidence", C["gen"])
    box(ax, 0.80, 0.18, 0.20, 0.64, "Per-window output\ntremor: p, frequency,\namplitude, quality\nHR, quality state, HRV,\nSpO2 (uncalibrated)\nsteps, cadence,\ndata-quality flags\n\nno composite severity\nscore is produced", "#FFFFFF")
    arrow(ax, (0.20, 0.83), (0.43, 0.84), color=RED, ls="--")
    arrow(ax, (0.20, 0.50), (0.43, 0.76), color=RED, ls="--")
    arrow(ax, (0.20, 0.40), (0.43, 0.51), color=RED, ls="--")
    arrow(ax, (0.20, 0.22), (0.43, 0.17), color=RED, ls="--")
    arrow(ax, (0.67, 0.84), (0.80, 0.68))
    arrow(ax, (0.67, 0.51), (0.80, 0.50))
    arrow(ax, (0.67, 0.17), (0.80, 0.32))
    ax.text(0.315, 0.875, "REMOVED", fontsize=5.3, color=RED, ha="center", bbox=dict(fc="white", ec="none", pad=0.6))
    ax.text(0.30, 0.67, "confirmed rest tremor", fontsize=5.3, color=RED, ha="center", bbox=dict(fc="white", ec="none", pad=0.6))
    ax.text(0.31, 0.45, "context, f_arm", fontsize=5.3, color=RED, ha="center", bbox=dict(fc="white", ec="none", pad=0.6))
    ax.text(0.31, 0.24, "e, p(tremor)", fontsize=5.3, color=RED, ha="center", bbox=dict(fc="white", ec="none", pad=0.6))
    save(fig, "p_fusion")


# ------------------------------------------------------------------------------------------ dashboard + logging architecture
def fig_dashlog():
    fig, ax = plt.subplots(figsize=(COL, 2.35))
    ax.set_xlim(-0.01, 1.01)
    ax.set_ylim(0, 1)
    ax.axis("off")
    box(ax, 0.30, 0.84, 0.40, 0.14, "RuntimeEngine\n(live = replay path)", C["gen"], fs=5.6)
    box(ax, 0.0, 0.52, 0.30, 0.20, "Recorder\ncapture.csv\n(79 columns)\nmetadata.json", "#FFFFFF", fs=5.4)
    box(ax, 0.36, 0.52, 0.28, 0.20, "FastAPI\n/live  /metrics\nJSON", "#FFFFFF", fs=5.4)
    box(ax, 0.70, 0.52, 0.30, 0.20, "Offline tools\nreplay, sleep,\nwear CLI,\nbaselines", "#FFFFFF", fs=5.4)
    box(ax, 0.0, 0.0, 1.0, 0.36, "Plotly Dash dashboard (consumer only)\nOverview · Live monitoring · Tremor analytics\nCardiovascular · Activity · Sessions · Data and research\nSIMULATED banner when the source is the synthetic generator", "#DCEBF7", fs=5.4)
    arrow(ax, (0.40, 0.84), (0.15, 0.72))
    arrow(ax, (0.50, 0.84), (0.50, 0.72))
    arrow(ax, (0.60, 0.84), (0.85, 0.72))
    arrow(ax, (0.50, 0.52), (0.50, 0.36))
    arrow(ax, (0.15, 0.52), (0.15, 0.36), ls=":", color=GREY)
    save(fig, "p_dashlog")


# ------------------------------------------------------------------------------------------ real BLE capture + context
def fig_capture():
    d = pd.read_csv(ROOT / "data/reference/ble_v1_104hz/parkinsense_20260630_123551.csv")
    t = d.timestamp.values.astype(float)
    dt = np.diff(t) / 1000.0
    fig, axs = plt.subplots(1, 4, figsize=(WIDE, 1.85), gridspec_kw={"width_ratios": [1, 1, 1.15, 1]})
    ax = axs[0]
    ax.hist(dt, bins=np.arange(2, 14.01, 0.25), color=BLUE)
    ax.axvline(1000 / 104.0, color=RED, lw=0.7, ls="--")
    ax.set_yscale("log")
    ax.set_xlabel("sample interval (ms)")
    ax.set_ylabel("count")
    ax.set_title("(a) sample intervals", fontsize=6.8, loc="left")
    ax = axs[1]
    tt = (t - t[0]) / 1e6
    drift = (t - t[0] - np.arange(len(t)) * (1e6 / 104.0)) / 1000.0
    ax.plot(tt[::10], drift[::10], color=BLUE)
    ax.set_xlabel("time (s)")
    ax.set_ylabel("drift versus 104 Hz (ms)")
    ax.set_title("(b) packet-start drift", fontsize=6.8, loc="left")
    ax = axs[2]
    ax.semilogy(tt, d.ir.clip(lower=1), color=RED, lw=0.5, label="IR counts")
    ax.set_xlabel("time (s)")
    ax.set_ylabel("IR (counts)")
    ax2 = ax.twinx()
    ax2.plot(tt, np.sqrt(d.ax ** 2 + d.ay ** 2 + d.az ** 2), color=GREEN, lw=0.4)
    ax2.set_ylabel("|a| (g)", color=GREEN)
    ax2.spines["right"].set_visible(True)
    ax.set_title("(c) IR counts and |a|", fontsize=6.8, loc="left")
    ax = axs[3]
    import json
    g = json.load(open(ROOT / "tests/regression/golden.json"))
    names = ["stationary_60s", "vibration_reference_30s", "simulated_tremor_30s", "normal_motion_60s", "walking_60s", "parkinsense_20260630_123551"]
    short = ["still", "vibr.", "sim. tremor", "normal", "walking", "BLE capture"]
    left = np.zeros(len(names))
    for st, c in (("REST", GREEN), ("LOW MOTION", ORANGE), ("ACTIVE", RED)):
        v = np.array([g[n]["outputs"]["motion_state_fraction"].get(st, 0.0) for n in names])
        ax.barh(range(len(names)), v, left=left, color=c, label=st, height=0.7)
        left += v
    ax.set_yticks(range(len(names)))
    ax.set_yticklabels(short, fontsize=5.8)
    ax.invert_yaxis()
    ax.set_xlim(0, 1)
    ax.set_xlabel("fraction of windows")
    ax.set_title("(d) motion context", fontsize=6.8, loc="left")
    ax.legend(loc="upper center", bbox_to_anchor=(0.45, -0.34), ncol=3, fontsize=5.3, handlelength=0.8, columnspacing=0.8)
    fig.tight_layout(w_pad=0.7)
    save(fig, "p_capture")
    return {"n": len(d), "dur_s": float(tt[-1]), "rate": float(1e6 * (len(t) - 1) / (t[-1] - t[0])), "max_dt_ms": float(dt.max()),
            "drift_ms": float(drift[-1]), "drift_max_ms": float(np.abs(drift[::10]).max())}


if __name__ == "__main__":
    fig_prototype()
    fig_dash()
    fig_pipelines()
    fig_acq()
    fig_fusion()
    fig_dashlog()
    import json
    print(json.dumps(fig_capture()))
