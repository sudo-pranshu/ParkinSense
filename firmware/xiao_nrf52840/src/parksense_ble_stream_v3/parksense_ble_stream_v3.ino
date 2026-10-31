/*
  MQ-9 / MQ-135 voltage and resistance logger for classic ESP32 (ESP32-WROOM-32)
  Arduino-ESP32 core; logs CSV to an SPI microSD card.

  Default wiring assumed:
    MQ module AO -- 12k resistor --+--> MCP6002 buffer non-inverting input
                                  |
                                10k resistor
                                  |
                                 GND
    MCP6002 buffer output -> ESP32 GPIO34
    Divider/buffer GND, MQ GND, ESP32 GND and SD GND must be common.

  Classic ESP32 VSPI pins for microSD (configured explicitly below):
    SD SCK  -> GPIO18
    SD MISO -> GPIO19
    SD MOSI -> GPIO23
    SD CS   -> GPIO5

  IMPORTANT:
  - Sensor AO is reconstructed from the divider ratio. The assumed divider is
    12k (top) and 10k (bottom), so V_AO ~= V_GPIO34 * 2.2.
  - The Rs estimate is valid only when MQ AO is the direct Rs/RL junction of
    the usual MQ sensing divider. Set MQ_MODULE_RL_OHMS to the actual onboard
    load resistor. The external 12k+10k divider loads AO, so the code includes
    that 22k path in parallel with the module's RL when calculating Rs.
  - If you do not know the module RL/topology, set CALCULATE_RS to false; the
    CSV will still contain raw ADC, measured voltage and reconstructed AO.
  - This does NOT calculate gas concentration in ppm. That requires R0
    calibration and gas-specific curve parameters.
*/

#include <Arduino.h>
#include <SPI.h>
#include <SD.h>
#include <math.h>

// ---------- USER CONFIGURATION ----------
const char *SENSOR_NAME = "MQ135";       // Change to "MQ9" when testing MQ-9
const char *LOG_FILE_PATH = "/mq_log.csv";

constexpr int SENSOR_ADC_PIN = 34;        // ADC1_CH6, input-only pin on classic ESP32
constexpr int SD_CS_PIN   = 5;
constexpr int SD_SCK_PIN  = 18;
constexpr int SD_MISO_PIN = 19;
constexpr int SD_MOSI_PIN = 23;

constexpr uint32_t LOG_INTERVAL_MS = 1000; // One record per second
constexpr uint8_t  NUM_ADC_SAMPLES = 16;   // Average this many measurements

// External AO protection divider: AO -- R_TOP -- ADC node -- R_BOTTOM -- GND
constexpr float DIVIDER_R_TOP_OHMS    = 12000.0f;
constexpr float DIVIDER_R_BOTTOM_OHMS = 10000.0f;

// Sensor sensing-circuit supply and onboard RL. Change RL to the ACTUAL value
// from the MQ module schematic/marking, not the comparator potentiometer.
constexpr float MQ_VC_VOLTS = 5.0f;
constexpr float MQ_MODULE_RL_OHMS = 10000.0f;  // Example only; verify your module
constexpr bool  CALCULATE_RS = true;           // Set false if RL/topology unknown

// ---------- INTERNAL STATE ----------
uint32_t lastLogMs = 0;

struct Reading {
  uint16_t raw;
  uint32_t adcMilliVolts;
  float adcVolts;
  float reconstructedAoVolts;
  float estimatedRsOhms;
};

float parallelResistance(float r1, float r2) {
  if (r1 <= 0.0f || r2 <= 0.0f) return 0.0f;
  return 1.0f / ((1.0f / r1) + (1.0f / r2));
}

