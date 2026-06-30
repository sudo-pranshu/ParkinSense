#include <bluefruit.h>
#include <Adafruit_SPIFlash.h>
#include <Adafruit_TinyUSB.h>
#include <Wire.h>
#include <LSM6DS3.h>
#include "MAX30105.h"

Adafruit_FlashTransport_QSPI flashTransport;

// =====================
// TIMING INTERVALS
// =====================
constexpr uint32_t INTERVAL_IMU_US     = 9615;    // ~104 Hz
constexpr uint32_t INTERVAL_SPO2_MS    = 20;      // 50 Hz
constexpr uint32_t INTERVAL_RECONNECT_MS = 10000; // 10 seconds

// Anti-runaway clamp: if the scheduler falls more than this many
// intervals behind (e.g. BLE/Serial stall), resync instead of
// bursting through a pile of catch-up notifies in one loop pass.
constexpr uint32_t IMU_MAX_BACKLOG_INTERVALS = 5;

// =====================
// SENSOR STRUCTS & GLOBALS
// =====================
struct SensorData {
  long Red;
  long IR;
};

struct IMUData {
  float aX, aY, aZ;
  float gX, gY, gZ;
};

LSM6DS3 myIMU(I2C_MODE, 0x6A);
MAX30105 particleSensor;

bool deviceConnected = false;

// Sensor Status Flags
bool imuReady = false;
bool spo2Ready = false;

// Timers
uint32_t lastImuUs       = 0;
uint32_t lastSpo2Ms      = 0;
uint32_t lastReconnectMs = 0;
uint32_t lastStatsMs     = 0;

// Debug Counters
uint32_t imuPacketsSent  = 0;
uint32_t spo2PacketsSent = 0;
uint32_t imuSamplesRead  = 0;
uint32_t spo2SamplesRead = 0;

// Cache of the last good SPO2 reading, returned if the FIFO is
// momentarily empty so downstream consumers don't see a fake zero.
SensorData lastSpo2Data = {0, 0};

// =====================
// BLE GATT Profile
// =====================
BLEService customService = BLEService("4fafc201-1fb5-459e-8fcc-c5c9c331914b");
BLECharacteristic imuChar = BLECharacteristic(0x27A8);
BLECharacteristic spo2Char = BLECharacteristic(0x2A8D);

// =====================
// SENSOR INITS
// =====================
void initSPO2() {
  if (!particleSensor.begin(Wire, I2C_SPEED_FAST)) {
    Serial.println("SPO2 not found. Will retry later.");
    spo2Ready = false;
  } else {
    byte ledBrightness = 40;
    byte sampleAverage = 1;
    byte ledMode = 2;
    int sampleRate = 100; // Set closer to 50Hz requirement
    int pulseWidth = 69;
    int adcRange = 4096;
    particleSensor.setup(ledBrightness, sampleAverage, ledMode, sampleRate, pulseWidth, adcRange);
    Serial.println("SPO2 OK");
    spo2Ready = true;
  }
}

void initIMU() {
  Wire.setClock(400000); 
  if (myIMU.begin() != 0) {
    Serial.println("IMU not found. Will retry later.");
    imuReady = false;
  } else {
    Serial.println("IMU OK");
    imuReady = true;
  }
}

void setupNRF(void) {
  customService.begin();

  imuChar.setProperties(CHR_PROPS_NOTIFY);
  imuChar.setPermission(SECMODE_OPEN, SECMODE_NO_ACCESS);
  imuChar.setFixedLen(64);
  imuChar.begin();

  spo2Char.setProperties(CHR_PROPS_NOTIFY);
  spo2Char.setPermission(SECMODE_OPEN, SECMODE_NO_ACCESS);
  spo2Char.begin();
}

void startAdv() {
  Bluefruit.Advertising.addName();
  Bluefruit.Advertising.addFlags(BLE_GAP_ADV_FLAGS_LE_ONLY_GENERAL_DISC_MODE);
  Bluefruit.Advertising.addTxPower();
  Bluefruit.Advertising.addService(customService); 
  Bluefruit.Advertising.restartOnDisconnect(true);
  Bluefruit.Advertising.setInterval(160, 1600);
  Bluefruit.Advertising.setFastTimeout(30);
  Bluefruit.Advertising.start(0);
}

