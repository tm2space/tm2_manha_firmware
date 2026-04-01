"""PWM Servo Driver for MicroPython"""

from machine import Pin, PWM
from micropython import const


class Servo:
    """Low-level PWM servo driver.

    Args:
        pin (int): GPIO pin number for servo signal.
        freq (int): PWM frequency in Hz (default 50Hz for standard servos).
        min_duty (int): Duty cycle (u16) corresponding to 0 degrees.
        max_duty (int): Duty cycle (u16) corresponding to 180 degrees.
    """

    _DEFAULT_FREQ = const(50)
    _DEFAULT_MIN_DUTY = const(2500)  # ~0.76ms pulse at 50Hz (0°)
    _DEFAULT_MAX_DUTY = const(7500)  # ~2.29ms pulse at 50Hz (180°)

    def __init__(
        self,
        pin: int,
        freq: int = _DEFAULT_FREQ,
        min_duty: int = _DEFAULT_MIN_DUTY,
        max_duty: int = _DEFAULT_MAX_DUTY,
    ) -> None:
        self._pwm = PWM(Pin(pin))
        self._pwm.freq(freq)
        self._min_duty = min_duty
        self._max_duty = max_duty

    def set_angle(self, angle: int) -> None:
        """Set servo position by angle.

        Args:
            angle (int): Target angle in degrees (0-180).
        """
        angle = max(0, min(180, angle))
        duty = self._min_duty + (self._max_duty - self._min_duty) * angle // 180
        self._pwm.duty_u16(duty)

    def deinit(self) -> None:
        """Release the PWM resource."""
        self._pwm.deinit()
