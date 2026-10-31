#pragma once

/*
 * ==========================================================
 * ParkinSense Wearable V3
 * MAX30102 Sensor Driver
 * ==========================================================
 */

#include <Arduino.h>

#include <MAX30105.h>

class MAX30102Sensor
{

public:

    bool begin();

    bool update();

    uint32_t getIR() const;

    uint32_t getRed() const;

    bool fingerDetected() const;

private:

    MAX30105 sensor;

    uint32_t ir = 0;

    uint32_t red = 0;

    bool finger = false;

};
