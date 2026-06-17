#include <LSM6DS3.h>
#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>

// ================= OLED =================
#define SCREEN_WIDTH   128
#define SCREEN_HEIGHT   64
#define OLED_RESET      -1
#define SCREEN_ADDRESS  0x3C

Adafruit_SSD1306 display(
  SCREEN_WIDTH,
  SCREEN_HEIGHT,
  &Wire,
  OLED_RESET
);

// ================= IMU ==================
LSM6DS3 myIMU(I2C_MODE, 0x6A);

// ================= DATA =================
uint32_t sampleCount = 0;

void setup()
{
  Serial.begin(115200);
  while (!Serial);

  Wire.begin();

  // OLED INIT
  if (!display.begin(
        SSD1306_SWITCHCAPVCC,
        SCREEN_ADDRESS))
  {
    Serial.println("SSD1306 failed");
    while (1);
  }

  // IMU INIT
  if (myIMU.begin() != 0)
  {
    display.clearDisplay();
    display.setTextSize(1);
    display.setTextColor(SSD1306_WHITE);
    display.setCursor(20, 28);
    display.println("IMU ERROR");
    display.display();

    while (1);
  }

  // SPLASH
  display.clearDisplay();
  display.setTextSize(2);
  display.setCursor(8, 24);
  display.println("ParkinSense");
  display.display();

  delay(2000);
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

  sampleCount++;

  // ---------- SERIAL ----------
  Serial.print(sampleCount);
  Serial.print(",");

  Serial.print(gx);
  Serial.print(",");
  Serial.print(gy);
  Serial.print(",");
  Serial.println(gz);

  // ---------- OLED ----------
  display.clearDisplay();

  display.setTextSize(1);
  display.setTextColor(SSD1306_WHITE);

  // Header
  display.setCursor(0, 0);
  display.println("ParkinSense");

  display.drawLine(
      0,
      10,
      127,
      10,
      SSD1306_WHITE);

  // Motion value
  display.setCursor(0, 18);
  display.print("Motion:");

  display.setCursor(55, 18);
  display.print((int)motion);

  // Status
  display.setCursor(0, 32);
  display.print("Status:");

  if (motion > 20)
    display.print(" ACTIVE");
  else
    display.print(" IDLE");

  // Motion Bar
  display.drawRect(
      4,
      50,
      120,
      10,
      SSD1306_WHITE);

  int barWidth = map(
      constrain((int)motion, 0, 150),
      0,
      150,
      0,
      118);

  display.fillRect(
      5,
      51,
      barWidth,
      8,
      SSD1306_WHITE);

  display.display();

  delay(50);
}