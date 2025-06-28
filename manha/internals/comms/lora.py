"""
▀▀█▀▀ █▀▄▀█ ▀▀▀▀█ ▄▀▀▀▀ █▀▀▀▄ ▄▀▀▀▄ ▄▀▀▀▀ █▀▀▀▀ 
  █   █   █ █▀▀▀▀  ▀▀▀▄ █▀▀▀  █▀▀▀█ █     █▀▀   
  ▀   ▀   ▀ ▀▀▀▀▀ ▀▀▀▀  ▀     ▀   ▀  ▀▀▀▀ ▀▀▀▀▀ 

LoRa communication module for the manha project.

This module provides a high-level interface for LoRa communication, including
sending and receiving data, as well as configuring the LoRa radio parameters.
"""

import time
import asyncio
from collections import namedtuple
from machine import Pin, SPI

import gc

from manha.internals.drivers import RFM9x, ModemConfig
from manha.internals.drivers.rfm9x_constants import *
from manha.utils import calculate_checksum

Packet = namedtuple(
    "Packet",
    ['sender_id', 'target_id', 'checksum', 'message', 'rssi', 'snr', 'valid_checksum']
)

def packet_processor(raw_payload: tuple) -> Packet:
    """
    Process a raw payload into a structured packet.
    
    Args:
        raw_payload: The raw packet data from the LoRa driver, a tuple of (data, rssi, snr)
        
    Returns:
        Packet: A structured packet with sender_id, target_id, checksum, message, rssi, snr, and validity of checksum.
    """
    raw_bytes, rssi, snr = raw_payload
    
    # Extract sender_id and target_id from the first 2 bytes
    sender_id = raw_bytes[0] if len(raw_bytes) > 0 else 0
    target_id = raw_bytes[1] if len(raw_bytes) > 1 else 0

    # Extract checksum and message from the remaining bytes
    if len(raw_bytes) > 2:
        checksum = raw_bytes[2]
        message = raw_bytes[3:]
    else:
        checksum = 0
        message = b''

    # Calculate checksum from received message
    calculated_checksum = calculate_checksum(message)
    valid_checksum = (calculated_checksum == checksum)

    return Packet(sender_id, target_id, checksum, message, rssi, snr, valid_checksum)


