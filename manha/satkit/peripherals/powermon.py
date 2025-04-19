from manha.internals.drivers import INA219, BatteryVoltage
from .base import ManhaSensor

from micropython import const
from machine import I2C

class PowerMonitor(ManhaSensor):
    
    _DEFAULT_ADDRESS = const(0x41)
    _DEFAULT_SHUNT_OHMS = const(0.1)
    _DEFAULT_MAX_EXPECTED_AMPS = const(0.03)
    
    def __init__(self, i2c: I2C, address=_DEFAULT_ADDRESS, shunt_ohms: float = _DEFAULT_SHUNT_OHMS, max_expected_amps: float = _DEFAULT_MAX_EXPECTED_AMPS) -> None:
        """Initialize the PowerMonitor with INA219 and BatteryADC instances.

        Args:
            i2c (I2C): I2C interface object.
            address (int): I2C address of the INA219 sensor.
        """
        print(f"PowerMonitor: {address=}, {shunt_ohms=}, {max_expected_amps=}")
        
        self._ina219 = INA219(shunt_ohms=shunt_ohms, i2c=i2c, max_expected_amps=max_expected_amps, address=address)
        self._ina219.configure(INA219.RANGE_16V)
        
        self._battery_adc = BatteryVoltage()
        
    def read(self) -> dict:
        """Read the current and voltage values from the INA219 and BatteryADC.

        Returns:
            dict: Dictionary containing current and voltage values.
        """
        try:
            current = self._ina219.current()
            voltage = self._battery_adc.percValue
            return {'current': current, 'v_perc': voltage}
        except Exception as e:
            print("Error reading power monitor data:", e)
            return {'current': -1, 'v_perc': -1}
        
    def configure(self, **kwargs) -> None:
        self._ina219.configure(
            voltage_range=kwargs.get('voltage_range', INA219.RANGE_16V),
            gain=kwargs.get('gain', INA219.GAIN_AUTO),
            bus_adc=kwargs.get('bus_adc', INA219.ADC_12BIT), 
            shunt_adc=kwargs.get('shunt_adc', INA219.ADC_12BIT))