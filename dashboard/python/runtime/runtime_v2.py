import asyncio
import csv
import struct
import time
import json

from bleak import BleakScanner
from bleak import BleakClient
from collections import deque
from dashboard.python.pipelines.motion_pipeline import MotionPipeline
from dashboard.python.activity.step_counter import StepCounter

DEVICE_NAME = "ParkinSense"

# Bumped whenever the runtime/pipeline processing logic changes in a way
# that would affect how a captured dataset should be interpreted later.
PIPELINE_VERSION = "2.1.0"

# Firmware version isn't queryable over BLE yet, so this is a manual
# placeholder -- update it to match whatever firmware build is flashed
# on the XIAO nRF52840 Sense when a capture is taken.
FIRMWARE_VERSION = "unknown"

# Versioned independently from PIPELINE_VERSION because the step-counting
# and PPG (heart rate / SpO2 / HRV) algorithms evolve on their own
# schedules. Bump whichever one changes so a dataset always records
# exactly which algorithm version produced its step/vitals columns,
# even if the rest of the pipeline is untouched.
STEP_COUNTER_VERSION = "1.0"
PPG_VERSION = "1.0"

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
step_counter = StepCounter(sample_rate=SAMPLE_RATE_HZ)

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
    "sample_timestamp_us",

    "ax",
    "ay",
    "az",

    "gx",
    "gy",
    "gz",

    "ir",
    "red",

    "classification",
    "tremor_score",
    "confidence",
    "severity",
    "dominant_frequency",
    "frequency_std",
    "band_ratio",
    "best_axis",
    "axis_agreement",
    "axis_dominance",
    "rest_index",

    "motion_state",
    "motion_rms",

    "steps",
    "cadence",
    "step_rate_hz",
    "walking_state",
    "distance_m",
    "active_minutes",
    "step_confidence",
    "walking_confidence",
    "activity_type",

    "heart_rate",
    "spo2",
    "hr_confidence",
    "spo2_confidence",
    "signal_quality",
    "sensor_status",
    "finger_detected",

    "rmssd",
    "sdnn",
    "mean_rr",
    "pnn50",

    "sample_count",
    "packet_count",
    "sampling_rate",

    "packet_version",
    "flags",

    "pipeline_version",
    "firmware_version",
    "step_counter_version",
    "ppg_version"
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

                # StepCounter is intentionally a sibling of MotionPipeline,
                # not something MotionPipeline calls internally. It gets
                # fed the same per-sample accel values, gated by the
                # motion_state MotionPipeline already computed, so a
                # tremor-only, stationary wrist never registers as steps.
                step_data = step_counter.update(
                    ax,
                    ay,
                    az,
                    context["state"],
                )

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
                    # Steps
                    # ===============================
                    "steps": step_data["steps"],
                    "cadence": step_data["cadence"],
                    "step_rate_hz": step_data["step_rate_hz"],
                    # Canonical activity-state field. The dashboard and
                    # CSV both key off this single string rather than
                    # keeping a separate boolean in sync alongside it.
                    "walking_state": (
                        "WALKING"
                        if step_data["walking"]
                        else "NOT_WALKING"
                    ),
                    "distance_m": step_data["distance_m"],
                    "active_minutes": step_data["active_minutes"],
                    "step_confidence": step_data["step_confidence"],
                    "walking_confidence": step_data["walking_confidence"],
                    "activity_type": step_data["activity_type"],
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
                    "motion_pipeline_state": context["state"],
                    # ===============================
                    # Versioning / Provenance
                    # ===============================
                    "pipeline_version": PIPELINE_VERSION,
                    "firmware_version": FIRMWARE_VERSION,
                    "step_counter_version": STEP_COUNTER_VERSION,
                    "ppg_version": PPG_VERSION
                }

                with open(METRICS_FILE, "w") as f:
                    json.dump(metrics, f, indent=2)

                writer.writerow([
                    metrics["timestamp"],
                    timestamp_us,

                    ax,
                    ay,
                    az,

                    gx,
                    gy,
                    gz,

                    ir_raw,
                    red_raw,

                    metrics["classification"],
                    metrics["tremor_score"],
                    metrics["confidence"],
                    metrics["severity"],
                    metrics["dominant_frequency"],
                    metrics["frequency_std"],
                    metrics["band_ratio"],
                    metrics["best_axis"],
                    metrics["axis_agreement"],
                    metrics["axis_dominance"],
                    metrics["rest_index"],

                    metrics["motion_state"],
                    metrics["motion_rms"],

                    metrics["steps"],
                    metrics["cadence"],
                    metrics["step_rate_hz"],
                    metrics["walking_state"],
                    metrics["distance_m"],
                    metrics["active_minutes"],
                    metrics["step_confidence"],
                    metrics["walking_confidence"],
                    metrics["activity_type"],

                    metrics["heart_rate"],
                    metrics["spo2"],
                    ppg.get("hr_confidence"),
                    metrics["spo2_confidence"],
                    metrics["signal_quality"],
                    metrics["sensor_status"],
                    metrics["finger_detected"],

                    metrics["rmssd"],
                    metrics["sdnn"],
                    metrics["mean_rr"],
                    metrics["pnn50"],

                    metrics["sample_count"],
                    metrics["packet_count"],
                    metrics["sampling_rate"],

                    metrics["packet_version"],
                    metrics["flags"],

                    metrics["pipeline_version"],
                    metrics["firmware_version"],
                    metrics["step_counter_version"],
                    metrics["ppg_version"]
                ])

                csv_file.flush()

                print("\n============= PARKINSENSE =============")
                print(f"Tremor        : {metrics['classification']}")
                print(f"Score         : {metrics['tremor_score']}/100")
                print(f"Severity      : {metrics['severity']}")
                print(f"Frequency     : {metrics['dominant_frequency']} Hz")
                print(f"Motion        : {metrics['motion_state']}")
                print(f"Steps         : {metrics['steps']} (cadence {metrics['cadence']} spm / {metrics['step_rate_hz']} Hz)")
                print(f"Walking       : {metrics['walking_state']}")
                print(f"Distance      : {metrics['distance_m']} m")
                print(f"Active Mins   : {metrics['active_minutes']}")
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
