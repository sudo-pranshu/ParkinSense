import serial
import numpy as np
import matplotlib.pyplot as plt
from collections import deque
from matplotlib.animation import FuncAnimation

PORT = "/dev/cu.usbmodem1101"   # replace
BAUD = 115200

ser = serial.Serial(PORT, BAUD)

WINDOW = 500

gx_data = deque(maxlen=WINDOW)

fig, (ax1, ax2) = plt.subplots(2, 1)

line1, = ax1.plot([])
line2, = ax2.plot([])

ax1.set_title("Gyroscope X")
ax2.set_title("FFT Spectrum")

def update(frame):

    try:
        line = ser.readline().decode().strip()

        parts = line.split(",")

        if len(parts) != 7:
            return

        gx = float(parts[4])

        gx_data.append(gx)

        line1.set_data(range(len(gx_data)), gx_data)

        ax1.relim()
        ax1.autoscale_view()

        if len(gx_data) > 128:

            signal = np.array(gx_data)

            fft = np.abs(np.fft.rfft(signal))

            freqs = np.fft.rfftfreq(
                len(signal),
                d=0.01
            )

            line2.set_data(freqs, fft)

            ax2.relim()
            ax2.autoscale_view()

    except:
        pass

ani = FuncAnimation(fig, update, interval=10)

plt.show()
