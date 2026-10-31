// Minimal API stubs: syntax/type-check the sketch on a host compiler.
// Not a simulator; does not replace compiling with the nRF52 core.
#pragma once
#include <stdint.h>
#include <stddef.h>
#include <math.h>
struct SerialStub { void begin(long){} explicit operator bool() const { return true; }
  template <class T> void print(T){} template <class T> void println(T){} void println(){} };
extern SerialStub Serial;
uint32_t millis(); uint32_t micros(); void delay(uint32_t);
