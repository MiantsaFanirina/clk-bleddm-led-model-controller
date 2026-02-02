import asyncio
from bleak import BleakScanner, BleakClient

# -----------------------------------
# Common test commands for BLE LED strips
# -----------------------------------
TEST_COMMANDS = [
    bytearray([0x7e, 0x04, 0x04, 0xf0, 0x00, 0x01, 0xff, 0x00, 0xef]),  # Common ON
    bytearray([0x7e, 0x07, 0x05, 0x03, 0xff, 0x00, 0x00, 0x10, 0xef]),  # Common RED
    bytearray([0x56, 0xff, 0x00, 0x00, 0x00, 0xf0, 0xaa]),              # Alternative RED
]

async def brute_force_ble_leds():
    print("Scanning for BLE devices...\n")
    devices = await BleakScanner.discover(timeout=8.0)

    if not devices:
        print("No BLE devices found.")
        return

    for device in devices:
        print(f"\nTrying device: {device.name} | {device.address}")

        try:
            async with BleakClient(device.address, timeout=6.0) as client:
                if not client.is_connected:
                    print("  Could not connect.")
                    continue

                print("  Connected.")

                services = await client.get_services()
                writable_chars = []

                # Find all writable characteristics
                for service in services:
                    for char in service.characteristics:
                        if "write" in char.properties or "write-without-response" in char.properties:
                            writable_chars.append(char)

                if not writable_chars:
                    print("  No writable characteristics found. Skipping.")
                    continue

                print(f"  Found {len(writable_chars)} writable characteristics.")

                possible_matches = []

                # Try every command on every writable characteristic
                for char in writable_chars:
                    print(f"\n  Testing characteristic: {char.uuid}")

                    for cmd in TEST_COMMANDS:
                        try:
                            await client.write_gatt_char(
                                char.uuid,
                                cmd,
                                response=False
                            )
                            await asyncio.sleep(0.4)

                            print(f"    ✅ Possible match -> UUID: {char.uuid} | HEX: {cmd.hex()}")

                            possible_matches.append({
                                "device": device.address,
                                "uuid": char.uuid,
                                "hex": cmd.hex()
                            })

                        except Exception as e:
                            print(f"    ❌ Write failed: {e}")

                # Summary for this device
                if possible_matches:
                    print("\n  ===== DEVICE SUMMARY =====")
                    print("  If your LED reacted, the correct values are likely one of these:\n")
                    for m in possible_matches:
                        print(f"  UUID: {m['uuid']} | HEX: {m['hex']}")

                else:
                    print("\n  No commands were accepted by this device.")

        except Exception as e:
            print(f"  Failed to connect: {e}")

    print("\nScan complete.")

asyncio.run(brute_force_ble_leds())
                      