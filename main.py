import network
import socket
import time
import uasyncio as asyncio
from machine import Pin, SoftI2C
from bme680 import BME680_I2C
import ubinascii
import hashlib
import struct

# Wi-Fi Access Point credentials
SSID = "MANHA_Wifi"
PASSWORD = "password"

# Pin configuration for I2C communication with the BME680 sensor
I2C_SCL_PIN = 1  # SCL pin
I2C_SDA_PIN = 0  # SDA pin

# WebSocket server port
WEBSOCKET_PORT = 8081

# WebSocket GUID for key hashing
WEBSOCKET_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"

# Initialize I2C and BME680 sensor
try:
    i2c = SoftI2C(scl=Pin(I2C_SCL_PIN), sda=Pin(I2C_SDA_PIN))
    bme680 = BME680_I2C(i2c)
    print("BME680 sensor initialized.")
except Exception as e:
    print("Failed to initialize BME680:", e)

# Function to set up Pico W as an access point
class PicoAccessPoint:
    def __init__(self, ssid, password):
        self.ssid = ssid
        self.password = password
        self.ap = network.WLAN(network.AP_IF)

    def start_ap(self):
        try:
            self.ap.active(True)
            time.sleep(1)
            self.ap.config(essid=self.ssid, password=self.password)
            timeout = 10  # Wait for 10 seconds for AP to activate
            while not self.ap.active() and timeout > 0:
                print("Waiting for Access Point to activate...")
                timeout -= 1

            if self.ap.active():
                print(f"Access Point '{self.ssid}' active with IP: {self.ap.ifconfig()[0]}")
                return True
            else:
                print("Failed to activate Access Point.")
                time.sleep(5)
                return False
        except Exception as e:
            print(f"Error starting Access Point: {e}")
            return False

    def stop_ap(self):
        self.ap.active(False)
        print(f"Access Point '{self.ssid}' stopped.")

# Function to read sensor data
def read_bme680():
    try:
        temp = bme680.temperature
        humidity = bme680.humidity
        pressure = bme680.pressure
        gas = bme680.gas
        return {"temp": temp, "humidity": humidity, "pressure": pressure, "gas": gas}
    except Exception as e:
        print("Error reading sensor data:", e)
        return None

# WebSocket server class
class PicoWebSocketServer:
    def __init__(self, ip, port=WEBSOCKET_PORT):
        self.ip = ip
        self.port = port
        self.server_socket = None
        self.buffer = None  # Buffer to hold the last BME680 reading

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
            data = read_bme680()
            if data:
                self.buffer = data  # Update buffer with latest data
            if self.buffer:
                json_data = str(self.buffer)
                frame = self.create_websocket_frame(json_data.encode())
                try:
                    websocket.send(frame)
                    print(f"Sent data: {json_data}")  # Debugging info
                except Exception as e:
                    print(f"Error sending data: {e}")
            await asyncio.sleep(1)  # Send data every 1 seconds

    # WebSocket server initialization
    def start_server(self):
        try:
            addr = socket.getaddrinfo(self.ip, self.port)[0][-1]
            self.server_socket = socket.socket()
            self.server_socket.bind(addr)
            self.server_socket.listen(1)
            print(f"WebSocket server started at ws://{self.ip}:{self.port}")
            return True
        except Exception as e:
            print(f"Error starting WebSocket server: {e}")
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

    def stop_server(self):
        if self.server_socket:
            self.server_socket.close()
            print("WebSocket server stopped.")

# Main logic for starting the AP and WebSocket server
def main():
    # Step 1: Initialize and start the access point
    pico_ap = PicoAccessPoint(ssid=SSID, password=PASSWORD)
    if pico_ap.start_ap():
        ip = pico_ap.ap.ifconfig()[0]  # Get the AP's IP address
        time.sleep(2)

        # Step 2: Initialize and start the WebSocket server
        web_server = PicoWebSocketServer(ip=ip)
        time.sleep(2)
        if web_server.start_server():
            try:
                # Serve WebSocket requests indefinitely
                asyncio.run(web_server.serve_forever())
            except KeyboardInterrupt:
                print("Wifi Server stopped by user.")
            finally:
                # Stop the WebSocket server and access point gracefully
                web_server.stop_server()
                pico_ap.stop_ap()

if __name__ == "__main__":
    main()

