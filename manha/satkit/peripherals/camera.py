"""ManhaCam - ESP32-CAM serial interface peripheral

Frame layout (32-bit aligned 8-byte overhead):
    [PREAMBLE 0xAA][SYNC 0x55][LEN 1B][TYPE 1B]    # 4-byte header
    [PAYLOAD 0..255 B]
    [CRC32_LE 4B]                                   # 4-byte trailer

CRC32 = binascii.crc32 over [SYNC + LEN + TYPE + PAYLOAD] (excludes
PREAMBLE). Zlib/Ethernet polynomial, matches esp_crc32_le(0, ...).

The 0xAA PREAMBLE is the UART light-sleep wake byte. Because the wake
machinery may drop or garble it during the ESP32 clock-ramp window, the
byte is NOT included in the CRC and the receiver syncs on SYNC (0x55)
rather than PREAMBLE. The PREAMBLE is still transmitted every frame to
trigger the wake threshold.

Response TYPE = request TYPE | 0x80 (ACK) or | 0xC0 (NACK).
NACK payload is a single error-code byte (FR_ERR_*).
"""

import time
import binascii
import uasyncio as asyncio
from .base import ManhaSensor

from micropython import const

# ── Frame constants ─────────────────────────────────────────────────────────
_PREAMBLE = const(0xAA)
_SYNC = const(0x55)
_ACK_BIT = const(0x80)
_NACK_BIT = const(0xC0)
_HEADER_LEN = const(4)           # PREAMBLE + SYNC + LEN + TYPE
_CRC_LEN = const(4)
_CRC_BODY_OFF = const(1)         # CRC body starts at SYNC (skip PREAMBLE)
_MIN_FRAME = const(8)            # header + zero payload + crc

# ── Request opcodes ─────────────────────────────────────────────────────────
_CMD_CAPTURE = const(0x01)
_CMD_STATUS = const(0x02)
_CMD_SET_SETTINGS = const(0x03)
_CMD_GET_SETTINGS = const(0x04)
_CMD_WEBUI_ON = const(0x05)
_CMD_WEBUI_OFF = const(0x06)
_CMD_WAKE_PREP = const(0x08)

# ── NACK error codes (from ESP side) ────────────────────────────────────────
_FR_ERR_UNKNOWN_CMD = const(0x01)
_FR_ERR_BAD_PAYLOAD = const(0x02)
_FR_ERR_CAPTURE = const(0x03)
_FR_ERR_BAD_COUNT = const(0x04)

# ── Timing ──────────────────────────────────────────────────────────────────
_DEFAULT_TIMEOUT_MS = const(300)    # STATUS / GET_SETTINGS / WAKE_PREP / WEBUI_OFF
_CAPTURE_TIMEOUT_MS = const(5000)   # OV2640 grab + JPEG + SD write can take ~0.5–2 s
_WAKE_SETTLE_MS = const(5)          # ESP DFS clock ramp + pm_unlock after wake edge
_WATCHDOG_MS = const(30000)


def _build_frame(opcode, payload=b""):
    """Build a complete frame: header + payload + CRC32_LE.

    CRC is computed over [SYNC, LEN, TYPE, payload] — PREAMBLE is
    excluded because the wake machinery may drop/garble it.
    """
    plen = len(payload)
    if plen > 255:
        raise ValueError("payload > 255 bytes")
    crc_body = bytes([_SYNC, plen, opcode]) + bytes(payload)
    crc = binascii.crc32(crc_body) & 0xFFFFFFFF
    return bytes([_PREAMBLE]) + crc_body + crc.to_bytes(4, "little")


