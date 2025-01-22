import lora

class LoRAComms:
    def __init__(self, this_addr):
        self.lora_handle = lora.LoRa(this_addr)

    def send(self, data, address):
        self.lora_handle.send(data, address)
        return self.lora_handle.wait_packet_sent()