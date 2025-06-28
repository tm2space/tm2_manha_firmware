from micropython import const

LORA_ADDR = const(11)

COMMANDS = {
    "help": "Display available commands",
    "ping": "Send a ping to the satellite",
    "reboot": "Command the satellite to reboot",
    "status": "Request status from the satellite",
    "sensors": "Request sensor data from the satellite",
    "tx-power": "Set the LoRa TX power (5-23 dBm)",
    "heartbeat": "Toggle automatic heartbeat messages",
    "quit": "Exit the command processor"
}