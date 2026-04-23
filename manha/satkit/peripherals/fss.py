from manha.internals.drivers import TSL2561
from .base import ManhaSensor

from micropython import const
from machine import I2C


class FineSunSensor(ManhaSensor):

    _DEFAULT_ADDRESS = const(0x39)

    def __init__(self, i2c: I2C, address: int = _DEFAULT_ADDRESS) -> None:
        """Initialize the TSL2561-backed Fine Sun Sensor.

        Args:
            i2c (I2C): Shared I2C bus.
            address (int): I2C address of the TSL2561.
        """
        self._tsl = TSL2561(i2c=i2c, address=address)
        # Keep the sensor powered so first read() skips the integration-wait path.
        self._tsl.active(True)

    def read(self) -> dict:
        """Read lux and raw channels from the TSL2561.

        Returns:
            dict: {"fss_lux": <float>, "fss_bb": <int>, "fss_ir": <int>}.
                  Any field -1 on saturation / I2C error.
        """
        try:
            # Single raw read + autogain; reuse channels for lux to avoid a
            # second I2C transaction.
            bb, ir = self._tsl.read(autogain=True, raw=True)
            try:
                lux = round(float(self._tsl._lux((bb, ir))), 2)
            except ValueError:
                # Saturated — keep raw channels, flag lux.
                lux = -1
            return {"fss_lux": lux, "fss_bb": int(bb), "fss_ir": int(ir)}
        except Exception as e:
            print("Error reading FSS (TSL2561):", e)
            return {"fss_lux": -1, "fss_bb": -1, "fss_ir": -1}

    def configure(self, **kwargs) -> None:
        """Configure gain and integration time.

        Args:
            **kwargs: 'gain' (1 or 16), 'integration_time' (0, 13, 101, 402).
        """
        if 'gain' in kwargs.keys():
            self._tsl.gain(kwargs['gain'])
        if 'integration_time' in kwargs.keys():
            self._tsl.integration_time(kwargs['integration_time'])
