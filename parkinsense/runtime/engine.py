import asyncio
import csv
import struct
import time
import json
from dataclasses import dataclass, field
from fastapi import FastAPI
import threading
import uvicorn
from bleak import BleakScanner
from bleak import BleakClient
from collections import deque
from dashboard.python.pipelines.motion_pipeline import MotionPipeline
from dashboard.python.activity.step_counter import StepCounter

DEVICE_NAME = "ParkinSense"

# Bumped whenever the runtime/pipeline processing logic changes in a way
# that would affect how a captured dataset should be interpreted later.
#
# 2.2.0 -- windowed analysis moved from per-sample to a fixed hop
#          (ANALYSIS_HOP_SAMPLES). This changed the analysis rate by ~200x,
#          redefined every TremorStateMachine threshold from samples to
#          seconds, and corrected PPG finger hysteresis from 0.48 s to its
#          declared 1.0 s. Recordings made under 2.1.0 and 2.2.0 are NOT
#          interpretable under the same temporal assumptions. See
#          docs/adr/0001 and docs/adr/0002.
PIPELINE_VERSION = "2.2.0"

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

# Fixed-point scale factors for the BLE wire format.
#
# These MUST match the firmware's packing in parksense_ble_stream_v4.ino
# (`packet.samples[i].ax = ax_f * 8192.0f`, `.gx = gx_f * 131.0f`). They are
# a wire-format contract, not a statement about the sensor's configured
# full-scale range: the firmware converts g/dps -> counts with these factors
# and the runtime converts straight back, so the round-trip is exact.
#
# Note the implied int16 saturation points (+-4 g, +-250 dps). Whether the
# sensor is actually configured to stay within them is a separate firmware
# concern and is tracked as its own issue; nothing here can detect or
# correct a value that already wrapped on the device.
ACCEL_COUNTS_PER_G = 8192.0
GYRO_COUNTS_PER_DPS = 131.0

# --- Analysis scheduling ---------------------------------------------------
#
# The motion pipeline analyses a WINDOW_SIZE (4 s) buffer. Re-running that
# analysis on every arriving sample would recompute a 99.8%-identical window
# 104 times a second, so analysis instead advances by a fixed hop and the
# most recent result is reused in between.
#
# SAMPLE_RATE_HZ // 2 gives a 0.5 s hop: 87.5% overlap between consecutive
# 4 s windows, and a 2 Hz biomarker update.
#
# The binding constraint is *evidence independence*, not CPU. With a 4 s
# window, fully independent estimates arrive only every 4 s; any shorter hop
# yields correlated scores that TremorStateMachine nonetheless counts as
# independent votes. Cost is not the discriminator -- one analysis is ~1-3 ms,
# so every hop from 0.25 s to 2 s stays under ~1.2% of a core.
#
#   hop     overlap   time to CONFIRMED (4 hops)   assessment
#   0.25 s  93.75%    1.0 s                        four near-duplicate votes
#   0.50 s  87.50%    2.0 s                        chosen
#   1.00 s  75.00%    4.0 s                        more latency than needed
#   2.00 s  50.00%    8.0 s                        risks missing short episodes
#
# 50-75% overlap is conventional for windowed inertial analysis (Banos et al.,
# "Window Size Impact in Human Activity Recognition", Sensors 14(4), 2014).
# Add the 4 s window fill for cold-start latency: ~6 s to first confirmation.
#
# CAUTION -- this constant currently fixes the unit of TremorStateMachine's
# high_count/low_count, which are hop counts. Changing it silently changes
# detection latency from a different file. That coupling is a known defect
# (review P1-6): the state machine should express its thresholds in seconds,
# after which this becomes a pure cost/responsiveness knob. Until then, treat
# hop size and state-machine thresholds as one latency budget.
ANALYSIS_HOP_SAMPLES = SAMPLE_RATE_HZ // 2
ANALYSIS_HOP_SECONDS = ANALYSIS_HOP_SAMPLES / SAMPLE_RATE_HZ

HEADER_FORMAT = "<BBHI"
HEADER_SIZE = struct.calcsize(HEADER_FORMAT)

SAMPLE_FORMAT = "<hhhhhhII"
SAMPLE_SIZE = struct.calcsize(SAMPLE_FORMAT)

