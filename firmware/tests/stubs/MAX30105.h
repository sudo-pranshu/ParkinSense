#pragma once
#include <stdint.h>
#include "Wire.h"
#define I2C_SPEED_FAST 400000
struct MAX30105 { bool begin(TwoWire&, uint32_t){ return true; } void setup(uint8_t,uint8_t,uint8_t,int,int,int){}
  uint16_t check(){ return 0; } uint8_t available(){ return 0; } uint32_t getFIFOIR(){ return 0; }
  uint32_t getFIFORed(){ return 0; } void nextSample(){} };
