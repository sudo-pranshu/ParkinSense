/*
 * ParkinSense — IMU Hardware FIFO + FreeRTOS BLE Stream
 *
 * The LSM6DS3 hardware FIFO collects samples AUTONOMOUSLY while the CPU
 * sleeps. A FreeRTOS task wakes every 200 ms via vTaskDelayUntil(), drains
 * the FIFO in one burst, and sends a BLE notification.
 *
 * Why not use the INT1 interrupt?
 * The Seeed_Arduino_LSM6DS3 library's fifoRead() reads the two FIFO output
 * bytes as TWO separate I2C transactions (L register then H register). On
 * the LSM6DS3TR-C variant, each read of FIFO_DATA_OUT_L advances the FIFO
 * pointer, so reading L and H separately gives misaligned data. The library
 * also hardcodes FIFO_CTRL4=0x09 which enables DS3+DS4 slots (adding 2
 * empty 3-word datasets per frame), making each frame 12 words not 6.
 * We work around both by doing a raw burst read directly.
 *
 * Power model:
 *   - Task blocked 200 ms at a time → CPU in FreeRTOS WFI sleep
 *   - ~10 ms active per wakeup (burst I2C read + BLE notify)
 *   - Duty cycle ≈ 5% active, 95% sleep
 *
 * Bus layout (XIAO nRF52840 Sense):
 *   Wire1 (pins 16/17) — internal IMU bus, handled by Seeed library
 */

#include <Arduino.h>
#include <bluefruit.h>
#include <Wire.h>
#include "LSM6DS3.h"

// =====================================================================
// IMU object — Seeed library internally uses Wire1 on this board
// =====================================================================
LSM6DS3 imu(I2C_MODE, 0x6A);

// =====================================================================
// BLE
// =====================================================================
BLEService        imuService("ABCD1234-0000-467A-9538-01F0652C74E0");
BLECharacteristic imuChar(
    "ABCD1234-0001-467A-9538-01F0652C74E0",
    BLENotify,
    244
);

// =====================================================================
// Configuration
// =====================================================================
static const uint8_t  IMU_BATCH_SIZE   = 10;   // samples per BLE packet
static const uint8_t  WORDS_PER_SAMPLE = 6;    // Gx Gy Gz Ax Ay Az (see note)
static const uint32_t POLL_MS          = 200;  // wake every 200 ms
// At 104 Hz, 200 ms = ~20 new samples. Fits well within FIFO (8 KB).

// NOTE on FIFO word layout:
// fifoBegin() hardcodes FIFO_CTRL4=0x09, enabling DS3+DS4 slots.
// Real frame = 12 words: [Gx Gy Gz Ax Ay Az DS3x DS3y DS3z DS4x DS4y DS4z]
// DS3/DS4 slots are empty (zeroed) since we only enabled gyro+accel.
// We read all 12 words but only decode the first 6 (gyro+accel).
static const uint8_t  WORDS_PER_FRAME  = 12;  // actual FIFO frame size

// =====================================================================
// Packet structure
// =====================================================================
#pragma pack(push, 1)
struct IMUSample { int16_t gx, gy, gz, ax, ay, az; };
struct IMUPacket { uint32_t timestamp_us; IMUSample samples[IMU_BATCH_SIZE]; };
#pragma pack(pop)

// =====================================================================
// Global state
// =====================================================================
static IMUPacket     imuPacket;
static uint8_t       imuBatchIdx   = 0;
static uint32_t      imuPktsSent   = 0;
static uint32_t      imuLastStatMs = 0;
static volatile bool bleConnected  = false;

// =====================================================================
// BLE callbacks
// =====================================================================
void onConnect(uint16_t) {
    bleConnected = true;
    Serial.println("[BLE] Connected");
}
void onDisconnect(uint16_t, uint8_t) {
    bleConnected = false;
    Serial.println("[BLE] Disconnected");
}

