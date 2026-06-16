import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from scipy.signal import butter, filtfilt

# -----------------------------
# CONFIG
# -----------------------------
FILE = "data/raw/parksense_20260615_143958.csv"
FS = 100  # Sampling rate

# -----------------------------
# LOAD DATA
# -----------------------------
df = pd.read_csv(FILE)

# Use gyroscope magnitude
gyro_mag = np.sqrt(
    df["gx"]**2 +
    df["gy"]**2 +
    df["gz"]**2
)

# -----------------------------
# BANDPASS FILTER
# Parkinson tremor ≈ 4-7 Hz
# -----------------------------
def bandpass_filter(data, lowcut=4.0, highcut=7.0, fs=100, order=4):
    nyq = fs / 2

    low = lowcut / nyq
    high = highcut / nyq

    b, a = butter(order, [low, high], btype='band')

    return filtfilt(b, a, data)

filtered = bandpass_filter(gyro_mag)

# -----------------------------
# FFT
# -----------------------------
window = filtered[:1000]  # first 10 sec

window = window - np.mean(window)

fft = np.abs(np.fft.rfft(window))
freqs = np.fft.rfftfreq(len(window), 1 / FS)

# Ignore DC
fft[0] = 0

# -----------------------------
# Tremor Metrics
# -----------------------------
peak_idx = np.argmax(fft)

dominant_frequency = freqs[peak_idx]

band_mask = (freqs >= 4) & (freqs <= 7)

band_energy = np.sum(fft[band_mask])

total_energy = np.sum(fft)

tremor_index = (
    band_energy /
    total_energy
) * 100

print()
print("===== ParkinSense Analysis =====")
print(f"Dominant Frequency : {dominant_frequency:.2f} Hz")
print(f"Tremor Index       : {tremor_index:.2f}%")

if tremor_index > 20:
    print("Status             : Tremor Detected")
else:
    print("Status             : No Tremor Detected")

# -----------------------------
# PLOT
# -----------------------------
plt.figure(figsize=(12, 6))

plt.plot(freqs, fft)

plt.axvspan(
    4,
    7,
    alpha=0.2,
    label="Parkinson Band"
)

plt.axvline(
    dominant_frequency,
    linestyle="--",
    label=f"{dominant_frequency:.2f} Hz"
)

plt.xlim(0, 15)

plt.xlabel("Frequency (Hz)")
plt.ylabel("Magnitude")

plt.title("ParkinSense Tremor Spectrum")

plt.legend()

plt.grid(True)

plt.show()
