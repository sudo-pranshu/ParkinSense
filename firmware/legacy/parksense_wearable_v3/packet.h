#pragma once

/*
 * ==========================================================
 * ParkinSense Wearable V3
 * BLE Packet Definition
 * ==========================================================
 */

#include <Arduino.h>

#include "config.h"

#pragma pack(push, 1)

/*
 * ----------------------------------------------------------
 * Packet Header
 * ----------------------------------------------------------
 *
 * version
 *     Packet format version.
 *
 * flags
 *     Sensor status flags.
 *
 * reserved
 *     Reserved for future use.
 *
 * timestamp_us
 *     Timestamp of the first sample.
 *
 */

struct PacketHeader
{
    uint8_t version;

    uint8_t flags;

    uint16_t reserved;

    uint32_t timestamp_us;
};

/*
 * ----------------------------------------------------------
 * One Wearable Sample
 * ----------------------------------------------------------
 */

struct SensorSample
{
    int16_t ax;
    int16_t ay;
    int16_t az;

    int16_t gx;
    int16_t gy;
    int16_t gz;

    uint32_t ir;

    uint32_t red;
};

/*
 * ----------------------------------------------------------
 * Complete BLE Packet
 * ----------------------------------------------------------
 */

struct WearablePacket
{
    PacketHeader header;

    SensorSample samples[BATCH_SIZE];
};

#pragma pack(pop)

/*
 * ----------------------------------------------------------
 * Packet Version
 * ----------------------------------------------------------
 */

constexpr uint8_t PACKET_VERSION = 1;

/*
 * ----------------------------------------------------------
 * Packet Flags
 * ----------------------------------------------------------
 */

enum PacketFlags : uint8_t
{
    FLAG_IMU_VALID      = 1 << 0,

    FLAG_PPG_VALID      = 1 << 1,

    FLAG_FINGER_PRESENT = 1 << 2,

    FLAG_BATTERY_LOW    = 1 << 3,

    FLAG_RESERVED_4     = 1 << 4,

    FLAG_RESERVED_5     = 1 << 5,

    FLAG_RESERVED_6     = 1 << 6,

    FLAG_RESERVED_7     = 1 << 7
};
