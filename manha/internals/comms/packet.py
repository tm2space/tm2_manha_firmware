"""
Packet class for MANHA LoRa communication protocol
"""

import struct
from manha.utils import calculate_checksum


class Packet:
    """
    LoRa packet structure for MANHA communication protocol
    
    Fields:
        addr_to (int): Destination address (0-255)
        addr_from (int): Source address (0-255) 
        checksum (int): Message checksum (0-255)
        message (bytes): Message payload
        rssi (int): Received Signal Strength Indicator (set during reception)
        snr (float): Signal to Noise Ratio (set during reception)
    """
    
    def __init__(self, addr_to: int, addr_from: int, message: bytes, checksum: int = None, rssi: int = None, snr: float = None):
        """
        Initialize a new packet
        
        Args:
            addr_to: Destination address (0-255)
            addr_from: Source address (0-255) 
            message: Message payload as bytes
            checksum: Message checksum (calculated if not provided)
            rssi: Received Signal Strength Indicator (set during reception)
            snr: Signal to Noise Ratio (set during reception)
        """
        self.addr_to = addr_to
        self.addr_from = addr_from
        self.message = message
        self.checksum = checksum if checksum is not None else self.calculate_checksum(message)
        self.rssi = rssi
        self.snr = snr
    
    def encode(self) -> bytes:
        """
        Encode packet to bytes for transmission
        
        Format: [addr_from][addr_to][checksum][message]
        
        Returns:
            bytes: Encoded packet ready for transmission
        """
        return bytes([self.addr_from, self.addr_to, self.checksum]) + self.message
    
    @classmethod
    def decode(cls, data: bytes, rssi: int = None, snr: float = None):
        """
        Decode received bytes into a Packet object
        
        Args:
            data: Raw received bytes
            rssi: Received Signal Strength Indicator
            snr: Signal to Noise Ratio
            
        Returns:
            Packet: Decoded packet object or None if invalid
        """
        if len(data) < 3:
            return None
            
        addr_from = data[0]
        addr_to = data[1] 
        checksum = data[2]
        message = data[3:] if len(data) > 3 else b''
        
        return cls(addr_to, addr_from, message, checksum, rssi, snr)
    
    @staticmethod
    def calculate_checksum(message: bytes) -> int:
        """
        Calculate checksum for message bytes
        
        Args:
            message: Message bytes to calculate checksum for
            
        Returns:
            int: Calculated checksum (0-255)
        """
        return calculate_checksum(message)
    
    def is_valid_checksum(self) -> bool:
        """
        Verify if packet checksum is valid
        
        Returns:
            bool: True if checksum is valid
        """
        return self.checksum == self.calculate_checksum(self.message)
    
    def __str__(self) -> str:
        """String representation of packet"""
        return f"Packet(to={self.addr_to}, from={self.addr_from}, msg_len={len(self.message)}, rssi={self.rssi}, snr={self.snr})"
    
    def __repr__(self) -> str:
        """Detailed representation of packet"""
        return f"Packet(addr_to={self.addr_to}, addr_from={self.addr_from}, checksum={self.checksum}, message={self.message!r}, rssi={self.rssi}, snr={self.snr})"