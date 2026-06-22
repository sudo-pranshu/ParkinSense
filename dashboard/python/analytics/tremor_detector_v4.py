import os
import numpy as np
import pandas as pd

from scipy.fft import rfft, rfftfreq

DATASETS = [
    "stationary_60s.csv",
    "normal_motion_60s.csv",
    "walking_60s.csv",
    "simulated_tremor_30s.csv",
    "vibration_reference_30s.csv"
]

for dataset in DATASETS:

    FILE = os.path.join(
        "dashboard/python/data/raw",
        dataset
    )

    print("\n" + "=" * 60)
    print(f"DATASET: {dataset}")
    print("=" * 60)

    df = pd.read_csv(FILE)

    dt = np.diff(df["timestamp"])
    fs = 1000 / np.mean(dt)

    print(f"\nSampling Rate : {fs:.2f} Hz")

    gx = df["gx"].to_numpy()
    gy = df["gy"].to_numpy()
    gz = df["gz"].to_numpy()

    ax = df["ax"].to_numpy()
    ay = df["ay"].to_numpy()
    az = df["az"].to_numpy()

    gyro_mag = np.sqrt(
        gx**2 +
        gy**2 +
        gz**2
    )

    gyro_mag = gyro_mag - np.mean(
        gyro_mag
    )

    acc_mag = np.sqrt(
        ax**2 +
        ay**2 +
        az**2
    )

    rest_index = np.std(
        acc_mag
    )

    rms_motion = np.sqrt(
        np.mean(
            gyro_mag**2
        )
    )

    window_sec = 5

    window_size = int(
        fs * window_sec
    )

    dominant_freqs = []
    energy_ratios = []

    for start in range(
        0,
        len(gyro_mag) - window_size,
        window_size
    ):

        segment = gyro_mag[
            start:start + window_size
        ]

        segment = (
            segment -
            np.mean(segment)
        )

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

        band_freqs = freqs[
            band_mask
        ]

        band_fft = fft_vals[
            band_mask
        ]

        if len(band_fft) == 0:
            continue

        dominant_freqs.append(
            band_freqs[
                np.argmax(
                    band_fft
                )
            ]
        )

        total_energy = np.sum(
            fft_vals**2
        )

        band_energy = np.sum(
            band_fft**2
        )

        if total_energy > 0:

            energy_ratios.append(
                band_energy /
                total_energy
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

    axis_freqs = []

    for axis in [
        gx,
        gy,
        gz
    ]:

        signal = (
            axis -
            np.mean(axis)
        )

        fft_axis = np.abs(
            rfft(signal)
        )

        freq_axis = rfftfreq(
            len(signal),
            d=1/fs
        )

        mask = (
            (freq_axis >= 3) &
            (freq_axis <= 9)
        )

        if np.sum(mask) == 0:
            continue

        band_fft = fft_axis[
            mask
        ]

        band_freqs = freq_axis[
            mask
        ]

        axis_freqs.append(
            band_freqs[
                np.argmax(
                    band_fft
                )
            ]
        )

    if len(axis_freqs) >= 2:

        coherence_std = np.std(
            axis_freqs
        )

    else:

        coherence_std = 999

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

    coherence_gate = (
        coherence_std < 1.00
    )

    rest_gate = (
        rest_index < 0.20
    )

    # Axis dominance

    axis_energies = []

    for axis in [gx, gy, gz]:

        signal = axis - np.mean(axis)

        fft_axis = np.abs(
            rfft(signal)
        )

        freq_axis = rfftfreq(
            len(signal),
            d=1/fs
        )

        mask = (
            (freq_axis >= 3) &
            (freq_axis <= 9)
        )

        axis_energies.append(
            np.sum(
                fft_axis[mask] ** 2
            )
        )

    total_axis_energy = sum(
        axis_energies
    )

    if total_axis_energy > 0:

        dominance = (
            max(axis_energies) /
            total_axis_energy
        )

    else:

        dominance = 0

    dominance_gate = (
        dominance > 0.55
    )

    score = 0

    if motion_gate:
        score += 20

    if frequency_gate:
        score += 20

    if energy_gate:
        score += 20

    if stability_gate:
        score += 15

    if coherence_gate:
        score += 10

    if dominance_gate:
        score += 15

    # Hard rejections

    if rms_motion < 5:
        score = 0

    if mean_energy_ratio < 0.20:
        score = max(
            0,
            score - 20
        )

    if not rest_gate:
        score = max(
            0,
            score - 20
        )

    if score < 50:

        severity = "NONE"

    elif score < 75:

        severity = "MILD"

    elif score < 90:

        severity = "MODERATE"

    else:

        severity = "SEVERE"

    classification = (
        "TREMOR"
        if score >= 80
        else "NO TREMOR"
    )

    print()
    print(f"Rest Index         : {rest_index:.3f}")
    print(f"RMS Motion         : {rms_motion:.2f}")
    print(f"Mean Frequency     : {mean_freq:.2f} Hz")
    print(f"Frequency Std Dev  : {freq_std:.2f} Hz")
    print(f"Axis Coherence     : {coherence_std:.2f}")
    print(f"Axis Dominance     : {dominance:.2f}")
    print(f"Band Energy Ratio  : {mean_energy_ratio:.3f}")

    print()
    print("Decision Gates")
    print(f"Motion Gate        : {motion_gate}")
    print(f"Frequency Gate     : {frequency_gate}")
    print(f"Energy Gate        : {energy_gate}")
    print(f"Stability Gate     : {stability_gate}")
    print(f"Coherence Gate     : {coherence_gate}")
    print(f"Rest Gate          : {rest_gate}")
    print(f"Dominance Gate     : {dominance_gate}")

    print()
    print(f"Tremor Score       : {score}/100")
    print(f"Severity           : {severity}")
    print(f"Classification     : {classification}")