class ManhaCam(ManhaSensor):
    """ESP32-CAM serial peripheral.

    Args:
        uart: Pre-configured UART-like object (PioUart or machine.UART).
        timeout_ms (int): Default response timeout.
    """

    def __init__(self, uart, timeout_ms=_DEFAULT_TIMEOUT_MS):
        self._timeout_ms = timeout_ms
        self._uart = uart
        self._last_count = -1
        self._last_file = None
        self._last_status_ms = time.ticks_ms()

    # ── Low-level frame I/O ─────────────────────────────────────────────────
    async def _send_frame(self, opcode, payload=b"", timeout_ms=None):
        """Send one frame, await one response frame for the matching opcode.

        Returns:
            tuple: (status, payload_bytes)
                status is 'ACK', 'NACK', or 'ERR'.
                For 'ERR' the payload describes the failure.
        """
        if timeout_ms is None:
            timeout_ms = self._timeout_ms

        while self._uart.any():
            self._uart.read()

        self._uart.write(_build_frame(opcode, payload))
        # Give ESP time to clock back up from light sleep before it starts
        # parsing. Preamble already fired the wake; this covers DFS ramp.
        await asyncio.sleep_ms(_WAKE_SETTLE_MS)

        return await self._read_frame(opcode, timeout_ms)

    async def _read_frame(self, expected_opcode, timeout_ms):
        """Read bytes until a valid frame addressed to expected_opcode arrives,
        or timeout.

        Syncs on SYNC (0x55) rather than PREAMBLE — the preamble byte may
        be consumed/corrupted by the ESP light-sleep wake path, so we treat
        it as optional. CRC validates the rest of the frame; any false
        SYNC-byte match will fail CRC and be discarded.
        """
        expected_ack = expected_opcode | _ACK_BIT
        expected_nack = expected_opcode | _NACK_BIT

        start = time.ticks_ms()
        buf = b""

        while time.ticks_diff(time.ticks_ms(), start) < timeout_ms:
            if self._uart.any():
                chunk = self._uart.read()
                if chunk:
                    buf += chunk

            # Try to consume whole frames from buf
            while True:
                # Find SYNC byte; PREAMBLE before it is optional and ignored.
                idx = buf.find(bytes([_SYNC]))
                if idx < 0:
                    buf = b""
                    break
                if idx > 0:
                    buf = buf[idx:]

                # Need at least [SYNC][LEN][TYPE] + CRC = 3 + 4 = 7 bytes
                if len(buf) < _MIN_FRAME - 1:
                    break

                plen = buf[1]
                crc_body_len = 3 + plen      # SYNC + LEN + TYPE + payload
                total = crc_body_len + _CRC_LEN
                if len(buf) < total:
                    break

                crc_body = buf[:crc_body_len]
                rx_crc = int.from_bytes(buf[crc_body_len:total], "little")
                calc_crc = binascii.crc32(crc_body) & 0xFFFFFFFF

                if rx_crc != calc_crc:
                    # Bad frame; drop SYNC and keep scanning
                    buf = buf[1:]
                    continue

                resp_type = crc_body[2]
                resp_payload = bytes(crc_body[3:])
                buf = buf[total:]

                if resp_type == expected_ack:
                    return ("ACK", resp_payload)
                if resp_type == expected_nack:
                    return ("NACK", resp_payload)
                # Unrelated frame — ignore, keep scanning

            await asyncio.sleep_ms(5)

        return ("ERR", b"timeout")

    # ── Public API ──────────────────────────────────────────────────────────
    async def probe(self):
        """Non-blocking STATUS check. Returns 'OK' or error string."""
        status, _ = await self._send_frame(_CMD_STATUS, timeout_ms=500)
        return "OK" if status == "ACK" else f"ERR:{status}"

    async def read(self):
        """STATUS: read image count from ESP. Also resets ESP watchdog.

        Returns:
            dict: {"cam_count": int} on success,
                  {"cam_count": -1, "error": str} on failure.
        """
        self._last_status_ms = time.ticks_ms()
        status, payload = await self._send_frame(_CMD_STATUS)
        if status == "ACK" and len(payload) >= 4:
            self._last_count = int.from_bytes(payload[:4], "little")
            return {"cam_count": self._last_count}
        self._last_count = -1
        return {"cam_count": -1, "error": f"{status}:{payload}"}

    @property
    def needs_keepalive(self):
        """True if ESP watchdog is about to fire (>20s since last STATUS)."""
        return time.ticks_diff(time.ticks_ms(), self._last_status_ms) > (
            _WATCHDOG_MS - 10000
        )

    async def keepalive(self):
        """Lightweight STATUS poll to reset ESP watchdog. Discards response."""
        self._last_status_ms = time.ticks_ms()
        await self._send_frame(_CMD_STATUS, timeout_ms=500)

    async def wake_prep(self, timeout_ms=1000):
        """Ask ESP to bring sensor out of PWDN ahead of a capture.

        Call ~300 ms before capture() for lowest latency on the hot path.
        Returns True on ACK.
        """
        status, _ = await self._send_frame(_CMD_WAKE_PREP, timeout_ms=timeout_ms)
        return status == "ACK"

    async def capture(self):
        """Trigger a photo capture on the ESP.

        Returns:
            tuple: (filename, None) on success, (None, error_str) on failure.
        """
        status, payload = await self._send_frame(_CMD_CAPTURE,
                                                 timeout_ms=_CAPTURE_TIMEOUT_MS)
        if status == "ACK":
            fname = payload.decode("utf-8")
            self._last_file = fname
            return fname, None
        self._last_file = None
        return None, _fmt_err(status, payload)

    async def webui_on(self):
        """Start WiFi AP + HTTP server. Returns 'ACK:ip=X.X.X.X' or error."""
        status, payload = await self._send_frame(_CMD_WEBUI_ON, timeout_ms=5000)
        if status == "ACK" and len(payload) >= 4:
            ip = ".".join(str(b) for b in payload[:4])
            return f"ACK:ip={ip}"
        return _fmt_err(status, payload)

    async def webui_off(self):
        """Stop WiFi AP + HTTP server."""
        status, payload = await self._send_frame(_CMD_WEBUI_OFF)
        if status == "ACK":
            return "ACK"
        return _fmt_err(status, payload)

    async def configure_remote(self, raw_kv_bytes):
        """Forward raw KV settings to ESP.

        Args:
            raw_kv_bytes (bytes): key-value pairs (e.g. b'\\x02\\x0A\\x16\\x01').

        Returns:
            str: 'ACK:applied=N' or error.
        """
        num_pairs = len(raw_kv_bytes) // 2
        payload = bytes([num_pairs]) + bytes(raw_kv_bytes)
        status, resp = await self._send_frame(_CMD_SET_SETTINGS, payload)
        if status == "ACK" and len(resp) >= 1:
            return f"ACK:applied={resp[0]}"
        return _fmt_err(status, resp)

    async def read_settings(self):
        """Read all current settings as raw KV bytes.

        Returns:
            bytes | None: 42 bytes (21 KV pairs) on success, None on failure.
        """
        status, payload = await self._send_frame(_CMD_GET_SETTINGS)
        if status == "ACK":
            return bytes(payload)
        return None

    def configure(self, **kwargs):
        """Configure local peripheral params (not camera settings).

        Args:
            **kwargs: timeout_ms (int).
        """
        if "timeout_ms" in kwargs:
            self._timeout_ms = kwargs["timeout_ms"]


def _fmt_err(status, payload):
    """Format an error payload. NACK payload is a 1-byte code; ERR payload
    is a diagnostic string (e.g. b"timeout")."""
    if status == "NACK":
        return f"NACK:{_decode_nack(payload)}"
    return f"{status}:{payload.decode('utf-8', 'replace')}"


def _decode_nack(payload):
    """Turn NACK payload into a readable error string."""
    if not payload:
        return "no_payload"
    code = payload[0]
    names = {
        _FR_ERR_UNKNOWN_CMD: "unknown_cmd",
        _FR_ERR_BAD_PAYLOAD: "bad_payload",
        _FR_ERR_CAPTURE: "capture_failed",
        _FR_ERR_BAD_COUNT: "bad_count",
    }
    return names.get(code, f"err=0x{code:02X}")
