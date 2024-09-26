import network
import time

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