// =====================================================================
// IMU FreeRTOS task
// Wakes every 200 ms, drains FIFO with raw burst reads, sends BLE.
// CPU is in WFI sleep the rest of the time — nearly zero power.
// =====================================================================
void imuTask(void*)
{
    TickType_t xLastWake = xTaskGetTickCount();

    Serial.println("[IMU] Task started — 200 ms FIFO drain cycle");

    while (true)
    {
        // Sleep until next 200 ms boundary — CPU in WFI during this
        vTaskDelayUntil(&xLastWake, pdMS_TO_TICKS(POLL_MS));

        // Read FIFO word count from status register
        // bits[10:0] = unread word count
        uint16_t wordCount   = imu.fifoGetStatus() & 0x07FF;
        uint16_t frameCount  = wordCount / WORDS_PER_FRAME;

        if (frameCount == 0) continue;

        if (imuBatchIdx == 0)
            imuPacket.timestamp_us = micros();

        for (uint16_t f = 0; f < frameCount; f++)
        {
            // Burst-read one full FIFO frame (12 words = 24 bytes) in a
            // single I2C transaction to avoid the library's byte-split bug.
            // FIFO_DATA_OUT_L = 0x3E; reading 24 bytes auto-increments.
            uint8_t raw[24];
            imu.readRegisterRegion(raw, 0x3E, 24);

            // Word layout (int16 LE): Gx Gy Gz Ax Ay Az DS3(x,y,z) DS4(x,y,z)
            auto w = [&](uint8_t i) -> int16_t {
                return (int16_t)(raw[i*2] | (raw[i*2+1] << 8));
            };

            imuPacket.samples[imuBatchIdx].gx = (int16_t)(imu.calcGyro (w(0)) * 131.0f);
            imuPacket.samples[imuBatchIdx].gy = (int16_t)(imu.calcGyro (w(1)) * 131.0f);
            imuPacket.samples[imuBatchIdx].gz = (int16_t)(imu.calcGyro (w(2)) * 131.0f);
            imuPacket.samples[imuBatchIdx].ax = (int16_t)(imu.calcAccel(w(3)) * 8192.0f);
            imuPacket.samples[imuBatchIdx].ay = (int16_t)(imu.calcAccel(w(4)) * 8192.0f);
            imuPacket.samples[imuBatchIdx].az = (int16_t)(imu.calcAccel(w(5)) * 8192.0f);
            // w(6)..w(11) = DS3+DS4 dummy words — discarded

            imuBatchIdx++;

            if (imuBatchIdx >= IMU_BATCH_SIZE)
            {
                if (bleConnected)
                {
                    if (imuChar.notify((uint8_t*)&imuPacket, sizeof(imuPacket)))
                        imuPktsSent++;
                }
                imuBatchIdx = 0;
                imuPacket.timestamp_us = micros();
            }
        }

        // Stats every 5 s (non-blocking serial)
        uint32_t now = millis();
        if (now - imuLastStatMs >= 5000)
        {
            char buf[48];
            int n = snprintf(buf, sizeof(buf),
                             "[IMU] %.1f sps | FIFO words=%u\r\n",
                             (float)(imuPktsSent * IMU_BATCH_SIZE) / 5.0f,
                             wordCount);
            if (n > 0 && n < (int)sizeof(buf) && Serial.availableForWrite() >= n)
                Serial.write((uint8_t*)buf, n);
            imuPktsSent   = 0;
            imuLastStatMs = now;
        }
    }
}

// =====================================================================
// IMU initialisation
// =====================================================================
bool initIMU()
{
    // Settings MUST be set before begin() — begin() writes them to hardware
    imu.settings.accelEnabled        = 1;
    imu.settings.gyroEnabled         = 1;
    imu.settings.accelRange          = 4;    // ±4g
    imu.settings.gyroRange           = 245;  // ±245 dps
    imu.settings.accelSampleRate     = 104;  // Hz
    imu.settings.gyroSampleRate      = 104;

    // FIFO settings (used by fifoBegin())
    imu.settings.accelFifoEnabled    = 1;
    imu.settings.accelFifoDecimation = 1;
    imu.settings.gyroFifoEnabled     = 1;
    imu.settings.gyroFifoDecimation  = 1;
    imu.settings.fifoSampleRate      = 100;  // Hz
    // Watermark = 20 frames × 12 words/frame = 240 words
    // (fifoBegin hardcodes DS3+DS4, so actual frame size is 12 words)
    imu.settings.fifoThreshold       = 20 * WORDS_PER_FRAME;

    if (imu.begin() != 0)
    {
        Serial.println("[IMU] begin() FAILED");
        return false;
    }

    imu.fifoBegin();  // programs FIFO registers (Continuous mode = 6)
    imu.fifoClear();  // flush any stale FIFO data

    Serial.println("[IMU] OK — hardware FIFO running @ 104 Hz");
    return true;
}

// =====================================================================
// BLE initialisation
// =====================================================================
void initBLE()
{
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

    Bluefruit.Periph.setConnectCallback(onConnect);
    Bluefruit.Periph.setDisconnectCallback(onDisconnect);

    Serial.println("[BLE] Advertising as 'ParkinSense'");
}

// =====================================================================
// Setup
// =====================================================================
void setup()
{
    Serial.begin(115200);
    for (uint32_t t = millis(); !Serial && (millis() - t < 3000); ) delay(10);

    Serial.println("\n=== ParkinSense IMU FIFO+FreeRTOS ===");

    if (!initIMU()) { Serial.println("HALTED"); while (1); }
    initBLE();

    xTaskCreate(imuTask, "IMU", 2048, NULL, 3, NULL);

    Serial.println("[SETUP] Done — task sleeping 200 ms between FIFO drains\n");
}

// =====================================================================
// Loop — idle only; FreeRTOS enters WFI between task wakeups
// =====================================================================
void loop()
{
    delay(1000);
}