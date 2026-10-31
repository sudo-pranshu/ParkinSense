// Build-time configuration for parkinsense_wearable (protocol v2).
#pragma once
#include <stdint.h>

#define PS_FIRMWARE_VERSION "5.0.0"

// Sampling ------------------------------------------------------------------
constexpr uint32_t SAMPLE_INTERVAL_US    = 9615;   // 104.0 Hz, identical to v4
constexpr uint8_t  MAX_CATCHUP_INTERVALS = 5;

// IMU: applied BEFORE imu.begin() (v4 assigned them after begin(), so the
// sensor ran at driver defaults: +-16 g, +-2000 dps, 416 Hz -- audit P0-3).
// ODR 104 Hz matches the host sample rate, so the sensor's own digital
// low-pass acts as the anti-alias filter and no software decimation is needed.
constexpr uint16_t IMU_ACCEL_RANGE_G     = 4;
constexpr uint16_t IMU_GYRO_RANGE_DPS    = 500;
constexpr uint16_t IMU_ODR_HZ            = 104;
constexpr uint16_t IMU_ACCEL_BW_HZ       = 50;

// PPG (MAX30102): unchanged sensor setup (100 SPS, LED 0x1F, 411 us, 4096 nA).
// v2 drains the FIFO on every IMU tick and places the newest sample in each
// slot (~100 distinct samples/s) instead of keeping one sample per 100 ms
// (10 Hz, aliased -- audit P0-2 / P1-7).
constexpr uint8_t  PPG_LED_POWER         = 0x1F;
constexpr uint8_t  PPG_SAMPLE_AVERAGE    = 1;
constexpr uint8_t  PPG_LED_MODE          = 2;      // red + IR
constexpr int      PPG_SAMPLE_RATE       = 100;
constexpr int      PPG_PULSE_WIDTH       = 411;
constexpr int      PPG_ADC_RANGE         = 4096;

// Finger gate (behaviour preserved from v4; set false to stream IMU data
// without a finger on the PPG sensor, e.g. for tremor-only monitoring).
constexpr bool     REQUIRE_FINGER_FOR_STREAMING = true;
constexpr uint32_t FINGER_THRESHOLD_IR   = 50000;
constexpr uint8_t  FINGER_DEBOUNCE_COUNT = 3;
constexpr uint32_t FINGER_POLL_INTERVAL_MS = 250;

// Robustness / power ----------------------------------------------------------
constexpr uint32_t SENSOR_RETRY_MS       = 10000;
// Yield to the RTOS (FreeRTOS idle -> WFE sleep on the nRF52) when the next
// sample is further away than this. Effect on current is NOT measured yet --
// see docs/validation/HARDWARE_TEST_PROCEDURE.md (H5).
constexpr uint32_t YIELD_THRESHOLD_US    = 2000;

// BLE: request a 7.5-15 ms connection interval; ~10.4 notifications/s.
constexpr uint16_t CONN_INTERVAL_MIN     = 6;      // x1.25 ms
constexpr uint16_t CONN_INTERVAL_MAX     = 12;