void connect_callback(uint16_t conn_handle) {
  deviceConnected = true;
  Serial.println("BLE Connected!");
}

void disconnect_callback(uint16_t conn_handle, uint8_t reason) {
  deviceConnected = false;
  Serial.println("BLE Disconnected!");
}

void setup() {
  Serial.begin(115200);
  
  unsigned long start = millis();
  while (!Serial && (millis() - start < 5000)) {
    delay(10);
  }
  
  Serial.println("\n--- IN SETUP ---");

  // Power efficiency for nRF52
  NRF_POWER->DCDCEN = 1;

  // Put QSPI flash to sleep
  flashTransport.begin();
  flashTransport.runCommand(0xB9);
  delayMicroseconds(5);
  flashTransport.end();

  Wire.begin();

  initSPO2();
  initIMU(); 

  // BLE init
  Bluefruit.begin();
  Bluefruit.configPrphBandwidth(BANDWIDTH_MAX);
  Bluefruit.setName("ParkinSense");
  Bluefruit.Periph.setConnectCallback(connect_callback);
  Bluefruit.Periph.setDisconnectCallback(disconnect_callback);

  setupNRF();
  startAdv();

  Serial.println("Setup complete! BLE Advertising started.");
  
  uint32_t now = millis();
  lastImuUs = micros();
  lastSpo2Ms = now;
  lastReconnectMs = now;
  lastStatsMs = now;
}

// =====================
// DATA READERS
// =====================
IMUData readIMUData() {
  IMUData data = {0,0,0,0,0,0};
  if (!imuReady) return data;
  data.aX = myIMU.readFloatAccelX();
  data.aY = myIMU.readFloatAccelY();
  data.aZ = myIMU.readFloatAccelZ();
  data.gX = myIMU.readFloatGyroX();
  data.gY = myIMU.readFloatGyroY();
  data.gZ = myIMU.readFloatGyroZ();
  return data;
}

// Reads one MAX30105 FIFO sample (Red+IR), draining any stale
// backlog first so the value returned is always the freshest one
// the sensor has, rather than whatever is sitting at the old read
// pointer. Returns the last known-good reading if the FIFO is
// currently empty (no new sample since the last call).
SensorData readRedIR() {
  if (!spo2Ready) return SensorData{0, 0};

  // FIFO_WR_PTR = 0x04, FIFO_RD_PTR = 0x06 (MAX30105/MAX30102 register map)
  Wire.beginTransmission(0x57);
  Wire.write(0x04);
  Wire.endTransmission(false);
  Wire.requestFrom(0x57, 1, true);
  uint8_t wrPtr = Wire.available() ? Wire.read() : 0;

  Wire.beginTransmission(0x57);
  Wire.write(0x06);
  Wire.endTransmission(false);
  Wire.requestFrom(0x57, 1, true);
  uint8_t rdPtr = Wire.available() ? Wire.read() : 0;

  uint8_t available = (wrPtr - rdPtr) & 0x1F; // FIFO depth is 32 samples

  if (available == 0) {
    return lastSpo2Data; // nothing new yet, reuse last good value
  }

  // Drain every stale sample except the newest one
  for (uint8_t i = 0; i < available - 1; i++) {
    Wire.beginTransmission(0x57);
    Wire.write(0x07);
    Wire.endTransmission();
    Wire.requestFrom(0x57, 6, true);
    while (Wire.available()) Wire.read();
  }

  // Read the freshest sample
  Wire.beginTransmission(0x57);
  Wire.write(0x07);
  Wire.endTransmission();
  Wire.requestFrom(0x57, 6, true);

  SensorData data = {0, 0};
  if (Wire.available() >= 6) {
    data.Red = (Wire.read() << 16 | Wire.read() << 8 | Wire.read()) & 0x3FFFF;
    data.IR  = (Wire.read() << 16 | Wire.read() << 8 | Wire.read()) & 0x3FFFF;
  }

  lastSpo2Data = data;
  return data;
}

