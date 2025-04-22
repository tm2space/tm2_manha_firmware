"""
▀▀█▀▀ █▀▄▀█ ▀▀▀▀█ ▄▀▀▀▀ █▀▀▀▄ ▄▀▀▀▄ ▄▀▀▀▀ █▀▀▀▀ 
  █   █   █ █▀▀▀▀  ▀▀▀▄ █▀▀▀  █▀▀▀█ █     █▀▀   
  ▀   ▀   ▀ ▀▀▀▀▀ ▀▀▀▀  ▀     ▀   ▀  ▀▀▀▀ ▀▀▀▀▀ 

MANHA (Modular Architecture for Nano-satellite Hardware and Applications) firmware package

This is the main package for the TM2Space MANHA firmware, providing
modular hardware and application support for nano-satellites.

Subpackages:
- gs: Ground Station module for LoRa communication
- satkit: Satellite kit components and interface
- internals: Internal modules and drivers
- utils: Utility functions and classes
"""

from . import gs, satkit, internals, utils

__version__ = "1.0.0"
__all__ = ['gs', 'satkit', 'internals', 'utils']