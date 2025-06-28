from manha.satkit.peripherals import ManhaSensor
from manha.satkit import MANHA

from qmc5883 import QMC5883
from machine import Pin, SoftI2C

import asyncio as aio
import time
    
class Compass(ManhaSensor):
    
    def __init__(self, i2c, address=0x0D):
        self._compass = QMC5883(i2c, slvAddr=address)
        pass
        
    def read(self):
        try:
            reading = self._compass.measure()
            return {
                "cs_x": reading[0],
                "cs_y": reading[1],
                "cs_z": reading[2],
                }
        except Exception as e:
            print(f"Error in Compass: {e}")
            return {
                "cs_x": -1,
                "cs_y": -1,
                "cs_z": -1,
                }
            
def main():
    manha = MANHA()
    
    manha.setup_default_sensors()  # Setup default sensors

    try:
        compass = Compass(manha.i2c)
    
        manha.add_sensor(compass)
    except Exception as e:
        print("Error Adding QMC5883",e)

    try:
        manha.run()
    except Exception as e:
        print(f"Main loop error: {e}")
        try:
            manha.shutdown()
        except:
            pass
        machine.reset()
      
if __name__ == "__main__":
    main()
