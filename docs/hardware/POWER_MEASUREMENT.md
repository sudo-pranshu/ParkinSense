# Power measurement guide (Nordic PPK2)

**No current measurement exists for any ParkinSense firmware.** Earlier figures (~7 mA, µA sleep, ~100 h) are not
supported (audit A-P0-4). Nothing in this repository may claim a power improvement or a battery life until the tables
at the bottom are filled from real measurements made with this procedure.

Instrument: Nordic Power Profiler Kit II (PPK2) or an equivalent with ≤ 1 µA resolution at low currents and
≥ 100 kSa/s. Nordic's documentation for the PPK2 was not re-fetched in this phase; confirm the mode and wiring steps
against it before measuring.

## 1. Setup (record every item with the results)

| Item | Requirement |
|---|---|
| Device | board serial, firmware version and **profile** (A finger-gated / B continuous), sensor wiring photo, enclosure on/off |
| Supply | PPK2 **source-meter mode** at the battery input of the board at 3.7 V (the nominal Li-ion level); USB **disconnected**, so the measurement is not hidden behind USB power. State the voltage used. Repeat one scenario at 3.3 V and 4.1 V to show supply sensitivity |
| Battery assumption for life estimates | README lists a 3.7 V 700 mAh pack (902035), **not re-verified**. Use 80 % of nominal usable capacity unless the pack is measured. State both numbers |
| Host | BLE central model/OS, distance (1 m, line of sight), `parkinsense-live` version, connection interval actually negotiated |
| Environment | temperature, finger/wrist/table condition per scenario, ambient light (the optical sensor is light-sensitive) |
| Sampling | PPK2 at its maximum sample rate; export raw CSV; keep the raw file |
| Comparison | v4 (`firmware/legacy/ble_stream_v4`) and v5 measured **back to back on the same board, wiring, supply and host** |

Bring up the board first with H0–H3 so measurements are of a working device.

## 2. Scenarios (programme list)

Each scenario ≥ 5 min after a 60 s settling period, except S7.

| ID | Scenario | State to hold | Notes |
|---|---|---|---|
| S1 | Worn, IMU and PPG active | finger on sensor (profile A) or wrist worn with contact (B); BLE connected, streaming 104 Hz | the reference research mode |
| S2 | Worn, IMU active, PPG unavailable | profile B, sensor window covered or finger off, wrist moving; BLE connected | proves IMU/PPG independence |
| S3 | Removed, low-power mode | **only after a low-power mode exists** (needs the §2 sensor in the architecture doc). Until then measure "idle, no finger" in profile A as the only available proxy and **label it as such** | do not call this REMOVED mode |
| S4 | BLE connected | streaming vs idle, same profile | separate radio from sensor cost with S5 |
| S5 | BLE disconnected | advertising, streaming or idle as in S4 | |
| S6 | Reconnection | disconnect (host side) → advertising → reconnect → resume; ≥ 20 cycles | integrate charge over each cycle; report mean ± SD of overhead per reconnection in µAh and seconds to first packet |
| S7 | Long-duration acquisition | ≥ 8 h in profile B with realistic connection; log total charge and the capture's completeness (`metadata.json` integrity block) | also the overnight dry-run; needed for any battery-life statement |

## 3. Metrics to report per scenario

Mean, median, 5th/95th percentile and maximum current (mA); charge per hour (mAh/h); for S6 µAh per reconnection;
for S7 total mAh and capture completeness. Include a plot of the first 10 s to show the connection-event structure.
Statistical statement: number of runs (≥ 3 for S1–S5) and their spread.

## 4. Battery-life statement (only after S1–S7 are measured)

`hours = usable_mAh / mean_mA` for a named profile (e.g. "16 h worn at S1 + 8 h removed at S3"). Always print the
capacity assumption and the profile next to the number. Never quote life from a short run, and never from the idle
scenario alone.

## 5. Comparisons the programme requires

Profile A vs B at S1/S2/idle; v4 vs v5 at S1; lever sweeps from the architecture document §7 (IMU ODR, BLE connection
interval, PPG on/off, advertising interval) **one change at a time** against S1.

## 6. Results log (empty — nothing has been measured)

| Date | Board | FW / profile | Scenario | Supply | Runs | Mean mA | p95 mA | mAh/h | Raw file | Notes |
|---|---|---|---|---|---|---|---|---|---|---|
| | | | | | | | | | | |
