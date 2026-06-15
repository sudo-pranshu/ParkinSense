#include <Wire.h>
#include "LSM6DS3.h"

LSM6DS3 imu(I2C_MODE, 0x6A);

const uint16_t SAMPLE_RATE_HZ = 100;
const uint32_t SAMPLE_PERIOD_MS = 10;

uint32_t lastSample = 0;

void setup()
{
    Serial.begin(115200);

    while (!Serial);

    if (imu.begin() != 0)
    {
        Serial.println("IMU init failed");
        while (1);
    }

    Serial.println("timestamp,ax,ay,az,gx,gy,gz");

    lastSample = millis();
}

void loop()
{
    if (millis() - lastSample >= SAMPLE_PERIOD_MS)
    {
        lastSample += SAMPLE_PERIOD_MS;

        float ax = imu.readFloatAccelX();
        float ay = imu.readFloatAccelY();
        float az = imu.readFloatAccelZ();

        float gx = imu.readFloatGyroX();
        float gy = imu.readFloatGyroY();
        float gz = imu.readFloatGyroZ();

        Serial.print(millis());
        Serial.print(",");

        Serial.print(ax, 4);
        Serial.print(",");

        Serial.print(ay, 4);
        Serial.print(",");

        Serial.print(az, 4);
        Serial.print(",");

        Serial.print(gx, 4);
        Serial.print(",");

        Serial.print(gy, 4);
        Serial.print(",");

        Serial.println(gz, 4);
    }
}
