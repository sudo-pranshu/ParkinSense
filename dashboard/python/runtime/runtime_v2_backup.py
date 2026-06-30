import asyncio
import csv
import struct
import time

import json

from bleak import BleakScanner
from bleak import BleakClient

from collections import deque

from dashboard.python.pipelines.motion_pipeline import MotionPipeline


DEVICE_NAME = "ParkinSense"

SERVICE_UUID = "ABCD1234-0000-467A-9538-01F0652C74E0"
CHAR_UUID = "ABCD1234-0001-467A-9538-01F0652C74E0"

SAMPLE_RATE_HZ = 104
SAMPLE_PERIOD_US = int(1_000_000 / SAMPLE_RATE_HZ)

BATCH_SIZE = 10

packet_count = 0
sample_count = 0

start_time = time.time()

pipeline = MotionPipeline(SAMPLE_RATE_HZ)

WINDOW_SIZE = SAMPLE_RATE_HZ * 4

ax_buffer = deque(maxlen=WINDOW_SIZE)
ay_buffer = deque(maxlen=WINDOW_SIZE)
az_buffer = deque(maxlen=WINDOW_SIZE)

gx_buffer = deque(maxlen=WINDOW_SIZE)
gy_buffer = deque(maxlen=WINDOW_SIZE)
gz_buffer = deque(maxlen=WINDOW_SIZE)

METRICS_FILE = "realtime_metrics_v2.json"

csv_file = open(
    "realtime_capture_v2.csv",
    "w",
    newline=""
)

writer = csv.writer(csv_file)

writer.writerow([
    "timestamp",
    "ax",
    "ay",
    "az",
    "gx",
    "gy",
    "gz"
])


def notification_handler(sender, data):

    global packet_count
    global sample_count

    packet_count += 1

    header_size = 4
    sample_size = 12

    expected_size = (
        header_size +
        BATCH_SIZE * sample_size
    )

    if len(data) != expected_size:

        print(
            f"BAD PACKET: "
            f"{len(data)} bytes "
            f"(expected {expected_size})"
        )

        return

    packet_timestamp_us = struct.unpack_from(
        "<I",
        data,
        0
    )[0]

    offset = header_size

    for i in range(BATCH_SIZE):

        (
            ax_raw,
            ay_raw,
            az_raw,
            gx_raw,
            gy_raw,
            gz_raw
        ) = struct.unpack_from(
            "<hhhhhh",
            data,
            offset
        )

        timestamp_us = (
            packet_timestamp_us +
            i * SAMPLE_PERIOD_US
        )

        ax = ax_raw / 8192.0
        ay = ay_raw / 8192.0
        az = az_raw / 8192.0

        gx = gx_raw / 131.0
        gy = gy_raw / 131.0
        gz = gz_raw / 131.0

        writer.writerow([
            timestamp_us,
            ax,
            ay,
            az,
            gx,
            gy,
            gz
        ])

        ax_buffer.append(ax)
        ay_buffer.append(ay)
        az_buffer.append(az)

        gx_buffer.append(gx)
        gy_buffer.append(gy)
        gz_buffer.append(gz)

        sample_count += 1

        if len(gx_buffer) == WINDOW_SIZE:

            result = pipeline.process(

                list(ax_buffer),
                list(ay_buffer),
                list(az_buffer),

                list(gx_buffer),
                list(gy_buffer),
                list(gz_buffer)

            )

            if result is not None:

                analysis = result["result"]
                context  = result["context"]

                metrics = {

                    "classification": (
                        "TREMOR"
                        if analysis["tremor"]
                        else "NO TREMOR"
                    ),

                    "tremor_score": int(analysis["score"]),

                    "confidence": float(analysis["confidence"]),

                    "severity": analysis["severity"],

                    "dominant_frequency": float(analysis["frequency"]),

                    "frequency_std": float(analysis["frequency_std"]),

                    "band_ratio": float(analysis["band_ratio"]),

                    "best_axis": analysis["best_axis"],

                    "axis_agreement": float(analysis["axis_agreement"]),

                    "axis_dominance": float(analysis["axis_dominance"]),

                    "motion_state": context["state"],

                    "motion_rms": float(context["motion_rms"]),

                    "sample_count": sample_count,

                    "packet_count": packet_count,

                    "sampling_rate": float(
                        sample_count /
                        max(
                            1,
                            time.time() - start_time
                        )
                    )

                }

                with open(METRICS_FILE, "w") as f:
                    json.dump(metrics, f, indent=2)

                print("\n========== PARKINSENSE V2 ==========")

                print(f"State          : {metrics['classification']}")
                print(f"Score          : {metrics['tremor_score']}/100")
                print(f"Confidence     : {metrics['confidence']:.1f}%")
                print(f"Severity       : {metrics['severity']}")
                print(f"Frequency      : {metrics['dominant_frequency']:.2f} Hz")
                print(f"Best Axis      : {metrics['best_axis']}")
                print(f"Motion         : {metrics['motion_state']}")
                print(f"Motion RMS     : {metrics['motion_rms']:.3f}")

                print("===================================\n")

        offset += sample_size

    csv_file.flush()

    if packet_count % 10 == 0:

        elapsed = (
            time.time() -
            start_time
        )

        rate = (
            sample_count /
            elapsed
        )

        print(
            f"Packets={packet_count} "
            f"Samples={sample_count} "
            f"Rate={rate:.1f} Hz"
        )



async def main():

    print(
        "Searching for ParkinSense..."
    )

    device = await BleakScanner.find_device_by_filter(
        lambda d, ad:
        d.name and DEVICE_NAME in d.name
    )

    if device is None:

        print("Device not found")
        return

    print(
        "Found:",
        device.address
    )

    async with BleakClient(device) as client:

        print("Connected")

        await client.start_notify(
            CHAR_UUID,
            notification_handler
        )

        print("Streaming...")

        while True:

            await asyncio.sleep(1)


if __name__ == "__main__":

    try:

        asyncio.run(main())

    except KeyboardInterrupt:

        csv_file.close()

        print(
            "\nCapture stopped."
        )


