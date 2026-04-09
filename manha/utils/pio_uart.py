"""PIO-based software UART for RP2040.

Uses two PIO state machines to implement a full-duplex UART on arbitrary
GPIO pins. Based on the official MicroPython PIO UART examples.

Provides a machine.UART-compatible interface (write, read, any, readline)
so it can be used as a drop-in replacement for hardware UART.

Usage:
    from manha.utils.pio_uart import PioUart

    uart = PioUart(tx_pin=5, rx_pin=6, baudrate=115200)
    uart.write(b'\\x01')
    if uart.any():
        data = uart.read()
"""

import time
from machine import Pin
from rp2 import PIO, StateMachine, asm_pio


@asm_pio(
    sideset_init=PIO.OUT_HIGH,
    out_init=PIO.OUT_HIGH,
    out_shiftdir=PIO.SHIFT_RIGHT,
)
def _pio_uart_tx():
    # Block with TX deasserted until data available
    pull()
    # Assert start bit for 8 cycles
    set(x, 7).side(0)[7]  # noqa: E211
    # Shift out 8 data bits, 8 cycles per bit
    label("bitloop")
    out(pins, 1)[6]
    jmp(x_dec, "bitloop")
    # Assert stop bit for 8 cycles (incl 1 for pull())
    nop().side(1)[6]  # noqa: E211


@asm_pio(
    autopush=True,
    push_thresh=8,
    in_shiftdir=PIO.SHIFT_RIGHT,
    fifo_join=PIO.JOIN_RX,
)
def _pio_uart_rx():
    # Wait for start bit
    wait(0, pin, 0)
    # Preload bit counter, delay until eye of first data bit
    set(x, 7)[10]
    # Sample 8 data bits, 8 cycles per bit
    label("bitloop")
    in_(pins, 1)
    jmp(x_dec, "bitloop")[6]


class PioUart:
    """Software UART using RP2040 PIO state machines.

    Implements a machine.UART-compatible interface for use on any GPIO pins.
    Uses two state machines: one for TX and one for RX.

    Args:
        tx_pin (int): GPIO pin number for transmit.
        rx_pin (int): GPIO pin number for receive.
        baudrate (int): Baud rate (default 115200).
        sm_tx (int): PIO state machine index for TX (0-7, default 0).
        sm_rx (int): PIO state machine index for RX (0-7, default 1).
    """

    def __init__(self, tx_pin, rx_pin, baudrate=115200, sm_tx=0, sm_rx=1):
        self._baudrate = baudrate
        freq = 8 * baudrate

        self._sm_tx = StateMachine(
            sm_tx,
            _pio_uart_tx,
            freq=freq,
            sideset_base=Pin(tx_pin),
            out_base=Pin(tx_pin),
        )

        self._sm_rx = StateMachine(
            sm_rx,
            _pio_uart_rx,
            freq=freq,
            in_base=Pin(rx_pin, Pin.IN, Pin.PULL_UP),
        )

        self._sm_tx.active(1)
        self._sm_rx.active(1)

    def write(self, data):
        """Write bytes to the TX FIFO.

        Args:
            data (bytes | bytearray): Data to transmit.

        Returns:
            int: Number of bytes written.
        """
        for b in data:
            self._sm_tx.put(b)
        return len(data)

    def any(self):
        """Check if data is available in the RX FIFO.

        Returns:
            int: Number of words available (each word = 1 byte).
        """
        return self._sm_rx.rx_fifo()

    def read(self, nbytes=None):
        """Read available bytes from the RX FIFO (non-blocking).

        Args:
            nbytes (int | None): Max bytes to read. None = read all available.

        Returns:
            bytes | None: Data read, or None if nothing available.
        """
        buf = []
        count = 0
        while self._sm_rx.rx_fifo() > 0:
            if nbytes is not None and count >= nbytes:
                break
            word = self._sm_rx.get()
            buf.append(word >> 24)
            count += 1
        return bytes(buf) if buf else None

    def readline(self, timeout_ms=1000):
        """Read bytes until a newline character or timeout.

        Args:
            timeout_ms (int): Timeout in milliseconds.

        Returns:
            bytes | None: Line including newline, or None on timeout.
        """
        buf = []
        start = time.ticks_ms()
        while time.ticks_diff(time.ticks_ms(), start) < timeout_ms:
            if self._sm_rx.rx_fifo() > 0:
                word = self._sm_rx.get()
                b = word >> 24
                buf.append(b)
                if b == 0x0A:  # newline
                    return bytes(buf)
            else:
                time.sleep_ms(1)
        return bytes(buf) if buf else None

    def deinit(self):
        """Stop both state machines."""
        self._sm_tx.active(0)
        self._sm_rx.active(0)
