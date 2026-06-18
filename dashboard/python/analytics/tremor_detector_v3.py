import os
import numpy as np
import pandas as pd

from scipy.fft import rfft, rfftfreq

# ============================================================
# DATASETS
# ============================================================

DATASETS = [
    "stationary_60s.csv",
    "normal_motion_60s.csv",
    "walking_60s.csv",
    "simulated_tremor_30s.csv",
    "vibration_reference_30s.csv"
]

# ============================================================
# MAIN LOOP
# ============================================================

for dataset in DATASETS:

    FILE = os.path.join(
        "dashboard/python/data/raw",
        dataset
    )

    print("\n" + "=" * 60)
    print(f"DATASET: {dataset}")
    print("=" * 60)

    df = pd.read_csv(FILE)

    # ========================================================
    # SAMPLING RATE
    # ========================================================

    dt = np.diff(df["timestamp"])

    fs = 1000 / np.mean(dt)

    print(f"\nSampling Rate : {fs:.2f} Hz")

    # ========================================================
    # GYRO MAGNITUDE
    # ========================================================

    gyro_mag = np.sqrt(
        df["gx"]**2 +
        df["gy"]**2 +
        df["gz"]**2
    )

    gyro_mag = gyro_mag - np.mean(gyro_mag)

    gyro_mag_np = gyro_mag.to_numpy()

    # ========================================================
    # WINDOW ANALYSIS
    # ========================================================

    window_sec = 5
    window_size = int(fs * window_sec)

    dominant_freqs = []
    energy_ratios = []

    for start in range(
            0,
            len(gyro_mag_np) - window_size,
            window_size):

        segment = gyro_mag_np[
            start:start + window_size
        ]

        segment = segment - np.mean(segment)

        fft_vals = np.abs(
            rfft(segment)
        )

        freqs = rfftfreq(
            len(segment),
            d=1/fs
        )

        band_mask = (
            (freqs >= 3.0) &
            (freqs <= 9.0)
        )

        band_freqs = freqs[band_mask]
        band_fft = fft_vals[band_mask]

        if len(band_fft) == 0:
            continue

        dominant_freqs.append(
            band_freqs[np.argmax(band_fft)]
        )

        total_energy = np.sum(
            fft_vals ** 2
        )

        band_energy = np.sum(
            band_fft ** 2
        )

        if total_energy > 0:

            energy_ratios.append(
                band_energy /
                total_energy
            )

    # ========================================================
    # FEATURE EXTRACTION
    # ========================================================

    rms_motion = np.sqrt(
        np.mean(gyro_mag_np ** 2)
    )

    if len(dominant_freqs) == 0:

        mean_freq = 0
        freq_std = 999

    else:

        mean_freq = np.mean(
            dominant_freqs
        )

        freq_std = np.std(
            dominant_freqs
        )

    if len(energy_ratios) == 0:

        mean_energy_ratio = 0

    else:

        mean_energy_ratio = np.mean(
            energy_ratios
        )

    # ========================================================
    # BEST AXIS
    # ========================================================

    axis_scores = []

    for axis in ["gx", "gy", "gz"]:

        signal = df[axis].to_numpy()

        signal = signal - np.mean(
            signal
        )

        fft_axis = np.abs(
            rfft(signal)
        )

        freq_axis = rfftfreq(
            len(signal),
            d=1/fs
        )

        axis_mask = (
            (freq_axis >= 3) &
            (freq_axis <= 9)
        )

        score = np.sum(
            fft_axis[axis_mask] ** 2
        )

        axis_scores.append(
            (axis, score)
        )

    best_axis, best_axis_score = max(
        axis_scores,
        key=lambda x: x[1]
    )

    # ========================================================
    # DECISION GATES
    # ========================================================

    motion_gate = (
        rms_motion > 10 and
        rms_motion < 70
    )

    frequency_gate = (
        4.0 <= mean_freq <= 7.0
    )

    energy_gate = (
        mean_energy_ratio > 0.30
    )

    stability_gate = (
        freq_std < 1.50
    )

    score = 0

    if motion_gate:
        score += 25

    if frequency_gate:
        score += 25

    if energy_gate:
        score += 25

    if stability_gate:
        score += 25

    # ========================================================
    # EXTRA REJECTION LOGIC
    # ========================================================

    if rms_motion < 5:
        score = 0

    if mean_energy_ratio < 0.20:
        score = max(0, score - 25)

    # ========================================================
    # OUTPUT
    # ========================================================

    print(
        "Window Frequencies :",
        dominant_freqs
    )

    print()
    print(f"Sampling Rate      : {fs:.2f} Hz")
    print(f"RMS Motion         : {rms_motion:.2f}")
    print(f"Mean Frequency     : {mean_freq:.2f} Hz")
    print(f"Frequency Std Dev  : {freq_std:.2f} Hz")
    print(f"Band Energy Ratio  : {mean_energy_ratio:.3f}")
    print(f"Best Axis          : {best_axis}")

    print()
    print("Decision Gates")
    print(f"Motion Gate        : {motion_gate}")
    print(f"Frequency Gate     : {frequency_gate}")
    print(f"Energy Gate        : {energy_gate}")
    print(f"Stability Gate     : {stability_gate}")

    print()
    print(f"Tremor Score       : {score}/100")

    if score >= 75:

        print("Classification     : TREMOR")

    else:

        print("Classification     : NO TREMOR")

    print()
