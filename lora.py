import ulora

SERVER_ADDR = 2
LORA_SPI_CHAN
LORA_SCK  = const(10)
LORA_MOSI = const(11)
LORA_MISO = const(8)
LORA_CS   = const(9)
LORA_IRQ  = None
LORA_RST  = None
LORA_ADDR = 1


lora = ulora.LoRa((LORA_SPI_CHANNEL,LORA_SCK,LORA_MOSI,LORA_MISO), LORA_IRQ, LORA_,ADDR LORA_CS)        
        
while True:
    lora.send_to_wait('test succesfful', SERVER_ADDR)
    time.sleep(1000)

import machine
import time

# lora = machine.SPI(1, baudrate=400_000, sck=machine.Pin(10), miso=machine.Pin(8), mosi=machine.Pin(11))
# cs = machine.Pin(9, mode=machine.Pin.OUT, value=1)



try:
    cs(0)
    print(lora.read(2, 0x02))
except:
    print('Not successfuk')        
finally:
    cs(1)
