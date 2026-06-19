import asyncio
import csv
import struct
import time

from bleak import BleakScanner
from bleak import BleakClient

from realtime_tremor import RealtimeTremorDetector


DEVICE_NAME = "ParkinSense"

SERVICE_UUID = "ABCD1234-0000-467A-9538-01F0652C74E0"
CHAR_UUID = "ABCD1234-0001-467A-9538-01F0652C74E0"

SAMPLE_RATE_HZ = 104
SAMPLE_PERIOD_US = int(1_000_000 / SAMPLE_RATE_HZ)

BATCH_SIZE = 10

packet_count = 0
sample_count = 0

start_time = time.time()

detector = RealtimeTremorDetector()

csv_file = open(
    "realtime_capture.csv",
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

        detector.add_sample(
            gx,
            gy,
            gz
        )

        sample_count += 1

        if sample_count % SAMPLE_RATE_HZ == 0:

            result = detector.analyze()

            if result is not None:

                print()

                print(
                    "========== TREMOR ANALYSIS =========="
                )

                print(
                    f"Dominant Frequency: "
                    f"{result['dominant_frequency']:.2f} Hz"
                )

                print(
                    f"Band Ratio: "
                    f"{result['band_ratio']:.3f}"
                )

                print(
                    f"Tremor Score: "
                    f"{result['tremor_score']}"
                )

                if result["tremor_detected"]:

                    print(
                        "Classification: TREMOR"
                    )

                else:

                    print(
                        "Classification: NO TREMOR"
                    )

                print(
                    "===================="
                )

                print()

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
