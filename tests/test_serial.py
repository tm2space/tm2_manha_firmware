"""
Desktop bench test for ESP32-CAM framed protocol over USB-serial.
Run on a PC with pyserial: `python test_serial.py /dev/ttyUSB0`
"""

import sys
import time
import struct
import binascii

try:
    import serial
except ImportError:
    print("pyserial not installed: pip install pyserial")
    sys.exit(1)

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

NACK_NAMES = {
    0x01: "unknown_cmd",
    0x02: "bad_payload",
    0x03: "capture_failed",
    0x04: "bad_count",
}


def build_frame(opcode, payload=b""):
    # CRC over [SYNC, LEN, TYPE, payload] — PREAMBLE excluded.
    crc_body = bytes([SYNC, len(payload), opcode]) + payload
    crc = binascii.crc32(crc_body) & 0xFFFFFFFF
    return bytes([PREAMBLE]) + crc_body + struct.pack("<I", crc)


def read_frame(ser, expected_opcode, timeout_s=2.0):
    expected_ack = expected_opcode | ACK_BIT
    expected_nack = expected_opcode | NACK_BIT
    t0 = time.time()
    buf = b""
    while time.time() - t0 < timeout_s:
        chunk = ser.read(ser.in_waiting or 1)
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
            rx_crc = struct.unpack("<I", buf[crc_body_len:total])[0]
            calc = binascii.crc32(crc_body) & 0xFFFFFFFF
            if rx_crc != calc:
                print(f"  [CRC fail rx={rx_crc:08x} calc={calc:08x}]")
                buf = buf[1:]
                continue
            rtype = crc_body[2]
            payload = bytes(crc_body[3:])
            buf = buf[total:]
            elapsed = (time.time() - t0) * 1000
            if rtype == expected_ack:
                return ("ACK", payload, elapsed)
            if rtype == expected_nack:
                return ("NACK", payload, elapsed)
    return ("ERR", b"timeout", (time.time() - t0) * 1000)


def send(ser, opcode, payload=b"", label="", timeout_s=2.0):
    ser.reset_input_buffer()
    ser.write(build_frame(opcode, payload))
    time.sleep(0.005)
    print(f"TX: 0x{opcode:02X} ({label}) len={len(payload)}")
    status, resp, ms = read_frame(ser, opcode, timeout_s)
    if status == "NACK" and resp:
        code = resp[0]
        name = NACK_NAMES.get(code, f"0x{code:02X}")
        print(f"RX: NACK {name} ({ms:.1f}ms)")
    else:
        tail = resp if len(resp) <= 32 else resp[:32] + b"..."
        print(f"RX: {status} len={len(resp)} ({ms:.1f}ms) {tail}")
    return status, resp


def status(ser):
    s, p = send(ser, CMD_STATUS, label="STATUS")
    if s == "ACK" and len(p) >= 4:
        cnt = struct.unpack("<I", p[:4])[0]
        print(f"  image_counter = {cnt}")


def capture(ser):
    s, p = send(ser, CMD_CAPTURE, label="CAPTURE", timeout_s=5.0)
    if s == "ACK":
        print(f"  file = {p.decode('utf-8')}")


def wake_prep(ser):
    send(ser, CMD_WAKE_PREP, label="WAKE_PREP", timeout_s=1.0)


def get_settings(ser):
    s, p = send(ser, CMD_GET_SETTINGS, label="GET_SETTINGS")
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


def set_quality(ser, q):
    # count=1, key=0x02 (quality), val=q
    send(ser, CMD_SET_SETTINGS, bytes([1, 0x02, q]), label=f"SET quality={q}")


def main():
    port = sys.argv[1] if len(sys.argv) > 1 else "/dev/ttyUSB0"
    print(f"Opening {port} @ 115200")
    ser = serial.Serial(port, 115200, timeout=0.1)
    time.sleep(1.0)
    ser.reset_input_buffer()

    print("\n--- STATUS ---")
    status(ser)

    print("\n--- WAKE_PREP + CAPTURE (hot path) ---")
    wake_prep(ser)
    time.sleep(0.3)
    capture(ser)

    print("\n--- CAPTURE (cold path) ---")
    capture(ser)

    print("\n--- SET quality=12 ---")
    set_quality(ser, 12)

    print("\n--- GET_SETTINGS ---")
    get_settings(ser)

    ser.close()


if __name__ == "__main__":
    main()
