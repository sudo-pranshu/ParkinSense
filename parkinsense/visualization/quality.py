"""
Presentation of ParkinSense quality states. Semantics are defined by the
runtime (`config.Quality`, docs/runtime/RUNTIME_AND_RECORDING.md); this module
only maps them to labels, colours and explanations. Two display-only states
are added: STALE (no fresh data from the runtime) and OFFLINE (runtime
unreachable) -- neither is ever written to a recording.
"""

from __future__ import annotations

from parkinsense.config import Quality

# token -> (label, css class, explanation)
STATES = {
    Quality.VALID.value: ("Valid", "q-valid", "Measurement passed all quality checks."),
    Quality.LOW_CONFIDENCE.value: ("Low confidence", "q-warn", "Computed, but confidence is below the publish threshold."),
    Quality.MOTION_ARTIFACT.value: ("Motion artefact", "q-artifact", "Coincides with wrist motion; likely corrupted by movement."),
    Quality.NO_CONTACT.value: ("No contact", "q-muted", "No finger on the PPG sensor."),
    Quality.INSUFFICIENT_DATA.value: ("Insufficient data", "q-muted", "Not enough clean signal yet to compute a value."),
    Quality.DATA_GAP.value: ("Data gap", "q-bad", "Window unusable: stream rate invalid or a gap in the data."),
    Quality.SENSOR_FAULT.value: ("Sensor fault", "q-bad", "Too many clipped / faulty samples in the window."),
    Quality.RATE_INVALID.value: ("Rate invalid", "q-bad", "Device sample rate is more than 5 % off nominal."),
    "STALE": ("Stale", "q-muted", "No new data from the runtime recently; value is not live."),
    "OFFLINE": ("Runtime offline", "q-muted", "The runtime API is not reachable."),
    "ESTIMATE": ("Uncalibrated estimate", "q-estimate", "Research estimate only; not a calibrated or clinical measurement."),
}

ORDERED = [q.value for q in Quality]


def label(state: str | None) -> str:
    return STATES.get(state or "", (state or "Unknown", "", ""))[0]


def css(state: str | None) -> str:
    return STATES.get(state or "", ("", "q-muted", ""))[1]


def explain(state: str | None) -> str:
    return STATES.get(state or "", ("", "", "Unknown quality state."))[2]


def is_trustworthy(state: str | None) -> bool:
    return state == Quality.VALID.value


# Colours used in charts (kept in sync with assets/style.css).
CHART_COLORS = {
    "VALID": "#3ecf8e", "LOW_CONFIDENCE": "#e6b450", "MOTION_ARTIFACT": "#f08a4b",
    "NO_CONTACT": "#6b7280", "INSUFFICIENT_DATA": "#6b7280", "DATA_GAP": "#ef5f6b",
    "SENSOR_FAULT": "#ef5f6b", "RATE_INVALID": "#ef5f6b",
}
