import machine
from neopixel import NeoPixel
import time

class PixelColors:
    """Common Colors Enum class for DotMatrix"""
    @property
    def RED(self) -> tuple:
        return (20,0,0)

    @property
    def GREEN(self) -> tuple:
        return (0,20,0)

    @property
    def BLUE(self) -> tuple:
        return (0,0,20)

    @property
    def WHITE(self) -> tuple:
        return (20,20,20)

    def CLEAR(self) -> tuple:
        return (0,0,0)

class DotMatrix:
    """Driver for CJMCU 8x8 WS2812 LED Matrix
    
    :param width: number of leds in a row
    :param height: number of leds in a column
    :param do: digital out pin
    :param initial_color: initial color to fill matrix with"""
    def __init__(self, width=8, height=8, do=3, initial_color=None):
        """Initializes DotMatrix object at pin 'do'"""
        self._width = width
        self._height = height

        self._neopixel = NeoPixel(machine.Pin(do), width * height)

        if initial_color is not None:
            self.fill(initial_color)

    def fill(self, color) -> None:
        """Set all leds in matrix to 'color'"""
        if self.color is None:
            print('Color not provided!')
        else:
            self._neopixel.fill(color)
            self._neopixel.write()

    def clear(self) -> None:
        """Set all lEDs in matrix to 'Pixelcolors.CLEAR'"""
        self.fill(PixelColors.CLEAR)
        self._neopixel.write()

    def setPixel(self, x, y, color):
        """Set lED at (x,y) in matrix to (0,0,0)"""
        if self.color is None:
            print('Color not provided!')
        else:
            self._neopixel[(8 * y) + x] = color
            self._neopixel.write()

    def __setitem__(self, idx, item):
        """Set individual LED in matrix as array"""
        self._neopixel[idx] = item
        self._neopixel.write()

    def __getitem__(self, idx) -> tuple:
        """Get individual LED in matrix as array"""
        return self._neopixel[idx]