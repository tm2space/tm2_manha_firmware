import network
import machine
import time
import i2c
from microdot import Microdot, send_file
from microdot.websocket import with_websocket
from read_sensors import *
from gs_comms import *
from dotmatrix import *

ssid = 'MANHA v2'
password = 'space1234'

lora_address_to = 3
lora_channel_id = 2

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

led_matrix = DotMatrix(8,8,3,initial_color=PixelColors.WHITE) # start led matrix with white fill

try:
    gps_sensor = NeoGPS()
    gps_parser = GPSParser(location_formatting='dd')
    bme680 = BME680_I2C(i2c.m_i2c)
    imu = ADXL345(i2c.m_i2c)
    uv = UVS12SD(28)
    gs = LoRAComms(lora_channel_id)
except Exception as e:
    while True:
        led_matrix.fill(PixelColors.BLUE)
        time.sleep_ms(500)
        led_matrix.clear()
        time.sleep_ms(500)

@app.route('/')
async def index(request):
    return send_file('index.html')
@app.errorhandler(404)
async def not_found(request):
    return {'error': 'invalid manha resource requested'}, 404

    

@app.route('/live')
@with_websocket
async def live_socket(request, ws):
    led_matrix.clear()
    while True:
        try:
            b_d = read_bme680(bme680)
            a_d = read_adxl345(imu)
            g_d = read_gps(gps_sensor, gps_parser)
            uv_d = read_uv(uv)
            
            json_data = str(dict(b_d, **a_d, **g_d, **uv_d))

            await ws.send(json_data)

            # send data in blocking mode over lora
            lora_status = gs.send(json_data, lora_address_to)

            # fill matrix with red if lora send failed, green if success
            if not lora_status:
                raise Exception("LoRa send failed")
            
            print(f"Sent data: {json_data}")
            led.off()
            led_matrix.fill(PixelColors.GREEN)
            time.sleep_ms(500)
            led_matrix.clear()
            led.on()
            time.sleep_ms(500)
            led_matrix.fill(PixelColors.GREEN)
            time.sleep_ms(500)
            led_matrix.clear()
            
        except Exception as e:
            print(f"Error sending socket data: {e}")

            led_matrix.fill(PixelColors.RED)
            
            machine.reset()
            pass

app.run(debug=True)