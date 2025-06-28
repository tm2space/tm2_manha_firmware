"""
Satellite LoRa communication module for MANHA project
"""

import time
import asyncio
import json
import gc
import os
from machine import Pin, SPI, reset

from manha.internals.drivers import RFM9x, ModemConfig
from manha.internals.drivers.rfm9x_constants import *
from manha.internals.comms.packet import Packet
from .constants import *


class LoRa:
    """
    Satellite LoRa communication class
    
    Handles:
    - JSON telemetry transmission (single/multipart)
    - Command reception and processing
    - 120s timeout beaconing mechanism
    - RESET command with file handling
    """
    
    def __init__(self, device_id: int, cs_pin: Pin, spi: SPI, reset_pin: Pin = None,
                 freq: float = 868.0, tx_power: int = 14, timeout_ms: int = 1000, led_matrix=None):
        """
        Initialize Satellite LoRa
        
        Args:
            device_id: Satellite address (0-255)
            cs_pin: Chip select pin
            spi: SPI interface
            reset_pin: Reset pin (optional)
            freq: Frequency in MHz
            tx_power: TX power in dBm (5-23)
            timeout_ms: Operation timeout
            led_matrix: LED matrix instance for visual indicators
        """
        self.device_id = device_id
        self.ground_station_address = None  # Set when first packet received
        self.led_matrix = led_matrix  # LED matrix for visual feedback
        
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
        self._last_ack_time = time.ticks_ms()
        self._beacon_mode = False
        self._beacon_interval = 10000  # 10s default, adjustable based on power/priority
        
        # Command handling
        self._command_handlers = {
            'PING': self._handle_ping,
            'RESET': self._handle_reset
        }
        
        # Callbacks
        self._callbacks = {
            CALLBACK_TELEMETRY_REQUEST: None,
            CALLBACK_COMMAND: None
        }
        
        # Check for reset file on startup
        self._check_reset_file()
    
    def _check_reset_file(self):
        """Check for RMT_RESET file on startup"""
        try:
            if 'RMT_RESET' in os.listdir('/'):
                os.remove('/RMT_RESET')
                # Will send RESET_OK on first transmission
                self._reset_occurred = True
            else:
                self._reset_occurred = False
        except:
            self._reset_occurred = False
    
    async def send_telemetry_and_listen(self, data: dict, target_addr: int = None, max_size: int = 200, listen_timeout: int = 5000) -> tuple:
        """
        Send telemetry data and then listen for response
        
        Args:
            data: Telemetry data dictionary
            target_addr: Target address 
            max_size: Maximum single packet size
            listen_timeout: Time to listen for response after sending
            
        Returns:
            tuple: (send_success: bool, received_packet: Packet or None)
        """
        send_success = await self.send_telemetry(data, target_addr, max_size)
        
        if send_success:
            # After successful send, listen for response
            received_packet = await self._listen_for_packet(listen_timeout)
            return (True, received_packet)
        else:
            return (False, None)
    
    async def send_telemetry(self, data: dict, target_addr: int = None, max_size: int = 200) -> bool:
        """
        Send telemetry data as JSON (with multipart support)
        
        Args:
            data: Telemetry data dictionary
            target_addr: Target address (uses ground_station_address if None)
            max_size: Maximum single packet size
            
        Returns:
            bool: True if sent successfully
        """
        if target_addr is None:
            target_addr = self.ground_station_address or 255  # Broadcast if unknown
        
        try:
            # Check if we need to send RESET_OK first
            if self._reset_occurred:
                await self._send_command_response("RESET_OK", target_addr)
                self._reset_occurred = False
            
            json_str = json.dumps(data)
            json_bytes = json_str.encode('utf-8')
            
            # Check if we need multipart
            if len(json_bytes) <= max_size:
                # Single part
                packet = Packet(target_addr, self.device_id, json_bytes)
                return await self._send_packet_with_ack(packet, 0)
            else:
                # Multipart transmission
                return await self._send_multipart_json(json_str, target_addr, max_size)
                
        except Exception as e:
            print(f"Telemetry send error: {e}")
            await self._flash_led_error()
            return False
    
    async def _send_multipart_json(self, json_str: str, target_addr: int, max_size: int) -> bool:
        """Send JSON as multipart packets"""
        try:
            # Calculate how many parts we need
            available_size = max_size - 50  # Reserve space for multipart metadata
            total_parts = (len(json_str) + available_size - 1) // available_size
            
            for part_num in range(1, total_parts + 1):
                start_idx = (part_num - 1) * available_size
                end_idx = min(start_idx + available_size, len(json_str))
                part_data = json_str[start_idx:end_idx]
                
                # Create multipart packet
                multipart_data = {
                    '_part': part_num,
                    '_total': total_parts,
                    'data': part_data
                }
                
                packet_json = json.dumps(multipart_data)
                packet = Packet(target_addr, self.device_id, packet_json.encode('utf-8'))
                
                # Send and wait for ACK
                success = await self._send_packet_with_ack(packet, part_num)
                if not success:
                    print(f"Multipart transmission failed at part {part_num}")
                    await self._flash_led_ack_error()
                    return False
                
                # Small delay between parts
                await asyncio.sleep_ms(50)
            
            return True
            
        except Exception as e:
            print(f"Multipart send error: {e}")
            await self._flash_led_error()
            return False
    
    async def _send_packet_with_ack(self, packet: Packet, expected_ack_part: int, timeout_ms: int = 5000) -> bool:
        """Send packet and wait for ACK"""
        try:
            async with self._lock:
                self._modem.set_mode_idle()
                if not self._modem.send(packet.encode()):
                    return False
                
                if not await self._wait_for_tx_complete():
                    return False
            
            # Wait for ACK
            ack_received = await self._wait_for_ack(expected_ack_part, timeout_ms)
            if not ack_received:
                await self._flash_led_ack_error()
            return ack_received
            
        except Exception as e:
            print(f"Packet send error: {e}")
            await self._flash_led_error()
            return False
    
    async def _listen_for_packet(self, timeout_ms: int) -> Packet:
        """Listen for any incoming packet"""
        start_time = time.ticks_ms()
        
        while time.ticks_diff(time.ticks_ms(), start_time) < timeout_ms:
            self._modem.set_mode_rx()
            
            # Check for received data
            if self._modem._is_flag_set(RX_DONE):
                recv_result = self._modem.recv_data()
                if recv_result:
                    raw_data, rssi, snr = recv_result
                    packet = Packet.decode(raw_data, rssi, snr)
                    if packet and packet.is_valid_checksum():
                        # Update last communication time
                        self._last_ack_time = time.ticks_ms()
                        
                        # Process the packet
                        await self._process_received_data(raw_data, rssi, snr)
                        return packet
            
            await asyncio.sleep_ms(10)
        
        return None
    
    async def _wait_for_ack(self, expected_part: int, timeout_ms: int) -> bool:
        """Wait for ACK packet"""
        packet = await self._listen_for_packet(timeout_ms)
        
        if packet:
            message = packet.message.decode('utf-8').strip()
            if message.startswith('ACK:'):
                try:
                    ack_part = int(message[4:])
                    return ack_part == expected_part
                except ValueError:
                    pass
        
        return False
    
    async def _send_command_response(self, response: str, target_addr: int) -> bool:
        """Send command response"""
        try:
            message = f"CMD:{response}\r\n".encode('utf-8')
            packet = Packet(target_addr, self.device_id, message)
            
            async with self._lock:
                self._modem.set_mode_idle()
                if self._modem.send(packet.encode()):
                    return await self._wait_for_tx_complete()
                return False
                
        except Exception as e:
            print(f"Command response error: {e}")
            await self._flash_led_error()
            return False
    
    def add_command_handler(self, command: str, handler):
        """Add custom command handler"""
        self._command_handlers[command] = handler
    
    def set_callback(self, callback_type: int, callback_func):
        """Set callback function"""
        if callback_type in self._callbacks:
            self._callbacks[callback_type] = callback_func
    
    async def start_receiver(self):
        """Start receiver task"""
        if not self._receiver_running:
            self._stop_receiver = False
            asyncio.create_task(self._receiver_loop())
    
    async def stop_receiver(self):
        """Stop receiver"""
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
        """Process received command data"""
        try:
            packet = Packet.decode(raw_data, rssi, snr)
            if not packet or not packet.is_valid_checksum():
                return
            
            # Set ground station address from first valid packet
            if self.ground_station_address is None:
                self.ground_station_address = packet.addr_from
            
            message = packet.message.decode('utf-8').strip()
            
            # Handle commands
            if message.startswith('CMD:'):
                command = message[4:].strip()
                await self._handle_command(command, packet.addr_from)
                
        except Exception as e:
            print(f"Data processing error: {e}")
            await self._flash_led_error()
    
    async def _handle_command(self, command: str, sender_addr: int):
        """Handle received command"""
        try:
            if command in self._command_handlers:
                await self._command_handlers[command](sender_addr)
            elif self._callbacks[CALLBACK_COMMAND]:
                await self._callbacks[CALLBACK_COMMAND](command, sender_addr)
            else:
                print(f"Unknown command: {command}")
                
        except Exception as e:
            print(f"Command handling error: {e}")
            await self._flash_led_error()
    
    async def _handle_ping(self, sender_addr: int):
        """Handle PING command"""
        await self._send_command_response("PING_OK", sender_addr)
    
    async def _handle_reset(self, sender_addr: int):
        """Handle RESET command"""
        try:
            # Create reset file
            with open('/RMT_RESET', 'w') as f:
                f.write(str(time.time()))
            
            # Send acknowledgment
            await self._send_command_response("RESET_ACK", sender_addr)
            
            # Small delay then reset
            await asyncio.sleep_ms(1000)
            reset()
            
        except Exception as e:
            print(f"Reset handling error: {e}")
            await self._flash_led_error()
    
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
    
    def set_beacon_interval(self, interval_ms: int):
        """Set beacon interval based on power mode/priority"""
        self._beacon_interval = interval_ms
    
    def set_tx_power(self, tx_power: int):
        """Set transmission power (5-23 dBm)"""
        if 5 <= tx_power <= 23:
            self._modem.set_tx_power(tx_power)
        else:
            raise ValueError("tx_power must be between 5 and 23 dBm")
    
    async def _flash_led_ack_error(self):
        """Flash LED matrix MAGENTA for ACK failures"""
        if self.led_matrix:
            try:
                # Import here to avoid circular imports
                from manha.satkit.peripherals import PixelColors
                self.led_matrix.fill(PixelColors.MAGENTA)
                await asyncio.sleep_ms(200)
                self.led_matrix.clear()
            except Exception as e:
                print(f"LED ACK error flash failed: {e}")
    
    async def _flash_led_error(self):
        """Flash LED matrix RED for general LoRa errors"""
        if self.led_matrix:
            try:
                # Import here to avoid circular imports
                from manha.satkit.peripherals import PixelColors
                self.led_matrix.fill(PixelColors.RED)
                await asyncio.sleep_ms(200)
                self.led_matrix.clear()
            except Exception as e:
                print(f"LED error flash failed: {e}")