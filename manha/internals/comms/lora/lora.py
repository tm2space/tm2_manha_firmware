"""
▀▀█▀▀ █▀▄▀█ ▀▀▀▀█ ▄▀▀▀▀ █▀▀▀▄ ▄▀▀▀▄ ▄▀▀▀▀ █▀▀▀▀ 
  █   █   █ █▀▀▀▀  ▀▀▀▄ █▀▀▀  █▀▀▀█ █     █▀▀   
  ▀   ▀   ▀ ▀▀▀▀▀ ▀▀▀▀  ▀     ▀   ▀  ▀▀▀▀ ▀▀▀▀▀ 
"""

import time
import asyncio
from collections import namedtuple
from machine import Pin, SPI

from manha.internals.drivers import RFM9x, ModemConfig
from manha.internals.drivers.rfm9x_constants import *

def calculate_checksum(data: bytes) -> int:
    """
    Calculate a simple checksum for the given data.
    
    Args:
        data: The bytes data to calculate checksum for
        
    Returns:
        int: The calculated checksum (0-255)
    """
    # Simple sum of bytes modulo 256
    checksum = 0
    for byte in data:
        checksum = (checksum + byte) % 256
    return checksum

def default_recv_callback(raw_payload: tuple) -> namedtuple:
    """
    The default callback for processing a received raw packet into a structured payload.
    
    Args:
        raw_payload: The raw packet data from the LoRa driver, a tuple of (data, rssi, snr)
        
    Returns:
        namedtuple: A structured payload with sender_id, target_id, message, rssi, snr, and valid_checksum
    """
    raw_bytes, rssi, snr = raw_payload
    
    # Extract sender_id and receiver_id from the first 2 bytes
    sender_id = raw_bytes[0] if len(raw_bytes) > 0 else 0
    receiver_id = raw_bytes[1] if len(raw_bytes) > 1 else 0
    
    # Extract checksum and message from the remaining bytes
    if len(raw_bytes) > 2:
        received_checksum = raw_bytes[2]
        message = raw_bytes[3:]
    else:
        received_checksum = 0
        message = b''
    
    # Calculate checksum from received message
    calculated_checksum = calculate_checksum(message)
    valid_checksum = (calculated_checksum == received_checksum)
    
    # Create a structured payload from the raw data
    payload = namedtuple(
        "Payload",
        ['sender_id', 'target_id', 'message', 'rssi', 'snr', 'valid_checksum']
    )(sender_id, receiver_id, message, rssi, snr, valid_checksum)
    
    # save to file 
    with open("lora_payload.txt", "a") as f:
        f.write(f"{time.time()}: {payload}\n")
    
    return payload

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
                 recv_callback=default_recv_callback,
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
            recv_callback: Function to process received packets (default provided)
            modem_config: LoRa modem configuration (see ModemConfig class)
            band: Frequency band identifier (e.g., '800', '900')
            channel: Channel within the band
            freq: Frequency in MHz if band/channel not specified
            tx_power: Transmission power in dBm (5-23)
        """
        try:
            # Put the module in reset state
            reset_pin.value(0)
            time.sleep_ms(100)  # Extended reset time
            reset_pin.value(1)
            time.sleep_ms(100)  # Extended stabilization time
            
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
            self._recv_callback = recv_callback
            
            # Async receiver state
            self._receiver_running = False
            self._stop_receiver = False
            self._receiver_task = None
            self._is_receiving = False
            self._last_payload = None
            
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
        try:
            async with self._lock:
                print(f"Sending data to {target_id}: {data}")
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
                
                # Calculate checksum
                checksum = calculate_checksum(payload)
                
                # Create packet: sender_id + target_id + checksum + payload
                packet = bytes([self.device_id, target_id, checksum]) + payload
                
                # Send the packet
                if not self._modem.send(packet):
                    print("Failed to queue packet for sending")
                    return False
                    
                # Wait for TX to complete asynchronously with longer timeout (2000ms)
                start_time = time.ticks_ms()
                while True:
                    irq_flags = self._modem._spi_read(REG_12_IRQ_FLAGS)
                    if irq_flags & TX_DONE:
                        self._modem.clear_irq_flags()
                        print(f"Transmission to {target_id} completed successfully")
                        # Return to idle mode after transmission
                        self._modem.set_mode_idle()
                        return True
                        
                    if time.ticks_diff(time.ticks_ms(), start_time) > 2000:  # 2 second timeout
                        print(f"Transmission to {target_id} timed out after 2 seconds")
                        # Return to idle mode after timeout
                        self._modem.set_mode_idle()
                        return False
                        
                    await asyncio.sleep_ms(10)
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
                        
                        if raw_data:
                            # Process the raw data using the recv_callback
                            payload = self._recv_callback(raw_data)
                            
                            # Store the last received payload
                            self._last_payload = payload
                            
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
                        await asyncio.sleep_ms(10)
                        break
                    
                    # Small delay to avoid tight looping
                    await asyncio.sleep_ms(5)
                    
            except Exception as e:
                print(f"Error in receiver loop: {e}")
                self._is_receiving = False
                self._modem.set_mode_idle()
                await asyncio.sleep_ms(100)
        
        self._receiver_running = False