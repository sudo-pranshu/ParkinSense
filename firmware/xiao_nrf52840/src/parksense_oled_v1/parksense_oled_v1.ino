#include <Wire.h>
#include <LSM6DS3.h>
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

void loop() {

  ax = imu.readFloatAccelX();
  ay = imu.readFloatAccelY();
  az = imu.readFloatAccelZ();

  gx = imu.readFloatGyroX();
  gy = imu.readFloatGyroY();
  gz = imu.readFloatGyroZ();

  sampleCount++;

  float motionMagnitude =
    abs(gx) +
    abs(gy) +
    abs(gz);

  if (motionMagnitude > 20) {
    motionState = "ACTIVE";
  }
  else {
    motionState = "IDLE";
  }

  // ===== SERIAL =====

  Serial.print(sampleCount);
  Serial.print(",");

  Serial.print(ax);
  Serial.print(",");
  Serial.print(ay);
  Serial.print(",");
  Serial.print(az);
  Serial.print(",");
  Serial.print(gx);
  Serial.print(",");
  Serial.print(gy);
  Serial.print(",");
  Serial.println(gz);

  // ===== OLED =====

  display.clearDisplay();

  display.setTextSize(1);

  display.setCursor(0, 0);
  display.println("ParkinSense");

  display.drawLine(
    0, 10,
    128, 10,
    SSD1306_WHITE
  );

  display.setCursor(0, 18);
  display.print("IMU: OK");

  display.setCursor(0, 32);
  display.print("Motion:");

  display.setCursor(55, 32);
  display.print(motionState);

  display.setCursor(0, 50);
  display.print("Samples:");

  display.setCursor(60, 50);
  display.print(sampleCount);

  display.display();

  delay(10); // ~100 Hz
}
