"""
Single source of truth for constants shared across ParkinSense modules.

Rule: a constant used by more than one module lives here. Module-private
tuning parameters stay in their module, next to the code they tune, with a
justification. Changing anything here that alters how a recording should be
interpreted requires bumping PIPELINE_VERSION (see docs/decisions/).
"""

from __future__ import annotations

from enum import Enum

# ---------------------------------------------------------------------------
# Versioning / provenance
# ---------------------------------------------------------------------------

# 3.0.0 -- tremor features computed on the un-band-passed gyro spectrum;
#          motion context excludes the tremor band; HMM temporal filter
#          replaces the count state machine (published classification now
#          comes from the temporal filter); PPG analysed at the true slot
#          rate; signal-time clock for all temporal logic. See
#          docs/decisions/0004..0009. Recordings from 2.x are not comparable.
# 2.2.0 -- analysis on a fixed hop (ADR-0001); time-based PPG hysteresis.
PIPELINE_VERSION = "3.0.0"
CAPTURE_SCHEMA_VERSION = "3"
TREMOR_ALGORITHM_VERSION = "3.0"
PPG_VERSION = "2.0"
# Version of each selectable step algorithm. This is the single source of truth.
STEP_ALGORITHM_VERSIONS = {"default": "1.1", "periodic": "2.0", "gated": "3.0-dev"}
# Deprecated alias: the version of the DEFAULT step counter. Until Phase 8 this constant read "2.0" and was
# written into every recording although the default counter is v1.1 (audit D1). Recordings made before the
# correction keep the old label; use `step_algorithm_version_of()` to interpret any recording.
# See docs/decisions/0013-step-version-label-correction.md.
STEP_COUNTER_VERSION = STEP_ALGORITHM_VERSIONS["default"]
LEGACY_STEP_COUNTER_LABEL = "2.0"
# metadata.json revision: 1 = no key (all recordings before Phase 8); 2 = step_counter_version names the
# algorithm that actually ran. Additive: no capture column was added, removed or renamed.
METADATA_REVISION = 2
SLEEP_ALGORITHM_VERSION = "1.0"
SLEEP_EPOCH_SCHEMA_VERSION = "1"

# ---------------------------------------------------------------------------
# Sampling
# ---------------------------------------------------------------------------

SAMPLE_RATE_HZ = 104.0               # nominal IMU rate (firmware 9615 us interval)
WINDOW_SECONDS = 4.0                 # motion/tremor analysis window
WINDOW_SAMPLES = int(round(SAMPLE_RATE_HZ * WINDOW_SECONDS))   # 416
ANALYSIS_HOP_SAMPLES = int(SAMPLE_RATE_HZ // 2)                 # 52 -> 0.5 s, see ADR-0001
ANALYSIS_HOP_SECONDS = ANALYSIS_HOP_SAMPLES / SAMPLE_RATE_HZ

# PPG samples arrive one per IMU slot (zero-order hold of the sensor's own
# rate), so the PPG buffer's sample rate *is* the slot rate. The sensor's
# distinct-sample rate depends on firmware: 10 Hz for protocol v1, ~100 Hz
# for protocol v2 (docs/protocol/BLE_PROTOCOL.md).
PPG_SLOT_RATE_HZ = SAMPLE_RATE_HZ
PPG_WINDOW_SECONDS = 10.0

# Measured-rate validation (audit P0-4): warn beyond 2 %, mark data invalid
# for frequency-domain analysis beyond 5 %.
RATE_WARN_FRACTION = 0.02
RATE_INVALID_FRACTION = 0.05

# A device-time gap longer than this resets windowed state, so a window never
# splices pre-gap and post-gap data (review P2-13).
MAX_GAP_BEFORE_RESET_S = 0.5

# ---------------------------------------------------------------------------
# Shared vocabularies (string values are the wire/CSV representation and
# must not change without a schema bump)
# ---------------------------------------------------------------------------


class MotionState(str, Enum):
    REST = "REST"
    LOW_MOTION = "LOW MOTION"     # historical spelling with a space, kept for CSV compatibility
    ACTIVE = "ACTIVE"

    @classmethod
    def parse(cls, value) -> "MotionState | None":
        if value is None:
            return None
        if isinstance(value, MotionState):
            return value
        v = str(value).strip().upper().replace("_", " ")
        for m in cls:
            if m.value == v:
                return m
        return None


class Quality(str, Enum):
    """
    Measurement-quality state attached to every published biomarker. A
    consumer must treat anything other than VALID as "do not interpret as a
    measurement".
    """
    VALID = "VALID"
    LOW_CONFIDENCE = "LOW_CONFIDENCE"
    MOTION_ARTIFACT = "MOTION_ARTIFACT"
    NO_CONTACT = "NO_CONTACT"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    DATA_GAP = "DATA_GAP"
    SENSOR_FAULT = "SENSOR_FAULT"
    RATE_INVALID = "RATE_INVALID"


# ---------------------------------------------------------------------------
# Tremor band definitions (Hz). PD rest tremor is typically 4-6 Hz, range
# ~3.5-7.5 Hz (Deuschl et al., Mov Disord 1998;13 Suppl 3:2-23). ParaDigMa
# (Timmermans et al., npj Parkinson's Dis 2025) searches 3-7 Hz.
# ---------------------------------------------------------------------------

TREMOR_BAND_HZ = (3.5, 7.5)
ARM_MOVEMENT_BAND_HZ = (0.5, 3.0)     # non-tremor purposeful movement (ParaDigMa)
ANALYSIS_BAND_HZ = (0.5, 15.0)

# API / files
DEFAULT_API_PORT = 8000
DEFAULT_DASHBOARD_PORT = 8050
METRICS_FILENAME = "realtime_metrics_v2.json"   # historical name kept for the dashboard/app


def step_algorithm_version_of(step_counter_version: str | None = None, step_algorithm: str | None = None,
                              metadata_revision: int | None = None) -> str | None:
    """
    The version of the step algorithm that produced a recording, from whatever its metadata or capture holds.

      * `step_algorithm` present (metadata.json since Phase 7)  -> STEP_ALGORITHM_VERSIONS[step_algorithm]
      * revision >= 2                                          -> `step_counter_version` as recorded
      * otherwise the label is the legacy constant: every such recording was produced by the default counter
        (v1.1) because no other counter was selectable before Phase 7, so the label "2.0" is read as "1.1".
    """
    if step_algorithm in STEP_ALGORITHM_VERSIONS:
        return STEP_ALGORITHM_VERSIONS[step_algorithm]
    if (metadata_revision or 1) >= 2:
        return step_counter_version
    if step_counter_version in (None, ""):
        return None
    return STEP_ALGORITHM_VERSIONS["default"] if step_counter_version == LEGACY_STEP_COUNTER_LABEL \
        else step_counter_version
