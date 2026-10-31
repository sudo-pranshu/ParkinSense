// Host unit tests for firmware/parkinsense_wearable/packet.h.
//   g++ -std=c++17 -Wall -Wextra -Werror -I firmware/parkinsense_wearable firmware/tests/test_packet.cpp -o /tmp/t
#include <cassert>
#include <cmath>
#include <cstdio>
#include <cstring>
#include "packet.h"

static void put16(uint8_t *b, int i, int16_t v) { b[2 * i] = v & 0xFF; b[2 * i + 1] = (v >> 8) & 0xFF; }

int main() {
  // 1. layout is the 208-byte wire contract
  static_assert(sizeof(ps::Packet) == 208, "size");

  // 2. scaling: raw LSM6DS3 counts -> wire counts
  uint8_t raw[12];
  put16(raw, 0, 5714);            // gyro x: 5714 * 17.5 mdps = 99.995 dps
  put16(raw, 1, -5714);
  put16(raw, 2, 0);
  put16(raw, 3, 8197);            // accel x: 8197 * 0.122 mg = 1.000 g
  put16(raw, 4, 0);
  put16(raw, 5, -8197);
  ps::Sample s{};
  uint8_t flags = 0;
  ps::packImu(raw, s, flags);
  assert(std::abs(s.gx / ps::GYRO_COUNTS_PER_DPS - 99.995f) < 0.02f);
  assert(s.gy == -s.gx);
  assert(std::abs(s.ax / ps::ACCEL_COUNTS_PER_G - 1.0f) < 0.002f);
  assert(flags == 0);

  // 3. sensor full scale (+-500 dps raw) fits the +-512 dps wire range without clipping
  put16(raw, 0, 28571);           // 499.99 dps
  flags = 0;
  ps::packImu(raw, s, flags);
  assert(!(flags & ps::FLAG_GYRO_CLIPPED));
  assert(std::abs(s.gx / ps::GYRO_COUNTS_PER_DPS - 499.99f) < 0.05f);

  // 4. sensor at its own rail -> flagged, value saturates with correct sign
  put16(raw, 1, -32768);
  flags = 0;
  ps::packImu(raw, s, flags);
  assert(flags & ps::FLAG_GYRO_CLIPPED);
  assert(s.gy < 0);

  // 5. saturation never wraps
  bool c = false;
  assert(ps::sat16(1e6f, c) == 32767 && c);
  c = false;
  assert(ps::sat16(-1e6f, c) == -32768 && c);

  // 6. scheduler: fixed cadence, bounded catch-up with discontinuity report
  ps::Scheduler sc = {9615, 1000, 5};
  bool d = false;
  assert(sc.due(500, d) == 0);
  assert(sc.due(1000, d) == 1 && sc.next_us == 1000 + 9615 && !d);
  assert(sc.due(1000 + 9615 * 3, d) == 1 && !d);          // late but within catch-up
  assert(sc.due(1000 + 9615 * 50, d) == 1 && d);          // long stall -> snap + flag
  // micros() wrap
  ps::Scheduler w = {9615, 0xFFFFFF00u, 5};
  d = false;
  assert(w.due(0x00000010u, d) == 1 && !d);

  std::puts("firmware packet tests: OK");
  return 0;
}
