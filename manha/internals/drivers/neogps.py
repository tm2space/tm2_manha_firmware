import machine

class NeoGPS:
    def __init__(self):
        self.gps_serial = machine.UART(1, baudrate=9600, tx=4, rx=5)
    
    def read_gps(self):
        if self.gps_serial.any():
            return self.gps_serial.readline()  # Read a complete line from the UART