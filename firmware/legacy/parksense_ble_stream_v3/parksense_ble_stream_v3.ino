#include <Arduino.h>
#include <bluefruit.h>
#include <Wire.h>
#include "LSM6DS3.h"
#include <MAX30105.h>

LSM6DS3 imu(I2C_MODE, 0x6A);
MAX30105 max30102;

// ParkinSense BLE Service
BLEService imuService("ABCD1234-0000-467A-9538-01F0652C74E0");
BLECharacteristic imuChar(
    "ABCD1234-0001-467A-9538-01F0652C74E0",
    BLENotify,
    244
);

// ---- Configuration ----
const uint32_t SAMPLE_INTERVAL_US = 9615; // ~104 Hz
const uint8_t BATCH_SIZE = 10;
const uint32_t INTERVAL_RECONNECT_MS = 10000; // retry dead sensors every 10s
const uint8_t MAX_CATCHUP_INTERVALS = 5; // bounded catch-up cap

// ---- Packet Structures ----
#pragma pack(push,1)
struct PacketHeader
{
    uint8_t version;
    uint8_t flags;
    uint16_t reserved;
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
    uint32_t ir;
    uint32_t red;
};

struct IMUPacket
{
    PacketHeader header;
    IMUSample samples[BATCH_SIZE];
};
#pragma pack(pop)

// ---- Globals ----
IMUPacket packet;
uint8_t batchIndex = 0;
uint32_t lastSampleUs = 0;
uint32_t sampleCounter = 0;
uint32_t lastRateReport = 0;
uint32_t lastReconnectMs = 0;

bool imuReady = false;
bool spo2Ready = false;

// PPG (MAX30102) globals - runs at 10 Hz, independent of IMU loop
uint32_t lastPPGMs = 0;
uint32_t latestIR = 0;
uint32_t latestRED = 0;

// ---- Sensor Inits (non-blocking, retried in loop if they fail) ----
void initIMU()
{
    if (imu.begin() != 0)
    {
        Serial.println("IMU INIT FAILED (will retry)");
        imuReady = false;
    }
    else
    {
        imu.settings.accelEnabled = 1;
        imu.settings.gyroEnabled = 1;
        imu.settings.accelRange = 4;
        imu.settings.gyroRange = 245;
        Serial.println("IMU OK");
        imuReady = true;
    }
}

void initSPO2()
{
    if (max30102.begin(Wire, I2C_SPEED_STANDARD) == false)
    {
        Serial.println("MAX30102 INIT FAILED (will retry)");
        spo2Ready = false;
    }
    else
    {
        // powerLevel, sampleAverage, ledMode(2=Red+IR), sampleRate, pulseWidth, adcRange
        max30102.setup(0x1F, 1, 2, 100, 411, 4096);
        Serial.println("MAX30102 OK");
        spo2Ready = true;
    }
}

// ---- Setup ----
void setup()
{
    Serial.begin(115200);
    uint32_t serialWaitStart = millis();
    while (!Serial && (millis() - serialWaitStart) < 3000)
    {
        delay(10);
    }

    Wire.begin();
    Wire.setClock(400000);

    initIMU();
    initSPO2();

    Bluefruit.configPrphConn(
        247,
        247,
        6,
        6
    );
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
    lastPPGMs = millis();
    lastReconnectMs = millis();
}

