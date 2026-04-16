from machine import Pin, ADC

MAX_BATTERY_VOLTAGE = 4.2
MIN_BATTERY_VOLTAGE = 3.4
ADC_BUFFER_SIZE = 10

class BatteryVoltage:
    ADC_VREF = 3.3
    ADC_MAX  = 65535
    DIVIDER_GAIN = 1.27

    def __init__(self, adc_pin=26):
        self.adc_handle = ADC(Pin(adc_pin))
        self._buf = []
        self._n = 0

    @property
    def rawValue(self) -> int:
        self._buf.append(self.adc_handle.read_u16())
        if self._n < ADC_BUFFER_SIZE:
            self._n += 1
        else:
            self._buf.pop(0)
        return sum(self._buf) // self._n

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
