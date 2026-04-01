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
from manha.internals.comms.packet import Packet, MSG_TLM, MSG_ACK, MSG_CMD, MSG_CMD_RESP
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
        self._last_telemetry = None
        self._callbacks = {CALLBACK_TELEMETRY: None, CALLBACK_COMMAND_RESPONSE: None}

    async def send_command(self, command: str, target_addr: int = None) -> bool:
        """Send command to satellite

        Args:
            command: Command string (e.g., "PING", "RESET")
            target_addr: Target address (uses satellite_address if None)

        Returns:
            bool: True if sent successfully
        """
        if target_addr is None:
            target_addr = self.satellite_address

        try:
            if USE_LEGACY_PACKETIZATION:
                message = f"CMD:{command}\r\n".encode("utf-8")
                packet = Packet(target_addr, self.device_id, message)
            else:
                message = command.encode("utf-8")
                packet = Packet(target_addr, self.device_id, message, msg_type=MSG_CMD)

            async with self._lock:
                self._modem.set_mode_idle()
                if self._modem.send(packet.encode()):
                    return await self._wait_for_tx_complete()
                return False

        except Exception as e:
            print(f"Command send error: {e}")
            return False

    async def send_ack(self, seq: int, target_addr: int) -> bool:
        """Send ACK packet

        Args:
            seq: Sequence number to acknowledge
            target_addr: Target address

        Returns:
            bool: True if sent successfully
        """
        try:
            if USE_LEGACY_PACKETIZATION:
                message = f"ACK:{seq}\r\n".encode("utf-8")
                packet = Packet(target_addr, self.device_id, message)
            else:
                message = bytes([seq & 0xFF])
                packet = Packet(target_addr, self.device_id, message, msg_type=MSG_ACK)

            async with self._lock:
                self._modem.set_mode_idle()
                if self._modem.send(packet.encode()):
                    return await self._wait_for_tx_complete()
                return False

        except Exception as e:
            print(f"ACK send error: {e}")
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
        """Main receiver loop"""
        self._receiver_running = True

        while not self._stop_receiver:
            try:
                self._modem.set_mode_rx()

                start_time = time.ticks_ms()
                while not self._stop_receiver:
                    if self._modem._is_flag_set(RX_DONE):
                        recv_result = self._modem.recv_data()
                        if recv_result:
                            raw_data, rssi, snr = recv_result
                            await self._process_received_data(raw_data, rssi, snr)
                        break

                    if time.ticks_diff(time.ticks_ms(), start_time) > 1000:
                        break

                    await asyncio.sleep_ms(5)

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
                print(f"TLM:{message}")
                await self.send_ack(0, packet.addr_from)
                self._last_telemetry = data
                if self._callbacks[CALLBACK_TELEMETRY]:
                    await self._callbacks[CALLBACK_TELEMETRY](data, packet)
            except Exception as e:
                print(f"JSON parse error: {e}")
        else:
            print(f"CMDR:{message}")
            if self._callbacks[CALLBACK_COMMAND_RESPONSE]:
                await self._callbacks[CALLBACK_COMMAND_RESPONSE](message, packet)

    async def _process_binary(self, packet: Packet):
        """Process binary protocol packet by msg_type"""
        if packet.msg_type == MSG_TLM:
            await self._handle_binary_telemetry(packet)
        elif packet.msg_type == MSG_CMD_RESP:
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
            print(f"TLM:{json_str}")

            await self.send_ack(seq, packet.addr_from)
            self._last_telemetry = data
            if self._callbacks[CALLBACK_TELEMETRY]:
                await self._callbacks[CALLBACK_TELEMETRY](data, packet)

        except Exception as e:
            print(f"Binary TLM error: {e}")

    async def _handle_command_response(self, response: str, packet: Packet):
        """Handle command response"""
        print(f"CMDR:{response}")
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
