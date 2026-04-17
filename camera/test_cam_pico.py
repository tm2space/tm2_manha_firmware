"""
MicroPython test for ESP32-CAM over UART0.
Upload to Pico and run via REPL.

Usage: import test_cam_pico
"""

from machine import UART, Pin
import time

TX_PIN = 12
RX_PIN = 13
BAUD = 115200

CMD_STATUS = 0x02
CMD_CAPTURE = 0x01
CMD_GET_SETTINGS = 0x04

uart = UART(0, baudrate=BAUD, tx=Pin(TX_PIN), rx=Pin(RX_PIN))


def drain():
    while uart.any():
        uart.read()


def send_cmd(cmd_byte, label, timeout_ms=2000):
    drain()
    t0 = time.ticks_ms()
    uart.write(bytes([cmd_byte]))
    print(f"TX: 0x{cmd_byte:02X} ({label})")

    buf = b""
    while time.ticks_diff(time.ticks_ms(), t0) < timeout_ms:
        if uart.any():
            chunk = uart.read()
            if chunk:
                buf += chunk
                if b"\n" in buf:
                    elapsed = time.ticks_diff(time.ticks_ms(), t0)
                    text = buf.decode("utf-8").strip()
                    print(f"RX: {text}  ({elapsed}ms)")
                    return text
        time.sleep_ms(10)

    elapsed = time.ticks_diff(time.ticks_ms(), t0)
    if buf:
        print(f"RX partial: {buf}  ({elapsed}ms)")
    else:
        print(f"RX: timeout  ({elapsed}ms)")
    return None


def send_get_settings(timeout_ms=2000):
    drain()
    t0 = time.ticks_ms()
    uart.write(bytes([CMD_GET_SETTINGS]))
    print(f"TX: 0x{CMD_GET_SETTINGS:02X} (GET_SETTINGS)")

    buf = b""
    while time.ticks_diff(time.ticks_ms(), t0) < timeout_ms:
        if uart.any():
            chunk = uart.read()
            if chunk:
                buf += chunk
                if b"\x00" in buf and len(buf) >= 44:
                    break
        time.sleep_ms(10)

    elapsed = time.ticks_diff(time.ticks_ms(), t0)

    if len(buf) < 44:
        print(f"RX: too short ({len(buf)} bytes, {elapsed}ms)")
        print(f"RX raw: {buf}")
        return None

    # echo(1) + 21 key-value pairs(42) + terminator(1)
    kv = buf[1:43]
    names = {
        0x01: "Frame Size", 0x02: "Quality", 0x03: "Brightness",
        0x04: "Contrast", 0x05: "Saturation", 0x06: "Special Effect",
        0x07: "WB Mode", 0x08: "AWB", 0x09: "AWB Gain",
        0x0A: "AEC", 0x0B: "AEC2", 0x0C: "AE Level",
        0x0D: "AGC", 0x0E: "AGC Gain", 0x0F: "Gain Ceiling",
        0x10: "BPC", 0x11: "WPC", 0x12: "Raw GMA",
        0x13: "Lens Corr", 0x14: "H-Mirror", 0x15: "V-Flip",
    }

    print(f"Settings ({elapsed}ms):")
    for i in range(0, len(kv), 2):
        key, val = kv[i], kv[i + 1]
        name = names.get(key, f"0x{key:02X}")
        print(f"  {name:15s} = {val}")
    return kv


def status():
    send_cmd(CMD_STATUS, "STATUS")


def capture():
    send_cmd(CMD_CAPTURE, "CAPTURE", timeout_ms=5000)


def settings():
    send_get_settings()


def run():
    print("--- Drain boot ---")
    time.sleep(1)
    drain()

    print("\n--- STATUS ---")
    status()

    print("\n--- CAPTURE ---")
    capture()

    print("\n--- GET_SETTINGS ---")
    settings()


run()
