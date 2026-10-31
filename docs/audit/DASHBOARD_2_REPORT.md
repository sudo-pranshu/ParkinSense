# Dashboard 2.0 — engineering report

Scope: the dashboard, the runtime's live interface and the launch experience on
`transform/engineering-overhaul`. The processing pipeline (RuntimeEngine, protocol v1/v2,
SessionRecorder, capture schema v3, tremor v3, PPG, steps, quality semantics, analytics) is
unchanged: the golden regression outputs still match and every pre-existing test passes.

## 1. Decision: keep Dash

| Option | Verdict |
|---|---|
| Dash (Plotly) | **kept.** Python-only, already a dependency, Plotly gives research-grade interactive charts (zoom, hover, PNG export) for free, and the bottleneck was the data path, not the framework. |
| FastAPI + React/Vite SPA | better UI ceiling, but adds a Node toolchain and a second language to a research codebase; not justified by any measured limitation. |
| Streamlit | re-runs the whole script per interaction; poor fit for 2 Hz live updates. |

The data path was rebuilt instead (§2). Dash 4 deprecates `dash_table.DataTable` in favour of AG
Grid in a future major version; four tables use it today (a contained change when needed).

## 2. Architecture: before → after

| | 3.0.0 baseline dashboard | Dashboard 2.0 |
|---|---|---|
| Live data | re-parse the last 2.5 MB of `capture.csv` every 100 ms | runtime `GET /live?since_sample&since_analysis` (incremental, sequence-numbered); dashboard `LiveFeed` thread keeps bounded buffers; callbacks read memory only |
| Runtime unreachable | showed the last file values (no indication) | *Runtime offline* banner; values from the metrics file shown muted and *Stale* |
| No new data | indistinguishable from live | data age in the status bar; > 3 s → amber, every card *Stale* |
| Simulated / replayed data | not possible live | `--simulate`, `--replay CSV`; banner on every page; `device.source` recorded |
| Pages | one | seven: Overview, Live monitoring, Tremor analytics, Cardiovascular, Activity, Sessions, Data & research |
| History | none | any recording or replay: browse, metadata, integrity, charts, episodes, comparison, export |
| Session control | none | start / stop from the UI (`POST /session/{start,stop}`) |
| Quality states | text suffix on some cards | badge on every card, hollow markers in every chart, shaded artefact / no-contact periods, legend |
| Missing values | some cards printed `0` | always `—` (tested) |
| SpO₂ | labelled estimate | permanent *uncalibrated estimate* badge + page disclaimer; never next to clinical values |
| Algorithms in the UI | none | none: session summaries via `parkinsense.analytics`; PSD of a recorded window via `motion.features.gyro_spectrum`; replay and datasets via the CLIs in a subprocess |
| Process model | separate | separate, independently restartable, dashboard resynchronises on runtime restart |

## 3. Measurements

`python -m benchmarks.dashboard_bench --minutes 60 --legacy <3.0.0 dashboard.py> --full-reread`
on the development container (Python 3.13, pandas 3.1, numpy 2.5, Dash 4.5, Plotly 7.1). The
recording is a 60-minute simulated protocol-v2 session written by the real engine and recorder
(198.5 MB, 7 193 analysis windows). Raw numbers: [`benchmarks/results/dashboard_60min.json`](../../benchmarks/results/dashboard_60min.json).
Server-side Python cost only; browser rendering time was not measured.

### Live path (per update, at the 60-minute mark)

| | Before | After |
|---|---|---|
| develop `dashboard_v2` approach: full `read_csv` of the capture per tick | 3 686 ms every 100 ms tick (cannot keep up) | — |
| 3.0.0 dashboard `update_dashboard` (tail read + parse + figures) | 81 ms every **100 ms** tick (≈ 80 % of a core) | — |
| incremental `/live` poll (in-process, no HTTP) | — | 1.7 ms every 0.4 s |
| Overview callback | — | 28 ms every 1 s |
| Live-monitoring callback (5 charts, 10 s raw + 2 min trends) | — | 48 ms every 0.5 s |
| cost grows with session length | yes (develop) / no (3.0.0) | no — all buffers fixed size |

Live buffers after 60 minutes: runtime 6 240 samples (60 s) and 1 200 analyses; dashboard
3 120 samples (30 s) and 1 200 analyses. These are the maxima; they were full and did not grow.

### History path (60-minute session)

| | Value |
|---|---|
| first load of the analysis rows (chunked, `usecols`) | 1.8 s |
| repeat load (cache keyed by path, size, mtime) | < 0.1 ms |
| Tremor / Cardiovascular / Activity figures | 168 / 196 / 145 ms |
| click a window → its PSD (sparse line index, after first use) | 15 ms (first click builds the index: ≈ 130 ms) |
| dashboard process peak memory (max RSS), 60-min session open on every page | 257 MB, of which 167 MB is the process after importing Dash/Plotly/pandas; the session's analysis frame is 5.3 MB |

