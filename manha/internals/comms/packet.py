"""
Packet class for MANHA LoRa communication protocol
"""

import struct
from manha.utils import calculate_checksum
from manha.config import USE_LEGACY_PACKETIZATION

if USE_LEGACY_PACKETIZATION:
    print(
        "DEPRECATION: USE_LEGACY_PACKETIZATION is set. JSON packetization will be removed in a future version."
    )

# Message type constants (binary protocol only)
MSG_TM = 0x01  # Telemetry (satellite -> GS)
MSG_TC = 0x02  # Telecommand (GS -> satellite)
MSG_TC_ACK = 0x03  # Telecommand acknowledgment (satellite -> GS)


class Packet:
    """
    LoRa packet structure for MANHA communication protocol

    Binary header (default):  [addr_from][addr_to][msg_type][checksum][payload...]
    Legacy header:            [addr_from][addr_to][checksum][payload...]
    """

    def __init__(
        self,
        addr_to: int,
        addr_from: int,
        message: bytes,
        msg_type: int = None,
        checksum: int = None,
        rssi: int = None,
        snr: float = None,
    ):
        """
        Initialize a new packet

        Args:
            addr_to: Destination address (0-255)
            addr_from: Source address (0-255)
            message: Message payload as bytes
            msg_type: Message type (MSG_TM, MSG_TC, MSG_TC_ACK). Ignored in legacy mode.
            checksum: Message checksum (calculated if not provided)
            rssi: Received Signal Strength Indicator (set during reception)
            snr: Signal to Noise Ratio (set during reception)
        """
        self.addr_to = addr_to
        self.addr_from = addr_from
        self.message = message
        self.msg_type = msg_type
        self.rssi = rssi
        self.snr = snr

        if checksum is not None:
            self.checksum = checksum
        elif USE_LEGACY_PACKETIZATION:
            self.checksum = self.calculate_checksum(message)
        else:
            # Binary mode: checksum covers msg_type + message
            self.checksum = self.calculate_checksum(bytes([msg_type or 0]) + message)

    def encode(self) -> bytes:
        """
        Encode packet to bytes for transmission

        Returns:
            bytes: Encoded packet ready for transmission
        """
        if USE_LEGACY_PACKETIZATION:
            return bytes([self.addr_from, self.addr_to, self.checksum]) + self.message
        else:
            return (
                bytes([self.addr_from, self.addr_to, self.msg_type or 0, self.checksum])
                + self.message
            )

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
        if USE_LEGACY_PACKETIZATION:
            if len(data) < 3:
                return None
            addr_from = data[0]
            addr_to = data[1]
            checksum = data[2]
            message = data[3:] if len(data) > 3 else b""
            return cls(
                addr_to,
                addr_from,
                message,
                msg_type=None,
                checksum=checksum,
                rssi=rssi,
                snr=snr,
            )
        else:
            if len(data) < 4:
                return None
            addr_from = data[0]
            addr_to = data[1]
            msg_type = data[2]
            checksum = data[3]
            message = data[4:] if len(data) > 4 else b""
            return cls(
                addr_to,
                addr_from,
                message,
                msg_type=msg_type,
                checksum=checksum,
                rssi=rssi,
                snr=snr,
            )

    @staticmethod
    def calculate_checksum(message: bytes) -> int:
        """Calculate checksum for message bytes"""
        return calculate_checksum(message)

    def is_valid_checksum(self) -> bool:
        """Verify if packet checksum is valid"""
        if USE_LEGACY_PACKETIZATION:
            return self.checksum == self.calculate_checksum(self.message)
        else:
            return self.checksum == self.calculate_checksum(
                bytes([self.msg_type or 0]) + self.message
            )

    def __str__(self) -> str:
        """String representation of packet"""
        if USE_LEGACY_PACKETIZATION:
            return f"Packet(to={self.addr_to}, from={self.addr_from}, msg_len={len(self.message)}, rssi={self.rssi}, snr={self.snr})"
        return f"Packet(to={self.addr_to}, from={self.addr_from}, type={self.msg_type}, msg_len={len(self.message)}, rssi={self.rssi}, snr={self.snr})"

    def __repr__(self) -> str:
        """Detailed representation of packet"""
        return f"Packet(addr_to={self.addr_to}, addr_from={self.addr_from}, msg_type={self.msg_type}, checksum={self.checksum}, message={self.message!r}, rssi={self.rssi}, snr={self.snr})"
