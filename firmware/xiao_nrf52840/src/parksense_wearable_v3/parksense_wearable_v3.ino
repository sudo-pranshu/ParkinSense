/*
=========================================================
ParkinSense Wearable V3
IMU + MAX30102 + BLE Streaming
=========================================================
*/

#include <Arduino.h>
#include <Wire.h>
#include <bluefruit.h>
#include "config.h"
#include "packet.h"
#include "imu_sensor.h"
#include "max30102_sensor.h"

// ----------------------------------------------------
// Sensors
// ----------------------------------------------------

IMUSensor imu;
MAX30102Sensor ppg;

// ----------------------------------------------------
// BLE
// ----------------------------------------------------

BLEService wearableService(BLE_SERVICE_UUID);

BLECharacteristic wearableCharacteristic(
    BLE_CHARACTERISTIC_UUID,
    BLENotify,
    sizeof(WearablePacket)
);

// ----------------------------------------------------
// Packet
// ----------------------------------------------------

WearablePacket packet;
uint8_t batchIndex = 0;

// ----------------------------------------------------
// Timing
// ----------------------------------------------------

uint32_t lastSampleUs  = 0;
uint32_t sampleCounter = 0;
uint32_t lastRateReport = 0;

// ----------------------------------------------------
// Setup
// ----------------------------------------------------

void setup()
{
    Serial.begin(115200);

    while (!Serial)
    {
        delay(10);
    }

    Serial.println();
    Serial.println("=======================================");
    Serial.println("      ParkinSense Wearable V3");
    Serial.println("=======================================");

    // -----------------------------
    // I2C
    // -----------------------------

    Wire.begin();

    // -----------------------------
    // IMU
    // -----------------------------

    if (!imu.begin())
    {
        Serial.println("IMU FAILED");

        while (1)
        {
            delay(1000);
        }
    }

    // -----------------------------
    // MAX30102
    // -----------------------------

    if (!ppg.begin())
    {
        Serial.println("MAX30102 FAILED");

        while (1)
        {
            delay(1000);
        }
    }

    // -----------------------------
    // BLE
    // -----------------------------

    Bluefruit.configPrphConn(
        247,    // max MTU
        247,    // max MTU
        6,      // event length
        6       // event length
    );

    Bluefruit.begin();

    Bluefruit.setTxPower(4);

    Bluefruit.setName(DEVICE_NAME);

    wearableService.begin();

    wearableCharacteristic.begin();

    Bluefruit.Advertising.addService(wearableService);

    Bluefruit.Advertising.addName();

    Bluefruit.Advertising.restartOnDisconnect(true);

    Bluefruit.Advertising.start(0);

    Serial.println();
    Serial.println("BLE READY");
    Serial.println("Advertising...");

    lastSampleUs = micros();
}

// ----------------------------------------------------
// Main Loop
// ----------------------------------------------------

void loop()
{
    uint32_t nowUs = micros();

    if ((nowUs - lastSampleUs) < IMU_SAMPLE_INTERVAL_US)
    {
        return;
    }

    lastSampleUs += IMU_SAMPLE_INTERVAL_US;

    // ---------------------------------
    // Read IMU
    // ---------------------------------

    imu.update();

    // ---------------------------------
    // Read MAX30102
    // ---------------------------------

    ppg.update();

    // ---------------------------------
    // First sample timestamp
    // ---------------------------------

    if (batchIndex == 0)
    {
        packet.header.timestamp_us = micros();
    }

    // ---------------------------------
    // Accelerometer
    // ---------------------------------

    packet.samples[batchIndex].ax =
        (int16_t)(imu.ax() * ACCEL_SCALE);

    packet.samples[batchIndex].ay =
        (int16_t)(imu.ay() * ACCEL_SCALE);

    packet.samples[batchIndex].az =
        (int16_t)(imu.az() * ACCEL_SCALE);

    // ---------------------------------
    // Gyroscope
    // ---------------------------------

    packet.samples[batchIndex].gx =
        (int16_t)(imu.gx() * GYRO_SCALE);

    packet.samples[batchIndex].gy =
        (int16_t)(imu.gy() * GYRO_SCALE);

    packet.samples[batchIndex].gz =
        (int16_t)(imu.gz() * GYRO_SCALE);

    // ---------------------------------
    // MAX30102
    // ---------------------------------

    packet.samples[batchIndex].ir  = ppg.getIR();
    packet.samples[batchIndex].red = ppg.getRed();

    batchIndex++;
    sampleCounter++;

    // ---------------------------------
    // Send BLE Packet
    // ---------------------------------

    if (batchIndex >= BATCH_SIZE)
    {
        if (Bluefruit.connected())
        {
            wearableCharacteristic.notify(
                (uint8_t*)&packet,
                sizeof(packet)
            );
        }

        batchIndex = 0;
    }

    // ---------------------------------
    // Diagnostics
    // ---------------------------------

    if (millis() - lastRateReport >= 1000)
    {
        Serial.print("Rate : ");
        Serial.print(sampleCounter);
        Serial.print(" Hz");
        Serial.print(" | Finger : ");
        Serial.print(ppg.fingerDetected());
        Serial.print(" | IR : ");
        Serial.print(ppg.getIR());
        Serial.print(" | RED : ");
        Serial.println(ppg.getRed());

        sampleCounter    = 0;
        lastRateReport   = millis();
    }
}