### Optimisations made during the work (measured)

| Change | Effect |
|---|---|
| figure styling moved into a registered Plotly template instead of `update_layout` per figure | figure construction 17 → 1.3 ms; Live callback 132 → 37 ms (2-min session) |
| interval shading as one filled trace on a hidden overlay axis instead of one shape per interval | Cardiovascular figures, 60-min session: 939 → 196 ms |
| raw-window access by sparse byte-offset index instead of `skiprows` | PSD click, row 300 000: 437 → 15 ms |
| analysis-row chunk size 200 000 → 20 000 rows | load 2.5 → 1.8 s; peak memory 577 → 159 MB |
| intervals merged when < 1 s apart, each window drawn ± half a hop | single flagged windows visible; hundreds of slivers avoided |

## 4. Features preserved

Every card and graph of the 3.0.0 dashboard is still available: status, P(tremor), tremor
state, frequency, amplitude, data quality, motion context, steps, cadence, walking state, heart
rate, SpO₂ (estimate), finger contact (Overview); tremor score, rest index, band ratio, best axis,
distance, active minutes (Overview → Signal details); live gyroscope (Live monitoring); HR/SpO₂ and
cadence trends (Overview, Cardiovascular, Activity). The tremor-score gauge is replaced by the
P(tremor) trend plus the numeric score, because the score is per-window evidence and its old
colour zones implied a severity scale that does not exist. `/metrics` and `/health` are
unchanged; `read_tail` is still exported.

## 5. Launch experience

| | Before | After |
|---|---|---|
| install | manual venv + `pip install -e` | `./setup.sh` (reuses or creates `.venv`; never deletes one without `--recreate`) |
| run | two commands in two activated shells | `./start_parkinsense.sh [--simulate]`, or `./start_runtime.sh` + `./start_dashboard.sh`; no activation |
| checks | environment, ports, duplicates: none | Python ≥ 3.10, required modules per component, port in use, one runtime/dashboard per checkout (pid files verified against the process) |
| shutdown | Ctrl+C per terminal | one Ctrl+C: runtime gets SIGINT first (session finalised, metadata COMPLETE), then the dashboard; tested |
| logs | terminal only | `./logs/runtime_<time>.log`, `./logs/dashboard_<time>.log` |
| other | — | `./check.sh` (CI locally), `./replay.sh`, `./clean.sh` (dry run by default; never touches data) |

Verified end to end in a fresh copy of the repository: `./setup.sh` created `.venv` and installed
all extras from PyPI, then `./check.sh` passed every step (lint, pytest, benchmark smoke, firmware
host tests, doc links) with the newest dependency versions (pandas 3.1, numpy 2.5, Dash 4.5).

## 6. Tests

| | Before | After |
|---|---|---|
| `pytest` | 64 passed | 84 passed, 1 deselected (hardware) |
| dashboard | 1 test (old callback) | 10: LiveState incremental and bounded; LiveFeed against a real uvicorn server, then the server stops (offline + stale); session reset; session store read-only (SHA-256 unchanged); all pages build; figures with and without data; offline rendering shows `—`, not `0`; decimation keeps extremes; `read_tail` compatibility |
| launchers | none | 11: help and usage error for all 7 scripts; missing environment; port conflict; full `start_parkinsense.sh --simulate` cycle (health, dashboard HTML, duplicate runtime refused, `/live` data, Ctrl+C → exit 0, metadata COMPLETE, pid files removed, ports released); `clean.sh` dry run |
| browser | none | Playwright run of all seven pages against a simulated runtime: 0 console errors, 0 HTTP errors (development check, not in CI) |

Golden regression outputs: unchanged (the tests pass without regenerating `golden.json`).

## 7. Not done / limitations

* **No hardware run.** The dashboard was exercised with simulated and replayed streams only;
  BLE behaviour (reconnects, real packet loss) is covered by the runtime's existing tests, not
  by a dashboard test on a device.
* **Browser cost not measured.** The numbers above are server-side. Line charts are decimated for
  display (min/max preserving, ≤ 4 000 points per trace; quality scatter plots are not), but browser rendering
  of the 60-minute history pages was not timed.
* **Multi-hour recordings.** History loading is linear in file size (≈ 1.8 s per hour of data);
  a 24-hour file would take ≈ 45 s on first open. A columnar sidecar (Parquet) written by the
  recorder would remove this; it is a schema decision and was not made here.
* **RR intervals** are not in capture schema v3, so no inter-beat-interval chart exists; the
  page says so.
* **No authentication** on the API; launchers bind `127.0.0.1` by default.
* **Windows** needs WSL for the shell scripts; the `python -m …` commands work natively.
* `config.STEP_COUNTER_VERSION` still reads "2.0" while the default counter is v1.1 (known
  provenance bug, awaiting a decision because changing it alters recorded metadata).