@dataclass
class RuntimeState:
    """
    Mutable per-session runtime state.

    Grouped into one object rather than added as further loose module-level
    globals. The pre-existing globals (buffers, pipeline, CSV handle) are
    left alone here; fully encapsulating the runtime in a class is a
    worthwhile change but a separate one, and out of scope for this fix.
    """

    packet_count: int = 0
    sample_count: int = 0

    # Samples accumulated since the last windowed analysis. Drives the
    # ANALYSIS_HOP_SAMPLES schedule.
    samples_since_analysis: int = 0

    # Most recent motion-context state, carried forward between analyses so
    # per-sample consumers (StepCounter) always have one to gate against.
    # None until the first analysis completes.
    motion_state: str | None = None

    # Most recent step-counter output, refreshed every sample.
    step_data: dict | None = None

    # Most recent complete metrics dict. Published on /metrics, written to
    # the JSON file, and forward-filled into every capture row between
    # analyses. Empty until the first analysis completes.
    metrics: dict = field(default_factory=dict)


state = RuntimeState()

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
app = FastAPI(title="ParkinSense API")

# Capture-file schema. Named so the header and `_write_capture_row()` are
# checkable against each other rather than being two independent 60-element
# literals that can silently drift apart.
CAPTURE_COLUMNS = [
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
    "ppg_version",
]

csv_file = open(
    "realtime_capture_v2.csv",
    "w",
    newline=""
)

writer = csv.writer(csv_file)
writer.writerow(CAPTURE_COLUMNS)


@app.get("/metrics")
def get_metrics():
    return state.metrics

def _write_capture_row(
    timestamp_us, ax, ay, az, gx, gy, gz, ir_raw, red_raw, version, flags
):
    """
    Append one capture row.

    Column groups have deliberately different time bases, because the
    quantities behind them do:

    * **Per-sample (live).** Raw signal, wall clock, runtime counters, and
      every step-tracking field. `StepCounter` is a per-sample streaming
      detector, so sampling its output at the analysis rate would quantise
      step *timing* to the hop -- destroying exactly the resolution gait
      and cadence analysis depends on.
    * **Per-analysis (forward-filled).** Tremor, motion-context and PPG
      biomarkers. These are windowed verdicts; a 4 s window's result was
      never specific to the single sample whose arrival triggered it, so
      carrying it forward between analyses is what it always meant
      implicitly.
    * **Per-packet.** Packet version and flags, taken from the packet this
      sample arrived in rather than from the last analysed one.

    Keeping the raw and step columns live is what allows a recording to be
    re-analysed offline at a different hop and reproduce the same result.
    """
    metrics = state.metrics
    step = state.step_data or {}

    elapsed = max(time.time() - start_time, 1e-6)

    row = [
        time.time(),
        timestamp_us,

        ax, ay, az,
        gx, gy, gz,

        ir_raw, red_raw,

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

        # Live per-sample step fields (see docstring).
        step.get("steps"),
        step.get("cadence"),
        step.get("step_rate_hz"),
        "WALKING" if step.get("walking") else "NOT_WALKING",
        step.get("distance_m"),
        step.get("active_minutes"),
        step.get("step_confidence"),
        step.get("walking_confidence"),
        step.get("activity_type"),

        metrics["heart_rate"],
        metrics["spo2"],
        metrics["hr_confidence"],
        metrics["spo2_confidence"],
        metrics["signal_quality"],
        metrics["sensor_status"],
        metrics["finger_detected"],

        metrics["rmssd"],
        metrics["sdnn"],
        metrics["mean_rr"],
        metrics["pnn50"],

        # Live runtime counters: sample_count must stay usable as a row
        # index, which a forward-filled snapshot would break.
        state.sample_count,
        state.packet_count,
        round(state.sample_count / elapsed, 2),

        # From the packet this sample actually arrived in.
        version,
        flags,

        metrics["pipeline_version"],
        metrics["firmware_version"],
        metrics["step_counter_version"],
        metrics["ppg_version"],
    ]

    if len(row) != len(CAPTURE_COLUMNS):
        raise AssertionError(
            f"capture row has {len(row)} fields but CAPTURE_COLUMNS "
            f"declares {len(CAPTURE_COLUMNS)}"
        )

    writer.writerow(row)


def _print_status(metrics):
    """Human-readable status block, emitted once per analysis hop."""
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


