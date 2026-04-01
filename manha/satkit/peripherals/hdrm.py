"""MHDRM - Servo-based Hold-Down Release Mechanism"""

from manha.internals.drivers import Servo
from .base import ManhaSensor

from micropython import const


class MHDRM(ManhaSensor):
    """Servo-based Hold-Down Release Mechanism peripheral.

    Controls a servo to hold or release a deployment mechanism
    (e.g., antenna, solar panel).

    Args:
        pin (int): GPIO pin for servo signal.
        hold_angle (int): Servo angle for hold position (degrees).
        release_angle (int): Servo angle for release position (degrees).
    """

    _DEFAULT_PIN = const(15)
    _DEFAULT_HOLD_ANGLE = const(0)
    _DEFAULT_RELEASE_ANGLE = const(90)

    def __init__(
        self,
        pin: int = _DEFAULT_PIN,
        hold_angle: int = _DEFAULT_HOLD_ANGLE,
        release_angle: int = _DEFAULT_RELEASE_ANGLE,
    ) -> None:
        self._servo = Servo(pin=pin)
        self._hold_angle = hold_angle
        self._release_angle = release_angle
        self._released = False
        self._servo.set_angle(self._hold_angle)

    def read(self) -> dict:
        """Read HDRM state.

        Returns:
            dict: Dictionary with 'hdrm' key (1 = released, 0 = held).
        """
        return {"hdrm": 1 if self._released else 0}

    def configure(self, **kwargs) -> None:
        """Configure HDRM parameters.

        Args:
            **kwargs: Supported keys: hold_angle (int), release_angle (int).
        """
        if "hold_angle" in kwargs:
            self._hold_angle = kwargs["hold_angle"]
        if "release_angle" in kwargs:
            self._release_angle = kwargs["release_angle"]

    def release(self) -> None:
        """Move servo to release position."""
        self._servo.set_angle(self._release_angle)
        self._released = True

    def hold(self) -> None:
        """Move servo to hold position."""
        self._servo.set_angle(self._hold_angle)
        self._released = False
