#include "max30102_sensor.h"

#include "config.h"

bool MAX30102Sensor::begin()
{

    if (!sensor.begin(Wire, I2C_SPEED_FAST))
    {
        Serial.println("MAX30102 INIT FAILED");
        return false;
    }

    sensor.setup(

        MAX_LED_BRIGHTNESS,

        MAX_SAMPLE_AVERAGE,

        MAX_LED_MODE,

        MAX_SAMPLE_RATE,

        MAX_PULSE_WIDTH,

        MAX_ADC_RANGE

    );

    sensor.enableDIETEMPRDY();

    Serial.println("MAX30102 READY");

    return true;
}

bool MAX30102Sensor::update()
{
    sensor.check();

    if (!sensor.available())
    {
        return false;
    }

    red = sensor.getFIFORed();
    ir  = sensor.getFIFOIR();

    sensor.nextSample();

    finger = ir > FINGER_THRESHOLD;

    return true;
}

uint32_t MAX30102Sensor::getIR() const
{
    return ir;
}

uint32_t MAX30102Sensor::getRed() const
{
    return red;
}

bool MAX30102Sensor::fingerDetected() const
{
    return finger;
}
