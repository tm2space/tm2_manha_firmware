from manha.internals.drivers import BME680_I2C
from .base import ManhaSensor

from micropython import const
from machine import I2C

class GasSensor(ManhaSensor):
    
    _DEFAULT_ADDRESS = const(0x77)
    _DEFAULT_REFRESH_RATE = const(1)
    
    def __init__(self, i2c: I2C, address: int = _DEFAULT_ADDRESS, refresh_rate: int = _DEFAULT_REFRESH_RATE) -> None:
        """Initialize the BME680 sensor with I2C interface and address.

        Args:
            i2c (object): I2C interface object.
            address (int): I2C address of the BME680 sensor.
            refresh_rate (int): Refresh rate for sensor data.
        """
        self._bme680 = BME680_I2C(i2c=i2c, address=address, refresh_rate=refresh_rate)
        
        
    def read(self) -> dict:
        """Read data from the BME680 sensor.

        Returns:
            dict: Dictionary containing temperature, pressure, humidity, and gas resistance.
        """
        try:
            return {
                'tmp': round(self._bme680.temperature,2),
                'prs': round(self._bme680.pressure,2),
                'hum': round(self._bme680.humidity,2),
                'gas': round(self._bme680.gas,2)
            }
        except Exception as e:
            print("Error reading BME680 data:", e)
            return {
                'tmp': -1,
                'prs': -1,
                'hum': -1,
                'gas': -1
            }
        
    def configure(self, **kwargs) -> None:
        """Configure the BME680 sensor with provided parameters.

        Args:
            **kwargs: Configuration parameters specific to BME680.
        """
        if 'pressure_oversample' in kwargs.keys():
            self._bme680.pressure_oversample = kwargs['pressure_oversample']
        if 'humidity_oversample' in kwargs.keys():
            self._bme680.humidity_oversample = kwargs['humidity_oversample']
        if 'temperature_oversample' in kwargs.keys():
            self._bme680.temperature_oversample = kwargs['temperature_oversample']
        if 'filter_size' in kwargs.keys():
            self._bme680.filter_size = kwargs['filter_size']
            