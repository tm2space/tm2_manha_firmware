"""ManhaCam - ESP32-CAM serial interface peripheral"""

import time
from .base import ManhaSensor

from micropython import const

_DEFAULT_TIMEOUT_MS = const(2000)

_CMD_CAPTURE = const(0x01)
_CMD_STATUS = const(0x02)
_CMD_SET_SETTINGS = const(0x03)
_CMD_GET_SETTINGS = const(0x04)
_CMD_WEBUI_ON = const(0x05)
_CMD_WEBUI_OFF = const(0x06)

_WATCHDOG_MS = const(30000)


class ManhaCam(ManhaSensor):
    """ESP32-CAM serial interface for the MANHA satellite kit.

    Communicates with the ESP32-CAM over a PIO-based software UART using
    a single-byte command protocol:
        0x01 = CAPTURE       -> ACK:<filename> | NACK:capture_failed
        0x02 = STATUS        -> ACK:count=<N>
        0x03 = SET_SETTINGS  -> count + key-value pairs (FLP) -> ACK:settings=<N>
        0x04 = GET_SETTINGS  -> 0x04 + 21 key-value pairs (43 bytes FLP)

    Args:
        uart: Pre-configured UART-like object. If None, creates a PioUart.
        tx_pin (int): GPIO pin for transmit (default 5).
        rx_pin (int): GPIO pin for receive (default 6).
        baudrate (int): Baud rate (default 115200).
        timeout_ms (int): Response timeout in ms (default 2000).
    """

    def __init__(self, uart, timeout_ms=_DEFAULT_TIMEOUT_MS):
        self._timeout_ms = timeout_ms
        self._uart = uart
        self._last_count = -1
        self._last_file = None
        self._last_status_ms = time.ticks_ms()

    def _send_cmd(self, cmd_byte, timeout_ms=None):
        """Send a 1-byte command and read the response line.

        Returns:
            str: Response string (stripped), or error string starting with
                 "ERR:" on failure.
        """
        if timeout_ms is None:
            timeout_ms = self._timeout_ms

        # Drain any stale data
        while self._uart.any():
            self._uart.read()

        self._uart.write(bytes([cmd_byte]))

        # Wait for response line
        start = time.ticks_ms()
        buf = b""
        while time.ticks_diff(time.ticks_ms(), start) < timeout_ms:
            if self._uart.any():
                chunk = self._uart.read()
                if chunk:
                    buf += chunk
                    if b"\n" in buf:
                        return buf.decode("utf-8").strip()
            time.sleep_ms(10)

        if buf:
            return f"ERR:partial({buf})"
        return f"ERR:timeout({timeout_ms}ms)"

    def probe(self):
        """Single fast check if ESP32-CAM is responding. Non-blocking —
        returns immediately if no response. The camera may still be
        booting and will work on subsequent reads.

        Returns:
            str: "OK" on success, or error string.
        """
        while self._uart.any():
            self._uart.read()

        resp = self._send_cmd(_CMD_STATUS, timeout_ms=500)
        if resp.startswith("ACK:"):
            return "OK"
        return resp

    def read(self):
        """Read image count from the ESP32-CAM (STATUS command).
        Also resets the ESP32-CAM watchdog timer.

        Returns:
            dict: {"cam_count": int} -- number of images on SD, or -1 on error.
                  {"cam_count": -1, "error": str} on failure.
        """
        self._last_status_ms = time.ticks_ms()
        resp = self._send_cmd(_CMD_STATUS)
        if resp.startswith("ACK:count="):
            try:
                self._last_count = int(resp.split("=")[1])
            except (ValueError, IndexError):
                self._last_count = -1
                return {"cam_count": -1, "error": f"bad count: {resp}"}
        else:
            self._last_count = -1
            return {"cam_count": -1, "error": resp}
        return {"cam_count": self._last_count}

    @property
    def needs_keepalive(self):
        """True if ESP32-CAM watchdog is about to fire (>20s since last STATUS)."""
        return time.ticks_diff(time.ticks_ms(), self._last_status_ms) > (_WATCHDOG_MS - 10000)

    def keepalive(self):
        """Send a lightweight STATUS poll to reset the ESP32-CAM watchdog.
        Discards the response — use read() when you need the count."""
        self._last_status_ms = time.ticks_ms()
        self._send_cmd(_CMD_STATUS, timeout_ms=500)

    def capture(self):
        """Trigger a photo capture on the ESP32-CAM.

        Returns:
            tuple: (filename, None) on success, (None, error_str) on failure.
        """
        resp = self._send_cmd(_CMD_CAPTURE)
        if resp.startswith("ACK:"):
            self._last_file = resp[4:]
            return self._last_file, None
        self._last_file = None
        return None, resp

    def webui_on(self):
        """Start WiFi AP + HTTP server on the ESP32-CAM."""
        return self._send_cmd(_CMD_WEBUI_ON, timeout_ms=5000)

    def webui_off(self):
        """Stop WiFi AP + HTTP server on the ESP32-CAM."""
        return self._send_cmd(_CMD_WEBUI_OFF)

    def _send_raw(self, payload, timeout_ms=None):
        """Send raw bytes and read the response line.

        Args:
            payload (bytes): Raw bytes to send.
            timeout_ms (int): Response timeout in ms.

        Returns:
            str | None: Response string (stripped), or None on timeout.
        """
        if timeout_ms is None:
            timeout_ms = self._timeout_ms

        while self._uart.any():
            self._uart.read()

        self._uart.write(payload)

        start = time.ticks_ms()
        buf = b""
        while time.ticks_diff(time.ticks_ms(), start) < timeout_ms:
            if self._uart.any():
                chunk = self._uart.read()
                if chunk:
                    buf += chunk
                    if b"\n" in buf:
                        return buf.decode("utf-8").strip()
            time.sleep_ms(10)
        return None

    def configure_remote(self, raw_kv_bytes):
        """Forward raw binary settings to the ESP32-CAM.

        The Pico does not interpret the key-value pairs — it just relays
        them between LoRa and UART.  Uses fixed-length payload: count
        prefix byte followed by exactly count×2 data bytes (no 0x00
        terminator, so value 0x00 is safe).

        Args:
            raw_kv_bytes (bytes): Key-value pairs (e.g. b'\\x02\\x0A\\x16\\x01').

        Returns:
            str | None: ACK response string, or None on failure.
        """
        num_pairs = len(raw_kv_bytes) // 2
        payload = bytes([_CMD_SET_SETTINGS, num_pairs]) + raw_kv_bytes
        return self._send_raw(payload)

    def read_settings(self):
        """Read all current settings from the ESP32-CAM as raw bytes.

        Response format: 0x04 (echo) + 21 key-value pairs (42 bytes), no terminator.
        We read a fixed 43 bytes (echo + data) and strip the echo byte.

        Returns:
            bytes | None: Raw key-value pairs (21 pairs, 42 bytes),
                          or None on failure.
        """
        timeout_ms = self._timeout_ms

        while self._uart.any():
            self._uart.read()

        self._uart.write(bytes([_CMD_GET_SETTINGS]))

        # Fixed read: 1 echo byte + 42 data bytes = 43
        expected = 43
        start = time.ticks_ms()
        buf = b""
        while time.ticks_diff(time.ticks_ms(), start) < timeout_ms:
            if self._uart.any():
                chunk = self._uart.read()
                if chunk:
                    buf += chunk
                    if len(buf) >= expected:
                        return buf[1:expected]  # strip 0x04 echo
            time.sleep_ms(10)
        return None

    def configure(self, **kwargs):
        """Configure ManhaCam peripheral parameters (local, not camera settings).

        Args:
            **kwargs: Supported keys: timeout_ms (int).
        """
        if "timeout_ms" in kwargs:
            self._timeout_ms = kwargs["timeout_ms"]
