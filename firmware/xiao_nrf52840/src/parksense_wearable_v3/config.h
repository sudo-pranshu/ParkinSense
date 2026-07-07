#pragma once

/*
 * ==========================================================
 * ParkinSense Wearable V3
 * Global Configuration
 * ==========================================================
 */

#include <Arduino.h>

/*----------------------------------------------------------
  Firmware
----------------------------------------------------------*/

#define FW_MAJOR               3
#define FW_MINOR               0

/*----------------------------------------------------------
  Device
----------------------------------------------------------*/

#define DEVICE_NAME            "ParkinSense"

/*----------------------------------------------------------
  Sampling
----------------------------------------------------------*/

constexpr uint32_t IMU_SAMPLE_RATE_HZ        = 100;
constexpr uint32_t IMU_SAMPLE_INTERVAL_US    = 10000;  // 1,000,000 / 100 Hz

constexpr uint32_t PPG_SAMPLE_RATE_HZ        = 100;

/*----------------------------------------------------------
  BLE
----------------------------------------------------------*/

#define BLE_SERVICE_UUID       "ABCD1234-0000-467A-9538-01F0652C74E0"
#define BLE_CHARACTERISTIC_UUID "ABCD1234-0001-467A-9538-01F0652C74E0"

constexpr uint16_t BLE_MTU = 247;

constexpr uint8_t BATCH_SIZE = 10;

/*----------------------------------------------------------
  IMU Scaling
----------------------------------------------------------*/

constexpr float ACCEL_SCALE = 8192.0f;
constexpr float GYRO_SCALE  = 131.0f;

/*----------------------------------------------------------
  MAX30102 Configuration
----------------------------------------------------------*/

constexpr uint8_t MAX_LED_BRIGHTNESS = 0x1F;

// sampleAverage=1: chip outputs every ADC conversion directly.
// With sampleAverage=4 the FIFO output rate = sampleRate/4, which
// caused getIR()/getRed() to block up to 40 ms per call → ~13 Hz.
constexpr uint8_t MAX_SAMPLE_AVERAGE = 1;  // FIX: was 4

constexpr uint8_t MAX_LED_MODE = 2;      // RED + IR

// Internal ADC rate. With sampleAverage=1, FIFO output = sampleRate.
// Use 400 Hz internally so the FIFO always has a fresh sample ready
// when our 100 Hz loop calls update().
constexpr uint16_t MAX_SAMPLE_RATE = 400;  // FIX: was 100 (too tight with avg=4)

constexpr uint16_t MAX_PULSE_WIDTH = 411;

constexpr uint16_t MAX_ADC_RANGE = 4096;

/*----------------------------------------------------------
  Finger Detection
----------------------------------------------------------*/

constexpr uint32_t FINGER_THRESHOLD = 50000;

/*----------------------------------------------------------
  Future Features
----------------------------------------------------------*/

constexpr bool ENABLE_PPG = true;

constexpr bool ENABLE_IMU = true;

constexpr bool ENABLE_BATTERY = false;

constexpr bool ENABLE_TEMPERATURE = false;
