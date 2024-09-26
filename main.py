import network
import machine
import time
import i2c
from microdot import Microdot, send_file
from microdot.websocket import with_websocket
from read_sensors import *

ssid = 'MANHA v2'
password = 'space1234'

led = machine.Pin("LED",machine.Pin.OUT)

ap = network.WLAN(network.AP_IF)
ap.config(essid=ssid, password=password)
ap.active(True)

while ap.active() == False:
  pass

print('MANHA Wifi 2 on')
print(ap.ifconfig())
led.on()

ip = ap.ifconfig()[0]
print(ip)

app = Microdot()

i2c.init_i2c()
gps_sensor = NeoGPS()
gps_parser = GPSParser()
bme680 = BME680_I2C(i2c.m_i2c)
imu = ADXL345(i2c.m_i2c)


@app.route('/')
async def index(request):
    return send_file('index.html')

@app.route('/live')
@with_websocket
async def temperature_socket(request, ws):
    while True:
        try:
            b_d = read_bme680(bme680)
            a_d = read_adxl345(imu)
            g_d = read_gps(gps_sensor, gps_parser)
            
            json_data = str(dict(b_d, **a_d, **g_d))
                
    #        frame = self.create_websocket_frame(json_data.encode())
            await ws.send(json_data)
            #print(f"Sent data: {json_data}")
            led.off()
            time.sleep_ms(500)
            led.on()
            time.sleep_ms(500)
        except Exception as e:
            print(f"Error sending socket data: {e}")

app.run(debug=True)