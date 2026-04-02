"""ManhaCam - ESP32-CAM serial interface peripheral"""

import machine
import time
from .base import ManhaSensor

from micropython import const

_DEFAULT_UART_ID = const(1)
_DEFAULT_TX_PIN = const(4)
_DEFAULT_RX_PIN = const(5)
_DEFAULT_BAUD = const(115200)
_DEFAULT_TIMEOUT_MS = const(2000)

_CMD_CAPTURE = const(0x01)
_CMD_STATUS = const(0x02)


class ManhaCam(ManhaSensor):
    """ESP32-CAM serial interface for the MANHA satellite kit.

    Communicates with the ESP32-CAM over UART using a single-byte
    command protocol:
        0x01 = CAPTURE  -> ACK:<filename> | NACK:capture_failed
        0x02 = STATUS   -> ACK:count=<N>

    Args:
        uart_id (int): UART peripheral ID (default 1).
        tx_pin (int): TX GPIO pin (default 4).
        rx_pin (int): RX GPIO pin (default 5).
        baud (int): Baud rate (default 115200).
        timeout_ms (int): Response timeout in ms (default 2000).
    """

    def __init__(
        self,
        uart_id=_DEFAULT_UART_ID,
        tx_pin=_DEFAULT_TX_PIN,
        rx_pin=_DEFAULT_RX_PIN,
        baud=_DEFAULT_BAUD,
        timeout_ms=_DEFAULT_TIMEOUT_MS,
    ):
        self._timeout_ms = timeout_ms
        self._uart = machine.UART(
            uart_id,
            baudrate=baud,
            tx=machine.Pin(tx_pin),
            rx=machine.Pin(rx_pin),
        )
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

    def configure(self, **kwargs):
        """Configure ManhaCam parameters.

        Args:
            **kwargs: Supported keys: timeout_ms (int).
        """
        if "timeout_ms" in kwargs:
            self._timeout_ms = kwargs["timeout_ms"]
