import serial
import csv
from datetime import datetime
import os

os.makedirs("data/raw", exist_ok=True)

PORT = "/dev/cu.usbmodem1101" #replace
BAUD = 115200

name = input("Dataset name: ")

filename = f"data/raw/{name}.csv"

ser = serial.Serial(PORT, BAUD)

with open(filename, "w", newline="") as f:
    writer = csv.writer(f)

    writer.writerow([
        "timestamp",
        "ax",
        "ay",
        "az",
        "gx",
        "gy",
        "gz"
    ])

    print("Recording... Ctrl+C to stop")

    try:
        while True:
            line = ser.readline().decode().strip()

            parts = line.split(",")

            if len(parts) == 7:
                writer.writerow(parts)

    except KeyboardInterrupt:
        print("Saved:", filename)
