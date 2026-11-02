# Troubleshooting

Logs from `./start_parkinsense.sh` are in `./logs/runtime_<time>.log` and
`./logs/dashboard_<time>.log`. Every script prints `--help`. Exit codes: `1` environment,
`2` usage, `3` port in use / already running, `4` a component failed to start.

## Launching

| Symptom | Cause / fix |
|---|---|
| `No Python environment found. Run ./setup.sh first` | no `./.venv`, `./venv` or active venv. Run `./setup.sh`, or point to an interpreter: `PARKINSENSE_PYTHON=/path/to/python ./start_parkinsense.sh` |
| `Missing Python packages for …: dash plotly` | the environment lacks an extra: `./setup.sh` (installs `live,dashboard,dev`) |
| `… is not Python ≥ 3.10` | create the venv with a newer interpreter: `./setup.sh --python python3.12 --recreate` |
| `venv creation failed` | Debian/Ubuntu: `sudo apt install python3-venv` |
| `port 8000 is already in use` | another runtime or program. Find it: `lsof -i :8000` (macOS/Linux). Or choose another port: `./start_parkinsense.sh --api-port 8010` (`./start_runtime.sh --port 8010` + `./start_dashboard.sh --api http://127.0.0.1:8010`) |
| `port 8050 is already in use` | `--dashboard-port 8060` / `./start_dashboard.sh --port 8060` |
| `runtime is already running (pid …)` | one runtime per checkout (two would fight over BLE). Stop it with Ctrl+C in its terminal or `kill -INT <pid>`. A pid file left by a crash is ignored automatically |
| `runtime failed to start` | the last 20 log lines are printed; the full log is in `./logs/` |
| `Permission denied: ./start_parkinsense.sh` | `chmod +x *.sh` (git preserves the bit; some zip downloads do not) |
| Windows | the scripts need bash: use WSL, or run `python -m parkinsense.runtime.app` and `python -m parkinsense.visualization.dashboard` directly |

## Wearable and BLE

| Symptom | Cause / fix |
|---|---|
| status `DEVICE_NOT_FOUND`, retries every 3 s | firmware not advertising, or no finger on the sensor (streaming is finger-gated); macOS: allow Bluetooth for your terminal app (System Settings → Privacy & Security → Bluetooth) |
| connects but no data | finger gate closed; serial monitor should show `finger detected -> streaming` |
| `rate_status` WARN / INVALID | device sample rate off nominal; frequency outputs are flagged; check the firmware build |
| `firmware_version` = `unknown` | v4 cannot report it: `./start_parkinsense.sh -- --firmware-version 4` |
| disconnects | the runtime reconnects into a **new** session; the previous one is finalised |

## Dashboard

| What you see | Meaning / fix |
|---|---|
| **Runtime offline** banner | dashboard cannot reach the API. Start the runtime, or check `--api` / `PARKINSENSE_API`. Values shown are the last ones written to disk, marked stale |
| amber status pill, every card *Stale* | the runtime is up but no packet for > 3 s (finger off, device out of range, session stopped) |
| **SIMULATED** / **REPLAY** banner | the data is not from the wearable. Recordings made this way have `device.source` = `simulated` / `replay` |
| `—` instead of a number | no valid value (missing is never shown as 0); the badge says why |
| hollow points in a chart | that window's quality state is not VALID |
| *Tremor time — insufficient data* | needs ≥ 2 min of still, valid windows live (10 min for a session summary) |
| *HRV withheld* | effective PPG rate < 25 Hz (firmware v4) |
| Sessions page empty | no recordings yet, or the dashboard was started from another folder: the scripts always run from the repository root; otherwise set `PARKINSENSE_RECORDINGS` |
| slow first open of a long session | first load parses the analysis rows (≈ 2.5 s for one hour); later opens are cached |

## Signal quality

| Symptom | Cause / fix |
|---|---|
| `hr_quality_state` `NO_CONTACT` / `INSUFFICIENT_DATA` | finger placement; HR needs ≥ 5 s of clean signal after the 1 s finger-on hysteresis |
| many `MOTION_ARTIFACT` windows | arm movement couples into PPG; values in those windows are not measurements |
| RMSSD always empty with v4 | expected: v4 delivers 10 Hz PPG; HRV is withheld below 25 Hz |

## Replay and data

| Symptom | Cause / fix |
|---|---|
| replay refuses a CSV | a ~23 Hz legacy log: add `--resample`; other formats: [replay](../datasets/REPLAY_AND_DATASETS.md#supported-inputs-auto-detected) |
| `… already exists (replays never overwrite)` | choose another `--out`; outputs are never overwritten |
| dataset job: `datasets/<version> already exists` | pick a new version; datasets are immutable once built |
| want to free disk space | `./clean.sh` lists caches and logs it would remove (`--yes` to delete). It never touches recordings, replays, datasets or the venv; delete those yourself |
