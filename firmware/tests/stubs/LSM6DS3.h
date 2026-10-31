#pragma once
#include <stdint.h>
enum { I2C_MODE = 1 };
enum status_t { IMU_SUCCESS = 0, IMU_HW_ERROR };
#define LSM6DS3_ACC_GYRO_OUTX_L_G 0x22
struct SensorSettings { uint8_t gyroEnabled, accelEnabled; uint16_t gyroRange, gyroSampleRate, accelRange, accelSampleRate, accelBandWidth; };
struct LSM6DS3 { SensorSettings settings; LSM6DS3(int, uint8_t){} status_t begin(){ return IMU_SUCCESS; }
  status_t readRegisterRegion(uint8_t*, uint8_t, uint8_t){ return IMU_SUCCESS; } };
