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

constexpr uint32_t IMU_SAMPLE_RATE_HZ = 104;
constexpr uint32_t IMU_SAMPLE_INTERVAL_US = 9615;

constexpr uint32_t PPG_SAMPLE_RATE_HZ = 100;

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

constexpr uint8_t MAX_SAMPLE_AVERAGE = 4;

constexpr uint8_t MAX_LED_MODE = 2;      // RED + IR

constexpr uint16_t MAX_SAMPLE_RATE = 100;

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
