#include <Wire.h>
#include "LSM6DS3.h"

LSM6DS3 imu(I2C_MODE, 0x6A);

const uint16_t SAMPLE_RATE_HZ = 100;
const uint32_t SAMPLE_PERIOD_MS = 10;

uint32_t lastSample = 0;

void setup()
{
    Serial.begin(115200);

    while (!Serial);

    if (imu.begin() != 0)
    {
        Serial.println("IMU init failed");
        while (1);
    }

    Serial.println("timestamp,ax,ay,az,gx,gy,gz");

    lastSample = millis();
}

void loop()
{
    float gx = myIMU.readFloatGyroX();
    float gy = myIMU.readFloatGyroY();
    float gz = myIMU.readFloatGyroZ();

    float motion =
        abs(gx) +
        abs(gy) +
        abs(gz);

    int barWidth = map(
        constrain((int)motion, 0, 200),
        0,
        200,
        0,
        120
    );

    display.clearDisplay();

    display.setTextSize(1);

    display.setCursor(0, 0);
    display.println("ParkinSense");

    display.drawLine(
        0, 10,
        128, 10,
        SSD1306_WHITE
    );

    display.setCursor(0, 20);
    display.print("Motion:");

    display.setCursor(60, 20);
    display.print((int)motion);

    display.drawRect(
        4,
        40,
        120,
        12,
        SSD1306_WHITE
    );

    display.fillRect(
        4,
        40,
        barWidth,
        12,
        SSD1306_WHITE
    );

    display.display();

    delay(20);
}
