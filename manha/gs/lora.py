"""
Ground Station LoRa communication module for MANHA project
"""

import time
import asyncio
import json
import gc
from machine import Pin, SPI

from manha.internals.drivers import RFM9x, ModemConfig
from manha.internals.drivers.rfm9x_constants import *
from manha.internals.comms.packet import Packet, MSG_TM, MSG_TC, MSG_TC_ACK
from manha.config import USE_LEGACY_PACKETIZATION
from .constants import *


class LoRa:
    """
    Ground Station LoRa communication class

    Handles:
    - Command transmission
    - Telemetry reception (binary or legacy JSON)
    - ACK transmission
    - Command response processing
    """

    def __init__(
        self,
        device_id: int,
        cs_pin: Pin,
        spi: SPI,
        reset_pin: Pin = None,
        freq: float = 868.0,
        tx_power: int = 14,
        timeout_ms: int = 1000,
    ):
        """
        Initialize Ground Station LoRa

        Args:
            device_id: Ground station address (0-255)
            cs_pin: Chip select pin
            spi: SPI interface
            reset_pin: Reset pin (optional)
            freq: Frequency in MHz
            tx_power: TX power in dBm (5-23)
            timeout_ms: Operation timeout
        """
        self.device_id = device_id
        self.satellite_address = device_id

        if reset_pin:
            reset_pin.value(0)
            time.sleep_ms(100)
            reset_pin.value(1)
            time.sleep_ms(100)

        self._modem = RFM9x(
            id=device_id,
            cs=cs_pin,
            spi=spi,
            reset=reset_pin,
            freq=freq,
            tx_power=tx_power,
            timeout_ms=timeout_ms,
        )

        self._lock = asyncio.Lock()
        self._receiver_running = False
        self._stop_receiver = False
        self._tx_in_progress = False
        self._last_telemetry = None
        self._last_tm_time = 0
        self._tc_ack_event = asyncio.Event()
        self._callbacks = {CALLBACK_TELEMETRY: None, CALLBACK_COMMAND_RESPONSE: None}

    async def send_command(
        self,
        command: str,
        target_addr: int = None,
        retries: int = 3,
        ack_timeout_ms: int = 1500,
    ) -> bool:
        """Send command to satellite with retry until TC_ACK

        Args:
            command: Command string (e.g., "PING", "RESET")
            target_addr: Target address (uses satellite_address if None)
            retries: Number of send attempts
            ack_timeout_ms: Timeout per attempt waiting for TC_ACK

        Returns:
            bool: True if TC_ACK received
        """
        if target_addr is None:
            target_addr = self.satellite_address

        if USE_LEGACY_PACKETIZATION:
            message = f"CMD:{command}\r\n".encode("utf-8")
        else:
            message = command.encode("utf-8")

        if USE_LEGACY_PACKETIZATION:
            packet = Packet(target_addr, self.device_id, message)
        else:
            packet = Packet(
                target_addr, self.device_id, message, msg_type=MSG_TC
            )

        encoded = packet.encode()

        for attempt in range(retries):
            try:
                self._tc_ack_event.clear()
                self._tx_in_progress = True

                self._modem.set_mode_idle()
                if not self._modem.send(encoded):
                    self._tx_in_progress = False
                    self._modem.set_mode_rx()
                    continue
                if not await self._wait_for_tx_complete():
                    self._tx_in_progress = False
                    self._modem.set_mode_rx()
                    continue
                self._tx_in_progress = False
                self._modem.set_mode_rx()

                # Wait for TC_ACK from receiver loop
                start = time.ticks_ms()
                while time.ticks_diff(time.ticks_ms(), start) < ack_timeout_ms:
                    if self._tc_ack_event.is_set():
                        return True
                    await asyncio.sleep_ms(20)

                print(f"TC:{attempt + 1}/{retries}")

            except Exception as e:
                self._tx_in_progress = False
                print(f"Command send error: {e}")

        return False

    def set_callback(self, callback_type: int, callback_func):
        """Set callback for received data

        Args:
            callback_type: CALLBACK_TELEMETRY or CALLBACK_COMMAND_RESPONSE
            callback_func: Async function to call
        """
        if callback_type in self._callbacks:
            self._callbacks[callback_type] = callback_func

    async def start_receiver(self):
        """Start the receiver loop"""
        if not self._receiver_running:
            self._stop_receiver = False
            asyncio.create_task(self._receiver_loop())

    async def stop_receiver(self):
        """Stop the receiver loop"""
        self._stop_receiver = True
        while self._receiver_running:
            await asyncio.sleep_ms(10)

    async def _receiver_loop(self):
        """Main receiver loop. Pauses when send_command() is transmitting
        to avoid aborting TX by switching modem to RX."""
        self._receiver_running = True

        while not self._stop_receiver:
            try:
                # Skip modem access while TX is in progress
                if self._tx_in_progress:
                    await asyncio.sleep_ms(10)
                    continue

                self._modem.set_mode_rx()

                start_time = time.ticks_ms()
                recv_result = None
                while not self._stop_receiver and not self._tx_in_progress:
                    if self._modem._is_flag_set(RX_DONE):
                        recv_result = self._modem.recv_data()
                        break

                    if time.ticks_diff(time.ticks_ms(), start_time) > 1000:
                        break

                    await asyncio.sleep_ms(5)

                if recv_result:
                    raw_data, rssi, snr = recv_result
                    await self._process_received_data(raw_data, rssi, snr)

                await asyncio.sleep_ms(10)

            except Exception as e:
                print(f"Receiver error: {e}")
                await asyncio.sleep_ms(100)

        self._receiver_running = False

    async def _process_received_data(self, raw_data: bytes, rssi: int, snr: float):
        """Process received data, routing by message type"""
        try:
            packet = Packet.decode(raw_data, rssi, snr)
            if not packet or not packet.is_valid_checksum():
                return

            if USE_LEGACY_PACKETIZATION:
                await self._process_legacy(packet)
            else:
                await self._process_binary(packet)

        except Exception as e:
            print(f"Data processing error: {e}")

    async def _process_legacy(self, packet: Packet):
        """Process legacy JSON-based packet"""
        message = packet.message.decode("utf-8").strip()

        if message.startswith("CMD:"):
            await self._handle_command_response(message[4:], packet)
        elif message.startswith("{"):
            try:
                data = json.loads(message)
                if isinstance(data, dict) and "_part" in data:
                    # Multipart (legacy, rarely used)
                    return
                print(f"TM:{message}")
                self._last_telemetry = data
                if self._callbacks[CALLBACK_TELEMETRY]:
                    await self._callbacks[CALLBACK_TELEMETRY](data, packet)
            except Exception as e:
                print(f"JSON parse error: {e}")
        else:
            print(f"AK:{message}")
            if self._callbacks[CALLBACK_COMMAND_RESPONSE]:
                await self._callbacks[CALLBACK_COMMAND_RESPONSE](message, packet)

    async def _process_binary(self, packet: Packet):
        """Process binary protocol packet by msg_type"""
        if packet.msg_type == MSG_TM:
            await self._handle_binary_telemetry(packet)
        elif packet.msg_type == MSG_TC_ACK:
            response = packet.message.decode("utf-8").strip()
            await self._handle_command_response(response, packet)
        else:
            print(f"Unknown msg_type: {packet.msg_type}")

    async def _handle_binary_telemetry(self, packet: Packet):
        """Decode binary telemetry, forward as JSON over serial"""
        try:
            from manha.internals.comms.binary_tlm import decode_tlm

            data = decode_tlm(packet.message)
            if data is None:
                print("TLM decode error: invalid binary data")
                return

            seq = data.get("seq", 0)

            # Forward as JSON over USB serial (app compatibility)
            json_str = json.dumps(data)
            print(f"TM:{json_str}")

            self._last_telemetry = data
            self._last_tm_time = time.ticks_ms()
            if self._callbacks[CALLBACK_TELEMETRY]:
                await self._callbacks[CALLBACK_TELEMETRY](data, packet)

        except Exception as e:
            print(f"Binary TLM error: {e}")

    async def _handle_command_response(self, response: str, packet: Packet):
        """Handle command response"""
        print(f"AK:{response}")
        self._tc_ack_event.set()
        if self._callbacks[CALLBACK_COMMAND_RESPONSE]:
            try:
                await self._callbacks[CALLBACK_COMMAND_RESPONSE](response, packet)
            except Exception as e:
                print(f"Command response callback error: {e}")

    async def _wait_for_tx_complete(self, timeout_ms: int = 2000) -> bool:
        """Wait for transmission completion"""
        start_time = time.ticks_ms()
        while True:
            irq_flags = self._modem._spi_read(REG_12_IRQ_FLAGS)
            if irq_flags & TX_DONE:
                self._modem.clear_irq_flags()
                self._modem.set_mode_idle()
                return True

            if time.ticks_diff(time.ticks_ms(), start_time) > timeout_ms:
                self._modem.set_mode_idle()
                return False

            await asyncio.sleep_ms(10)

    def get_last_telemetry(self):
        """Get last received telemetry data"""
        return self._last_telemetry

    def set_tx_power(self, tx_power: int):
        """Set transmission power (5-23 dBm)"""
        if 5 <= tx_power <= 23:
            self._modem.set_tx_power(tx_power)
