import asyncio
import struct
from bleak import BleakClient, BleakScanner

# Bleak prefers lowercase UUIDs for cross-platform stability
SERVICE_UUID = "abcd1234-0000-467a-9538-01f0652c74e0"
CHARACTERISTIC_UUID = "abcd1234-0001-467a-9538-01f0652c74e0"

# Global trackers to verify 0% packet loss
expected_sequence_id = -1
total_samples_received = 0
total_packets_received = 0
lost_packets = 0

def notification_handler(sender, data):
    """
    This callback fires every time the nRF52840 sends a packet.
    """
    global expected_sequence_id, total_samples_received, total_packets_received, lost_packets

    if len(data) < 4:
        return

    # 1. Unpack the header (Little-Endian, Unsigned 32-bit Integer)
    sequence_id = struct.unpack('<I', data[0:4])[0]

    # 2. Check for missing sequence numbers
    if expected_sequence_id != -1 and sequence_id != expected_sequence_id:
        lost_count = sequence_id - expected_sequence_id
        print(f"\n⚠️ PACKET LOSS: Expected {expected_sequence_id}, got {sequence_id}. Lost {lost_count} packets!\n")
        lost_packets += lost_count
    
    expected_sequence_id = sequence_id + 1

    # 3. Calculate samples (Subtract 4 bytes for header, divide by 12 bytes per sample)
    payload_bytes = len(data) - 4
    num_samples = payload_bytes // 12
    
    total_samples_received += num_samples
    total_packets_received += 1

    print(f"Packet {sequence_id:<5} | Received {num_samples:02} samples | Total Samples: {total_samples_received:<5} | Packets Lost: {lost_packets}")

async def run():
    print("Scanning for devices with 'ParkinSense' in the name...")
    
    # Custom filter to bypass exact-name caching issues
    device = await BleakScanner.find_device_by_filter(
        lambda d, ad: d.name and "ParkinSense" in d.name,
        timeout=10.0
    )

    if not device:
        print("❌ Could not find the watch.")
        print("Make sure PC Bluetooth is on, nRF Connect on your phone is DISCONNECTED, and the board is near.")
        return

    print(f"✅ Found '{device.name}' at {device.address}. Connecting...")

    try:
        async with BleakClient(device) as client:
            print("✅ Connected! Subscribing to IMU data...\n")
            
            await client.start_notify(CHARACTERISTIC_UUID, notification_handler)
            
            print("🎧 Listening for batched IMU data. Press Ctrl+C to stop.\n")
            
            while True:
                await asyncio.sleep(1)
                
    except asyncio.CancelledError:
        pass 
    except Exception as e:
        print(f"\n❌ Disconnected or Error: {e}")
    finally:
        print("\n" + "="*40)
        print("           FINAL SESSION STATS")
        print("="*40)
        print(f"Total Samples Received : {total_samples_received}")
        print(f"Total Packets Received : {total_packets_received}")
        print(f"Total Packets Lost     : {lost_packets}")
        print("="*40 + "\n")

if __name__ == "__main__":
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        print("\nUser stopped the script. Exiting gracefully...")