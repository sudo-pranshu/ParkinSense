#include <LSM6DS3.h>
#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>

// ================= OLED =================

#define SCREEN_WIDTH 128
#define SCREEN_HEIGHT 64
#define OLED_RESET -1
#define SCREEN_ADDRESS 0x3C

Adafruit_SSD1306 display(
    SCREEN_WIDTH,
    SCREEN_HEIGHT,
    &Wire,
    OLED_RESET);

// ================= IMU =================

LSM6DS3 myIMU(I2C_MODE, 0x6A);

// ================= DATA =================

unsigned long startTime = 0;
uint32_t sampleCount = 0;

// ================= SETUP =================

void setup()
{
    Serial.begin(115200);

    Wire.begin();

    if (!display.begin(
            SSD1306_SWITCHCAPVCC,
            SCREEN_ADDRESS))
    {
        while (1);
    }

    if (myIMU.begin() != 0)
    {
        display.clearDisplay();
        display.setCursor(10, 30);
        display.println("IMU ERROR");
        display.display();

        while (1);
    }

    display.clearDisplay();

    display.setTextSize(2);
    display.setTextColor(SSD1306_WHITE);

    display.setCursor(5, 24);
    display.println("ParkinSense");

    display.display();

    delay(2000);

    startTime = millis();
}

// ================= LOOP =================

void loop()
{
    float ax = myIMU.readFloatAccelX();
    float ay = myIMU.readFloatAccelY();
    float az = myIMU.readFloatAccelZ();

    float gx = myIMU.readFloatGyroX();
    float gy = myIMU.readFloatGyroY();
    float gz = myIMU.readFloatGyroZ();

    sampleCount++;

    // ---------- SERIAL CSV ----------

    Serial.print(millis());
    Serial.print(",");

    Serial.print(ax, 4);
    Serial.print(",");

    Serial.print(ay, 4);
    Serial.print(",");

    Serial.print(az, 4);
    Serial.print(",");

    Serial.print(gx, 4);
    Serial.print(",");

    Serial.print(gy, 4);
    Serial.print(",");

    Serial.println(gz, 4);

    // ---------- TIMER ----------

    unsigned long elapsed =
        (millis() - startTime) / 1000;

    int minutes = elapsed / 60;
    int seconds = elapsed % 60;

    // ---------- MOTION ----------

    float motion =
        abs(gx) +
        abs(gy) +
        abs(gz);

    // ---------- OLED ----------

    display.clearDisplay();

    display.setTextSize(1);
    display.setTextColor(SSD1306_WHITE);

    display.setCursor(0, 0);
    display.println("ParkinSense");

    display.drawLine(
        0,
        10,
        127,
        10,
        SSD1306_WHITE);

    display.setCursor(0, 18);

    display.print("REC ");

    if (minutes < 10)
        display.print("0");

    display.print(minutes);
    display.print(":");

    if (seconds < 10)
        display.print("0");

    display.println(seconds);

    display.setCursor(0, 34);
    display.print("Samples: ");
    display.println(sampleCount);

    display.setCursor(0, 50);

    if (motion > 20)
        display.print("ACTIVE");
    else
        display.print("IDLE");

    display.display();

    delay(10);
}

