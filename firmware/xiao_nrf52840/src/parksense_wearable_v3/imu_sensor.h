#pragma once

#include <Arduino.h>
#include <Wire.h>

#include <LSM6DS3.h>

class IMUSensor
{

public:

    bool begin();

    bool update();

    float ax() const;
    float ay() const;
    float az() const;

    float gx() const;
    float gy() const;
    float gz() const;

private:

    LSM6DS3 imu = LSM6DS3(I2C_MODE, 0x6A);

    float _ax = 0;
    float _ay = 0;
    float _az = 0;

    float _gx = 0;
    float _gy = 0;
    float _gz = 0;

};
