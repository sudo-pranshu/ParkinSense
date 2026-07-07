import asyncio
import struct
from bleak import BleakScanner, BleakClient

# --- Configuration ---
DEVICE_NAME = "ParkinSense"
IMU_CHAR_UUID = "ABCD1234-0001-467A-9538-01F0652C74E0"

# --- Globals for counting ---
batches_received = 0
samples_received = 0

# --- Struct Unpacking Variables ---
# Header: version(uint8), flags(uint8), reserved(uint16), timestamp(uint32) = 8 bytes
HEADER_FORMAT = '<BBHI' 
# Sample: 6 int16_t (IMU) + 2 uint32_t (SpO2) = 20 bytes
SAMPLE_FORMAT = '<hhhhhhII' 

HEADER_SIZE = struct.calcsize(HEADER_FORMAT) # 8 bytes
SAMPLE_SIZE = struct.calcsize(SAMPLE_FORMAT) # 20 bytes
BATCH_SIZE = 10
EXPECTED_PAYLOAD_SIZE = HEADER_SIZE + (BATCH_SIZE * SAMPLE_SIZE) # 208 bytes

def notification_handler(sender, data):
    global batches_received, samples_received
    
    if len(data) != EXPECTED_PAYLOAD_SIZE:
        print(f"Dropped malformed packet: got {len(data)} bytes, expected {EXPECTED_PAYLOAD_SIZE}")
        return
    
    batches_received += 1
    samples_received += BATCH_SIZE
    
    # 1. Unpack the header (8 bytes)
    version, flags, reserved, timestamp_us = struct.unpack_from(HEADER_FORMAT, data, offset=0)
    
    # 2. Unpack the 10 samples in this batch
    offset = HEADER_SIZE 
    
    for _ in range(BATCH_SIZE):
        ax, ay, az, gx, gy, gz, ir, red = struct.unpack_from(SAMPLE_FORMAT, data, offset)
        
        # --- Data is ready here! ---
        # You can append it to a list, write to a CSV, or feed a live plot here.
        
        # Move the offset forward by 20 bytes for the next sample
        offset += SAMPLE_SIZE

async def main():
    global batches_received, samples_received
    
    print(f"Scanning for '{DEVICE_NAME}'...")
    
    device = await BleakScanner.find_device_by_name(DEVICE_NAME, timeout=10.0)
    
    if not device:
        print(f"Could not find '{DEVICE_NAME}'. Ensure it is advertising and not paired to your phone.")
        return

    print(f"Found '{DEVICE_NAME}' at {device.address}! Connecting...")

    async with BleakClient(device) as client:
        print("Connected successfully!")
        
        await client.start_notify(IMU_CHAR_UUID, notification_handler)
        print(f"Subscribed to binary stream. Expecting {EXPECTED_PAYLOAD_SIZE}-byte packets.\n")
        
        # Print reception rates every 5 seconds
        while True:
            await asyncio.sleep(5.0)
            
            batch_rate = batches_received / 5.0
            sample_rate = samples_received / 5.0
            
            print("========== BLE RECEPTION STATS ==========")
            print(f"Data Rate : {batch_rate:.1f} packets/sec ({sample_rate:.1f} samples/sec)")
            print("=========================================\n")
            
            # Reset counters for the next window
            batches_received = 0
            samples_received = 0

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nScript manually terminated.")