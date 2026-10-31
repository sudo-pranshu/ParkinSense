# Installation and quick start

## 1. What you need

| Item | Purpose |
|---|---|
| Seeed XIAO nRF52840 Sense + MAX30102 + Li-ion cell | the wearable ([hardware](../hardware/HARDWARE.md)) |
| USB-C cable | flashing, charging |
| Computer with Bluetooth LE (macOS, Linux or Windows) | runtime, dashboard |
| Python ≥ 3.10 | runtime (CI tests 3.10 and 3.12) |
| Arduino IDE 2.x | firmware |

No hardware? Everything except live acquisition works on the bundled recordings and synthetic
data (sections 4–6).

## 2. Python

```bash
git clone https://github.com/sudo-pranshu/ParkinSense.git
cd ParkinSense
git checkout transform/engineering-overhaul
./setup.sh                                              # creates or reuses ./.venv, installs all extras
./check.sh --quick                                      # expect: 84 passed, 1 deselected
```

`setup.sh` reuses an active venv, `./.venv` or `./venv` and never deletes one unless you pass
`--recreate`. The launch scripts find that environment themselves; no activation is needed.

Windows (no bash): use WSL, or the manual route below and the `python -m …` commands shown in
each section.

```bash
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -e ".[live,dashboard,dev]"
pytest
```

`requirements.txt` lists the same dependencies for environments that cannot install in editable
mode.

## 3. Firmware

Use **v4** (`firmware/legacy/ble_stream_v4/`) for data collection today; it is the last build
verified on hardware. **v5** (`firmware/parkinsense_wearable/`) adds protocol v2 but has not been
built for the board yet — flashing it is test H0. Step-by-step instructions, board package and
libraries: [firmware](../firmware/FIRMWARE.md#build-and-flash-v5). The host decodes both.

Place a finger over the MAX30102: both firmware versions stream only while a finger is detected.

## 4. Record a session

```bash
./start_parkinsense.sh                                   # runtime + dashboard (v5 reports its firmware version)
./start_parkinsense.sh -- --firmware-version 4           # with v4, record it explicitly
./start_runtime.sh                                       # runtime only (= python -m parkinsense.runtime.app)
```

Expected log lines (from `runtime/app.py`):

```text
INFO parkinsense.app: scanning for ParkinSense ...
INFO parkinsense.app: connected: <address>
INFO parkinsense.app: recording to recordings/<YYYYmmdd_HHMMSS>_<id> (firmware <version>)
```

Ctrl-C ends the session cleanly (`metadata.json` status `COMPLETE`). After a disconnect the app
reconnects into a new session. Files: [runtime and recording](../runtime/RUNTIME_AND_RECORDING.md).

## 5. Dashboard

```bash
./start_dashboard.sh          # http://127.0.0.1:8050  (= python -m parkinsense.visualization.dashboard)
```

The dashboard runs with or without the runtime and can be restarted at any time. Live data is
also served at `http://127.0.0.1:8000/live` and `/metrics`. See
[dashboard and API](../software/DASHBOARD_AND_API.md); problems:
[troubleshooting](TROUBLESHOOTING.md).

## 6. Without hardware

```bash
# the whole live stack on a synthetic stream (labelled SIMULATED everywhere)
./start_parkinsense.sh --simulate

# replay a bundled real recording through the full pipeline
parkinsense-replay data/reference/ble_v1_104hz/parkinsense_20260630_123551.csv --out replays/demo

# legacy 23 Hz logs need resampling
parkinsense-replay data/reference/legacy_serial_23hz/walking_60s.csv --resample

# build a dataset and summarise a session
parkinsense-dataset data/reference/ble_v1_104hz/*.csv --out datasets/demo --version 0.1.0
python -c "import pandas as pd; from parkinsense.analytics.biomarkers import session_report as r; print(r(pd.read_csv('replays/demo/capture.csv', low_memory=False)))"

# reproduce the synthetic benchmarks
python -m benchmarks.run_benchmarks --impl current --out benchmarks/results/current.json
```

For the 87 s BLE recording, `session_report` returns `tremor_time_pct: None` with the reason
"only … min of still, valid data (< 10.0)" — aggregates refuse to report on too little data.

## 7. Troubleshooting

See [troubleshooting](TROUBLESHOOTING.md): launch scripts, ports, environment, BLE, signal
quality, dashboard states, replay.
