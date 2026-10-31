// ParkinSense wearable firmware 5.0.0 -- BLE protocol v2.
// Board: Seeed XIAO nRF52840 Sense (Adafruit nRF52 / Seeed nRF52 core).
// Libraries: Seeed_Arduino_LSM6DS3, SparkFun MAX3010x.
//
// STATUS: written and host-tested (packing logic) but NOT YET FLASHED OR
// MEASURED on hardware. ble_stream_v4 (firmware/legacy/) remains the last
// hardware-verified build. Validate with docs/validation/HARDWARE_TEST_PROCEDURE.md
// before relying on this build.
//
// Changes vs ble_stream_v4 (audit references in docs/audit/TRANSFORMATION_REPORT.md):
//   P0-3  IMU ranges/ODR set before begin(): +-4 g, +-500 dps, 104 Hz ODR.
//   P0-3  one 12-byte burst read per sample (was 6 separate register reads);
//         saturating conversion + clip flags (v4 wrapped above 250 dps).
//   P0-2  PPG FIFO drained every IMU tick; newest sample per slot (~100 Hz).
//   P1-8  16-bit packet sequence number in the former reserved field;
//         failed notify() reported in the next packet's flags.
//   P0-4  loop yields to the RTOS between samples (power effect unmeasured).
//   --    firmware revision exposed via the standard Device Information
//         Service so the host records it automatically.
// Wire framing (208 bytes) is unchanged; header.version = 2 tells the host
// which scale factors apply.

#include <Arduino.h>
#include <bluefruit.h>
#include <Wire.h>
#include "LSM6DS3.h"
#include <MAX30105.h>
#include "config.h"
#include "packet.h"

LSM6DS3 imu(I2C_MODE, 0x6A);
MAX30105 ppg;

BLEService imuService("ABCD1234-0000-467A-9538-01F0652C74E0");
BLECharacteristic imuChar("ABCD1234-0001-467A-9538-01F0652C74E0", BLENotify, 244);
BLEDis bledis;

static ps::Packet packet;
static ps::Scheduler sched = {SAMPLE_INTERVAL_US, 0, MAX_CATCHUP_INTERVALS};
static uint8_t  batchIndex = 0;
static uint16_t seq = 0;
static uint8_t  pendingFlags = 0;      // flags carried into the next packet
static bool     imuReady = false, ppgReady = false, systemActive = !REQUIRE_FINGER_FOR_STREAMING;
static uint32_t latestIR = 0, latestRED = 0;
static uint8_t  fingerAbove = 0, fingerBelow = 0;
static uint32_t lastFingerMs = 0, lastRetryMs = 0, lastReportMs = 0, samplesThisSecond = 0;

static void initIMU() {
  imu.settings.accelEnabled    = 1;
  imu.settings.gyroEnabled     = 1;
  imu.settings.accelRange      = IMU_ACCEL_RANGE_G;
  imu.settings.gyroRange       = IMU_GYRO_RANGE_DPS;
  imu.settings.accelSampleRate = IMU_ODR_HZ;
  imu.settings.gyroSampleRate  = IMU_ODR_HZ;
  imu.settings.accelBandWidth  = IMU_ACCEL_BW_HZ;
  imuReady = (imu.begin() == 0);         // begin() writes `settings` to the device
  Serial.println(imuReady ? "IMU OK (4g/500dps/104Hz)" : "IMU INIT FAILED (will retry)");
}

static void initPPG() {
  ppgReady = ppg.begin(Wire, I2C_SPEED_FAST);
  if (ppgReady) {
    ppg.setup(PPG_LED_POWER, PPG_SAMPLE_AVERAGE, PPG_LED_MODE, PPG_SAMPLE_RATE,
              PPG_PULSE_WIDTH, PPG_ADC_RANGE);
  }
  Serial.println(ppgReady ? "MAX30102 OK" : "MAX30102 INIT FAILED (will retry)");
}

// Drain the PPG FIFO; keep the newest pair. Returns true if any new sample arrived.
static bool drainPPG() {
  if (!ppgReady) return false;
  bool fresh = false;
  ppg.check();
  while (ppg.available()) {
    latestIR = ppg.getFIFOIR();
    latestRED = ppg.getFIFORed();
    ppg.nextSample();
    fresh = true;
  }
  return fresh;
}

