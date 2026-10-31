"""
ParkinSense BLE packet protocol -- decoder, encoder and stream integrity.

Authoritative specification: docs/protocol/BLE_PROTOCOL.md. This module
is the single host-side implementation; nothing else may parse packets.

Wire format (little-endian, packed) -- identical framing in v1 and v2:

    header  <BBHI   version:u8  flags:u8  seq_or_reserved:u16  timestamp_us:u32
    sample  <hhhhhhII  ax ay az gx gy gz (i16 counts)  ir red (u32 ADC counts)
    packet  = header + 10 samples = 208 bytes

Version differences (never silently reinterpreted -- dispatch on `version`):

    field             v1 (firmware <= ble_stream_v4)   v2 (parkinsense_wearable)
    seq_or_reserved   always 0                         packet sequence number (wraps 65535->0)
    flags             always 0                         PacketFlags bitfield
    accel scale       8192 counts/g  (+-4 g)           8192 counts/g  (+-4 g)
    gyro scale        131 counts/dps (+-250 dps)       64 counts/dps  (+-512 dps)
    IMU range applied no  (driver defaults +-16 g/2000) yes (+-4 g / +-500 dps, ODR 104 Hz)
    PPG per slot      10 Hz, decimated, ZOH            ~100 Hz, newest FIFO sample, ZOH

v1 gyro values beyond +-250 dps wrapped on the device (int16 overflow) and
cannot be recovered; `decode` flags any v1 sample whose magnitude is within
1 % of full scale as possibly clipped.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from enum import IntFlag

HEADER_FORMAT = "<BBHI"
SAMPLE_FORMAT = "<hhhhhhII"
HEADER_SIZE = struct.calcsize(HEADER_FORMAT)    # 8
SAMPLE_SIZE = struct.calcsize(SAMPLE_FORMAT)    # 20
BATCH_SIZE = 10
PACKET_SIZE = HEADER_SIZE + BATCH_SIZE * SAMPLE_SIZE  # 208

NOMINAL_SAMPLE_RATE_HZ = 104.0
# Firmware sample interval (SAMPLE_INTERVAL_US = 9615 -> 104.004 Hz).
SAMPLE_PERIOD_US = 9615

TIMESTAMP_MODULUS = 1 << 32
SEQ_MODULUS = 1 << 16


class PacketFlags(IntFlag):
    NONE = 0
    ACCEL_CLIPPED = 1 << 0        # at least one accel sample hit int16 full scale
    GYRO_CLIPPED = 1 << 1         # at least one gyro sample hit int16 full scale
    IMU_FAULT = 1 << 2            # IMU not ready; IMU fields are zero
    PPG_FAULT = 1 << 3            # MAX30102 not ready; ir/red are zero
    PPG_STALE = 1 << 4            # >=1 slot repeated the previous PPG sample
    PREV_NOTIFY_FAILED = 1 << 5   # firmware's previous notify() was rejected
    TIME_DISCONTINUITY = 1 << 6   # scheduler skipped intervals inside this packet


@dataclass(frozen=True)
class ScaleSpec:
    accel_counts_per_g: float
    gyro_counts_per_dps: float


SCALES = {
    1: ScaleSpec(8192.0, 131.0),
    2: ScaleSpec(8192.0, 64.0),
}
SUPPORTED_VERSIONS = tuple(SCALES)
INT16_CLIP = 32767 * 0.99


class ProtocolError(ValueError):
    pass


@dataclass(frozen=True)
class Sample:
    """One decoded IMU+PPG sample in physical units."""
    device_time_us: int        # 64-bit, unwrapped, nominal per-sample time
    ax: float
    ay: float
    az: float
    gx: float
    gy: float
    gz: float
    ir: int
    red: int
    index_in_packet: int
    possibly_clipped: bool


@dataclass(frozen=True)
class Packet:
    version: int
    flags: int
    seq: int | None            # None for v1 (field reserved)
    timestamp_us_raw: int      # 32-bit as transmitted
    samples: tuple[Sample, ...]


def decode(data: bytes, unwrapper: "TimestampUnwrapper | None" = None) -> Packet:
    """Decode one notification payload. Raises ProtocolError on any mismatch."""
    if len(data) != PACKET_SIZE:
        raise ProtocolError(f"packet is {len(data)} bytes, expected {PACKET_SIZE}")
    version, flags, seq, ts = struct.unpack_from(HEADER_FORMAT, data, 0)
    if version not in SCALES:
        raise ProtocolError(f"unsupported packet version {version}")
    scale = SCALES[version]
    t0 = unwrapper.unwrap(ts) if unwrapper is not None else ts
    out = []
    off = HEADER_SIZE
    for i in range(BATCH_SIZE):
        ax, ay, az, gx, gy, gz, ir, red = struct.unpack_from(SAMPLE_FORMAT, data, off)
        off += SAMPLE_SIZE
        clipped = any(abs(v) >= INT16_CLIP for v in (ax, ay, az, gx, gy, gz))
        out.append(Sample(
            device_time_us=t0 + i * SAMPLE_PERIOD_US,
            ax=ax / scale.accel_counts_per_g,
            ay=ay / scale.accel_counts_per_g,
            az=az / scale.accel_counts_per_g,
            gx=gx / scale.gyro_counts_per_dps,
            gy=gy / scale.gyro_counts_per_dps,
            gz=gz / scale.gyro_counts_per_dps,
            ir=ir, red=red, index_in_packet=i, possibly_clipped=clipped,
        ))
    return Packet(version, flags, seq if version >= 2 else None, ts, tuple(out))


def _sat16(v: float) -> int:
    # round-to-nearest: makes encode() the exact inverse of decode() for
    # replayed values; saturates like protocol-v2 firmware.
    return int(max(-32768, min(32767, round(v))))


def encode(samples, timestamp_us: int, version: int = 1, seq: int = 0, flags: int = 0) -> bytes:
    """
    Build one packet from 10 (ax, ay, az, gx, gy, gz, ir, red) tuples in
    physical units. Rounds to the nearest count and
    saturates (v2 firmware saturates; v1 firmware wrapped -- see module doc).
    Used by replay, tests and benchmarks.
    """
    if len(samples) != BATCH_SIZE:
        raise ValueError("encode() needs exactly BATCH_SIZE samples")
    scale = SCALES[version]
    hdr_seq = seq % SEQ_MODULUS if version >= 2 else 0
    hdr_flags = flags if version >= 2 else 0
    buf = bytearray(struct.pack(HEADER_FORMAT, version, hdr_flags, hdr_seq,
                                int(timestamp_us) % TIMESTAMP_MODULUS))
    for ax, ay, az, gx, gy, gz, ir, red in samples:
        a = [_sat16(v * scale.accel_counts_per_g) for v in (ax, ay, az)]
        g = [_sat16(v * scale.gyro_counts_per_dps) for v in (gx, gy, gz)]
        buf += struct.pack(SAMPLE_FORMAT, *a, *g, int(ir) & 0xFFFFFFFF, int(red) & 0xFFFFFFFF)
    return bytes(buf)


class TimestampUnwrapper:
    """
    Extends the device's 32-bit micros() (wraps every 71 min 35 s) to a
    monotonic 64-bit count. A backwards step of more than half the modulus
    is a wrap; a small backwards step is a genuine reordering/reset and is
    reported via `backward_steps` rather than silently "fixed".
    """

    def __init__(self) -> None:
        self._last_raw: int | None = None
        self._offset = 0
        self.wraps = 0
        self.backward_steps = 0

    def reset(self) -> None:
        self.__init__()

    def unwrap(self, raw: int) -> int:
        if self._last_raw is not None and raw < self._last_raw:
            if self._last_raw - raw > TIMESTAMP_MODULUS // 2:
                self._offset += TIMESTAMP_MODULUS
                self.wraps += 1
            else:
                self.backward_steps += 1
        self._last_raw = raw
        return raw + self._offset


class SequenceTracker:
    """Counts lost / duplicated / reordered packets from v2 sequence numbers."""

    def __init__(self) -> None:
        self.expected: int | None = None
        self.received = 0
        self.lost = 0
        self.duplicates_or_reordered = 0

    def reset(self) -> None:
        self.__init__()

    def update(self, seq: int | None) -> int:
        """Returns the number of packets lost immediately before this one."""
        self.received += 1
        if seq is None:
            return 0
        gap = 0
        if self.expected is not None:
            d = (seq - self.expected) % SEQ_MODULUS
            if d == 0:
                pass
            elif d < SEQ_MODULUS // 2:
                gap = d
                self.lost += d
            else:
                self.duplicates_or_reordered += 1
        self.expected = (seq + 1) % SEQ_MODULUS
        return gap

    @property
    def loss_fraction(self) -> float:
        total = self.received + self.lost
        return self.lost / total if total else 0.0


class GapDetector:
    """
    Version-agnostic loss detection from device timestamps: works for v1
    recordings that carry no sequence number. A packet whose first sample is
    more than 1.5 sample periods after the previous packet's last sample
    marks a gap.
    """

    def __init__(self, tolerance_periods: float = 1.5) -> None:
        self.tol = tolerance_periods * SAMPLE_PERIOD_US
        self._last_us: int | None = None
        self.gaps = 0
        self.missing_samples_est = 0

    def reset(self) -> None:
        self.__init__(self.tol / SAMPLE_PERIOD_US)

    def update(self, first_us: int, last_us: int) -> float:
        """Returns the gap duration in seconds (0.0 if contiguous)."""
        gap_s = 0.0
        if self._last_us is not None:
            dt = first_us - self._last_us
            if dt > self.tol + SAMPLE_PERIOD_US:
                self.gaps += 1
                missing = round(dt / SAMPLE_PERIOD_US) - 1
                self.missing_samples_est += max(0, missing)
                gap_s = dt / 1e6
        self._last_us = last_us
        return gap_s