def notification_handler(sender, data):
    state.packet_count += 1

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

        ax = ax_raw / ACCEL_COUNTS_PER_G
        ay = ay_raw / ACCEL_COUNTS_PER_G
        az = az_raw / ACCEL_COUNTS_PER_G

        gx = gx_raw / GYRO_COUNTS_PER_DPS
        gy = gy_raw / GYRO_COUNTS_PER_DPS
        gz = gz_raw / GYRO_COUNTS_PER_DPS

        ax_buffer.append(ax)
        ay_buffer.append(ay)
        az_buffer.append(az)

        gx_buffer.append(gx)
        gy_buffer.append(gy)
        gz_buffer.append(gz)

        state.sample_count += 1

        # ------------------------------------------------------------------
        # Per-sample path: streaming consumers that must see every sample.
        # ------------------------------------------------------------------

        # PPG ingestion is per-sample by necessity: PPGProcessor's rolling
        # buffer *is* the PPG waveform, so decimating ingestion would
        # decimate the signal itself. Analysis of that buffer happens on the
        # slower hop below, which is why ir/red are not passed to process().
        pipeline.ingest_ppg(ir_raw, red_raw)

        # StepCounter is a per-sample streaming detector (threshold crossing
        # + hysteresis re-arm + refractory period); skipping samples means
        # missing steps outright, so it stays outside the hop gate. It is a
        # deliberate sibling of MotionPipeline rather than something
        # MotionPipeline calls internally, and it consumes the most recent
        # motion state -- a 4 s-window context that legitimately changes far
        # more slowly than the sample rate -- so that a tremor-only,
        # stationary wrist never registers as steps.
        if state.motion_state is not None:
            state.step_data = step_counter.update(
                ax,
                ay,
                az,
                state.motion_state,
            )

        # ------------------------------------------------------------------
        # Per-hop path: windowed analysis over the full buffer.
        # ------------------------------------------------------------------
        if len(gx_buffer) >= WINDOW_SIZE:
            state.samples_since_analysis += 1

            # Run immediately once the window first fills (so there is no
            # dead period before any metrics exist), and on the fixed hop
            # thereafter.
            if state.samples_since_analysis >= ANALYSIS_HOP_SAMPLES or not state.metrics:
                state.samples_since_analysis = 0

                result = pipeline.process(
                    list(ax_buffer),
                    list(ay_buffer),
                    list(az_buffer),
                    list(gx_buffer),
                    list(gy_buffer),
                    list(gz_buffer),
                    ir=None,
                    red=None,
                )

                analysis = result["result"]
                context  = result["context"]
                ppg      = result["ppg"]

                state.motion_state = context["state"]

                # Prime the step counter on the very first analysis: the
                # per-sample gate above skips it until a motion state
                # exists, so without this the first metrics dict would have
                # no step fields to report.
                if state.step_data is None:
                    state.step_data = step_counter.update(
                        ax, ay, az, state.motion_state
                    )
                step_data = state.step_data

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
                    "sample_count": state.sample_count,
                    "packet_count": state.packet_count,
                    "sampling_rate": round(
                        state.sample_count /
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

                # Publish this hop's metrics for the /metrics endpoint.
                # A .copy() is used (rather than a reference) so a
                # concurrent HTTP GET on the uvicorn thread can't see a
                # dict that's still being mutated on the BLE thread.
                state.metrics = metrics.copy()

                with open(METRICS_FILE, "w") as f:
                    json.dump(metrics, f, indent=2)

                _print_status(metrics)

        # Capture row, written per sample so the raw signal columns stay at
        # the full sample rate. Suppressed until the first analysis has
        # produced metrics, matching the previous behaviour of emitting
        # nothing before the window was ready.
        if state.metrics:
            _write_capture_row(
                timestamp_us,
                ax, ay, az,
                gx, gy, gz,
                ir_raw, red_raw,
                version, flags,
            )

        offset += sample_size

    # Flush once per packet rather than once per row: bounds worst-case
    # data loss to a single packet while cutting write syscalls by BATCH_SIZE.
    csv_file.flush()

    if state.packet_count % 10 == 0:
        elapsed = (
            time.time() -
            start_time
        )
        rate = (
            state.sample_count /
            elapsed
        )
        print(
            f"Packets={state.packet_count} "
            f"Samples={state.sample_count} "
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


def start_api():
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        log_level="warning",
    )


if __name__ == "__main__":
    # Serve /metrics on a background thread so the FastAPI/uvicorn event
    # loop doesn't block or contend with the asyncio BLE loop in main().
    threading.Thread(
        target=start_api,
        daemon=True,
    ).start()

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        csv_file.close()
        print(
            "\nCapture stopped."
        )
