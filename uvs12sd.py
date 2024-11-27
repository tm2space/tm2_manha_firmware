from machine import Pin, ADC
import time

#ADC.width(ADC.WIDTH_10BIT)

class UVS12SD:
    def __init__(self, pin):
        self._pin = ADC(Pin(pin))
        #self._pin.atten(ADC.ATTN_11DB)
        
    def uvValue(self):
        time.sleep(0.1)
        return self._pin.read_u16()