Reading readSensor() {
  uint32_t rawSum = 0;
  uint64_t milliVoltSum = 0;

  for (uint8_t i = 0; i < NUM_ADC_SAMPLES; ++i) {
    rawSum += static_cast<uint16_t>(analogRead(SENSOR_ADC_PIN));
    milliVoltSum += analogReadMilliVolts(SENSOR_ADC_PIN);
    delay(2);
  }

  Reading r{};
  r.raw = static_cast<uint16_t>(rawSum / NUM_ADC_SAMPLES);
  r.adcMilliVolts = static_cast<uint32_t>(milliVoltSum / NUM_ADC_SAMPLES);
  r.adcVolts = r.adcMilliVolts / 1000.0f;

  const float dividerRatio =
      (DIVIDER_R_TOP_OHMS + DIVIDER_R_BOTTOM_OHMS) / DIVIDER_R_BOTTOM_OHMS;
  r.reconstructedAoVolts = r.adcVolts * dividerRatio;
  r.estimatedRsOhms = NAN;

  if (CALCULATE_RS && MQ_MODULE_RL_OHMS > 0.0f &&
      r.reconstructedAoVolts > 0.005f &&
      r.reconstructedAoVolts < MQ_VC_VOLTS) {
    // The external divider presents a (Rtop + Rbottom) load from AO to GND.
    // If AO is the direct Rs/RL junction, this path is in parallel with RL.
    const float externalDividerLoad =
        DIVIDER_R_TOP_OHMS + DIVIDER_R_BOTTOM_OHMS;
    const float effectiveRl = parallelResistance(
        MQ_MODULE_RL_OHMS, externalDividerLoad);
    r.estimatedRsOhms = effectiveRl *
        ((MQ_VC_VOLTS / r.reconstructedAoVolts) - 1.0f);

    if (r.estimatedRsOhms < 0.0f) {
      r.estimatedRsOhms = NAN;
    }
  }

  return r;
}

bool openLogAndWriteHeaderIfNeeded() {
  File file = SD.open(LOG_FILE_PATH, FILE_APPEND);
  if (!file) {
    Serial.println("ERROR: Could not open the CSV log file on the SD card.");
    return false;
  }

  if (file.size() == 0) {
    file.println("elapsed_ms,sensor,adc_gpio,adc_raw,adc_pin_mV,reconstructed_AO_V,estimated_Rs_ohm");
    file.flush();
  }
  file.close();
  return true;
}

void logOneSample(uint32_t elapsedMs) {
  const Reading r = readSensor();

  Serial.printf("t=%lu ms | %s | ADC=%u | pin=%.3f V | AO~=%.3f V | Rs~=",
                static_cast<unsigned long>(elapsedMs), SENSOR_NAME,
                r.raw, r.adcVolts, r.reconstructedAoVolts);
  if (isfinite(r.estimatedRsOhms)) {
    Serial.printf("%.1f ohm\n", r.estimatedRsOhms);
  } else {
    Serial.println("NA (check RL/topology or enable calculation)");
  }

  File file = SD.open(LOG_FILE_PATH, FILE_APPEND);
  if (!file) {
    Serial.println("ERROR: Failed to open CSV for writing; check SD card/wiring.");
    return;
  }

  file.printf("%lu,%s,%d,%u,%lu,%.4f,",
              static_cast<unsigned long>(elapsedMs), SENSOR_NAME,
              SENSOR_ADC_PIN, r.raw,
              static_cast<unsigned long>(r.adcMilliVolts),
              r.reconstructedAoVolts);
  if (isfinite(r.estimatedRsOhms)) {
    file.printf("%.3f\n", r.estimatedRsOhms);
  } else {
    file.println("NA");
  }
  file.flush();
  file.close();
}

void setup() {
  Serial.begin(115200);
  delay(800);
  Serial.println();
  Serial.println("MQ sensor SD logger starting...");

  analogReadResolution(12);  // Raw ADC values nominally range from 0 to 4095
  analogSetPinAttenuation(SENSOR_ADC_PIN, ADC_11db);
  pinMode(SENSOR_ADC_PIN, INPUT);

  SPI.begin(SD_SCK_PIN, SD_MISO_PIN, SD_MOSI_PIN, SD_CS_PIN);
  if (!SD.begin(SD_CS_PIN, SPI, 4000000)) {
    Serial.println("ERROR: SD card initialization failed.");
    Serial.println("Check FAT32 format, SD module voltage/logic compatibility, CS and SPI wiring.");
    while (true) delay(1000);
  }

  Serial.printf("SD card initialized; size = %llu MB\n",
                SD.cardSize() / (1024ULL * 1024ULL));

  if (!openLogAndWriteHeaderIfNeeded()) {
    while (true) delay(1000);
  }

  Serial.printf("Logging to %s once every %lu ms. Open Serial Monitor at 115200 baud.\n",
                LOG_FILE_PATH, static_cast<unsigned long>(LOG_INTERVAL_MS));
  Serial.println("Power-cycle elapsed_ms restarts at zero; previous records are appended.");
}

void loop() {
  const uint32_t now = millis();
  if (now - lastLogMs >= LOG_INTERVAL_MS) {
    lastLogMs = now;
    logOneSample(now);
  }
}