static void updateFingerGate(uint32_t nowMs) {
  if (!REQUIRE_FINGER_FOR_STREAMING || !ppgReady) return;
  if (nowMs - lastFingerMs < FINGER_POLL_INTERVAL_MS) return;
  lastFingerMs = nowMs;
  bool on = latestIR > FINGER_THRESHOLD_IR;
  if (!systemActive) {
    fingerAbove = on ? fingerAbove + 1 : 0;
    if (fingerAbove >= FINGER_DEBOUNCE_COUNT) {
      systemActive = true; fingerAbove = 0; batchIndex = 0;
      sched.next_us = micros();
      Serial.println("finger detected -> streaming");
    }
  } else {
    fingerBelow = on ? 0 : fingerBelow + 1;
    if (fingerBelow >= FINGER_DEBOUNCE_COUNT) {
      systemActive = false; fingerBelow = 0; batchIndex = 0;
      Serial.println("finger removed -> idle");
    }
  }
}

void setup() {
  Serial.begin(115200);
  uint32_t t0 = millis();
  while (!Serial && millis() - t0 < 3000) delay(10);

  Wire.begin();
  Wire.setClock(400000);
  initIMU();
  initPPG();

  Bluefruit.configPrphConn(247, 247, 6, 6);
  Bluefruit.begin();
  Bluefruit.setTxPower(4);
  Bluefruit.setName("ParkinSense");
  Bluefruit.Periph.setConnInterval(CONN_INTERVAL_MIN, CONN_INTERVAL_MAX);

  bledis.setManufacturer("ParkinSense");
  bledis.setModel("XIAO nRF52840 Sense");
  bledis.setFirmwareRev(PS_FIRMWARE_VERSION);
  bledis.begin();

  imuService.begin();
  imuChar.begin();
  Bluefruit.Advertising.addService(imuService);
  Bluefruit.Advertising.addName();
  Bluefruit.Advertising.restartOnDisconnect(true);
  Bluefruit.Advertising.start(0);

  sched.next_us = micros();
  lastRetryMs = lastFingerMs = lastReportMs = millis();
  Serial.println("ParkinSense " PS_FIRMWARE_VERSION " ready (protocol v2)");
}

void loop() {
  uint32_t nowMs = millis();

  if (nowMs - lastRetryMs >= SENSOR_RETRY_MS) {
    lastRetryMs = nowMs;
    if (!imuReady) initIMU();
    if (!ppgReady) initPPG();
  }

  if (!systemActive) {
    // Idle: poll the finger sensor only. v4 behaviour preserved; the sensor
    // keeps running so a finger can be detected (no INT pin is wired).
    drainPPG();
    updateFingerGate(nowMs);
    delay(10);
    return;
  }

  uint32_t nowUs = micros();
  bool disc = false;
  if (!sched.due(nowUs, disc)) {
    uint32_t rem = sched.remaining_us(nowUs);
    if (rem > YIELD_THRESHOLD_US) delay((rem - 1000) / 1000);   // RTOS sleep
    return;
  }
  if (disc) pendingFlags |= ps::FLAG_TIME_DISCONTINUITY;

  if (batchIndex == 0) {
    packet.header.version = ps::PROTOCOL_VERSION;
    packet.header.flags = pendingFlags;
    packet.header.seq = seq;
    packet.header.timestamp_us = micros();
    pendingFlags = 0;
  }

  ps::Sample &s = packet.samples[batchIndex];
  uint8_t raw[12];
  if (imuReady && imu.readRegisterRegion(raw, LSM6DS3_ACC_GYRO_OUTX_L_G, 12) == IMU_SUCCESS) {
    ps::packImu(raw, s, packet.header.flags);
  } else {
    s.ax = s.ay = s.az = s.gx = s.gy = s.gz = 0;
    packet.header.flags |= ps::FLAG_IMU_FAULT;
  }

  bool fresh = drainPPG();
  if (!ppgReady) packet.header.flags |= ps::FLAG_PPG_FAULT;
  else if (!fresh) packet.header.flags |= ps::FLAG_PPG_STALE;
  s.ir = latestIR;
  s.red = latestRED;
  updateFingerGate(nowMs);
  if (!systemActive) return;          // finger removed mid-batch: discard partial batch

  samplesThisSecond++;
  if (++batchIndex >= ps::BATCH_SIZE) {
    batchIndex = 0;
    if (Bluefruit.connected()) {
      if (!imuChar.notify((uint8_t *)&packet, sizeof(packet))) {
        pendingFlags |= ps::FLAG_PREV_NOTIFY_FAILED;
      }
    }
    seq++;                              // increments even when not connected/sent
  }

  if (nowMs - lastReportMs >= 1000) {
    Serial.print("RATE="); Serial.print(samplesThisSecond);
    Serial.print(" IR="); Serial.print(latestIR);
    Serial.print(" SEQ="); Serial.print(seq);
    Serial.print(" BLE="); Serial.println(Bluefruit.connected() ? 1 : 0);
    samplesThisSecond = 0;
    lastReportMs = nowMs;
  }
}
