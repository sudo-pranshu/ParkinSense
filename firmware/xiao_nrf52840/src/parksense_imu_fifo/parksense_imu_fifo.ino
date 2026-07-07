#include "LSM6DS3.h"
#include "Wire.h"

// Initialize IMU on internal I2C
LSM6DS3 myIMU(I2C_MODE, 0x6A); 

// Map the hardware interrupt to the correct Nordic Pin (P0.11)
const int IMU_INT_PIN = PIN_LSM6DS3TR_C_INT1; 
volatile bool fifoWatermarkHit = false;

// Interrupt Service Routine: Keep it lightning fast!
void imuISR() {
    fifoWatermarkHit = true;
}

// --- HELPER FUNCTION: Read one 16-bit word ---
// Safely reads the FIFO doorway without breaking the Gyro/Accel alignment
int16_t readFifoWord() {
    uint8_t lowByte = 0;
    uint8_t highByte = 0;
    
    // Read 0x3E (latches data) then 0x3F (pops the queue)
    myIMU.readRegister(&lowByte, 0x3E);
    myIMU.readRegister(&highByte, 0x3F);
    
    return (int16_t)((highByte << 8) | lowByte);
}

void setup() {
    Serial.begin(115200);
    
    // Wait up to 3 seconds for Serial. If battery powered, it skips and proceeds.
    uint32_t t = millis();
    while (!Serial && (millis() - t < 3000)); 

    if (myIMU.begin() != 0) {
        Serial.println("IMU Initialization Error!");
        while (1);
    }

    // 0. FORCE MAIN SENSOR SETTINGS 
    // Lock Accel to 104Hz and +/- 2g (Multiplier: 0.061)
    myIMU.writeRegister(0x10, 0x40); 
    // Lock Gyro to 104Hz and +/- 2000 dps (Multiplier: 70.0)
    myIMU.writeRegister(0x11, 0x4C); 

    // 1. ROUTE SENSORS TO FIFO (No decimation)
    myIMU.writeRegister(0x08, 0x09); 

    // 2. SET WATERMARK THRESHOLD TO 1600 WORDS (0x0640)
    // 1600 words / 6 parameters / 104Hz = ~2.56 seconds of sleep
    myIMU.writeRegister(0x06, 0x40); // Lower 8 bits (0x40)
    myIMU.writeRegister(0x07, 0x06); // Upper 4 bits (0x06)
    
    // 3. ROUTE WATERMARK INTERRUPT TO PHYSICAL INT1 PIN
    myIMU.writeRegister(0x0D, 0x08);

    // 4. THE GHOST WIPE: Clear out any misaligned ghost memory
    myIMU.writeRegister(0x0A, 0x00); 
    delay(10);
    
    // 5. MASTER SWITCH: 104 Hz, Continuous Mode
    myIMU.writeRegister(0x0A, 0x46); 

    // 6. ARM THE MCU INTERRUPT
    pinMode(IMU_INT_PIN, INPUT);
    attachInterrupt(digitalPinToInterrupt(IMU_INT_PIN), imuISR, RISING);

    Serial.println("Tremor Engine Armed. MCU going to deep sleep...");
    Serial.println("---------------------------------------------------");
}

void loop() {
    if (fifoWatermarkHit) {
        fifoWatermarkHit = false;
        
        // 1. Check exact hardware stack depth
        uint8_t status1 = 0;
        uint8_t status2 = 0;
        myIMU.readRegister(&status1, 0x3A);
        myIMU.readRegister(&status2, 0x3B);
        uint16_t unreadWords = ((status2 & 0x0F) << 8) | status1;
        
        // 2. Calculate exactly how many complete 6-DoF snapshots exist (~266)
        int completeSnapshots = unreadWords / 6;

        Serial.print("Woke up! Extracting "); 
        Serial.print(completeSnapshots); 
        Serial.println(" snapshots from memory...");

        // 3. Extract batch dynamically to maintain perfect 6-word alignment
        for(int i = 0; i < completeSnapshots; i++) {
            
            int16_t rawGyroX = readFifoWord();
            int16_t rawGyroY = readFifoWord();
            int16_t rawGyroZ = readFifoWord();
            int16_t rawAccelX = readFifoWord();
            int16_t rawAccelY = readFifoWord();
            int16_t rawAccelZ = readFifoWord();
            
            // Print only the first snapshot of the 2.5s batch to avoid Serial bottlenecks
            if (i == 0) {
                float aX = rawAccelX * 0.061 / 1000.0;
                float aY = rawAccelY * 0.061 / 1000.0;
                float aZ = rawAccelZ * 0.061 / 1000.0;
                
                float gX = rawGyroX * 70.0 / 1000.0;
                float gY = rawGyroY * 70.0 / 1000.0;
                float gZ = rawGyroZ * 70.0 / 1000.0;
                Serial.print("  -> Snapshot 1 | Accel (g): X="); Serial.print(aX, 2);
                Serial.print(" Y="); Serial.print(aY, 2);
                Serial.print(" Z="); Serial.print(aZ, 2);
                Serial.print(" | Gyro (dps): X="); Serial.print(gX, 2);
                Serial.print(" Y="); Serial.print(gY, 2);
                Serial.print(" Z="); Serial.println(gZ, 2);
            }
        }
        Serial.println("Batch processed. MCU returning to sleep.");
        Serial.println("---------------------------------------------------");
    }
    
    // --- HALT CPU ---
    // MCU stays completely frozen here for ~2.56 seconds until IMU buffer fills
    __WFI(); 
}