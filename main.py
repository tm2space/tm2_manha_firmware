import time
import uasyncio as asyncio
from pico_access_point import PicoAccessPoint
from manha_server import ManhaServer


# Wi-Fi Access Point credentials
SSID = "MANHA_Wifi"
PASSWORD = "password"

# Main logic for starting the AP and WebSocket server
def main():
    # Step 1: Initialize and start the access point
    pico_ap = PicoAccessPoint(ssid=SSID, password=PASSWORD)
    if pico_ap.start_ap():
        # Get the AP's IP address
        ip = pico_ap.ap.ifconfig()[0]  
        time.sleep(1)

        # Step 2: Initialize and start the WebSocket server
        m_server = ManhaServer(ip=ip)
        time.sleep(2)
        if m_server.start():
            try:
                # Serve WebSocket requests indefinitely
                asyncio.run(m_server.serve_forever())
            except KeyboardInterrupt:
                print("Wifi Server stopped by user.")
            finally:
                # Stop the WebSocket server and access point gracefully
                m_server.stop()
                pico_ap.stop_ap()

if __name__ == "__main__":
    main()

