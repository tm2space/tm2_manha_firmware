"""Simple LoRa RX test. Prints received packets."""

import time
from machine import Pin, SPI

from manha.internals.drivers import RFM9x
from manha.internals.drivers.rfm9x_constants import RX_DONE
from manha.gs.constants import (
    LORA_SPI_CHANNEL,
    LORA_SCK,
    LORA_MOSI,
    LORA_MISO,
    LORA_CS,
    LORA_RESET,
)

DEVICE_ID = 0x22
FREQ = 868.0

spi = SPI(
    LORA_SPI_CHANNEL,
    baudrate=5_000_000,
    polarity=0,
    phase=0,
    sck=Pin(LORA_SCK),
    mosi=Pin(LORA_MOSI),
    miso=Pin(LORA_MISO),
)

lora = RFM9x(
    id=DEVICE_ID,
    cs=Pin(LORA_CS, Pin.OUT),
    spi=spi,
    reset=Pin(LORA_RESET, Pin.OUT),
    freq=FREQ,
    tx_power=14,
)

print(f"LoRa RX listening @ {FREQ} MHz, id={DEVICE_ID}")
lora.set_mode_rx()

while True:
    if lora._is_flag_set(RX_DONE):
        result = lora.recv_data()
        if result:
            data, rssi, snr = result
            print(f"RX [rssi={rssi} snr={snr}] len={len(data)}: {data}")
        lora.set_mode_rx()
    time.sleep_ms(10)
