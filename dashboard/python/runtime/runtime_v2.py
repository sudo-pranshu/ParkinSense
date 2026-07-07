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

HEADER_FORMAT = "<BBHI"
HEADER_SIZE = struct.calcsize(HEADER_FORMAT)

SAMPLE_FORMAT = "<hhhhhhII"
SAMPLE_SIZE = struct.calcsize(SAMPLE_FORMAT)

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
    "gz",
    "ir",
    "red",
    "packet_version",
    "flags"
])

def notification_handler(sender, data):
    global packet_count
    global sample_count

    packet_count += 1

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

    (
        version,
        flags,
        reserved,
        packet_timestamp_us
    ) = struct.unpack_from(
        HEADER_FORMAT,
        data,
        0
    )

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

        writer.writerow([
            timestamp_us,
            ax,
            ay,
            az,
            gx,
            gy,
            gz,
            ir_raw,
            red_raw,
            version,
            flags
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
                list(gz_buffer),
                ir=ir_raw,
                red=red_raw
            )

            if result is not None:
                analysis = result["result"]
                context  = result["context"]
                ppg      = result["ppg"]

                metrics = {
                    # ===============================
                    # Tremor
                    # ===============================
                    "classification": (
                        "TREMOR"
                        if analysis["tremor"]
                        else "NO TREMOR"
                    ),
                    "tremor_score": int(analysis["score"]),
                    "confidence": round(
                        float(analysis["confidence"]),
                        3
                    ),
                    "severity": analysis["severity"],
                    "dominant_frequency": round(
                        float(analysis["frequency"]),
                        2
                    ),
                    "frequency_std": round(
                        float(analysis["frequency_std"]),
                        2
                    ),
                    "band_ratio": round(
                        float(analysis["band_ratio"]),
                        3
                    ),
                    "best_axis": analysis["best_axis"],
                    "axis_agreement": round(
                        float(analysis["axis_agreement"]),
                        3
                    ),
                    "axis_dominance": round(
                        float(analysis["axis_dominance"]),
                        3
                    ),
                    "rest_index": round(
                        float(analysis["rest_index"]),
                        3
                    ),
                    # ===============================
                    # Motion
                    # ===============================
                    "motion_state": context["state"],
                    "motion_rms": round(
                        float(context["motion_rms"]),
                        3
                    ),
                    # ===============================
                    # Heart Rate
                    # ===============================
                    "heart_rate": ppg.get("heart_rate"),
                    "signal_quality": ppg.get("signal_quality"),
                    "sensor_status": ppg.get("sensor_status"),
                    "finger_detected": ppg.get("finger_detected"),
                    "hr_confidence": ppg.get("hr_confidence"),
                    "spo2": ppg.get("spo2"),
                    "spo2_confidence": ppg.get("spo2_confidence"),
                    # ===============================
                    # HR Quality
                    # ===============================
                    "hr_quality": ppg.get("hr_quality", {}),
                    # ===============================
                    # HRV
                    # ===============================
                    "rmssd": ppg.get("hrv", {}).get("rmssd"),
                    "sdnn": ppg.get("hrv", {}).get("sdnn"),
                    "mean_rr": ppg.get("hrv", {}).get("mean_rr"),
                    "pnn50": ppg.get("hrv", {}).get("pnn50"),
                    # ===============================
                    # Raw PPG
                    # ===============================
                    "latest_ir": int(ppg["ir"])
                    if ppg["ir"] is not None
                    else 0,
                    "latest_red": int(ppg["red"])
                    if ppg["red"] is not None
                    else 0,
                    # ===============================
                    # Runtime
                    # ===============================
                    "sample_count": sample_count,
                    "packet_count": packet_count,
                    "sampling_rate": round(
                        sample_count /
                        max(
                            time.time() - start_time,
                            1e-6
                        ),
                        2
                    ),
                    "packet_version": version,
                    "flags": flags,
                    "timestamp": ppg.get("timestamp"),
                    "motion_pipeline_state": context["state"]
                }

                with open(METRICS_FILE, "w") as f:
                    json.dump(metrics, f, indent=2)

                print("\n============= PARKINSENSE =============")
                print(f"Tremor        : {metrics['classification']}")
                print(f"Score         : {metrics['tremor_score']}/100")
                print(f"Severity      : {metrics['severity']}")
                print(f"Frequency     : {metrics['dominant_frequency']} Hz")
                print(f"Motion        : {metrics['motion_state']}")
                print("--------------------------------------")
                print(f"Heart Rate    : {metrics['heart_rate']} BPM")
                print(f"SpO2          : {metrics['spo2']} %")
                print(f"Signal Quality: {metrics['signal_quality']}")
                print(f"Finger        : {metrics['finger_detected']}")
                print(f"Sensor Status : {metrics['sensor_status']}")
                print("--------------------------------------")
                print(f"RMSSD         : {metrics['rmssd']}")
                print(f"SDNN          : {metrics['sdnn']}")
                print(f"Mean RR       : {metrics['mean_rr']}")
                print(f"pNN50         : {metrics['pnn50']}")
                print("======================================\n")

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
