#include <Arduino.h>
#include <bluefruit.h>
#include <Wire.h>
#include "LSM6DS3.h"
#include <MAX30105.h>          // Step 2: add MAX30102 header

LSM6DS3 imu(I2C_MODE, 0x6A);
MAX30105 max30102;             // Step 2: MAX30102 object

// ParkinSense BLE Service
BLEService imuService("ABCD1234-0000-467A-9538-01F0652C74E0");
BLECharacteristic imuChar(
    "ABCD1234-0001-467A-9538-01F0652C74E0",
    BLENotify,
    244
);

// ---- Configuration ----

const uint32_t SAMPLE_INTERVAL_US = 9615;  // ~104 Hz
const uint8_t  BATCH_SIZE         = 10;

// ---- Packet Structures ----

#pragma pack(push, 1)

struct PacketHeader
{
    uint32_t timestamp_us;
};

struct IMUSample
{
    int16_t ax;
    int16_t ay;
    int16_t az;

    int16_t gx;
    int16_t gy;
    int16_t gz;
};

struct IMUPacket
{
    PacketHeader header;
    IMUSample    samples[BATCH_SIZE];
};

#pragma pack(pop)

// ---- Globals ----

IMUPacket packet;

uint8_t  batchIndex    = 0;
uint32_t lastSampleUs  = 0;
uint32_t sampleCounter = 0;
uint32_t lastRateReport = 0;

// Step 3: holding variables for PPG samples
uint32_t ppg_ir  = 0;
uint32_t ppg_red = 0;

// ---- Setup ----

void setup()
{
    Serial.begin(115200);

    // Single Wire.begin() for the entire bus — both sensors share it
    Wire.begin();

    // IMU init
    if (imu.begin() != 0)
    {
        Serial.println("IMU INIT FAILED");
        while (1) { delay(1000); }
    }
    imu.settings.accelEnabled = 1;
    imu.settings.gyroEnabled  = 1;
    imu.settings.accelRange   = 4;
    imu.settings.gyroRange    = 245;

    // Step 2: MAX30102 init — one begin(), no second Wire.begin()
    if (!max30102.begin(Wire, I2C_SPEED_FAST))
    {
        Serial.println("MAX30102 INIT FAILED");
        while (1) { delay(1000); }
    }
    max30102.setup();
    max30102.setPulseAmplitudeRed(0x1F);
    max30102.setPulseAmplitudeIR(0x1F);

    // BLE
    Bluefruit.configPrphConn(247, 247, 6, 6);
    Bluefruit.begin();
    Bluefruit.setTxPower(4);
    Bluefruit.setName("ParkinSense");

    imuService.begin();
    imuChar.begin();

    Bluefruit.Advertising.addService(imuService);
    Bluefruit.Advertising.addName();
    Bluefruit.Advertising.restartOnDisconnect(true);
    Bluefruit.Advertising.start(0);

    Serial.println("ParkinSense V2 Ready");
    lastSampleUs = micros();
}

// ---- Loop ----

void loop()
{
    uint32_t nowUs = micros();

    if ((nowUs - lastSampleUs) < SAMPLE_INTERVAL_US)
    {
        return;
    }
    lastSampleUs += SAMPLE_INTERVAL_US;

    // IMU — unchanged
    float ax_f = imu.readFloatAccelX();
    float ay_f = imu.readFloatAccelY();
    float az_f = imu.readFloatAccelZ();
    float gx_f = imu.readFloatGyroX();
    float gy_f = imu.readFloatGyroY();
    float gz_f = imu.readFloatGyroZ();

    if (batchIndex == 0)
    {
        packet.header.timestamp_us = micros();
    }

    packet.samples[batchIndex].ax = (int16_t)(ax_f * 8192.0f);
    packet.samples[batchIndex].ay = (int16_t)(ay_f * 8192.0f);
    packet.samples[batchIndex].az = (int16_t)(az_f * 8192.0f);
    packet.samples[batchIndex].gx = (int16_t)(gx_f * 131.0f);
    packet.samples[batchIndex].gy = (int16_t)(gy_f * 131.0f);
    packet.samples[batchIndex].gz = (int16_t)(gz_f * 131.0f);

    batchIndex++;
    sampleCounter++;

    // Step 3: read PPG every loop iteration — if this drops rate, move to every Nth sample
    ppg_ir  = max30102.getIR();
    ppg_red = max30102.getRed();

    if (batchIndex >= BATCH_SIZE)
    {
        if (Bluefruit.connected())
        {
            imuChar.notify((uint8_t*)&packet, sizeof(packet));
        }
        batchIndex = 0;
    }

    // Step 4: serial rate report now includes IR, RED, and heap
    if (millis() - lastRateReport >= 1000)
    {
        Serial.print("RATE=");
        Serial.print(sampleCounter);

        Serial.print(" IR=");
        Serial.print(ppg_ir);

        Serial.print(" RED=");
        Serial.print(ppg_red);

        Serial.print(" HEAP=");
        Serial.println(mallinfo().uordblks);

        sampleCounter  = 0;
        lastRateReport = millis();
    }
}