#include <Wire.h>
#include <LSM6DS3.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>

// ================= OLED =================

#define SCREEN_WIDTH 128
#define SCREEN_HEIGHT 64
#define OLED_RESET -1
#define SCREEN_ADDRESS 0x3C

unsigned long startTime = 0;
uint32_t sampleCount = 0;

Adafruit_SSD1306 display(
  SCREEN_WIDTH,
  SCREEN_HEIGHT,
  &Wire,
  OLED_RESET
);

// ================= IMU =================

LSM6DS3 imu(I2C_MODE, 0x6A);

// ================= VARIABLES =================

uint32_t sampleCount = 0;

float ax, ay, az;
float gx, gy, gz;

String motionState = "IDLE";

// ================= SETUP =================

void setup() {
  startTime = millis();
  Serial.begin(115200);

  Wire.begin();

  if (!display.begin(
      SSD1306_SWITCHCAPVCC,
      SCREEN_ADDRESS)) {

    while (1);
  }

  if (imu.begin() != 0) {

    display.clearDisplay();

    display.setCursor(0, 20);
    display.setTextSize(1);

    display.println("IMU ERROR");

    display.display();

    while (1);
  }

  display.clearDisplay();

  display.setTextSize(2);
  display.setCursor(8, 20);

  display.println("ParkinSense");

  display.display();

  delay(2000);
}

// ================= LOOP =================

void loop()
{
  float gx = myIMU.readFloatGyroX();
  float gy = myIMU.readFloatGyroY();
  float gz = myIMU.readFloatGyroZ();

  float motion =
      abs(gx) +
      abs(gy) +
      abs(gz);

  sampleCount++;

  unsigned long elapsed =
      (millis() - startTime) / 1000;

  int minutes = elapsed / 60;
  int seconds = elapsed % 60;

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

  // TIMER
  display.setCursor(0, 18);
  display.print("Time: ");

  if (minutes < 10)
      display.print("0");

  display.print(minutes);
  display.print(":");

  if (seconds < 10)
      display.print("0");

  display.println(seconds);

  // SAMPLE COUNT
  display.setCursor(0, 34);
  display.print("Samples: ");
  display.println(sampleCount);

  // MOTION STATUS
  display.setCursor(0, 50);

  if (motion > 20)
      display.print("ACTIVE");
  else
      display.print("IDLE");

  display.display();

  delay(10);
}