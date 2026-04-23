"""
MicroPython test for ESP32-CAM framed protocol over UART0.
Upload to Pico and run via REPL.

Usage: import test_cam_pico
"""

from machine import UART, Pin
import time
import binascii

TX_PIN = 12
RX_PIN = 13
BAUD = 115200

PREAMBLE = 0xAA
SYNC = 0x55
ACK_BIT = 0x80
NACK_BIT = 0xC0

CMD_CAPTURE = 0x01
CMD_STATUS = 0x02
CMD_SET_SETTINGS = 0x03
CMD_GET_SETTINGS = 0x04
CMD_WEBUI_ON = 0x05
CMD_WEBUI_OFF = 0x06
CMD_WAKE_PREP = 0x08

uart = UART(0, baudrate=BAUD, tx=Pin(TX_PIN), rx=Pin(RX_PIN))


def drain():
    while uart.any():
        uart.read()


def build_frame(opcode, payload=b""):
    # CRC over [SYNC, LEN, TYPE, payload] — PREAMBLE excluded.
    crc_body = bytes([SYNC, len(payload), opcode]) + bytes(payload)
    crc = binascii.crc32(crc_body) & 0xFFFFFFFF
    return bytes([PREAMBLE]) + crc_body + crc.to_bytes(4, "little")


def read_frame(expected_opcode, timeout_ms=2000):
    expected_ack = expected_opcode | ACK_BIT
    expected_nack = expected_opcode | NACK_BIT
    t0 = time.ticks_ms()
    buf = b""
    while time.ticks_diff(time.ticks_ms(), t0) < timeout_ms:
        if uart.any():
            chunk = uart.read()
            if chunk:
                buf += chunk
        while True:
            # Sync on SYNC; preamble is optional.
            idx = buf.find(bytes([SYNC]))
            if idx < 0:
                buf = b""
                break
            if idx > 0:
                buf = buf[idx:]
            if len(buf) < 7:
                break
            plen = buf[1]
            crc_body_len = 3 + plen
            total = crc_body_len + 4
            if len(buf) < total:
                break
            crc_body = buf[:crc_body_len]
            rx_crc = int.from_bytes(buf[crc_body_len:total], "little")
            calc = binascii.crc32(crc_body) & 0xFFFFFFFF
            if rx_crc != calc:
                buf = buf[1:]
                continue
            rtype = crc_body[2]
            payload = bytes(crc_body[3:])
            buf = buf[total:]
            elapsed = time.ticks_diff(time.ticks_ms(), t0)
            if rtype == expected_ack:
                return ("ACK", payload, elapsed)
            if rtype == expected_nack:
                return ("NACK", payload, elapsed)
        time.sleep_ms(5)
    return ("ERR", b"timeout", time.ticks_diff(time.ticks_ms(), t0))


def send(opcode, payload=b"", label="", timeout_ms=2000):
    drain()
    uart.write(build_frame(opcode, payload))
    time.sleep_ms(5)
    print(f"TX: 0x{opcode:02X} ({label}) len={len(payload)}")
    status, resp, ms = read_frame(opcode, timeout_ms)
    print(f"RX: {status} len={len(resp)} ({ms}ms) {resp}")
    return status, resp


def status():
    s, p = send(CMD_STATUS, label="STATUS")
    if s == "ACK" and len(p) >= 4:
        print(f"  image_counter = {int.from_bytes(p[:4], 'little')}")


def capture():
    s, p = send(CMD_CAPTURE, label="CAPTURE", timeout_ms=5000)
    if s == "ACK":
        print(f"  file = {p.decode('utf-8')}")


def wake_prep():
    send(CMD_WAKE_PREP, label="WAKE_PREP", timeout_ms=1000)


def get_settings():
    s, p = send(CMD_GET_SETTINGS, label="GET_SETTINGS")
    if s != "ACK":
        return
    names = {
        0x01: "Frame Size", 0x02: "Quality", 0x03: "Brightness",
        0x04: "Contrast", 0x05: "Saturation", 0x06: "Special Effect",
        0x07: "WB Mode", 0x08: "AWB", 0x09: "AWB Gain",
        0x0A: "AEC", 0x0B: "AEC2", 0x0C: "AE Level",
        0x0D: "AGC", 0x0E: "AGC Gain", 0x0F: "Gain Ceiling",
        0x10: "BPC", 0x11: "WPC", 0x12: "Raw GMA",
        0x13: "Lens Corr", 0x14: "H-Mirror", 0x15: "V-Flip",
    }
    for i in range(0, len(p), 2):
        k, v = p[i], p[i + 1]
        print(f"  {names.get(k, f'0x{k:02X}'):15s} = {v}")


def run():
    print("--- Drain boot ---")
    time.sleep(1)
    drain()

    print("\n--- STATUS ---")
    status()

    print("\n--- WAKE_PREP ---")
    wake_prep()

    print("\n--- CAPTURE (hot) ---")
    time.sleep_ms(300)
    capture()

    print("\n--- GET_SETTINGS ---")
    get_settings()


run()
