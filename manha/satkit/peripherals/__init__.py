"""
MANHA Peripherals Package

This package contains classes for interfacing with various hardware peripherals
on the MANHA platform.
"""

__version__ = "1.0.0"
__all__ = [
    "ManhaSensor",
    "LEDMatrix",
    "PixelColors",
    "UVSensor",
    "GasSensor",
    "Accelerometer",
    "PowerMonitor",
    "GPS",
    "MHDRM",
    "ManhaCam",
    "FineSunSensor",
]

from .ledmatrix import LEDMatrix
from .uv import UVSensor
from .gas import GasSensor
from .accelerometer import Accelerometer
from .powermon import PowerMonitor
from .gps import GPS
from .hdrm import MHDRM
from .camera import ManhaCam
from .fss import FineSunSensor
from .base import ManhaSensor

from manha.internals.drivers import PixelColors
