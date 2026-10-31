#pragma once
#include <stdint.h>
enum { BLENotify = 0x10 };
struct BLEService { BLEService(const char*){} void begin(){} };
struct BLECharacteristic { BLECharacteristic(const char*, int, int){} void begin(){} bool notify(const uint8_t*, uint16_t){ return true; } };
struct BLEDis { void setManufacturer(const char*){} void setModel(const char*){} void setFirmwareRev(const char*){} void begin(){} };
struct Periph_ { void setConnInterval(uint16_t, uint16_t){} };
struct Adv_ { void addService(BLEService&){} void addName(){} void restartOnDisconnect(bool){} void start(int){} };
struct Bluefruit_ { Periph_ Periph; Adv_ Advertising; void configPrphConn(int,int,int,int){} void begin(){} void setTxPower(int){} void setName(const char*){} bool connected(){ return true; } };
extern Bluefruit_ Bluefruit;
