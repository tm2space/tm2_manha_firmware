import lora
from lora_constants import TX_DONE, REG_12_IRQ_FLAGS

class LoRAComms:
    def __init__(self, this_addr):
        self.lora_handle = lora.LoRa(this_addr)

    def send(self, data, address) -> bool:
        self.lora_handle.send(data, address)
        status = self.lora_handle._wait_flag_set(TX_DONE)
        self.lora_handle._spi_write(REG_12_IRQ_FLAGS, 0xff)
        return status