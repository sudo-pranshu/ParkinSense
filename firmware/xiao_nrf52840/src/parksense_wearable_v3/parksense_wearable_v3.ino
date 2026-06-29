/*
==========================================================
ParkinSense Wearable V3

Milestone 1

MAX30102 Validation Firmware
==========================================================
*/

#include <Arduino.h>
#include <Wire.h>

#include "config.h"
#include "max30102_sensor.h"

MAX30102Sensor ppg;

uint32_t lastSample = 0;

void setup()
{
    Serial.begin(115200);

    while (!Serial)
    {
        delay(10);
    }

    Wire.begin();

    Serial.println();
    Serial.println("====================================");
    Serial.println("ParkinSense Wearable V3");
    Serial.println("MAX30102 Validation");
    Serial.println("====================================");

    if (!ppg.begin())
    {
        Serial.println("PPG INIT FAILED");

        while (1)
        {
            delay(1000);
        }
    }

    lastSample = millis();
}

void loop()
{
    if (millis() - lastSample < 10)
    {
        return;
    }

    lastSample = millis();

    ppg.update();

    Serial.print("IR: ");
    Serial.print(ppg.getIR());

    Serial.print("   RED: ");
    Serial.print(ppg.getRed());

    Serial.print("   Finger: ");

    if (ppg.fingerDetected())
        Serial.println("YES");
    else
        Serial.println("NO");
}