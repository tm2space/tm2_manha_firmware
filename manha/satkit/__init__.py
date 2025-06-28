"""
MANHA Satellite Kit (satkit) - Main package initialization

This package provides interfaces for various satellite components and sensors,
including GPS, environmental sensors, power monitoring, and communication modules.
"""

from .manha import MANHA
from .peripherals import ManhaSensor

__version__ = '1.0.0'
__all__ = [
    'MANHA',
    'ManhaSensor',
]