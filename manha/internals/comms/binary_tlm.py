"""
Binary telemetry encoder/decoder for MANHA LoRa protocol

Core layout: '<IBBfffffffBhhhffff' (57 bytes)

Core fields:
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

TLV extension tail (optional, backwards-compatible):
    [ext_count: u8]
      per entry:
        [key_len: u8][key: ASCII][fmt: u8][value: struct.pack("<"+fmt, v)]

Old decoders (no TLV support) still read the 57 B core correctly.
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

# Budget = LoRa max (255) - Packet header (4 bytes: addr_from, addr_to, msg_type, checksum)
MAX_TLM_PAYLOAD = 251


def encode_tlm(data: dict, seq: int, lpm: bool, ts: int, ext_fields=None) -> bytes:
    """Pack telemetry dict into binary bytes (core + optional TLV tail).

    Args:
        data: Telemetry data dict from sensor readings
        seq: Sequence number (0-255)
        lpm: Low power mode flag
        ts: Timestamp in milliseconds (time.ticks_ms())
        ext_fields: Optional list of (key_str, fmt_char) tuples for extension tail.
                    fmt_char is a struct format char ('f','h','H','B','b','i','I').

    Returns:
        bytes: Packed binary telemetry (57 B core + optional TLV tail)
    """
    flags = 0x01 if lpm else 0x00

    core = struct.pack(
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

    ext_fields = ext_fields or []
    ext_keys = set()
    entries = bytearray()
    count = 0
    running = len(core) + 1  # +1 for ext_count byte

    for key, fmt in ext_fields:
        ext_keys.add(key)
        if key not in data:
            continue
        try:
            k = key.encode("ascii")
            val_bytes = struct.pack("<" + fmt, data[key])
        except Exception as e:
            print("TLM: pack error for %s: %s" % (key, e))
            continue
        entry_size = 1 + len(k) + 1 + len(val_bytes)
        if running + entry_size > MAX_TLM_PAYLOAD:
            print("TLM: budget exceeded, dropped %s" % key)
            break
        entries.append(len(k))
        entries.extend(k)
        entries.append(ord(fmt))
        entries.extend(val_bytes)
        running += entry_size
        count += 1

    # Loud-drop detector for keys the encoder has no slot for
    unmapped = set(data.keys()) - set(TLM_FIELDS) - ext_keys
    if unmapped:
        print("TLM: unmapped %s" % unmapped)

    return core + bytes([count]) + bytes(entries)


def decode_tlm(data: bytes) -> dict:
    """Unpack binary bytes into telemetry dict (core + optional TLV tail).

    Args:
        data: Packed binary telemetry bytes (57 B core, optional tail)

    Returns:
        dict: Telemetry data dict with all fields, or None if invalid
    """
    if len(data) < TLM_SIZE:
        return None

    values = struct.unpack(TLM_FORMAT, data[:TLM_SIZE])

    result = {}
    for i, field in enumerate(TLM_FIELDS):
        result[field] = values[i]

    result["lpm"] = bool(result["flags"] & 0x01)
    del result["flags"]

    # TLV tail (optional)
    i = TLM_SIZE
    n = len(data)
    if i >= n:
        return result

    ext_count = data[i]
    i += 1

    for _ in range(ext_count):
        if i + 1 > n:
            print("TLM: truncated tail at key_len")
            break
        klen = data[i]
        i += 1
        if i + klen + 1 > n:
            print("TLM: truncated tail at key")
            break
        try:
            key = bytes(data[i:i + klen]).decode("ascii")
        except Exception:
            print("TLM: non-ascii key, aborting tail")
            break
        i += klen
        fmt = chr(data[i])
        i += 1
        try:
            size = struct.calcsize("<" + fmt)
        except Exception:
            print("TLM: unknown fmt %r, aborting tail" % fmt)
            break
        if i + size > n:
            print("TLM: truncated tail at value for %s" % key)
            break
        try:
            (val,) = struct.unpack("<" + fmt, data[i:i + size])
        except Exception as e:
            print("TLM: unpack error %s: %s" % (key, e))
            break
        result[key] = val
        i += size

    return result
