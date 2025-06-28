import machine
from neopixel import NeoPixel
import time

MAX_PIXEL_BRIGHTNESS = 5
MIN_PIXEL_BRIGHTNESS = 0

class PixelColors:
    """Common Colors Enum class for DotMatrix"""
    # Standard terminal colors
    RED = (MAX_PIXEL_BRIGHTNESS, 0, 0)
    GREEN = (0, MAX_PIXEL_BRIGHTNESS, 0)
    YELLOW = (MAX_PIXEL_BRIGHTNESS//2, MAX_PIXEL_BRIGHTNESS//2, 0)
    BLUE = (0, 0, MAX_PIXEL_BRIGHTNESS)
    MAGENTA = (MAX_PIXEL_BRIGHTNESS//2, 0, MAX_PIXEL_BRIGHTNESS//2)
    CYAN = (0, MAX_PIXEL_BRIGHTNESS//2, MAX_PIXEL_BRIGHTNESS//2)
    WHITE = (MAX_PIXEL_BRIGHTNESS//3, MAX_PIXEL_BRIGHTNESS//3, MAX_PIXEL_BRIGHTNESS//3)
    BLACK = (0, 0, 0)
    CLEAR = (0, 0, 0)


class WS2812Matrix:
    def __init__(self, width=8, height=8, do=3, initial_color=None):
        """Initialize the 8x8 WS2812 LED Matrix
        
        Args:
            width: number of leds in a row
            height: number of leds in a column
            do: digital out pin
            initial_color: initial color to fill matrix with
        """
        self._width = width
        self._height = height

        self._neopixel = NeoPixel(machine.Pin(do), width * height)

        if initial_color is not None:
            self.fill(initial_color)

    def fill(self, color) -> None:
        """Set all LEDs in matrix to color
        
        Args:
            color: color to fill matrix with
        """
        if color is None:
            print('Color not provided!')
        else:
            self._neopixel.fill(color)
            self._neopixel.write()

    def clear(self) -> None:
        """Set all LEDs in matrix to 'PixelColors.CLEAR'
        
        Args:
            color: color to fill matrix with
        """
        self.fill(PixelColors.CLEAR)
        self._neopixel.write()

    def setPixel(self, x, y, color):
        """Set LED at (x,y) in matrix to (0,0,0)
        
        Args:
            x: x coordinate of LED
            y: y coordinate of LED
            color: color to set LED to
        """
        if color is None:
            print('Color not provided!')
        else:
            self._neopixel[(8 * y) + x] = color
            self._neopixel.write()
            
    def get(self, x, y) -> tuple:
        """Get LED at (x,y) in matrix as array
        
        Args:
            x: x coordinate of LED
            y: y coordinate of LED
            
        Returns:
            tuple: color of LED at (x,y)
        """
        return self._neopixel[(8 * y) + x]

    def __setitem__(self, idx, value) -> None:
        """Set individual LED in matrix as array
        
        Args:
            idx: index of LED in matrix
            value: color to set LED to
        """
        self._neopixel[idx] = value
        self._neopixel.write()

    def __getitem__(self, idx) -> tuple:
        """Get individual LED in matrix as array
        
        Args:
            idx: index of LED in matrix
            
        Returns:
            tuple: color of LED at index idx
        """
        return self._neopixel[idx]