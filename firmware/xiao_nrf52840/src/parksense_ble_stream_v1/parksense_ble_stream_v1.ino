#include <Arduino.h>
#include <bluefruit.h>
#include <Wire.h>
#include "LSM6DS3.h"

LSM6DS3 imu(I2C_MODE, 0x6A);

// ParkinSense BLE Service
BLEService imuService("ABCD1234-0000-467A-9538-01F0652C74E0");
BLECharacteristic imuChar(
    "ABCD1234-0001-467A-9538-01F0652C74E0",
    BLENotify,
    244
);

BLECharacteristic spo2Char(
    "ABCD1234-0002-467A-9538-01F0652C74E0",
    BLENotify,
    20
);

// –––– Configuration ––––
const uint32_t SAMPLE_INTERVAL_US = 9615;    // ~104 Hz for IMU
const uint8_t BATCH_SIZE = 10;
const uint32_t SPO2_SAMPLE_INTERVAL_US = 100000; // 10 Hz for SpO2
const uint8_t SPO2_MAX30102_ADDR = 0x57;
const uint8_t SPO2_FIFO_REG = 0x07;

// –––– Packet Structures ––––
#pragma pack(push, 1)
struct PacketHeader {
    uint32_t timestamp_us;
};

struct IMUSample {
    int16_t ax;
    int16_t ay;
    int16_t az;
    int16_t gx;
    int16_t gy;
    int16_t gz;
};

struct IMUPacket {
    PacketHeader header;
    IMUSample samples[BATCH_SIZE];
};

struct SensorData {
    uint32_t Red;
    uint32_t IR;
};

struct SpO2Packet {
    PacketHeader header;
    uint32_t Red;
    uint32_t IR;
};

#pragma pack(pop)

// –––– Globals ––––
IMUPacket packet;
uint8_t batchIndex = 0;
uint32_t lastSampleUs = 0;
uint32_t lastSpo2SampleUs = 0;
uint32_t sampleCounter = 0;
uint32_t spo2Counter = 0;
uint32_t lastRateReport = 0;
bool spo2Ready = false;

// –––– SpO2 Functions ––––
SensorData readRedIR() {
    SensorData data = {0, 0};
    if (!spo2Ready) return data;
    
    Wire.beginTransmission(SPO2_MAX30102_ADDR);
    Wire.write(SPO2_FIFO_REG);
    Wire.endTransmission();
    Wire.requestFrom(SPO2_MAX30102_ADDR, 6, true);
    
    if (Wire.available() >= 6) {
        data.Red = (Wire.read() << 16 | Wire.read() << 8 | Wire.read()) & 0x3FFFF;
        data.IR = (Wire.read() << 16 | Wire.read() << 8 | Wire.read()) & 0x3FFFF;
    }
    return data;
}

void initSpO2() {
    // Reset
    Wire.beginTransmission(SPO2_MAX30102_ADDR);
    Wire.write(0x09);  // MODE_CONFIG register
    Wire.write(0x40);  // RESET bit
    Wire.endTransmission();
    delay(100);

    // Mode: SpO2 (0x03)
    Wire.beginTransmission(SPO2_MAX30102_ADDR);
    Wire.write(0x09);
    Wire.write(0x03);
    Wire.endTransmission();
    delay(10);

    // LED current
    Wire.beginTransmission(SPO2_MAX30102_ADDR);
    Wire.write(0x0C);  // LED1_PA
    Wire.write(0x24);  // ~12mA
    Wire.endTransmission();
    delay(10);

    // Sample rate & pulse width
    Wire.beginTransmission(SPO2_MAX30102_ADDR);
    Wire.write(0x0A);  // SpO2_CONFIG
    Wire.write(0x27);  // 100Hz, 1600us
    Wire.endTransmission();
    delay(10);

    spo2Ready = true;
    Serial.println("SpO2 sensor initialized");
}

// –––– Setup ––––
void setup() {
    Serial.begin(115200);
    Wire.begin();

    // Initialize IMU
    if (imu.begin() != 0) {
        Serial.println("IMU INIT FAILED");
        while (1) {
            delay(1000);
        }
    }

    imu.settings.accelEnabled = 1;
    imu.settings.gyroEnabled = 1;
    imu.settings.accelRange = 4;
    imu.settings.gyroRange = 245;

    // Initialize SpO2
    initSpO2();

    // BLE Setup
    Bluefruit.configPrphConn(247, 247, 6, 6);
    Bluefruit.begin();
    Bluefruit.setTxPower(4);
    Bluefruit.setName("ParkinSense");

    imuService.begin();
    imuChar.begin();
    spo2Char.begin();

    Bluefruit.Advertising.addService(imuService);
    Bluefruit.Advertising.addName();
    Bluefruit.Advertising.restartOnDisconnect(true);
    Bluefruit.Advertising.start(0);

    Serial.println("ParkinSense V2 Ready");
    lastSampleUs = micros();
    lastSpo2SampleUs = micros();
}

// –––– Loop ––––
void loop() {
    uint32_t nowUs = micros();

    // ––– IMU Sampling –––
    if ((nowUs - lastSampleUs) >= SAMPLE_INTERVAL_US) {
        lastSampleUs += SAMPLE_INTERVAL_US;

        float ax_f = imu.readFloatAccelX();
        float ay_f = imu.readFloatAccelY();
        float az_f = imu.readFloatAccelZ();
        float gx_f = imu.readFloatGyroX();
        float gy_f = imu.readFloatGyroY();
        float gz_f = imu.readFloatGyroZ();

        if (batchIndex == 0) {
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

        if (batchIndex >= BATCH_SIZE) {
            if (Bluefruit.connected()) {
                imuChar.notify((uint8_t*)&packet, sizeof(packet));
            }
            batchIndex = 0;
        }
    }

    // ––– SpO2 Sampling –––
    if ((nowUs - lastSpo2SampleUs) >= SPO2_SAMPLE_INTERVAL_US) {
        lastSpo2SampleUs += SPO2_SAMPLE_INTERVAL_US;

        SensorData spo2Data = readRedIR();

        if (Bluefruit.connected()) {
            SpO2Packet spo2Packet;
            spo2Packet.header.timestamp_us = micros();
            spo2Packet.Red = spo2Data.Red;
            spo2Packet.IR = spo2Data.IR;

            spo2Char.notify((uint8_t*)&spo2Packet, sizeof(spo2Packet));
        }

        spo2Counter++;
    }

    // ––– Rate Reporting –––
    if (millis() - lastRateReport >= 1000) {
        Serial.print("IMU_RATE=");
        Serial.print(sampleCounter);
        Serial.print(" SPO2_RATE=");
        Serial.println(spo2Counter);
        sampleCounter = 0;
        spo2Counter = 0;
        lastRateReport = millis();
    }
}