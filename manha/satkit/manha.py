"""
▀▀█▀▀ █▀▄▀█ ▀▀▀▀█ ▄▀▀▀▀ █▀▀▀▄ ▄▀▀▀▄ ▄▀▀▀▀ █▀▀▀▀ 
  █   █   █ █▀▀▀▀  ▀▀▀▄ █▀▀▀  █▀▀▀█ █     █▀▀   
  ▀   ▀   ▀ ▀▀▀▀▀ ▀▀▀▀  ▀     ▀   ▀  ▀▀▀▀ ▀▀▀▀▀ 
"""

import network
import machine
import asyncio
import time
import gc
from manha.internals.comms.wifi.microdot import Microdot, send_file
from manha.internals.comms.wifi.microdot.websocket import with_websocket
from collections import namedtuple

# Import all needed modules upfront
from manha.satkit.peripherals import LEDMatrix, PixelColors, GPS, Accelerometer, UVSensor, PowerMonitor, ManhaSensor  
from manha.internals.comms.lora import LoRa
from . import i2c


_SSID = "MANHA v2"
_PASS = "space1234"
_LORA_ADDR_TO=3
_LORA_ADDR_SELF=2
# _LORA_SPI_CHANNEL = 1
_LORA_SPI_SCK = 6
_LORA_SPI_MISO = 8
_LORA_SPI_MOSI = 7
_LORA_SPI_CS = 9
_LORA_SPI_RESET = 13

    
# default callback to use for recvd messages
def sample_lora_rx_callback(raw_payload: tuple) -> namedtuple:
    """
    The default callback for processing a received raw packet into a structured payload.
    
    Args:
        raw_payload: The raw packet data from the LoRa driver, a tuple of (data, rssi, snr)
        
    Returns:
        namedtuple: A structured payload with sender_id, target_id, message, rssi, snr, and valid_checksum
    """
    raw_bytes, rssi, snr = raw_payload
    
    # Extract sender_id and receiver_id from the first 2 bytes
    sender_id = raw_bytes[0] if len(raw_bytes) > 0 else 0
    receiver_id = raw_bytes[1] if len(raw_bytes) > 1 else 0
    
    # Extract checksum and message from the remaining bytes
    if len(raw_bytes) > 2:
        cmd_code = raw_bytes[3]
        cmd_data = raw_bytes[4:]
    else:
        cmd_code = cmd_data = b''
    
    # Create a structured payload from the raw data
    payload = namedtuple(
        "Payload",
        ['sender_id', 'target_id', 'cmd_code', 'cmd_data', 'rssi', 'snr']
    )(sender_id, receiver_id, cmd_code, cmd_data, rssi, snr)
    
    # save to file 
    with open("lora_payload.txt", "a") as f:
        f.write(f"{time.time()}: {payload}\n")
    
    return payload

