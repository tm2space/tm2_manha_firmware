import machine
from neopixel import NeoPixel
import time

# Specs
# 8x8
# GPIO6

class PixelColors:
    @property
    def RED(self) -> tuple:
        return (20,0,0)

    @property
    def GREEN(self) -> tuple:
        return (0,20,0)

    @property
    def BLUE(self) -> tuple:
        return (0,0,20)

class DotMatrix:
    """Driver for CJMCU 8x8 WS2812 LED Matrix"""

    _neopixel:NeoPixel
    _width:int
    _height:int

    def __init__(self, width:int=8, height:int=8, do:int=3, initial_color:None|tuple=None):
       self._width = width
       self._height = height

       self._neopixel = NeoPixel(machine.Pin(do), width * height)

       if initial_color is not None:
           self.fill(color)


    def fill(self, color:tuple, commit=True) -> None:
        if self.color is None:
            print('Color not provided!')
        else:
            self._neopixel.fill(color)
            if commit:
                self._neopixel.write()

    def clear(self, commit=True) -> None:
        self.fill((0,0,0))
        if commit:
            self._neopixel.write()

    def setPixel(self, x, y, color, commit=True):
        if self.color is None:
            print('Color not provided!')
        else:
            self._neopixel[(8 * y) + x] = color
            if commit:
                self._neopixel.write()

    def __setitem__(self, idx:int, item:tuple):
        self._neopixel[idx] = item

    def __getitem__(self, idx:int) -> tuple:
        return self._neopixel[idx]


if __name__ == '__main__':

    width = 8
    height = 8

    matrix = DotMatrix()

    for y in range(height):
        for x in range(width):
            if i < (width*height/3):
                matrix.setPixel()



# pix = 64

# np = NeoPixel(machine.Pin(3), pix)


# if __name__ == '__main__':
# for i in range(7):
#    device[i] = (128,0,0)
    
# while True:
#     for i in range(0,8):
#         np[(5*8)+i] = (20,0,0)
# #     np.fill((64,64,64))
#     for i in range(1,6):
#         np[(8*i)-1] = (20,0,0)
#     np.write()
#     time.sleep_ms(100)
# #     np.fill((0,0,0))

"""
def demo(np):
    n = np.n

    # cycle
    print('cycle')
    for i in range(4 * n):
        for j in range(n):
            np[j] = (0, 0, 0, 128)
        np[i % n] = (255, 255, 255, 128)
        np.write()
        time.sleep_ms(25)

    # bounce
    print('b')
    for i in range(4 * n):
        for j in range(n):
            np[j] = (0, 0, 128, 128)
        if (i // n) % 2 == 0:
            np[i % n] = (0, 0, 0, 128)
        else:
            np[n - 1 - (i % n)] = (0, 0, 0, 128)
        np.write()
        time.sleep_ms(60)

    # fade in/out
    print('fade')
    for i in range(0, 4 * 256, 8):
        for j in range(n):
            if (i // 256) % 2 == 0:
                val = i & 0xff
            else:
                val = 255 - (i & 0xff)
            np[j] = (val, 0, 0, 128)
        np.write()

    # clear
    for i in range(n):
        np[i] = (0, 0, 0)
    np.write()

while True:
    demo(device)
    time.sleep_ms(100)
"""
