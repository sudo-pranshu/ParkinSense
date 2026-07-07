import asyncio
import time
from bleak import BleakScanner, BleakClient

# --- Configuration ---
DEVICE_NAME = "Wearables"

# Bluefruit library expands your 16-bit UUIDs (0x27A8 and 0x2A8D) 
# into standard 128-bit Bluetooth SIG UUIDs.
IMU_UUID = "000027a8-0000-1000-8000-00805f9b34fb"
SPO2_UUID = "00002a8d-0000-1000-8000-00805f9b34fb"

# --- Globals for counting ---
imu_packets = 0
spo2_packets = 0

# --- Callbacks ---
# These functions run every time a new packet arrives from the nRF52
def imu_notification_handler(sender, data):
    global imu_packets
    imu_packets += 1
    
    # Optional: If you want to see the actual string data flooding in, uncomment this:
    # print(f"[IMU] {data.decode('utf-8', errors='ignore')}")

def spo2_notification_handler(sender, data):
    global spo2_packets
    spo2_packets += 1
    
    # Optional: If you want to see the actual string data flooding in, uncomment this:
    # print(f"[SPO2] {data.decode('utf-8', errors='ignore')}")

async def main():
    global imu_packets, spo2_packets
    
    print(f"Scanning for '{DEVICE_NAME}'...")
    
    # 1. Scan for the specific device
    device = await BleakScanner.find_device_by_name(DEVICE_NAME, timeout=10.0)
    
    if not device:
        print(f"Could not find a device named '{DEVICE_NAME}'. Make sure it is turned on and not connected to your phone.")
        return

    print(f"Found '{DEVICE_NAME}' at {device.address}! Connecting...")

    # 2. Connect and subscribe
    async with BleakClient(device) as client:
        print("Connected successfully!")
        
        # Enable notifications on both characteristics
        await client.start_notify(IMU_UUID, imu_notification_handler)
        await client.start_notify(SPO2_UUID, spo2_notification_handler)
        
        print("Subscribed to IMU and SPO2 streams. Gathering data...\n")
        
        # 3. Main loop: calculate and print the rate every 5 seconds
        while True:
            # Sleep for 5 seconds while data streams in the background
            await asyncio.sleep(5.0)
            
            # Calculate rates
            imu_rate = imu_packets / 5.0
            spo2_rate = spo2_packets / 5.0
            
            print("========== LAPTOP RECEPTION STATS ==========")
            print(f"IMU Packets Received : {imu_packets}  (Rate: {imu_rate:.1f} Hz)")
            print(f"SPO2 Packets Received: {spo2_packets}  (Rate: {spo2_rate:.1f} Hz)")
            print("============================================\n")
            
            # Reset counters for the next 5-second window
            imu_packets = 0
            spo2_packets = 0

if __name__ == "__main__":
    # Run the async main loop
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nScript manually terminated.")

        #firmware/xiao_nrf52840/src/parksense_ble_stream_v1/receiver.py