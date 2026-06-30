import asyncio
import csv
import os
import struct
import time

import json

from bleak import BleakScanner
from bleak import BleakClient

from realtime_tremor import RealtimeTremorDetector


DEVICE_NAME = "ParkinSense"

SERVICE_UUID = "ABCD1234-0000-467A-9538-01F0652C74E0"
CHAR_UUID = "ABCD1234-0001-467A-9538-01F0652C74E0"

SAMPLE_RATE_HZ = 104
SAMPLE_PERIOD_US = int(1_000_000 / SAMPLE_RATE_HZ)

BATCH_SIZE = 10

HEADER_FORMAT = "<BBHI"
HEADER_SIZE = struct.calcsize(HEADER_FORMAT)

SAMPLE_FORMAT = "<hhhhhhII"
SAMPLE_SIZE = struct.calcsize(SAMPLE_FORMAT)

packet_count = 0
sample_count = 0
firmware_version_logged = False

start_time = time.time()

detector = RealtimeTremorDetector()

DATA_DIR = "data/raw"
os.makedirs(DATA_DIR, exist_ok=True)

METRICS_FILE = os.path.join(
    DATA_DIR,
    "realtime_metrics.json"
)

run_timestamp = time.strftime("%Y%m%d_%H%M%S")
csv_path = os.path.join(DATA_DIR, f"parkinsense_{run_timestamp}.csv")

csv_file = open(
    csv_path,
    "w",
    newline=""
)

print(f"Recording to: {csv_path}")

writer = csv.writer(csv_file)

writer.writerow([
    "timestamp",
    "ax",
    "ay",
    "az",
    "gx",
    "gy",
    "gz",
    "ir",
    "red",
    "packet_version"
])


def notification_handler(sender, data):

    global packet_count
    global sample_count
    global firmware_version_logged

    header_size = HEADER_SIZE
    sample_size = SAMPLE_SIZE

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

    packet_count += 1

    (
        version,
        flags,
        _,
        packet_timestamp_us
    ) = struct.unpack_from(
        HEADER_FORMAT,
        data,
        0
    )

    # NOTE: the current firmware always sets flags=0 (it does not yet
    # populate imu_valid/ppg_valid/finger_present bits), so those are
    # intentionally not decoded here. Re-add bit decoding once the
    # firmware actually sets bit0/bit1/bit2.

    if not firmware_version_logged:
        print("Firmware Packet Version:", version)
        firmware_version_logged = True

    offset = header_size

    for i in range(BATCH_SIZE):

        (
            ax_raw,
            ay_raw,
            az_raw,
            gx_raw,
            gy_raw,
            gz_raw,
            ir_raw,
            red_raw
        ) = struct.unpack_from(
            SAMPLE_FORMAT,
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

        ir = ir_raw
        red = red_raw

        writer.writerow([
            timestamp_us,
            ax,
            ay,
            az,
            gx,
            gy,
            gz,
            ir,
            red,
            version
        ])

        detector.add_sample(
            ax,
            ay,
            az,
            gx,
            gy,
            gz
        )

        sample_count += 1

        if sample_count % SAMPLE_RATE_HZ == 0:

            result = detector.analyze()

            if result is not None:

                metrics = {
                    "dominant_frequency": float(result["dominant_frequency"]),
                    "frequency_std": float(result["frequency_std"]),
                    "band_ratio": float(result["band_ratio"]),
                    "best_axis": result["best_axis"],

                    "rest_index": float(result["rest_index"]),
                    "axis_coherence": float(result["axis_coherence"]),
                    "axis_dominance": float(result["axis_dominance"]),

                    "tremor_score": int(result["tremor_score"]),
                    "confidence": int(result["confidence"]),
                    "persistence": int(result["persistence"]),
                    "tremor_burden": float(result["tremor_burden"]),

                    "severity": result["severity"],

                    "classification":
                        "TREMOR"
                        if result["tremor_detected"]
                        else "NO TREMOR",

                    "sample_count": int(sample_count),
                    "packet_count": int(packet_count),

                    "sampling_rate": float(
                        sample_count /
                        max(1, time.time() - start_time)
                    ),
                    "dropped_packets": 0,

                    "latest_ir": int(ir),
                    "latest_red": int(red),

                    "packet_version": version
                }

                with open(METRICS_FILE, "w") as f:
                    json.dump(metrics, f, indent=2)

                print()

                print(
                    "========== TREMOR ANALYSIS =========="
                )

                print(
                    f"Dominant Frequency: "
                    f"{result['dominant_frequency']:.2f} Hz"
                )

                print(
                    f"RMS Motion: "
                    f"{result['rms_motion']:.2f}"
                )

                print(
                    f"Frequency Std Dev: "
                    f"{result['frequency_std']:.2f} Hz"
                )

                print(
                    f"Band Ratio: "
                    f"{result['band_ratio']:.3f}"
                )

                print(
                    f"Best Axis: "
                    f"{result['best_axis']}"
                )

                print(
                    f"Rest Index: "
                    f"{result['rest_index']:.3f}"
                )

                print(
                    f"Axis Coherence: "
                    f"{result['axis_coherence']:.2f}"
                )

                print(
                    f"Axis Dominance: "
                    f"{result['axis_dominance']:.2f}"
                )

                print(
                    f"Motion Gate: "
                    f"{result['motion_gate']}"
                )

                print(
                    f"Frequency Gate: "
                    f"{result['frequency_gate']}"
                )

                print(
                    f"Energy Gate: "
                    f"{result['energy_gate']}"
                )

                print(
                    f"Stability Gate: "
                    f"{result['stability_gate']}"
                )

                print(
                    f"Coherence Gate: "
                    f"{result['coherence_gate']}"
                )

                print(
                    f"Dominance Gate: "
                    f"{result['dominance_gate']}"
                )

                print(
                    f"Rest Gate: "
                    f"{result['rest_gate']}"
                )

                print()

                print(
                    f"Tremor Score: "
                    f"{result['tremor_score']}/100"
                )

                print(
                    f"Confidence: "
                    f"{result['confidence']}%"
                )

                print(
                    f"Severity: "
                    f"{result['severity']}"
                )

                print(
                    f"Persistence: "
                    f"{result['persistence']}/5"
                )

                print(
                    f"Tremor Burden: "
                    f"{result['tremor_burden']:.1f}%"
                )

                print(
                    f"IR: {ir}  RED: {red}"
                )

                print()

                if result['tremor_detected']:

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

    if packet_count % 20 == 0:
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

        # In current bleak, .services is populated automatically once
        # connect() completes (which the async-with above already did),
        # so this is normally non-None. get_services() is deprecated, but
        # kept as a fallback for older bleak versions/backends where
        # discovery timing can differ - avoids the deprecation warning in
        # the common case while still guarding against the edge case.
        services = client.services
        if services is None:
            services = await client.get_services()

        known_char_uuids = [
            c.uuid.lower()
            for s in services
            for c in s.characteristics
        ]

        if CHAR_UUID.lower() not in known_char_uuids:
            print("Characteristic not found.")
            return

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

        print(
            "\nCapture stopped."
        )

    finally:

        csv_file.flush()
        csv_file.close()
