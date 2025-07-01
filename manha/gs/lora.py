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
from manha.internals.comms.packet import Packet
from .constants import *


class LoRa:
    """
    Ground Station LoRa communication class
    
    Handles:
    - Command transmission as CMD:<COMMAND>\r\n
    - JSON telemetry reception (single/multipart)
    - ACK transmission with ACK:<part>\r\n format
    - Command response processing
    """
    
    def __init__(self, device_id: int, cs_pin: Pin, spi: SPI, reset_pin: Pin = None,
                 freq: float = 868.0, tx_power: int = 14, timeout_ms: int = 1000):
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
        self.satellite_address = device_id  # Set when first packet received
        
        # Initialize hardware
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
            timeout_ms=timeout_ms
        )
        
        # State management
        self._lock = asyncio.Lock()
        self._receiver_running = False
        self._stop_receiver = False
        self._multipart_buffer = {}
        self._last_telemetry = None
        self._callbacks = {
            CALLBACK_TELEMETRY: None,
            CALLBACK_COMMAND_RESPONSE: None
        }
    
    async def send_command(self, command: str, target_addr: int = None) -> bool:
        """
        Send command to satellite
        
        Args:
            command: Command string (e.g., "PING", "RESET")
            target_addr: Target address (uses satellite_address if None)
            
        Returns:
            bool: True if sent successfully
        """
        if target_addr is None:
            target_addr = self.satellite_address
        
        try:
            message = f"CMD:{command}\r\n".encode('utf-8')
            packet = Packet(target_addr, self.device_id, message)
            
            async with self._lock:
                self._modem.set_mode_idle()
                if self._modem.send(packet.encode()):
                    return await self._wait_for_tx_complete()
                return False
                
        except Exception as e:
            print(f"Command send error: {e}")
            return False
    
    async def send_ack(self, part: int, target_addr: int) -> bool:
        """
        Send ACK packet
        
        Args:
            part: Part number (0 for single part)
            target_addr: Target address
            
        Returns:
            bool: True if sent successfully
        """
        try:
            message = f"ACK:{part}\r\n".encode('utf-8')
            packet = Packet(target_addr, self.device_id, message)
            
            async with self._lock:
                self._modem.set_mode_idle()
                if self._modem.send(packet.encode()):
                    return await self._wait_for_tx_complete()
                return False
                
        except Exception as e:
            print(f"ACK send error: {e}")
            return False
    
    def set_callback(self, callback_type: int, callback_func):
        """
        Set callback for received data
        
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
                        # recv_data returns (bytes, rssi, snr)
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
        """Process received data"""
        try:
            # Decode packet
            packet = Packet.decode(raw_data, rssi, snr)
            if not packet or not packet.is_valid_checksum():
                return
            
            message = packet.message.decode('utf-8').strip()
            
            # Handle different message types
            if message.startswith('CMD:'):
                # Command response - don't ACK
                await self._handle_command_response(message[4:], packet)
            else:
                # Assume telemetry JSON
                await self._handle_telemetry(message, packet)
                
        except Exception as e:
            print(f"Data processing error: {e}")
    
    async def _handle_command_response(self, response: str, packet: Packet):
        """Handle command response"""
        print(f"CMDR:{response}")
        if self._callbacks[CALLBACK_COMMAND_RESPONSE]:
            try:
                await self._callbacks[CALLBACK_COMMAND_RESPONSE](response, packet)
            except Exception as e:
                print(f"Command response callback error: {e}")
    
    async def _handle_telemetry(self, message: str, packet: Packet):
        """Handle telemetry data (JSON) or simple text responses"""
        try:
            if packet.addr_to != self.satellite_address:
                return
            
            # Check if message starts with '{' to determine if it's JSON
            if not message.startswith('{'):
                # Not JSON - treat as command response
                print(f"CMDR:{message}")
                if self._callbacks[CALLBACK_COMMAND_RESPONSE]:
                    await self._callbacks[CALLBACK_COMMAND_RESPONSE](message, packet)
                return
            
            # Try to parse as JSON
            data = json.loads(message)
            
            # Check if JSON parsing actually worked (MicroPython returns string if invalid)
            if isinstance(data, str) and data == message:
                print(f"INVALID:{message}")
                return
            
            # Valid telemetry
            print(f"TLM:{message}")
            
            # Check for multipart data
            if isinstance(data, dict) and '_part' in data:
                complete_data = await self._handle_multipart(data, packet.addr_from)
                if complete_data:
                    self._last_telemetry = complete_data
                    if self._callbacks[CALLBACK_TELEMETRY]:
                        await self._callbacks[CALLBACK_TELEMETRY](complete_data, packet)
            else:
                # Single part telemetry
                await self.send_ack(0, packet.addr_from)
                self._last_telemetry = data
                if self._callbacks[CALLBACK_TELEMETRY]:
                    await self._callbacks[CALLBACK_TELEMETRY](data, packet)
                    
        except Exception as e:
            print(f"Telemetry handling error: {e}")
    
    async def _handle_multipart(self, data: dict, sender_id: int):
        """Handle multipart JSON reconstruction"""
        try:
            part_num = data.get('_part', 1)
            total_parts = data.get('_total', 1)
            part_data = data.get('data', '')
            
            # Send ACK for this part
            await self.send_ack(part_num, sender_id)
            
            # Initialize buffer for this sender
            if sender_id not in self._multipart_buffer:
                self._multipart_buffer[sender_id] = {}
            
            # Store this part
            self._multipart_buffer[sender_id][part_num] = part_data
            
            # Check if we have all parts
            if len(self._multipart_buffer[sender_id]) == total_parts:
                # Reconstruct complete message
                complete_data = ''
                for i in range(1, total_parts + 1):
                    if i in self._multipart_buffer[sender_id]:
                        complete_data += self._multipart_buffer[sender_id][i]
                
                # Clear buffer for this sender
                del self._multipart_buffer[sender_id]
                gc.collect()
                
                # Parse complete JSON
                parsed_data = json.loads(complete_data)
                # Check if JSON parsing worked (MicroPython returns string if invalid)
                if isinstance(parsed_data, str) and parsed_data == complete_data:
                    print(f"INVALID:{complete_data}")
                    return None
                return parsed_data
            
            return None  # Incomplete
            
        except Exception as e:
            print(f"Multipart handling error: {e}")
            return None
    
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
        else:
            raise ValueError("tx_power must be between 5 and 23 dBm")
