if ((nowUs - lastSampleUs) < SAMPLE_INTERVAL_US)
{
    return;
}

lastSampleUs += SAMPLE_INTERVAL_US;

float ax_f = imu.readFloatAccelX();
float ay_f = imu.readFloatAccelY();
float az_f = imu.readFloatAccelZ();

float gx_f = imu.readFloatGyroX();
float gy_f = imu.readFloatGyroY();
float gz_f = imu.readFloatGyroZ();

if (batchIndex == 0)
{
    packet.header.timestamp_us = micros();
}

packet.samples[batchIndex].ax =
    (int16_t)(ax_f * 8192.0f);

packet.samples[batchIndex].ay =
    (int16_t)(ay_f * 8192.0f);

packet.samples[batchIndex].az =
    (int16_t)(az_f * 8192.0f);

packet.samples[batchIndex].gx =
    (int16_t)(gx_f * 131.0f);

packet.samples[batchIndex].gy =
    (int16_t)(gy_f * 131.0f);

packet.samples[batchIndex].gz =
    (int16_t)(gz_f * 131.0f);

batchIndex++;
sampleCounter++;

if (batchIndex >= BATCH_SIZE)
{
    if (Bluefruit.connected())
    {
        imuChar.notify(
            (uint8_t*)&packet,
            sizeof(packet)
        );
    }

    batchIndex = 0;
}

if (millis() - lastRateReport >= 1000)
{
    Serial.print("RATE=");
    Serial.println(sampleCounter);

    sampleCounter = 0;
    lastRateReport = millis();
}