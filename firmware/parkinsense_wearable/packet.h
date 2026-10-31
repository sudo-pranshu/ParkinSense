// ParkinSense wire protocol v2 -- device side.
// Specification: docs/protocol/BLE_PROTOCOL.md. Host decoder:
// parkinsense/protocol/packet.py. The framing is identical to v1 (208 bytes);
// v2 gives meaning to `flags` and to the former `reserved` field (sequence
// number) and changes the gyro wire scale to 64 counts/dps (+-512 dps).
//
// This header is deliberately free of Arduino dependencies so its logic is
// unit-tested on the host (firmware/tests/test_packet.cpp, run in CI).
#pragma once
#include <stdint.h>
#include <math.h>

namespace ps {

constexpr uint8_t  PROTOCOL_VERSION      = 2;
constexpr uint8_t  BATCH_SIZE            = 10;
constexpr float    ACCEL_COUNTS_PER_G    = 8192.0f;   // +-4 g on the wire
constexpr float    GYRO_COUNTS_PER_DPS   = 64.0f;     // +-512 dps on the wire

// LSM6DS3 raw sensitivities for the configured ranges (datasheet DocID026899,
// Table 3): +-4 g -> 0.122 mg/LSB, +-500 dps -> 17.50 mdps/LSB.
constexpr float    ACCEL_G_PER_LSB_4G    = 0.000122f;
constexpr float    GYRO_DPS_PER_LSB_500  = 0.0175f;

enum Flags : uint8_t {
  FLAG_ACCEL_CLIPPED      = 1u << 0,
  FLAG_GYRO_CLIPPED       = 1u << 1,
  FLAG_IMU_FAULT          = 1u << 2,
  FLAG_PPG_FAULT          = 1u << 3,
  FLAG_PPG_STALE          = 1u << 4,
  FLAG_PREV_NOTIFY_FAILED = 1u << 5,
  FLAG_TIME_DISCONTINUITY = 1u << 6,
};

#pragma pack(push, 1)
struct Header {
  uint8_t  version;
  uint8_t  flags;
  uint16_t seq;          // v1: reserved (always 0)
  uint32_t timestamp_us; // micros() at the first sample of the batch
};
struct Sample {
  int16_t  ax, ay, az;
  int16_t  gx, gy, gz;
  uint32_t ir, red;
};
struct Packet {
  Header header;
  Sample samples[BATCH_SIZE];
};
#pragma pack(pop)

static_assert(sizeof(Header) == 8, "header must stay 8 bytes");
static_assert(sizeof(Sample) == 20, "sample must stay 20 bytes");
static_assert(sizeof(Packet) == 208, "packet must stay 208 bytes (fits one 244-byte notification)");

// Saturating float -> int16 with round-to-nearest. v1 firmware cast with
// (int16_t)(x), which wrapped beyond full scale (audit P0-3); saturation plus
// a flag keeps the sign and records that the value is a lower bound.
inline int16_t sat16(float v, bool &clipped) {
  float r = roundf(v);
  if (r >= 32767.0f)  { clipped = true; return 32767; }
  if (r <= -32768.0f) { clipped = true; return -32768; }
  return (int16_t)r;
}

// Convert one raw LSM6DS3 burst (OUTX_L_G .. OUTZ_H_XL, 12 bytes:
// gx gy gz ax ay az, little-endian int16) to wire counts.
inline void packImu(const uint8_t raw[12], Sample &s, uint8_t &flags) {
  int16_t g[3], a[3];
  for (int i = 0; i < 3; i++) {
    g[i] = (int16_t)(raw[2 * i] | (raw[2 * i + 1] << 8));
    a[i] = (int16_t)(raw[6 + 2 * i] | (raw[6 + 2 * i + 1] << 8));
  }
  bool ac = false, gc = false;
  s.ax = sat16(a[0] * ACCEL_G_PER_LSB_4G * ACCEL_COUNTS_PER_G, ac);
  s.ay = sat16(a[1] * ACCEL_G_PER_LSB_4G * ACCEL_COUNTS_PER_G, ac);
  s.az = sat16(a[2] * ACCEL_G_PER_LSB_4G * ACCEL_COUNTS_PER_G, ac);
  s.gx = sat16(g[0] * GYRO_DPS_PER_LSB_500 * GYRO_COUNTS_PER_DPS, gc);
  s.gy = sat16(g[1] * GYRO_DPS_PER_LSB_500 * GYRO_COUNTS_PER_DPS, gc);
  s.gz = sat16(g[2] * GYRO_DPS_PER_LSB_500 * GYRO_COUNTS_PER_DPS, gc);
  // The sensor's own full scale is also a clip, independent of wire scale.
  for (int i = 0; i < 3; i++) {
    if (a[i] == 32767 || a[i] == -32768) ac = true;
    if (g[i] == 32767 || g[i] == -32768) gc = true;
  }
  if (ac) flags |= FLAG_ACCEL_CLIPPED;
  if (gc) flags |= FLAG_GYRO_CLIPPED;
}

// Fixed-cadence scheduler with bounded catch-up. Returns the number of
// sample intervals that elapsed (0 = not yet due). If more than maxCatchup
// elapsed (e.g. a long BLE stall) it snaps forward and reports the
// discontinuity so the host knows reconstructed timestamps are approximate.
struct Scheduler {
  uint32_t interval_us;
  uint32_t next_us;
  uint8_t  max_catchup;
  uint32_t due(uint32_t now_us, bool &discontinuity) {
    int32_t late = (int32_t)(now_us - next_us);
    if (late < 0) return 0;
    uint32_t n = (uint32_t)late / interval_us + 1;
    if (n > max_catchup) { discontinuity = true; next_us = now_us + interval_us; return 1; }
    next_us += interval_us;
    return 1;
  }
  uint32_t remaining_us(uint32_t now_us) const {
    int32_t r = (int32_t)(next_us - now_us);
    return r > 0 ? (uint32_t)r : 0;
  }
};

}  // namespace ps
