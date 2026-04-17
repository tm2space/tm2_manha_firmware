"""
Test ESP32-CAM serial command interface from PC.

Usage:
    python test_serial.py [PORT] [BAUD]

Defaults: /dev/ttyUSB0 115200
"""

import sys
import time
import serial

PORT = sys.argv[1] if len(sys.argv) > 1 else "/dev/ttyUSB0"
BAUD = int(sys.argv[2]) if len(sys.argv) > 2 else 115200

CMD_CAPTURE = 0x01
CMD_STATUS = 0x02
CMD_SET_SETTINGS = 0x03
CMD_GET_SETTINGS = 0x04


def open_port():
    s = serial.Serial(PORT, BAUD, timeout=3)
    print(f"Opened {PORT} @ {BAUD}")
    return s


def wait_for_ready(s, max_attempts=10):
    """Wait for ESP32 to finish booting by sending STATUS until we get a valid response."""
    print("Waiting for ESP32-CAM to be ready...", flush=True)
    for attempt in range(max_attempts):
        # Drain any pending data
        if s.in_waiting:
            stale = s.read(s.in_waiting)
            print(f"  [drain: {stale!r}]")

        s.write(bytes([CMD_STATUS]))
        t0 = time.perf_counter()
        resp = s.readline()
        ms = (time.perf_counter() - t0) * 1000

        if resp:
            text = resp.decode("utf-8", errors="replace").strip()
            if text.startswith("ACK:count="):
                print(f"  Ready! (attempt {attempt + 1}, {ms:.0f}ms)")
                return True
            print(f"  attempt {attempt + 1}: got {text!r} ({ms:.0f}ms)")
        else:
            print(f"  attempt {attempt + 1}: timeout ({ms:.0f}ms)")

        time.sleep(0.5)

    print("  ESP32-CAM not responding after all attempts")
    return False


def send_cmd(s, cmd_byte, label="CMD"):
    """Send 1-byte command, read response line. Returns (response, elapsed_ms)."""
    # Drain stale data
    if s.in_waiting:
        stale = s.read(s.in_waiting)
        print(f"  [stale: {stale}]")

    t0 = time.perf_counter()
    s.write(bytes([cmd_byte]))
    print(f"  TX: 0x{cmd_byte:02X} ({label})")

    resp = s.readline()
    elapsed_ms = (time.perf_counter() - t0) * 1000

    if resp:
        print(f"  RX: {resp!r} -> {resp.decode('utf-8', errors='replace').strip()}")
    else:
        print(f"  RX: (timeout, no response)")
    print(f"  RTT: {elapsed_ms:.1f}ms")
    return resp, elapsed_ms


def test_status(s):
    print("\n--- STATUS ---")
    resp, ms = send_cmd(s, CMD_STATUS, "STATUS")
    if resp and b"ACK:count=" in resp:
        count = resp.decode().strip().split("=")[1]
        print(f"  Image count: {count}")
    elif resp:
        print(f"  Unexpected: {resp}")
    else:
        print("  FAIL: no response")


def test_capture(s):
    print("\n--- CAPTURE ---")
    resp, ms = send_cmd(s, CMD_CAPTURE, "CAPTURE")
    if resp and b"ACK:" in resp:
        fname = resp.decode().strip()[4:]
        print(f"  Saved: {fname} ({ms:.0f}ms)")
    elif resp and b"NACK:" in resp:
        print(f"  Camera NACK: {resp.decode().strip()}")
    else:
        print("  FAIL: no response")


def test_get_settings(s):
    print("\n--- GET SETTINGS ---")
    if s.in_waiting:
        s.read(s.in_waiting)

    t0 = time.perf_counter()
    s.write(bytes([CMD_GET_SETTINGS]))
    print(f"  TX: 0x{CMD_GET_SETTINGS:02X} (GET_SETTINGS)")

    # Read binary response: echo byte + key-value pairs + 0x00 + newline
    time.sleep(0.5)
    data = s.read(s.in_waiting or 128)
    elapsed_ms = (time.perf_counter() - t0) * 1000
    print(f"  RTT: {elapsed_ms:.1f}ms")
    if not data:
        print("  FAIL: no response")
        return

    print(f"  RX raw: {data.hex()}")

    # Format: echo(0x04) + 21 key-value pairs (42 bytes) + 0x00 + \r\n
    # Keys 0x01-0x15, values can be 0x00 so we can't use 0x00 as delimiter
    NUM_SETTINGS = 21
    EXPECTED = 1 + NUM_SETTINGS * 2  # echo + 42 kv bytes

    if len(data) < EXPECTED:
        print(f"  FAIL: too short ({len(data)} bytes, need {EXPECTED})")
        return

    kv = data[1:EXPECTED]  # skip echo byte, take exactly 42 bytes

    NAMES = {
        0x01: "Frame Size", 0x02: "Quality", 0x03: "Brightness",
        0x04: "Contrast", 0x05: "Saturation", 0x06: "Special Effect",
        0x07: "WB Mode", 0x08: "AWB", 0x09: "AWB Gain",
        0x0A: "AEC", 0x0B: "AEC2", 0x0C: "AE Level",
        0x0D: "AGC", 0x0E: "AGC Gain", 0x0F: "Gain Ceiling",
        0x10: "BPC", 0x11: "WPC", 0x12: "Raw GMA",
        0x13: "Lens Corr", 0x14: "H-Mirror", 0x15: "V-Flip",
    }

    print(f"  Settings ({len(kv)//2} pairs):")
    for i in range(0, len(kv), 2):
        key, val = kv[i], kv[i + 1]
        name = NAMES.get(key, f"0x{key:02X}")
        print(f"    {name:15s} = {val}")


def interactive(s):
    print("\n--- INTERACTIVE ---")
    print("Commands: s=status, c=capture, g=get_settings, q=quit")
    while True:
        try:
            cmd = input("> ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            break
        if cmd == "s":
            test_status(s)
        elif cmd == "c":
            test_capture(s)
        elif cmd == "g":
            test_get_settings(s)
        elif cmd == "q":
            break
        elif cmd == "":
            continue
        else:
            print(f"Unknown: {cmd}")


def main():
    s = open_port()
    if not wait_for_ready(s):
        s.close()
        return
    test_status(s)
    test_capture(s)
    test_get_settings(s)
    interactive(s)
    s.close()
    print("Done.")


if __name__ == "__main__":
    main()
