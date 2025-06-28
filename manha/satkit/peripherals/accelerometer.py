from manha.internals.drivers import ADXL345
from .base import ManhaSensor

from micropython import const
from machine import I2C

class Accelerometer(ManhaSensor):
    
    _DEFAULT_ADDRESS = const(0x53)
    
    def __init__(self, i2c: I2C, address: int = _DEFAULT_ADDRESS) -> None:
        """Initialize the Accelerometer with I2C interface and address.

        Args:
            i2c (object): I2C interface object.
            address (int): I2C address of the Accelerometer.
        """
        self._acc = ADXL345(i2c=i2c, addr=address)
        
        
    def read(self) -> dict:
        """Read data from the Accelerometer.

        Returns:
            dict: Dictionary containing x,y,z axis data.
        """
        try:
            return {
                'x': round(self._acc.xValue,2),
                'y': round(self._acc.yValue,2),
                'z': round(self._acc.zValue,2)
            }
        except Exception as e:
            print("Error reading accelerometer data:", e)
            return {'x': 0, 'y': 0, 'z': 0}
        
    def configure(self, **kwargs) -> None:
        """Configure the Accelerometer with provided parameters.

        Args:
            **kwargs: Configuration parameters for the Accelerometer.
        """
        pass