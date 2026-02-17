from machine import Pin, ADC
import time

MAX_BATTERY_VOLTAGE = 4.2
MIN_BATTERY_VOLTAGE = 3.4

class BatteryVoltage:
    ADC_VREF = 3.3
    ADC_MAX  = 65535
    DIVIDER_GAIN = 1.27

    def __init__(self, adc_pin=26):
        self.adc_handle = ADC(Pin(adc_pin))
        
    @property
    def rawValue(self) -> int:
        time.sleep(0.05)  # Allow time for ADC to stabilize
        _read_val = self.adc_handle.read_u16()
        return _read_val
    
    @property
    def voltage(self) -> float:
        _raw_read_val = self.rawValue

        _read_val_conv = (_raw_read_val * self.ADC_VREF / self.ADC_MAX) * self.DIVIDER_GAIN

        return _read_val_conv

    
    @property
    def percValue(self) -> float:
        _voltage = self.voltage

        # clamp voltage to bounds
        if _voltage > MAX_BATTERY_VOLTAGE:
            _voltage = MAX_BATTERY_VOLTAGE
        elif _voltage < MIN_BATTERY_VOLTAGE:
            _voltage = MIN_BATTERY_VOLTAGE
        
        # convert to percentage
        _read_val_conv = (_voltage - MIN_BATTERY_VOLTAGE) / (MAX_BATTERY_VOLTAGE - MIN_BATTERY_VOLTAGE) * 100
        
        return _read_val_conv