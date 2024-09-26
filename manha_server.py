import network
import socket
import i2c
import hashlib
import ubinascii
import struct
import uasyncio as asyncio
from bme680 import BME680_I2C
from adxl345 import ADXL345
from gps import NeoGPS
from GPSParser import GPSParser

# WebSocket server port
WEBSOCKET_PORT = 8081

# WebSocket GUID for key hashing
WEBSOCKET_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"

# Functions to read sensor data
def read_adxl345(imu):
    try:
        return {"x": imu.xValue, "y": imu.yValue, "z": imu.zValue}
    except Exception as e:
        print("Failed to read ADXL:", e)
        
def read_gps(gps_sensor, gps_parser):
    try:
        g_d = gps_sensor.read_gps()
        for byte in g_d:
            stat = gps_parser.update(chr(byte))
            if stat is not None:
                # return parsed GPS data
                return {"lat": gps_parser.latitude, "lng": gps_parser.longitude, "alt": gps_parser.altitude, "gps_sc": gps_parser.satellites_in_use, "gps_hdop": gps_parser.hdop }
            else:
                return {"lat": 0.0, "lng": 0.0, "alt": -1, "gps_sc": -1, "gps_hdop": -1 }
    except Exception as e:
        print(f"Failed to read GPS:", e)
        
# Initialize I2C and BME680 sensor
def init_bme680():
    try:
        global bme680
        bme680 = BME680_I2C(i2c.m_i2c)
    except Exception as e:
        print("Failed to initialize BME680:", e)
        
def read_bme680(bme680):
    try:
        return {"temp": bme680.temperature, "humidity": bme680.humidity, "pressure": bme680.pressure, "gas": bme680.gas}

    except Exception as e:
        print("Error reading bme data:", e)
        return None

# Manha server class
class ManhaServer:
    def __init__(self, ip, port=WEBSOCKET_PORT):
        self.ip = ip
        self.port = port
        self.server_socket = None
        self.buffer = None  # Buffer to hold the last BME680 reading
        i2c.init_i2c()
        self.gps_sensor = NeoGPS()
        self.gps_parser = GPSParser()
        self.bme680 = BME680_I2C(i2c.m_i2c)
        self.imu = ADXL345(i2c.m_i2c)

    # WebSocket handshake
    def handshake(self, client):
        try:
            request = client.recv(1024).decode()  # Read request
            headers = request.split("\r\n")
            
            # Find the WebSocket Key from headers
            websocket_key = ""
            for header in headers:
                if "Sec-WebSocket-Key" in header:
                    websocket_key = header.split(": ")[1]
                    break

            if websocket_key:
                # Generate response for WebSocket handshake
                websocket_accept = hashlib.sha1((websocket_key + WEBSOCKET_GUID).encode()).digest()
                websocket_accept = ubinascii.b2a_base64(websocket_accept).decode().strip()

                # Send WebSocket upgrade response
                response = (
                    "HTTP/1.1 101 Switching Protocols\r\n"
                    "Upgrade: websocket\r\n"
                    "Connection: Upgrade\r\n"
                    f"Sec-WebSocket-Accept: {websocket_accept}\r\n"
                    "\r\n"
                )
                client.send(response.encode())
                return True
            else:
                print("WebSocket key not found in headers.")
                return False
        except Exception as e:
            print(f"Error during WebSocket handshake: {e}")
            return False

    # WebSocket frame creator
    def create_websocket_frame(self, data):
        byte_array = bytearray()
        byte_array.append(129)  # Text frame opcode
        length = len(data)
        if length <= 125:
            byte_array.append(length)
        else:
            byte_array.append(126)
            byte_array.extend(struct.pack(">H", length))
        byte_array.extend(data)
        return byte_array

    # Function to send sensor data over WebSocket
    async def send_data(self, websocket):
        while True:
            b_d = read_bme680()
            a_d = read_adxl345()
            g_d = read_gps(self.gps_sensor, self.gps_parser)
            
            try:
                json_data = str(dict(b_d, **a_d, **g_d))
                
                frame = self.create_websocket_frame(json_data.encode())
                websocket.send(frame)
                print(f"Sent data: {json_data}")  # Debugging info
            except Exception as e:
                print(f"Error sending data: {e}")
            await asyncio.sleep(1)  # Send data every 1 seconds
                

    # WebSocket server initialization
    def start(self):
        try:
            addr = socket.getaddrinfo(self.ip, self.port)[0][-1]
            self.server_socket = socket.socket()
            self.server_socket.bind(addr)
            self.server_socket.listen(1)
            print(f"Manha server socket at ws://{self.ip}:{self.port}")
            print(f"Initiating Manha sensors")
            
            print(f"lets do the first sensor read")
            b_d = read_bme680(self.bme680)
            a_d = read_adxl345(self.imu)
            g_d = read_gps(self.gps_sensor, self.gps_parser)
            
            json_data = str(dict(b_d, **a_d, **g_d))
            print(json_data)
                
            return True
        except Exception as e:
            print(f"Error starting Manha server: {e}")
            return False

    # Serve WebSocket requests indefinitely
    async def serve_forever(self):
        while True:
            try:
                client, addr = self.server_socket.accept()  # Accept incoming client connection
                print(f"Client connected from {addr}")

                # Perform WebSocket handshake
                if not self.handshake(client):
                    print("Handshake failed. Closing connection.")
                    client.close()
                    continue

                # Start sending data after a successful handshake
                await self.send_data(client)
            except Exception as e:
                print(f"WebSocket error: {e}")
            finally:
                client.close()  # Close the client connection when done

    def stop(self):
        if self.server_socket:
            self.server_socket.close()
            print("WebSocket server stopped.")
