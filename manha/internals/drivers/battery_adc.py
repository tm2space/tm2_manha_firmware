from machine import Pin, ADC
import time

MAX_BATTERY_VOLTAGE = (3.3 / 3.3) * 65535
MIN_BATTERY_VOLTAGE = (1.6 / 3.3) * 65535

class BatteryVoltage:
    def __init__(self, adc_pin=26):
        self.adc_handle = ADC(Pin(adc_pin))
        
    @property
    def rawValue(self) -> int:
        time.sleep(0.1)  # Allow time for ADC to stabilize
        _read_val = self.adc_handle.read_u16()
        return _read_val
    
    @property
    def percValue(self) -> float:
        _raw_read_val = self.rawValue
        
        # x2 due to voltage divider
        _read_val_conv = ((_raw_read_val - MIN_BATTERY_VOLTAGE) * 100 * 2) / MAX_BATTERY_VOLTAGE
        
        return _read_val_conv