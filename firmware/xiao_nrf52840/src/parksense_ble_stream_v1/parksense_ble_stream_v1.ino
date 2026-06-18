#include <Arduino.h>
#include <bluefruit.h>
#include <Wire.h>
#include "LSM6DS3.h"

LSM6DS3 imu(I2C_MODE, 0x6A);

// BLE UART
BLEUart bleuart;

uint32_t lastSample = 0;
const uint32_t SAMPLE_INTERVAL_MS = 20; // 50 Hz

void setup()
{
    Serial.begin(115200);

    Wire.begin();

    if (imu.begin() != 0)
    {
        Serial.println("IMU INIT FAILED");
        while (1);
    }

    Bluefruit.begin();
    Bluefruit.setTxPower(4);
    Bluefruit.setName("ParkinSense");

    bleuart.begin();

    Bluefruit.Advertising.addFlags(
        BLE_GAP_ADV_FLAGS_LE_ONLY_GENERAL_DISC_MODE
    );

    Bluefruit.Advertising.addTxPower();
    Bluefruit.Advertising.addName();

    Bluefruit.Advertising.start(0);

    Serial.println("ParkinSense BLE Ready");
}

void loop()
{
    if (millis() - lastSample < SAMPLE_INTERVAL_MS)
        return;

    lastSample = millis();

    float ax = imu.readFloatAccelX();
    float ay = imu.readFloatAccelY();
    float az = imu.readFloatAccelZ();

    float gx = imu.readFloatGyroX();
    float gy = imu.readFloatGyroY();
    float gz = imu.readFloatGyroZ();

    String packet =
        String(millis()) + "," +
        String(ax, 4) + "," +
        String(ay, 4) + "," +
        String(az, 4) + "," +
        String(gx, 4) + "," +
        String(gy, 4) + "," +
        String(gz, 4);

    bleuart.println(packet);

    Serial.println(packet);
}
