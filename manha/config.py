from micropython import const

LORA_ADDR = const(11)
LOW_POWER_THRESHOLD = const(35)  # Battery % below which Low-Power Mode activates
TELEMETRY_INTERVAL_MS = const(1000)  # ms between TLM packets
LOW_POWER_TELEMETRY_INTERVAL_MS = const(5000)  # ms between TLM in Low-Power Mode
MIN_CMD_LISTEN_MS = const(500)  # minimum RX window for incoming commands

# Set True for legacy JSON packetization (deprecated).
USE_LEGACY_PACKETIZATION = False
ENABLE_HDRM = False
ENABLE_CAM = False
SATKIT_LOG_TELEMETRY_TO_CONSOLE = False
SATKIT_LOG_TELEMETRY_TO_FILE = False  # False or filename string (e.g., "tlm.log")

COMMANDS = {
    "help": "Display available commands",
    "ping": "Send a ping to the satellite",
    "reboot": "Command the satellite to reboot",
    "status": "Request status from the satellite",
    "sensors": "Request sensor data from the satellite",
    "tx-power": "Set the LoRa TX power (5-23 dBm)",
    "heartbeat": "Toggle automatic heartbeat messages",
    "quit": "Exit the command processor",
}
