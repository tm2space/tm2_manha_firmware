"""
Binary telemetry encoder/decoder for MANHA LoRa protocol

Format: '<IBBfffffffBhhhffff' (57 bytes)

Fields:
    ts      uint32    Monotonic timestamp (ms)
    seq     uint8     Sequence number (0-255)
    flags   uint8     bit0=lpm, bits1-7=reserved
    v_p     float32   Battery percentage (0-100)
    i       float32   Current (mA)
    s_v     float32   Shunt voltage (V)
    b_v     float32   Bus voltage (V)
    lat     float32   Latitude (decimal degrees)
    lng     float32   Longitude (decimal degrees)
    alt     float32   Altitude (m)
    sats    uint8     Satellite count
    a_x     int16     Accelerometer X
    a_y     int16     Accelerometer Y
    a_z     int16     Accelerometer Z
    uv      float32   UV index
    temp    float32   Temperature (C)
    pres    float32   Pressure (hPa)
    hum     float32   Humidity (%)
"""

import struct

TLM_FORMAT = "<IBBfffffffBhhhffff"
TLM_SIZE = struct.calcsize(TLM_FORMAT)  # 57 bytes

TLM_FIELDS = (
    "ts",
    "seq",
    "flags",
    "v_p",
    "i",
    "s_v",
    "b_v",
    "lat",
    "lng",
    "alt",
    "sats",
    "a_x",
    "a_y",
    "a_z",
    "uv",
    "temp",
    "pres",
    "hum",
)


def encode_tlm(data: dict, seq: int, lpm: bool, ts: int) -> bytes:
    """Pack telemetry dict into binary bytes

    Args:
        data: Telemetry data dict from sensor readings
        seq: Sequence number (0-255)
        lpm: Low power mode flag
        ts: Timestamp in milliseconds (time.ticks_ms())

    Returns:
        bytes: Packed binary telemetry (57 bytes)
    """
    flags = 0x01 if lpm else 0x00

    return struct.pack(
        TLM_FORMAT,
        ts & 0xFFFFFFFF,
        seq & 0xFF,
        flags,
        float(data.get("v_p", -1)),
        float(data.get("i", -1)),
        float(data.get("s_v", -1)),
        float(data.get("b_v", -1)),
        float(data.get("lat", 0.0)),
        float(data.get("lng", 0.0)),
        float(data.get("alt", 0.0)),
        int(data.get("sats", 0)) & 0xFF,
        int(data.get("a_x", 0)),
        int(data.get("a_y", 0)),
        int(data.get("a_z", 0)),
        float(data.get("uv", -1)),
        float(data.get("temp", -1)),
        float(data.get("pres", -1)),
        float(data.get("hum", -1)),
    )


def decode_tlm(data: bytes) -> dict:
    """Unpack binary bytes into telemetry dict

    Args:
        data: Packed binary telemetry bytes (57 bytes)

    Returns:
        dict: Telemetry data dict with all fields, or None if invalid
    """
    if len(data) < TLM_SIZE:
        return None

    values = struct.unpack(TLM_FORMAT, data[:TLM_SIZE])

    result = {}
    for i, field in enumerate(TLM_FIELDS):
        result[field] = values[i]

    # Unpack flags
    result["lpm"] = bool(result["flags"] & 0x01)
    del result["flags"]

    return result
