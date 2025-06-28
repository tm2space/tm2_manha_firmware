"""
MANHA Ground Station (ManhaGS) module for LoRa communication with MANHA satellite.

This module implements the ground station side of the MANHA communication system,
providing functionality to send commands to and receive telemetry from the satellite.
"""

from machine import Pin, reset, SPI
import time
import asyncio
import gc
import sys
import select  # Add select module for stdin handling
from micropython import const
gc.collect()
from .lora import LoRa
import network
from manha.internals.microdot import Microdot, send_file, websocket 
import json  # Import json module for data serialization

from manha.config import *
from .constants import *

class ManhaGS:
    """
    MANHA Ground Station class for LoRa communication with MANHA satellite.

    This class provides methods to initialize the ground station hardware, send commands
    to the satellite, receive telemetry data, and manage system tasks.
    """
    def __init__(self, ssid=GS_SSID, password=GS_PASS, lora_address_to=LORA_ADDR, lora_address_from=LORA_ADDR):
        """Initialize the ManhaGS class with default configuration
        
        Args:
            lora_address_to (int): LoRa address to send data to (satellite)
            lora_address_from (int): LoRa address of this device (ground station)
        """
        # Run garbage collection before initialization
        gc.collect()

        self.ws_clients = 0
        
        # Configuration
        self.lora_address_to = lora_address_to
        self.lora_address_from = lora_address_from
        
        # Current data to transmit periodically
        self.sequence = 0
        
        # Create a mutex for received data protection
        self.data_lock = asyncio.Lock()
        self.received_data = {}
        self.last_received_data = None 
        
        # Command system settings
        self.heartbeat_enabled = False
        self.command_buffer = ""
        
        # Set up command system
        self.commands = {}
        
        # Initialize hardware
        self.led = Pin("LED", Pin.OUT)
        self.led.on()

        # init network
        self.ssid = ssid
        self.password = password
        

        try:
            # Initialize SPI for LoRa communication
            spi = SPI(LORA_SPI_CHANNEL, baudrate=5_000_000, polarity=0, phase=0, 
                     miso=Pin(LORA_MISO), mosi=Pin(LORA_MOSI), sck=Pin(LORA_SCK))
            cs_pin = Pin(LORA_CS, Pin.OUT)
            reset_pin = Pin(LORA_RESET, Pin.OUT)
            
            # Initialize new LoRa class
            self.lora = LoRa(
                device_id=self.lora_address_from,
                cs_pin=cs_pin, 
                spi=spi, 
                reset_pin=reset_pin, 
                freq=868.0, 
                tx_power=14,
                timeout_ms=500
            )
            
            # Set up callbacks
            self.lora.set_callback(CALLBACK_TELEMETRY, self.handle_telemetry_data)
            self.lora.set_callback(CALLBACK_COMMAND_RESPONSE, self.handle_command_response)
            
            
            # Run garbage collection after LoRa setup
            gc.collect()
            
        except Exception as e:
            import sys
            sys.print_exception(e)  # Print the full exception details including traceback
            # Set lora to None to allow the system to continue without LoRa
            self.lora = None
        
       # Initialize web server
        self.app = Microdot()
        self._setup_routes()
                
        self._setup_network()
 


        # Run garbage collection after initialization
        gc.collect()
        
        # Print welcome message
        self.print_welcome()
 
    def _setup_network(self):
        self.ap = network.WLAN(network.AP_IF)
        self.ap.config(essid=self.ssid, password=self.password)
        self.ap.active(True)

        # Wait for AP to be active
        while self.ap.active() == False:
            pass
        
        self.led.on()
        
        self.ip = self.ap.ifconfig()[0]
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
        @websocket.with_websocket
        async def live_socket(request, ws):
                try:
                    self.ws_clients += 1
                    while True:
                        if self.last_received_data is not None:
                            await ws.send(self.last_received_data)
                            await asyncio.sleep(1)  # Allow some time for the client to process    
                except Exception as e:
                    pass
                finally:
                    try:
                        await ws.close()
                    except:
                        pass
                    finally:
                        self.ws_clients -= 1

        @self.app.route('/cmd')
        async def command_handler(request):
            try:
                cmd_str = request.args.get('cc')
                if not cmd_str:
                    return {'success': False, 'error': 'Missing Command Code'}, 400
                
                for k,v in request.args.items():
                    if k != 'cc':
                        cmd_str += f" {k}={v}"

                    success = self.send_command(cmd_str)
                    if not success:
                        return {'success': False, 'error': 'Failed to send command'}, 500
            except Exception as e:
                return {'success': False, 'error': str(e)}, 500
            finally:
                return {'success': True}, 200


    def print_welcome(self):
        """Print the welcome message and command instructions"""
        pass
    
    async def send_heartbeat(self, message="GS alive", interval=TRANSMIT_INTERVAL):
        """
        Task that sends periodic PING commands to maintain connection.
        
        This method runs as an asyncio task, sending PING commands to the satellite at a regular interval.
        
        Args:
            message (str): Unused (kept for compatibility)
            interval (float): The time interval between transmissions in seconds.
        """
        
        while True:
            try:
                # Skip transmission if LoRa is not initialized or heartbeats are disabled
                if self.lora is None or not self.heartbeat_enabled:
                    await asyncio.sleep(interval)
                    continue
                    
                # Send PING command to maintain connection
                result = await self.lora.send_command("PING", self.lora_address_to)
                
                if not result:
                    print("Failed to send PING")
                    
                self.sequence += 1
                
                # Run garbage collection after sending
                gc.collect()
                
                # Wait for next transmission cycle
                await asyncio.sleep(interval)
                
            except Exception as e:
                await asyncio.sleep(1)

    async def send_command(self, command):
        """
        Send a command to the satellite via LoRa
        
        Args:
            command (str): The command string to send
            
        Returns:
            bool: True if the command was sent successfully, False otherwise
        """
        if self.lora is None:
            return False
            
        try:
            # Send the command using new LoRa class
            result = await self.lora.send_command(command, self.lora_address_to)
            return result
            
        except Exception as e:
            return False
    
    async def serial_command_task(self):
        """
        Task that listens for serial commands and processes them
        
        This method runs as an asyncio task, checking for input on the serial
        console and parsing commands when received. Commands are then sent to
        the satellite via LoRa.
        """
        
        while True:
            # Check if there's data available on stdin
            if sys.stdin in select.select([sys.stdin], [], [], 0)[0]:
                char = sys.stdin.read(1)
                
                # Process backspace
                if char == '\b' or char == '\x7f':  # Backspace or Delete
                    if self.command_buffer:
                        self.command_buffer = self.command_buffer[:-1]
                        # Move cursor back, clear character, move cursor back again
                        sys.stdout.write('\b \b')
                # Process enter key
                elif char == '\n' or char == '\r':
                    sys.stdout.write('\n')
                    # Process the command if buffer is not empty
                    if self.command_buffer:
                        await self.process_command(self.command_buffer)
                        self.command_buffer = ""
                    # Print new prompt
                # Add other characters to buffer
                else:
                    # Echo the character
                    sys.stdout.write(char)
                    self.command_buffer += char
            
            # Yield to other tasks
            await asyncio.sleep(0.05)
    
    async def process_command(self, command_str):
        """
        Process a command string from the serial interface
        
        Args:
            command_str (str): The command string to process
        """
        # Split into command and arguments
        parts = command_str.strip().split()
        if not parts:
            return
            
        command = parts[0].lower()
        args = parts[1:] if len(parts) > 1 else []
        
        # Check if command exists in our command registry
        if command in self.commands:
            try:
                # Execute the command handler with arguments
                await self.commands[command](args)
            except Exception as e:
                pass
        # Process built-in commands
        elif command == "help":
            self.show_help()
        elif command == "heartbeat":
            if args and args[0].lower() in ("on", "off"):
                self.heartbeat_enabled = args[0].lower() == "on"
        else:
            # Forward other commands to the satellite
            success = await self.send_command(command_str)
    
    def show_help(self):
        """Display help information for available commands"""
        pass
    

    def handle_received_data(self):
        """
        Process data received from the satellite
        
        Args:
            message (str): The message received from the satellite
            from_address (int): The address of the sender
        """

        async def handle_recv(packet):

            from_address = packet.sender_id
            message = packet.message


            # log to file
            with open("received_data.log", "a") as log_file:
                log_file.write(f"{time.time()}: {message}\n")
            
            # Only process messages from the satellite address
            if from_address != self.lora_address_to:
                return
                
            if message.startswith("STATUS:"):
                # Handle status response
                status_data = message[7:].strip()
                async with self.data_lock:
                    self.received_data["status"] = status_data
            
            elif message.startswith("SENSORS:"):
                # Handle sensor data
                sensor_data = message[8:].strip()
                async with self.data_lock:
                    self.received_data["sensors"] = sensor_data
                
            elif message.startswith("PING:"):
                # Handle ping response
                ping_data = message[5:].strip()
                
            elif message.startswith("ACK:"):
                # Handle command acknowledgment
                ack_data = message[4:].strip()
                
            elif message.startswith("ERR:"):
                # Handle error response
                err_data = message[4:].strip()
                
            else:
                # Try to parse as JSON and print only JSON data with \r\n separation
                try:
                    # Attempt to parse as JSON to validate it's a valid JSON packet
                    json.loads(message.decode('utf-8'))
                    # If successful, print the JSON with \r\n
                    print(message.decode('utf-8') + '\r\n')
                    self.last_received_data = message.decode('utf-8')  # Store raw message
                except Exception as e:
                    # Not a valid JSON packet, store but don't print
                    self.last_received_data = message.decode('utf-8')
                    print(self.last_received_data)
                
            
        return handle_recv
    
    async def handle_telemetry_data(self, data: dict, packet):
        """Handle received telemetry data"""
        try:
            # Store the received data
            async with self.data_lock:
                self.received_data["telemetry"] = data
            
            # Update last received data for websocket clients
            self.last_received_data = json.dumps(data)
            
            # Print telemetry data
            print(f"TLM:{data}")
            
        except Exception as e:
            print(f"TLM handling error: {e}")
    
    async def handle_command_response(self, response: str, packet):
        """Handle command response"""
        try:
            # Store response data
            async with self.data_lock:
                self.received_data["command_response"] = response
                
        except Exception as e:
            print(f"Command response handling error: {e}")
    
    async def _shutdown(self):
        """
        Clean up resources before shutdown.
        
        This method performs a graceful shutdown of the ground station,
        ensuring that all hardware resources are properly released and
        communication channels are closed.
        """
        try:
            # Stop the LoRa receiver if it was initialized
            if self.lora is not None:
                await self.lora.stop_receiver()
            self.led.off()
            
            # Run garbage collection on shutdown
            gc.collect()
            
        except Exception as e:
            pass
    
    async def _run(self):
        """
        Main entry point to run all ManhaGS tasks.
        
        Initializes the LoRa receiver, creates and schedules the periodic
        transmission and status reporting tasks, and waits for all tasks to complete.
        This is designed to run indefinitely until an exception occurs.
        """
        
        # Start the LoRa receiver if initialized
        if self.lora is not None:
            await self.lora.start_receiver()
        
        # Create and schedule tasks
        self.heartbeat_task = asyncio.create_task(self.send_heartbeat())
        self.command_task = asyncio.create_task(self.serial_command_task())        
        # Start the web server
        self.app_task = asyncio.create_task(self.app.start_server(port=5000))
        
        
        # Wait for all tasks (this will run forever)
        await asyncio.gather(self.heartbeat_task, self.command_task, self.app_task)

    def add_command(self, command_name: str, callback) -> None:
        """Add a new command to the command registry.
        
        Args:
            command_name: The name of the command (string)
            callback: The function to call when the command is received
        """
        self.commands[command_name] = callback
    
    def remove_command(self, command_name: str) -> None:
        """Remove a command from the command registry.
        
        Args:
            command_name: The name of the command to remove
        """
        if command_name in self.commands:
            del self.commands[command_name]

    def shutdown(self):
        """
        Shutdown the ManhaGS gracefully.
        """
        asyncio.run(self._shutdown())

    def run(self):
        """
        Run the ManhaGS main loop.
        """
        try:
            asyncio.run(self._run())
        except KeyboardInterrupt:
            self.shutdown()

