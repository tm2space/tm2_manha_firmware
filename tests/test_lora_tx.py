"""Simple LoRa TX test. Sends PING TC then listens for ACK."""

import time
from machine import Pin, SPI

from manha.internals.drivers import RFM9x
from manha.internals.drivers.rfm9x_constants import (
    TX_DONE,
    RX_DONE,
    REG_12_IRQ_FLAGS,
)
from manha.internals.comms.packet import Packet, MSG_TC
from manha.gs.constants import (
    LORA_SPI_CHANNEL,
    LORA_SCK,
    LORA_MOSI,
    LORA_MISO,
    LORA_CS,
    LORA_RESET,
)

GS_ADDR = 0x11
SAT_ADDR = 0x22
FREQ = 868.0
RX_TIMEOUT_MS = 5000

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
    id=GS_ADDR,
    cs=Pin(LORA_CS, Pin.OUT),
    spi=spi,
    reset=Pin(LORA_RESET, Pin.OUT),
    freq=FREQ,
    tx_power=14,
)

print(f"LoRa TX @ {FREQ} MHz, id={GS_ADDR} -> sat={SAT_ADDR}")

packet = Packet(SAT_ADDR, GS_ADDR, b"PING", msg_type=MSG_TC)
encoded = packet.encode()

lora.set_mode_idle()
ok = lora.send(encoded)

start = time.ticks_ms()
tx_done = False
while time.ticks_diff(time.ticks_ms(), start) < 2000:
    if lora._spi_read(REG_12_IRQ_FLAGS) & TX_DONE:
        lora.clear_irq_flags()
        tx_done = True
        break
    time.sleep_ms(5)

print(f"TX PING sent={ok} done={tx_done}: {encoded}")

print("Listening for response...")
lora.set_mode_rx()
start = time.ticks_ms()
while time.ticks_diff(time.ticks_ms(), start) < RX_TIMEOUT_MS:
    if lora._is_flag_set(RX_DONE):
        result = lora.recv_data()
        if result:
            data, rssi, snr = result
            print(f"RX [rssi={rssi} snr={snr}] len={len(data)}: {data}")
            pkt = Packet.decode(data, rssi, snr)
            if pkt:
                print(
                    f"  decoded: from={pkt.addr_from} to={pkt.addr_to} "
                    f"type={pkt.msg_type} msg={pkt.message} valid={pkt.is_valid_checksum()}"
                )
        lora.set_mode_rx()
    time.sleep_ms(10)

print("RX window closed.")
