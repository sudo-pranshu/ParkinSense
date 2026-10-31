# ParkinSense BLE protocol

Host implementation: `parkinsense/protocol/packet.py` (the only host-side parser).
Device implementation: `firmware/parkinsense_wearable/packet.h` (v2), `firmware/legacy/ble_stream_v4` (v1).

## GATT

| Item | UUID | Notes |
|---|---|---|
| Service | `ABCD1234-0000-467A-9538-01F0652C74E0` | unchanged |
| Data characteristic (notify, 244 B max) | `ABCD1234-0001-467A-9538-01F0652C74E0` | one packet per notification |
| Device Information → Firmware Revision | `0x2A26` | v2 firmware (5.0.0+) only; the host records it as `firmware_version` |

Advertised name: `ParkinSense`. Firmware requests a 7.5–15 ms connection interval (v2) and a 247-byte ATT MTU.

## Framing (identical in v1 and v2)

All fields little-endian, packed. 208 bytes per packet = 8-byte header + 10 × 20-byte samples.

```
Header  <BBHI
  u8   version          1 or 2 — the host dispatches on this; unknown versions are rejected
  u8   flags            v1: always 0 · v2: bitfield below
  u16  seq / reserved   v1: always 0 · v2: packet sequence number, wraps 65535 → 0
  u32  timestamp_us     device micros() at sample 0 of the batch; wraps every 71 min 35 s

Sample  <hhhhhhII  (×10)
  i16  ax ay az         wire counts, see scale table
  i16  gx gy gz
  u32  ir red           MAX30102 18-bit ADC counts (most recent PPG sample at this slot)
```

Per-sample time is reconstructed as `timestamp_us + i × 9615 µs`. The host unwraps the 32-bit
counter to 64 bits (`TimestampUnwrapper`) and estimates the true device sample rate from
consecutive header timestamps.

## Version differences

| | v1 (firmware ≤ ble_stream_v4) | v2 (parkinsense_wearable 5.x) |
|---|---|---|
| Accel wire scale | 8192 counts/g (±4 g) | 8192 counts/g (±4 g) |
| Gyro wire scale | 131 counts/dps (±250 dps) | **64 counts/dps (±512 dps)** |
| IMU configured range | not applied: driver default ±16 g / ±2000 dps, 416 Hz ODR | ±4 g / ±500 dps, 104 Hz ODR |
| Out-of-range values | wrap (int16 overflow, sign flips) | saturate + flag |
| PPG content per slot | one sample per 100 ms (10 Hz, no anti-alias), held | newest FIFO sample (~100 Hz), held |
| Sequence number | none | yes |
| Flags | none | yes |
| Firmware version | not readable | Device Information Service |

v1 data are decoded with v1 scales forever — the host never reinterprets an old recording with
new scales. v1 gyro samples at |value| ≥ 0.99 × full scale are marked `possibly_clipped`;
values that wrapped on the device cannot be recovered.

## v2 flags

| Bit | Name | Meaning |
|---|---|---|
| 0 | `ACCEL_CLIPPED` | an accel sample in this packet hit full scale |
| 1 | `GYRO_CLIPPED` | a gyro sample hit full scale |
| 2 | `IMU_FAULT` | IMU not ready / read failed; IMU fields are zero |
| 3 | `PPG_FAULT` | MAX30102 not ready; ir/red not valid |
| 4 | `PPG_STALE` | at least one slot repeated the previous PPG sample (100 vs 104 Hz) |
| 5 | `PREV_NOTIFY_FAILED` | the previous packet's `notify()` was rejected by the stack |
| 6 | `TIME_DISCONTINUITY` | the scheduler skipped intervals; per-sample times are approximate |

## Host integrity checks

Every capture row and `metadata.json` carries: packets lost (v2 sequence), timestamp gaps and
estimated missing samples (all versions), timestamp wraps and backward steps, measured device
rate and `rate_status` (`OK` ≤ 2 %, `WARN` ≤ 5 %, `INVALID` > 5 % from 104 Hz). A gap longer
than 0.5 s resets all windowed state so no analysis window spans a discontinuity.

## Compatibility rules

1. Framing (208 bytes, field order) never changes within a major protocol.
2. New meaning is introduced only with a new `version` value and a host decoder branch.
3. The host keeps decoders for every version ever shipped.
