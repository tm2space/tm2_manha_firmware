"""
▀▀█▀▀ █▀▄▀█ ▀▀▀▀█ ▄▀▀▀▀ █▀▀▀▄ ▄▀▀▀▄ ▄▀▀▀▀ █▀▀▀▀ 
  █   █   █ █▀▀▀▀  ▀▀▀▄ █▀▀▀  █▀▀▀█ █     █▀▀   
  ▀   ▀   ▀ ▀▀▀▀▀ ▀▀▀▀  ▀     ▀   ▀  ▀▀▀▀ ▀▀▀▀▀ 

MANHA (Modular Architecture for Nano-satellite Hardware and Applications) firmware package

This is the main package for the TM2Space MANHA firmware, providing
modular hardware and application support for nano-satellites.

Subpackages:
- comms: Communication modules (LoRa and WiFi)
- gs: Ground Station module for LoRa communication
- satkit: Satellite kit components and interface
- peripherals: Hardware peripherals interfaces
- internals: Internal modules and drivers
"""

from . import gs, satkit, internals

__version__ = "1.0.0"
__all__ = ['gs', 'satkit', 'internals']