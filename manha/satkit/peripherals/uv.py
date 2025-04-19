from manha.internals.drivers import UVS12SD
from .base import ManhaSensor

from micropython import const

class UVSensor(ManhaSensor):
    
    _DEFAULT_ADC_PIN = const(28)
    
    def __init__(self, adc_pin: int = _DEFAULT_ADC_PIN) -> None:
        """Initialize the UV sensor with ADC and I2C interface.

        Args:
            adc_pin (int): Pin number for ADC.
        """
        self._uv_sensor = UVS12SD(pin=adc_pin)
        
    def read(self) -> dict:
        """Read data from the UV sensor.

        Returns:
            dict: Dictionary containing UV value.
        """
        try:
            return {'uv_value': self._uv_sensor.uvValue}
        except Exception as e:
            print("Error reading UV sensor data:", e)
            return {'uv_value': -1}
        
    def configure(self, **kwargs) -> None:
        """Configure the UV sensor with provided parameters.

        Args:
            **kwargs: Configuration parameters specific to UV sensor.
        """
        pass