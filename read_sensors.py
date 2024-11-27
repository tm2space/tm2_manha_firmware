from bme680 import BME680_I2C
from adxl345 import ADXL345
from gps import NeoGPS
from GPSParser import GPSParser
from uvs12sd import UVS12SD

# Functions to read sensor data
def read_uv(uv):
    try:
        return {"uv": uv.uvValue()}
    except Exception as e:
        print("Failed to read UV:", e)
        return {"uv": 0}
    
def read_adxl345(imu):
    try:
        return {"x": imu.xValue, "y": imu.yValue, "z": imu.zValue}
    except Exception as e:
        print("Failed to read ADXL:", e)
        return {"x": 0, "y": 0, "z": 0}
        
def read_gps(gps_sensor, gps_parser):
    try:
        g_d = gps_sensor.read_gps()
        if g_d is None:
            return {"lat": 0.0, "lng": 0.0, "alt": -1, "gps_sc": -1, "gps_hdop": -1 }
        for byte in g_d:
            stat = gps_parser.update(chr(byte))
            
        return {"lat": gps_parser.latitude[0], "lng": gps_parser.longitude[0], "alt": gps_parser.altitude, "gps_sc": gps_parser.satellites_in_use, "gps_hdop": gps_parser.hdop }           
    except Exception as e:
        print(f"Failed to read GPS:", e)
        return {"lat": 0.0, "lng": 0.0, "alt": -1, "gps_sc": -1, "gps_hdop": -1 }
        
def read_bme680(bme680):
    try:
        return {"temp": bme680.temperature, "humidity": bme680.humidity, "pressure": bme680.pressure, "gas": bme680.gas}

    except Exception as e:
        print("Error reading bme data:", e)
        return {"temp": -1, "humidity": -1, "pressure": -1, "gas": -1}