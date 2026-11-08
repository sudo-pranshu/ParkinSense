"""Single source for the implementation-status matrix used by the paper (figure + table).

Evidence cells: 2 = done and documented in the repository, 1 = partial / owner-reported / one side only,
0 = none. Sources are in docs/research/IMPLEMENTATION_STATUS_MATRIX.md (same rows, with file pointers).
Columns: automated tests | synthetic | public data | ParkinSense hardware | clinical.
"""

STATUSES = ["Implemented", "Bench-tested", "Partial", "In development", "Planned", "Future"]

# id, capability, status, tests, synthetic, public, hardware, clinical
ROWS = [
    ("C1", "BLE protocol v1 decode (fw v4)", "Bench-tested", 2, 2, 0, 2, 0),
    ("C2", "BLE protocol v2 + fw 5.0.0", "Implemented", 2, 2, 0, 0, 0),
    ("C3", "Tremor v3 (PSD + HMM)", "Implemented", 2, 2, 0, 0, 0),
    ("C4", "Motion context + tremor guard", "Implemented", 2, 2, 0, 0, 0),
    ("C5", "PPG 2.0: finger, SQI, heart rate", "Implemented", 2, 2, 0, 1, 0),
    ("C6", "HRV (RMSSD, SDNN, pNN50)", "Implemented", 2, 2, 0, 0, 0),
    ("C7", "SpO2 ratio-of-ratios", "Partial", 2, 1, 0, 0, 0),
    ("C8", "Steps v1.1 (default)", "Implemented", 2, 2, 2, 0, 0),
    ("C9", "Steps gated 3.0-dev (opt-in)", "Partial", 2, 0, 2, 0, 0),
    ("C10", "Sleep/wake 1.0 (offline)", "Implemented", 2, 2, 2, 0, 0),
    ("C11", "Wear monitor 1.0 (opt-in)", "Partial", 2, 2, 1, 0, 0),
    ("C12", "Runtime, recording, replay", "Implemented", 2, 2, 0, 1, 0),
    ("C13", "Dashboard (live + history)", "Implemented", 2, 2, 0, 1, 0),
    ("C14", "Personal baselines", "Implemented", 2, 0, 0, 0, 0),
    ("C15", "Power and battery life", "In development", 0, 0, 0, 0, 0),
    ("C16", "Overnight recording", "In development", 0, 0, 0, 0, 0),
    ("C17", "Tremor on PD@Home; FoG on Daphnet", "In development", 0, 0, 0, 0, 0),
    ("C18", "Mobile app, product UI, cloud", "Planned", 0, 0, 0, 0, 0),
    ("C19", "Bradykinesia, dyskinesia, ML models", "Future", 0, 0, 0, 0, 0),
    ("C20", "Patient pilot, clinical validation", "Future", 0, 0, 0, 0, 0),
]
COLS = ["Tests", "Synthetic", "Public data", "Hardware", "Clinical"]