// =====================
// MAIN LOOP
// =====================
void loop() {
  uint32_t nowUs = micros();
  uint32_t nowMs = millis();

  // Heartbeat if disconnected
  static uint32_t lastHeartbeat = 0;
  if (!Bluefruit.connected() && (nowMs - lastHeartbeat >= 2000)) {
    lastHeartbeat = nowMs;
    Serial.println("Advertising... Waiting for BLE connection.");
  }

  // --- RECONNECT LOGIC (Every 10 Seconds) ---
  if (nowMs - lastReconnectMs >= INTERVAL_RECONNECT_MS) {
    lastReconnectMs = nowMs;
    
    if (!spo2Ready) {
      Serial.println("Attempting SPO2 Reconnect...");
      initSPO2();
    }
    if (!imuReady) {
      Serial.println("Attempting IMU Reconnect...");
      initIMU();
    }
  }

  // --- 1. IMU @ 104Hz ---
  // Fixed-cadence scheduler: advances by the ideal interval each
  // time, rather than resetting to "now", so transient delays
  // (BLE/Serial stalls) don't permanently slow the average rate.
  if ((nowUs - lastImuUs) >= INTERVAL_IMU_US) {
    lastImuUs += INTERVAL_IMU_US;

    // If we've fallen badly behind (e.g. a long BLE stall), resync
    // instead of bursting through a pile of queued catch-up ticks.
    if ((nowUs - lastImuUs) > (IMU_MAX_BACKLOG_INTERVALS * INTERVAL_IMU_US)) {
      lastImuUs = nowUs - INTERVAL_IMU_US;
    }

    if (imuReady) {
      imuSamplesRead++; // Count the hardware read

      if (Bluefruit.connected()) {
        IMUData imu = readIMUData();
        char imuStr[80];
        snprintf(imuStr, sizeof(imuStr),
                "AX:%.2f AY:%.2f AZ:%.2f GX:%.1f GY:%.1f GZ:%.1f",
                imu.aX, imu.aY, imu.aZ, imu.gX, imu.gY, imu.gZ);
                
        if (imuChar.notify((uint8_t*)imuStr, strlen(imuStr))) {
            imuPacketsSent++;
        }
      }
    }
  }

  // --- 2. SPO2 @ 50Hz ---
  if (nowMs - lastSpo2Ms >= INTERVAL_SPO2_MS) {
    lastSpo2Ms = nowMs; 

    if (spo2Ready) {
      spo2SamplesRead++; // Count the hardware read

      if (Bluefruit.connected()) {
        SensorData data = readRedIR();
        char dataStr[40];
        snprintf(dataStr, sizeof(dataStr), "%ld,%ld", data.Red, data.IR);
        
        if (spo2Char.notify((uint8_t*)dataStr, strlen(dataStr))) {
            spo2PacketsSent++;
        }
      }
    }
  }

  // --- 3. DEBUG PRINT (Every 5 Seconds) ---
  if (nowMs - lastStatsMs >= 5000) {
      Serial.println();
      Serial.println("========== SENSOR & BLE DEBUG ==========");

      Serial.print("IMU Hardware Sampling Rate : ");
      Serial.print(imuSamplesRead / 5.0);
      Serial.println(" Hz");
      
      Serial.print("IMU BLE Notifications Sent : ");
      Serial.print(imuPacketsSent);
      Serial.print("  (Rate: ");
      Serial.print(imuPacketsSent / 5.0);
      Serial.println(" Hz)");

      Serial.println("----------------------------------------");

      Serial.print("SPO2 Hardware Sampling Rate: ");
      Serial.print(spo2SamplesRead / 5.0);
      Serial.println(" Hz");

      Serial.print("SPO2 BLE Notifications Sent: ");
      Serial.print(spo2PacketsSent);
      Serial.print("  (Rate: ");
      Serial.print(spo2PacketsSent / 5.0);
      Serial.println(" Hz)");

      Serial.println("========================================");

      // Reset counters
      imuSamplesRead  = 0;
      imuPacketsSent  = 0;
      spo2SamplesRead = 0;
      spo2PacketsSent = 0;
      lastStatsMs = nowMs;
  }
}
