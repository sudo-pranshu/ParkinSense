
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

FILE = "../parksense_20260615_143958.csv"

df = pd.read_csv(FILE)

fs = 100

gx = df["gx"].values

# remove DC
gx = gx - np.mean(gx)

# take first 10 seconds
window = gx[:1000]

fft = np.abs(np.fft.rfft(window))
freqs = np.fft.rfftfreq(len(window), 1/fs)

plt.figure(figsize=(10,5))
plt.plot(freqs, fft)

plt.xlim(0,15)

plt.xlabel("Frequency (Hz)")
plt.ylabel("Magnitude")
plt.title("ParkinSense FFT")

plt.grid()

plt.show()

peak_idx = np.argmax(fft[1:]) + 1

print("Dominant Frequency:", freqs[peak_idx])
