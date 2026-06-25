"""
ParkinSense V2 Configuration
"""

# -----------------------------
# IMU
# -----------------------------

SAMPLE_RATE = 104

WINDOW_SECONDS = 4

WINDOW_SIZE = SAMPLE_RATE * WINDOW_SECONDS

# -----------------------------
# Filters
# -----------------------------

LOWCUT = 3.0

HIGHCUT = 8.0

FILTER_ORDER = 4

NOTCH_FREQ = 50.0

NOTCH_Q = 30

# -----------------------------
# Tremor
# -----------------------------

TREMOR_MIN_FREQ = 3.5

TREMOR_MAX_FREQ = 7.5

MIN_RMS = 0.8

MIN_BAND_RATIO = 0.12

PERSISTENCE_REQUIRED = 3

# -----------------------------
# Dashboard
# -----------------------------

DASHBOARD_REFRESH_MS = 100

# -----------------------------
# Heart Rate (future)
# -----------------------------

PPG_RATE = 100