class LoRa:
    """
    High-level LoRa communication manager that provides both synchronous and 
    asynchronous interfaces for transmitting and receiving data.
    
    This class replaces the functionality of both manha.gs.lora_gs.LoRaStation 
    and manha.satkit.gs_comms.LoRAComms with a unified interface.
    """
    
    def __init__(self, 
                 device_id: int,
                 cs_pin: Pin,
                 spi: SPI,
                 reset_pin: Pin,
                 packet_processor=packet_processor,
                 recv_callback=None,
                 modem_config: tuple = ModemConfig.Bw125Cr45Sf128,
                 band: str = None,
                 channel: int = None,
                 freq: float = 868.0,
                 tx_power: int = 14,
                 timeout_ms: int = 1000):
        """
        Initialize the LoRa communications interface.
        
        Args:
            device_id: Unique identifier for this device (0-255)
            cs_pin: Chip select pin for SPI communication
            spi: SPI interface object
            reset_pin: Reset pin for the LoRa module
            packet_processor: Function to process raw payloads into structured packets (default provided)
            recv_callback: Function to process received packets
            modem_config: LoRa modem configuration (see ModemConfig class)
            band: Frequency band identifier (e.g., '800', '900')
            channel: Channel within the band
            freq: Frequency in MHz if band/channel not specified
            tx_power: Transmission power in dBm (5-23)
        """
        try:
            if reset_pin is not None:
                # reset module
                reset_pin.value(0)
                time.sleep_ms(100)
                reset_pin.value(1)
                time.sleep_ms(100)
            
            print("RFM9x Initialization started...")
            
            self._modem = RFM9x(
                id=device_id,
                cs=cs_pin,
                spi=spi,
                reset=reset_pin,
                modem_config=modem_config,
                band=band,
                channel=channel,
                freq=freq,
                tx_power=tx_power,
                timeout_ms=timeout_ms  # Pass timeout to RFM9x driver
            )
            
            # Device identifier
            self.device_id = device_id
            
            # Asyncio lock for thread safety in async operations
            self._lock = asyncio.Lock()
            
            # Callback management
            self._packet_preprocessor = packet_processor
            self._recv_callback = recv_callback
            
            # Async receiver state
            self._receiver_running = False
            self._stop_receiver = False
            self._receiver_task = None
            self._is_receiving = False
            self._last_payload = None
            
            # Multi-part message handling
            self._multipart_messages = {}
            
            print("LoRa initialization complete")
            
        except Exception as e:
            import sys
            print(f"LoRa initialization failed: {e}")
            sys.print_exception(e)
            raise
    
    async def send_async(self, data, target_id: int = BROADCAST_ADDRESS) -> bool:
        """
        Asynchronously send data to a target device.
        
        Args:
            data: The data to send (can be bytes, string, int, or list of bytes)
            target_id: The target device ID (default: broadcast to all devices)
            
        Returns:
            bool: True if the transmission was successful
        """
        # CRITICAL FIX: Run GC before transmission
        gc.collect()
        try:
            async with self._lock:
                # Make sure we're in idle mode before sending
                self._modem.set_mode_idle()
                
                # Clear any previous flags
                self._modem.clear_irq_flags()
                
                # Convert data to bytes if it's not already
                if isinstance(data, str):
                    payload = bytes(data, 'utf-8')
                elif isinstance(data, int):
                    payload = bytes([data])
                elif isinstance(data, list):
                    payload = bytes(data)
                elif isinstance(data, bytes):
                    payload = data
                else:
                    payload = bytes(str(data), 'utf-8')
                    
                # Check if the payload is larger than 255 bytes and needs splitting
                if len(payload) > 255:
                    print(f"Large payload detected ({len(payload)} bytes), splitting into batches")
                    
                    # Calculate midpoint
                    mid_point = len(payload) // 2
                    
                    # Create two batches
                    batch1 = payload[:mid_point]
                    batch2 = payload[mid_point:]
                    
                    # Use base64 encoding to safely embed binary data in JSON
                    import binascii
                    import json
                    
                    # Encode batches as base64 to avoid JSON syntax issues
                    part1_obj = {
                        "_part": 1, 
                        "_total": 2,
                        "data": binascii.b2a_base64(batch1).decode('ascii').strip()
                    }
                    part2_obj = {
                        "_part": 2, 
                        "_total": 2,
                        "data": binascii.b2a_base64(batch2).decode('ascii').strip()
                    }
                    
                    batch1 = json.dumps(part1_obj).encode('utf-8')
                    batch2 = json.dumps(part2_obj).encode('utf-8')
                    
                    # Send first batch
                    checksum1 = calculate_checksum(batch1)
                    packet1 = bytes([self.device_id, target_id, checksum1]) + batch1
                    
                    if not self._modem.send(packet1):
                        print("CMD:Failed to queue first batch packet")
                        return False
                        
                    # Wait for first batch TX to complete
                    success1 = await self._wait_for_tx_complete(2000)
                    if not success1:
                        print("First batch transmission failed")
                        return False
                    
                    # Small delay between batches
                    await asyncio.sleep_ms(100)
                    
                    # Send second batch
                    checksum2 = calculate_checksum(batch2)
                    packet2 = bytes([self.device_id, target_id, checksum2]) + batch2
                    
                    if not self._modem.send(packet2):
                        print("CMD:Failed to queue second batch packet")
                        return False
                        
                    # Wait for second batch TX to complete
                    success2 = await self._wait_for_tx_complete(2000)
                    if not success2:
                        print("Second batch transmission failed")
                        return False
                        
                    return True
                
                # Single packet transmission
                # Calculate checksum
                checksum = calculate_checksum(payload)
                
                # Create packet: sender_id + target_id + checksum + payload
                packet = bytes([self.device_id, target_id, checksum]) + payload
                
                # Send the packet
                if not self._modem.send(packet):
                    print("CMD:Failed to queue packet")
                    return False
                    
                # Wait for TX to complete using the helper method
                return await self._wait_for_tx_complete(2000)
                
        except Exception as e:
            print(f"Exception during transmission: {e}")
            # Make sure we return to idle mode if there's an exception
            self._modem.set_mode_idle()
            return False
    
    async def recv_async(self, timeout_ms: int = 800) -> bytes:
        """Asynchronously receive data from any sender.
        
        Args:
            timeout_ms: Maximum time to wait for reception in milliseconds
            
        Returns:
            bytes: The received data or None if no data was received within the timeout
            None: If no data received within timeout period
        """
        try:
            async with self._lock:
                # Clear any previous flags
                self._modem.clear_irq_flags()
                
                # Put radio in receive mode
                self._modem.set_mode_rx()
                                
                start_time = time.ticks_ms()
                while True:
                    # Check for RX_DONE flag directly
                    if self._modem._is_flag_set(RX_DONE):
                        raw_data = self._modem.recv_data()
                        
                        if raw_data:
                            # Put radio back to idle mode
                            self._modem.set_mode_idle()
                            return raw_data
                    
                    # Check for timeout
                    if time.ticks_diff(time.ticks_ms(), start_time) > timeout_ms:
                        # Put radio back to idle mode
                        self._modem.set_mode_idle()
                        return None
                        
                    # Small delay to avoid tight looping
                    await asyncio.sleep_ms(5)
        except Exception as e:
            print(f"Exception during reception: {e}")
            # Make sure to restore idle mode on exception
            self._modem.set_mode_idle()
            return None
        
    def set_tx_power(self, tx_power: int) -> None:
        """
        Set the transmission power of the LoRa radio.
        
        Args:
            tx_power: Transmission power in dBm (5-23)
        """
        if 5 <= tx_power <= 23:
            self._modem.set_tx_power(tx_power)
        else:
            raise ValueError("tx_power must be between 5 and 23 dBm")
    
    def configure(self, 
                       modem_config: tuple = None,
                       band: str = None,
                       channel: int = None,
                       freq: float = None,
                       tx_power: int = None) -> None:
        """
        Reconfigure the LoRa radio parameters.
        
        Args:
            modem_config: New modem configuration
            band: New frequency band
            channel: New channel within the band
            freq: New frequency in MHz
            tx_power: New transmission power in dBm
        """
        # reset modem
        self._modem.reset()
        # delete object
        del self._modem
        # reconstruct object
        self._modem = RFM9x(
            id=self.device_id,
            cs=self._modem._cs,
            spi=self._modem._spi,
            reset=self._modem._reset,
            modem_config=modem_config,
            band=band,
            channel=channel,
            freq=freq,
            tx_power=tx_power
        )
    
    async def start_receiver(self) -> None:
        """Start the asynchronous receiver task."""
        if not self._receiver_running:
            self._stop_receiver = False
            self._receiver_task = asyncio.create_task(self._receiver_loop())
    
    async def stop_receiver(self) -> None:
        """Stop the asynchronous receiver task."""
        if self._receiver_running and self._receiver_task is not None:
            self._stop_receiver = True
            # Wait until receiver is actually stopped
            while self._receiver_running:
                await asyncio.sleep_ms(10)
    
    def is_receiving(self) -> bool:
        """
        Check if currently receiving data.
        
        Returns:
            bool: True if currently receiving data
        """
        return self._is_receiving
    
    def get_last_payload(self) -> namedtuple:
        """
        Get the last received payload (non-blocking).
        
        Returns:
            namedtuple: The last received payload or None if no data has been received
        """
        return self._last_payload

    async def _receiver_loop(self) -> None:
        """Main receiver coroutine that processes incoming messages."""
        self._receiver_running = True
        
        while not self._stop_receiver:
            try:
                # Put radio in receive mode
                self._modem.set_mode_rx()
                
                # Set receiving flag
                self._is_receiving = True
                
                # Check for RX_DONE flag directly with a short timeout
                start_time = time.ticks_ms()
                while not self._stop_receiver:
                    if self._modem._is_flag_set(RX_DONE):
                        raw_data = self._modem.recv_data()
                        
                        if raw_data:                            # Process the raw data using the recv_callback
                            payload = self._packet_preprocessor(raw_data)
                            
                            # Process and handle multi-part messages
                            processed_payload = await self._process_message(payload)
                            
                            # Only proceed if we have a complete message (None means incomplete multi-part)
                            if processed_payload is not None:
                                # Store the last received payload
                                self._last_payload = processed_payload

                                # If a callback is set, call it with the processed packet
                                if self._recv_callback:
                                    try:
                                        await self._recv_callback(processed_payload)
                                    except Exception as e:
                                        print(f"Error in recv_callback: {e}")
                            
                        # Reset receiving flag
                        self._is_receiving = False
                        
                        # Return to idle mode after reception
                        self._modem.set_mode_idle()
                        
                        # Short break before next receive
                        await asyncio.sleep_ms(10)
                        break
                    
                    # Check for timeout after 1 second
                    if time.ticks_diff(time.ticks_ms(), start_time) > 1000:
                        # Reset receiving flag
                        self._is_receiving = False
                        
                        # Return to idle mode after timeout
                        self._modem.set_mode_idle()
                        
                        # Short break before next attempt
                        await asyncio.sleep_ms(5)
                        break
                    
                    # Small delay to avoid tight looping
                    await asyncio.sleep_ms(5)
                    
            except Exception as e:
                print(f"Error in receiver loop: {e}")
                self._is_receiving = False
                self._modem.set_mode_idle()
                await asyncio.sleep_ms(100)
        
        self._receiver_running = False

    async def _wait_for_tx_complete(self, timeout_ms: int = 2000) -> bool:
        """
        Helper method to wait for transmission to complete.
        
        Args:
            timeout_ms: Maximum time to wait for transmission completion in milliseconds
            
        Returns:
            bool: True if transmission completed successfully, False if timed out
        """
        start_time = time.ticks_ms()
        while True:
            irq_flags = self._modem._spi_read(REG_12_IRQ_FLAGS)
            if irq_flags & TX_DONE:
                self._modem.clear_irq_flags()
                # Return to idle mode after transmission
                self._modem.set_mode_idle()
                return True
                
            if time.ticks_diff(time.ticks_ms(), start_time) > timeout_ms:
                print(f"Transmission timed out after {timeout_ms} ms")
                # Return to idle mode after timeout
                self._modem.set_mode_idle()
                return False
                
            await asyncio.sleep_ms(10)

    async def _process_message(self, payload):
        """
        Process a received message, handling multi-part messages if needed.
        
        Args:
            payload: The received payload object
            
        Returns:
            The processed payload (might be reconstructed from multi-part messages)
        """
        try:
            # Try to parse JSON message
            import json
            data = json.loads(payload.message.decode('utf-8'))
            
            # Check if this is a multi-part message
            if "_part" in data:
                part_num = data.get("_part")
                part_data = data.get("data")
                total_parts = data.get("_total", 2)  # Default to 2 parts
                sender_id = payload.sender_id
                
                # Create entry for this sender if not exists
                if sender_id not in self._multipart_messages:
                    self._multipart_messages[sender_id] = {}
                
                # Decode base64 data and store this part
                import binascii
                decoded_part = binascii.a2b_base64(part_data.encode('ascii'))
                self._multipart_messages[sender_id][part_num] = decoded_part
                
                # Check if we have all parts
                if len(self._multipart_messages[sender_id]) == total_parts:
                    # Reconstruct the complete message by combining parts in order
                    combined_data = b''
                    for i in range(1, total_parts + 1):
                        if i in self._multipart_messages[sender_id]:
                            combined_data += self._multipart_messages[sender_id][i]
                    
                    # Create a new payload with the combined data
                    from collections import namedtuple
                    combined_payload = namedtuple(
                        "Packet",
                        ['sender_id', 'target_id', 'checksum', 'message', 'rssi', 'snr', 'valid_checksum']
                    )
                    
                    # Clear the stored parts
                    del self._multipart_messages[sender_id]
                    
                    # Create a new payload with the combined message
                    return combined_payload(
                        payload.sender_id,
                        payload.target_id,
                        payload.checksum,  # Original checksum (not valid for combined message)
                        combined_data,     # Combined binary data
                        payload.rssi,
                        payload.snr,
                        False  # Checksum is not valid for the combined message
                    )
                
                # We don't have all parts yet, return None to indicate no complete message yet
                return None
            
            # Not a multi-part message, but it is valid JSON
            # Convert the parsed JSON back to a consistent format
            import json
            json_str = json.dumps(data)
            
            # Create a new payload with the JSON string as bytes
            from collections import namedtuple
            processed_payload = namedtuple(
                "Packet",
                ['sender_id', 'target_id', 'checksum', 'message', 'rssi', 'snr', 'valid_checksum']
            )
            
            return processed_payload(
                payload.sender_id,
                payload.target_id,
                payload.checksum,
                json_str.encode('utf-8'),  # Convert JSON back to bytes
                payload.rssi,
                payload.snr,
                payload.valid_checksum
            )
            
        except Exception as e:
            print(f"Error processing message: {e}")
            # Not JSON or other error, return original payload
            return payload