// ---- Loop ----
void loop()
{
    uint32_t nowMs = millis();

    // ---- Retry any sensor that failed to init, every 10s ----
    if (nowMs - lastReconnectMs >= INTERVAL_RECONNECT_MS)
    {
        lastReconnectMs = nowMs;
        if (!imuReady)
        {
            Serial.println("Retrying IMU init...");
            initIMU();
        }
        if (!spo2Ready)
        {
            Serial.println("Retrying MAX30102 init...");
            initSPO2();
        }
    }

    // ---- PPG: 10 Hz, independent of IMU timing ----
    // Reads via FIFO instead of getIR()/getRed() to avoid any
    // possibility of blocking on I2C while waiting for fresh samples.
    // FIFO is fully drained each tick (while, not if) - with no finger
    // on the sensor the FIFO barely fills so this made no visible
    // difference, but with a finger present the FIFO fills at 100 SPS
    // while we only checked once per 100ms, so it backed up more and
    // more every cycle, which is what was making things grind to a
    // crawl / appear stuck once you placed your finger.
    if (spo2Ready && (nowMs - lastPPGMs) >= 100)
    {
        lastPPGMs = nowMs;
        max30102.check(); // pulls any available FIFO samples into the lib's buffer
        while (max30102.available())
        {
            latestIR = max30102.getFIFOIR();
            latestRED = max30102.getFIFORed();
            max30102.nextSample();
        }
        // else: FIFO empty this cycle, keep previous latestIR/latestRED
    }

    uint32_t nowUs = micros();
    if ((nowUs - lastSampleUs) < SAMPLE_INTERVAL_US)
    {
        return;
    }

    // Bounded catch-up scheduler: if we've fallen behind by more than
    // MAX_CATCHUP_INTERVALS worth of samples (e.g. due to a BLE stall),
    // snap forward instead of unbounded incrementing, which would
    // otherwise fire a burst of back-to-back iterations to "catch up".
    uint32_t elapsed = nowUs - lastSampleUs;
    uint32_t intervalsElapsed = elapsed / SAMPLE_INTERVAL_US;
    if (intervalsElapsed > MAX_CATCHUP_INTERVALS)
    {
        intervalsElapsed = MAX_CATCHUP_INTERVALS;
    }
    lastSampleUs += intervalsElapsed * SAMPLE_INTERVAL_US;

    float ax_f = 0, ay_f = 0, az_f = 0, gx_f = 0, gy_f = 0, gz_f = 0;
    if (imuReady)
    {
        ax_f = imu.readFloatAccelX();
        ay_f = imu.readFloatAccelY();
        az_f = imu.readFloatAccelZ();
        gx_f = imu.readFloatGyroX();
        gy_f = imu.readFloatGyroY();
        gz_f = imu.readFloatGyroZ();
    }

    if (batchIndex == 0)
    {
        packet.header.version = 1;
        packet.header.flags = 0;
        packet.header.reserved = 0;
        packet.header.timestamp_us = micros();
    }

    packet.samples[batchIndex].ax =
        (int16_t)(ax_f * 8192.0f);
    packet.samples[batchIndex].ay =
        (int16_t)(ay_f * 8192.0f);
    packet.samples[batchIndex].az =
        (int16_t)(az_f * 8192.0f);
    packet.samples[batchIndex].gx =
        (int16_t)(gx_f * 131.0f);
    packet.samples[batchIndex].gy =
        (int16_t)(gy_f * 131.0f);
    packet.samples[batchIndex].gz =
        (int16_t)(gz_f * 131.0f);

    packet.samples[batchIndex].ir = latestIR;
    packet.samples[batchIndex].red = latestRED;

    batchIndex++;
    sampleCounter++;

    if (batchIndex >= BATCH_SIZE)
    {
        if (Bluefruit.connected())
        {
            uint16_t result = imuChar.notify(
                (uint8_t*)&packet,
                sizeof(packet)
            );
            (void)result; // notify() return value checked; no action needed on failure, next batch will simply retry
        }
        batchIndex = 0;
    }

    if (millis() - lastRateReport >= 1000)
    {
        Serial.print("RATE=");
        Serial.print(sampleCounter);
        Serial.print(" IR=");
        Serial.print(latestIR);
        Serial.print(" RED=");
        Serial.print(latestRED);
        Serial.print(" BLE=");
        Serial.println(Bluefruit.connected() ? 1 : 0);
        sampleCounter = 0;
        lastRateReport = millis();
    }
}