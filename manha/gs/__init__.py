"""
Ground Station (GS) package for MANHA LoRa communication

This package provides the necessary classes and functionality for LoRa communication
in the ground station component of the TM2Space MANHA project.
"""

# Direct imports instead of lazy loading
from .gs import ManhaGS, sample_gs_main

__version__ = "1.0.0"
__all__ = ['ManhaGS', "sample_gs_main"]