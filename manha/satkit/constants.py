"""
Constants for MANHA satellite kit module
"""

from micropython import const

LORA_SPI_CHANNEL = const(1)
LORA_SPI_SCK = const(10)
LORA_SPI_MISO = const(8)
LORA_SPI_MOSI = const(11)
LORA_SPI_CS = const(9)

# Callback type constants
CALLBACK_TELEMETRY_REQUEST = const(0)
CALLBACK_COMMAND = const(1)