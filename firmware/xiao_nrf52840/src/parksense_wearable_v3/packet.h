#pragma once

#include <Arduino.h>

#include "config.h"

#pragma pack(push,1)

/*
 * Packet Header
 */

struct PacketHeader
{
    uint32_t timestamp_us;
};

/*
 * One Sensor Sample
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
 * BLE Packet
 */

struct WearablePacket
{
    PacketHeader header;

    SensorSample samples[BATCH_SIZE];
};

#pragma pack(pop)
