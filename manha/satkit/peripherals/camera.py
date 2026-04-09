"""ManhaCam - ESP32-CAM serial interface peripheral"""

import time
from .base import ManhaSensor

from micropython import const

_DEFAULT_TX_PIN = const(5)
_DEFAULT_RX_PIN = const(6)
_DEFAULT_BAUD = const(115200)
_DEFAULT_TIMEOUT_MS = const(2000)

_CMD_CAPTURE = const(0x01)
_CMD_STATUS = const(0x02)
_CMD_SET_SETTINGS = const(0x03)
_CMD_GET_SETTINGS = const(0x04)


class ManhaCam(ManhaSensor):
    """ESP32-CAM serial interface for the MANHA satellite kit.

    Communicates with the ESP32-CAM over a PIO-based software UART using
    a single-byte command protocol:
        0x01 = CAPTURE       -> ACK:<filename> | NACK:capture_failed
        0x02 = STATUS        -> ACK:count=<N>
        0x03 = SET_SETTINGS  -> key-value pairs + 0x00 -> ACK:settings=<N>
        0x04 = GET_SETTINGS  -> 0x04 + key-value pairs + 0x00

    Args:
        uart: Pre-configured UART-like object. If None, creates a PioUart.
        tx_pin (int): GPIO pin for transmit (default 5).
        rx_pin (int): GPIO pin for receive (default 6).
        baudrate (int): Baud rate (default 115200).
        timeout_ms (int): Response timeout in ms (default 2000).
    """

    def __init__(
        self,
        uart=None,
        tx_pin=_DEFAULT_TX_PIN,
        rx_pin=_DEFAULT_RX_PIN,
        baudrate=_DEFAULT_BAUD,
        timeout_ms=_DEFAULT_TIMEOUT_MS,
    ):
        self._timeout_ms = timeout_ms
        if uart is not None:
            self._uart = uart
        else:
            from manha.utils.pio_uart import PioUart

            self._uart = PioUart(tx_pin=tx_pin, rx_pin=rx_pin, baudrate=baudrate)
        self._last_count = -1
        self._last_file = None

    def _send_cmd(self, cmd_byte, timeout_ms=None):
        """Send a 1-byte command and read the response line.

        Returns:
            str | None: Response string (stripped), or None on timeout.
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
        return None

    def read(self):
        """Read image count from the ESP32-CAM (STATUS command).

        Returns:
            dict: {"cam_count": int} -- number of images on SD, or -1 on error.
        """
        resp = self._send_cmd(_CMD_STATUS)
        if resp and resp.startswith("ACK:count="):
            try:
                self._last_count = int(resp.split("=")[1])
            except (ValueError, IndexError):
                self._last_count = -1
        else:
            self._last_count = -1
        return {"cam_count": self._last_count}

    def capture(self):
        """Trigger a photo capture on the ESP32-CAM.

        Returns:
            str | None: Filename on success, None on failure.
        """
        resp = self._send_cmd(_CMD_CAPTURE)
        if resp and resp.startswith("ACK:"):
            self._last_file = resp[4:]
            return self._last_file
        self._last_file = None
        return None

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

    def _read_binary_response(self, timeout_ms=None):
        """Read a binary response terminated by 0x00 followed by newline.

        Returns:
            bytes | None: Raw response bytes (excluding cmd echo and terminator),
                          or None on timeout.
        """
        if timeout_ms is None:
            timeout_ms = self._timeout_ms

        start = time.ticks_ms()
        buf = b""
        while time.ticks_diff(time.ticks_ms(), start) < timeout_ms:
            if self._uart.any():
                chunk = self._uart.read()
                if chunk:
                    buf += chunk
                    if b"\x00" in buf:
                        # Strip cmd echo byte at start and 0x00 terminator + newline
                        end = buf.index(b"\x00")
                        return buf[1:end]  # skip the 0x04 echo byte
            time.sleep_ms(10)
        return None

    def configure_remote(self, raw_kv_bytes):
        """Forward raw binary settings to the ESP32-CAM.

        The Pico does not interpret the key-value pairs — it just relays
        them between LoRa and UART.

        Args:
            raw_kv_bytes (bytes): Key-value pairs (e.g. b'\\x02\\x0A\\x16\\x01').

        Returns:
            str | None: ACK response string, or None on failure.
        """
        payload = bytes([_CMD_SET_SETTINGS]) + raw_kv_bytes + bytes([0x00])
        return self._send_raw(payload)

    def read_settings(self):
        """Read all current settings from the ESP32-CAM as raw bytes.

        Returns:
            bytes | None: Raw key-value pairs (22 pairs, 44 bytes),
                          or None on failure.
        """
        while self._uart.any():
            self._uart.read()

        self._uart.write(bytes([_CMD_GET_SETTINGS]))
        return self._read_binary_response()

    def configure(self, **kwargs):
        """Configure ManhaCam peripheral parameters (local, not camera settings).

        Args:
            **kwargs: Supported keys: timeout_ms (int).
        """
        if "timeout_ms" in kwargs:
            self._timeout_ms = kwargs["timeout_ms"]
