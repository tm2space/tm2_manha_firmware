"""
Constants for MANHA ground station module
"""

from micropython import const

LORA_SPI_CHANNEL = const(1)
LORA_SCK = const(10)
LORA_MOSI = const(11)
LORA_MISO = const(12)
LORA_CS = const(13)
LORA_RESET = const(7)
TRANSMIT_INTERVAL = const(1.0)
GS_SSID = "MANHA_GS"
GS_PASS = "ground1234"

# Callback type constants
CALLBACK_TELEMETRY = const(0)
CALLBACK_COMMAND_RESPONSE = const(1)