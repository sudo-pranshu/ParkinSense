#include "imu_sensor.h"

bool IMUSensor::begin()
{

    if (imu.begin() != 0)
    {
        Serial.println("IMU INIT FAILED");
        return false;
    }

    imu.settings.accelEnabled = 1;
    imu.settings.gyroEnabled = 1;

    imu.settings.accelRange = 4;
    imu.settings.gyroRange = 245;

    Serial.println("IMU READY");

    return true;

}

bool IMUSensor::update()
{

    _ax = imu.readFloatAccelX();
    _ay = imu.readFloatAccelY();
    _az = imu.readFloatAccelZ();

    _gx = imu.readFloatGyroX();
    _gy = imu.readFloatGyroY();
    _gz = imu.readFloatGyroZ();

    return true;

}

float IMUSensor::ax() const
{
    return _ax;
}

float IMUSensor::ay() const
{
    return _ay;
}

float IMUSensor::az() const
{
    return _az;
}

float IMUSensor::gx() const
{
    return _gx;
}

float IMUSensor::gy() const
{
    return _gy;
}

float IMUSensor::gz() const
{
    return _gz;
}