class MANHA:
    def __init__(self, ssid=_SSID, password=_PASS, lora_address_to=_LORA_ADDR_TO, lora_address_self=_LORA_ADDR_SELF, lora_rx_callback=sample_lora_rx_callback):
        """Initialize the MANHA class with default configuration
        
        Args:
            ssid (str): SSID for the access point
            password (str): Password for the access point
            lora_address_to (int): LoRa address to send data to
            lora_address_self (int): LoRa address for this device
            lora_rx_callback (Callable[namedtuple]): Function to call on reception
        """
        # Configuration
        self.ssid = ssid
        self.password = password
        self.lora_address_to = lora_address_to
        self.lora_address_self = lora_address_self
        self.lora_rx_callback = lora_rx_callback
        
        # Create a mutex for telemetry string protection
        self.telemetry_lock = asyncio.Lock()
        self.telemetry_string = "{}"  # Initial empty telemetry string
        
        # Sensors list - will hold tuples of (sensor_object, read_function, interval)
        self.sensors = []
        
        # Last read time for each sensor
        self.last_read_times = []
        
        # dict for storing tlm data
        self.telemetry_data = dict()
        
        # Initialize hardware
        self.led = machine.Pin("LED", machine.Pin.OUT)
        
        # Setup network
        self._setup_network()
        
        # Initialize I2C
        i2c.init_i2c()
        
        # Initialize LED Matrix
        self.led_matrix = LEDMatrix(8, 8, 3)
        self.led_matrix.fill(PixelColors.WHITE)
        
        # Initialize web server
        self.app = Microdot()
        self._setup_routes()
        
        # Setup SPI for LoRa
        spi = machine.SoftSPI(baudrate=5000000, polarity=0, phase=0,
                  sck=machine.Pin(_LORA_SPI_SCK), mosi=machine.Pin(_LORA_SPI_MOSI), miso=machine.Pin(_LORA_SPI_MISO))
        cs_pin = machine.Pin(_LORA_SPI_CS, machine.Pin.OUT)
        reset_pin = machine.Pin(_LORA_SPI_RESET, machine.Pin.OUT)
        
        # Initialize LoRa with new driver
        self.lora = LoRa(
            device_id=self.lora_address_self, 
            cs_pin=cs_pin, 
            spi=spi, 
            reset_pin=reset_pin, 
            freq=868.0,
            tx_power=14,
            recv_callback=self.lora_rx_callback,  # Set the callback for received messages
        )
        print('LoRa Initialized')
        
        # Run garbage collection after initialization
        gc.collect()
    
    def setup_default_sensors(self):
        """Initialize the default set of sensors"""
        # Initialize GPS
        gps = GPS()
        self.add_sensor(gps, 1)
        print('GPS Initialized')
        
        # Initialize IMU
        imu = Accelerometer(i2c.m_i2c)
        self.add_sensor(imu, 1)
        print('IMU Initialized')
        
        # Initialize UV Sensor
        uv = UVSensor(adc_pin=28)
        self.add_sensor(uv, 1)
        print('UV Sensor Initialized')
        
        # Initialize Power Monitor
        powermon = PowerMonitor(i2c.m_i2c)
        self.add_sensor(powermon, 1)
        print('Power Monitor Initialized')
    
    def add_sensor(self, sensor: ManhaSensor, interval: int=1):
        """Add a sensor to the MANHA system
        
        Args:
            sensor (ManhaSensor): The sensor object to add
            interval (int): Interval in seconds for reading the sensor
        """
        # Create a tuple and add it to the sensors list
        sensor_tuple = (sensor, interval)
        self.sensors.append(sensor_tuple)
        self.last_read_times.append(0)  # Initialize last read time
        
        return len(self.sensors) - 1  # Return the index of the added sensor
    
    def _setup_network(self):
        self.ap = network.WLAN(network.AP_IF)
        self.ap.config(essid=self.ssid, password=self.password)
        self.ap.active(True)

        # Wait for AP to be active
        while self.ap.active() == False:
            pass
        
        print('MANHA Wifi 2 on')
        print(self.ap.ifconfig())
        self.led.on()
        
        self.ip = self.ap.ifconfig()[0]
        print(self.ip)
        gc.collect()  # Run garbage collection after network setup
    
    def _setup_routes(self):
        """Set up the web server routes"""
        @self.app.route('/')
        async def index(request):
            return send_file('index.html')
        
        @self.app.errorhandler(404)
        async def not_found(request):
            return {'error': 'invalid manha resource requested'}, 404
        
        @self.app.route('/live')
        @with_websocket
        async def live_socket(request, ws):
            self.led_matrix.clear()
            while True:
                try:
                    # Get the latest telemetry string (protected by mutex)
                    async with self.telemetry_lock:
                        json_data = self.telemetry_string
                    
                    await ws.send(json_data)
                    print(f"Sent websocket data: {json_data}")
                    
                    await asyncio.sleep(1)
                    
                except Exception as e:
                    print(f"Error sending socket data: {e}")
                    self.led_matrix.fill(PixelColors.RED)
                    await asyncio.sleep(1)
                    
                    # Try to recover the connection
                    try:
                        await ws.close()  # Close the problematic connection
                        # Continue execution without resetting
                    except:
                        pass  # If close fails, just continue
    
    # Blink LED matrix
    async def blink_led_matrix(self, color):
        self.led_matrix.blink(color, 100)
        
    async def send_tlm_task(self, interval=1):
        """Task to send telemetry data periodically"""
        while True:
            await asyncio.sleep(interval)  # Wait for the specified interval before sending again
            
            try:
                # Create telemetry string
                new_telemetry = str(self.telemetry_data)
                
                # Update shared telemetry string (protected by mutex)
                async with self.telemetry_lock:
                    self.telemetry_string = new_telemetry
                    send_result = await self.lora.send_async(new_telemetry, self.lora_address_to)
                    if not send_result:
                        print(f"LORA SEND FAILED: Could not send telemetry data")
                
                print(f'Updated telemetry: {new_telemetry}')
                
                # Visual indication of successful sensor reading
                self.led_matrix.fill(PixelColors.GREEN)
                await asyncio.sleep(0.1)
                self.led_matrix.clear()
                
            except Exception as e:
                print(f"Error in telemetry task: {e}")
                self.led_matrix.fill(PixelColors.RED)
                await asyncio.sleep(0.1)
                self.led_matrix.clear()
                
    
    # Read all sensors based on their defined intervals
    async def read_sensors_task(self, interval: int=1):
        try:
            # Setup LoRa comms with command handler for the callback
            # Command ID 0 for general messages
            await self.lora.start_receiver()
            
            while True:
                await asyncio.sleep(interval)
                
                try:
                    # Read each sensor based on its interval
                    for i, sensor_tuple in enumerate(self.sensors):
                        # Check if it's time to read this sensor
                        if self.last_read_times[i] >= sensor_tuple[1]:
                            try:
                                # Call the read function with the sensor object
                                sensor = sensor_tuple[0]
                                data = sensor.read()
                                # Update telemetry data with the new readings
                                self.telemetry_data.update(data)
                                # Update last read time
                                self.last_read_times[i] = 0
                            except Exception as e:
                                print(f"Error reading sensor {sensor.__class__.__name__}: {e}")
                        else:
                            # Increment the last read time for this sensor
                            self.last_read_times[i] += 1
                    
                    gc.collect()  # Run garbage collection after each cycle
                    
                except Exception as e:
                    print(f"Error in sensor reading task: {e}")
                    self.led_matrix.fill(PixelColors.RED)
                    await asyncio.sleep(1)
                    self.led_matrix.clear()
                
        except Exception as e:
            print(f"Error initializing sensors: {e}")
            while True:
                # Blue screen of death
                self.led_matrix.fill(PixelColors.BLUE)
                await asyncio.sleep_ms(500)
                self.led_matrix.clear()
                await asyncio.sleep_ms(500)
    
    # Add proper cleanup method for graceful shutdown
    async def shutdown(self):
        """Clean up resources before shutdown"""
        try:
            # Stop the LoRa receiver
            await self.lora.stop_receiver()
            # Set the LED matrix to indicate shutdown
            self.led_matrix.clear()
            # Turn off Wi-Fi
            self.ap.active(False)
        except Exception as e:
            print(f"Error during shutdown: {e}")

    async def run(self):
        """Main entry point to run all MANHA tasks"""
        # Run garbage collection before starting tasks
        gc.collect()
        
        # Create and start the sensor reading task
        self.sensor_task = asyncio.create_task(self.read_sensors_task(2))
        
        # telemetry task to send data periodically
        self.send_task = asyncio.create_task(self.send_tlm_task(2))
        
        # Start the web server
        self.app_task = asyncio.create_task(self.app.start_server(port=80))
        
        # Wait for all tasks (this will run forever)
        await asyncio.gather(self.sensor_task, self.app_task, self.send_task)


# Main function to instantiate and run the Manha class
async def sample_satkit_main():
    # Run garbage collection before creating MANHA instance
    gc.collect()
    
    manha = MANHA()
    manha.setup_default_sensors()  # Setup default sensors
    
    try:
        await manha.run()
    except Exception as e:
        print(f"Main loop error: {e}")
        try:
            await manha.shutdown()
        except:
            pass
        machine.reset()