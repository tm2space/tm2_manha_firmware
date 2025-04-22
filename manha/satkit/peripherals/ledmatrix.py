from manha.internals.drivers import WS2812Matrix, PixelColors
from .base import ManhaSensor

from micropython import const

import time

class LEDMatrix:
    
    _DEFAULT_WIDTH = const(8)
    _DEFAULT_HEIGHT = const(8)
    _DEFAULT_COLOR = PixelColors.CLEAR
    _DEFAULT_DO = const(3)
    
    def __init__(self, width: int = _DEFAULT_WIDTH, height: int = _DEFAULT_HEIGHT, do: int = _DEFAULT_DO) -> None:
        """Initialize the LED matrix with specified width, height, and brightness.

        Args:
            width (int): Width of the LED matrix.
            height (int): Height of the LED matrix.
            brightness (int): Brightness level of the LEDs (0-255).
        """
        self._matrix = WS2812Matrix(width=width, height=height, do=do, initial_color=self._DEFAULT_COLOR)
        
    def set_pixel(self, x: int, y: int, color: tuple) -> None:
        """Set the color of a specific pixel in the matrix.

        Args:
            x (int): X-coordinate of the pixel.
            y (int): Y-coordinate of the pixel.
            color (tuple): RGB color value as a tuple.
        """
        self._matrix.setPixel(x, y, color)
        
    def get_pixel(self, x: int, y: int) -> tuple:
        """Get the color of a specific pixel in the matrix.

        Args:
            x (int): X-coordinate of the pixel.
            y (int): Y-coordinate of the pixel.

        Returns:
            tuple: RGB color value as a tuple.
        """
        return self._matrix.get(x, y)
        
    def fill(self, color: tuple) -> None:
        """Fill the entire matrix with a specific color.

        Args:
            color (tuple): RGB color value as a tuple.
        """
        self._matrix.fill(color)
        
    def clear(self) -> None:
        """Clear the matrix by setting all pixels to black (off)."""
        self._matrix.clear()
        
    def blink(self, color: tuple, delay: int, off_color: tuple = None) -> None:
        """Blink the entire matrix with a specific color once.

        Args:
            color (tuple): RGB color value as a tuple.
            delay (int): Delay in milliseconds between blinks.
        """
        self.fill(color)
        self._matrix.write()
        time.sleep_ms(delay)
        if off_color is None:
            self.clear()
        else:
            self.fill(off_color)
        self._matrix.write()
        time.sleep_ms(delay)