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
# Import the LoRa module directly instead of lazily
from manha.internals.comms.lora import LoRa

# Hardware Constants
_LORA_SPI_CHANNEL = const(1)

_LORA_SCK = const(10)
_LORA_MOSI = const(11)
_LORA_MISO = const(12)
_LORA_CS = const(13)

_LORA_RESET = const(7)

# Communication settings
_SATELLITE_ADDRESS = const(2)  # Address of the satellite
_GS_ADDRESS = const(3)        # Address of this ground station
_TRANSMIT_INTERVAL = const(1.0)  # 1 Hz transmission rate

# Command definitions
COMMANDS = {
    "help": "Display available commands",
    "ping": "Send a ping to the satellite",
    "reboot": "Command the satellite to reboot",
    "status": "Request status from the satellite",
    "sensors": "Request sensor data from the satellite",
    "tx-power": "Set the LoRa TX power (5-23 dBm)",
    "heartbeat": "Toggle automatic heartbeat messages",
    "quit": "Exit the command processor"
}

class ManhaGS:
    """
    MANHA Ground Station class for LoRa communication with MANHA satellite.

    This class provides methods to initialize the ground station hardware, send commands
    to the satellite, receive telemetry data, and manage system tasks.
    """
    def __init__(self, lora_address_to=_SATELLITE_ADDRESS, lora_address_from=_GS_ADDRESS):
        """Initialize the ManhaGS class with default configuration
        
        Args:
            lora_address_to (int): LoRa address to send data to (satellite)
            lora_address_from (int): LoRa address of this device (ground station)
        """
        # Run garbage collection before initialization
        gc.collect()
        
        # Configuration
        self.lora_address_to = lora_address_to
        self.lora_address_from = lora_address_from
        
        # Current data to transmit periodically
        self.sequence = 0
        
        # Create a mutex for received data protection
        self.data_lock = asyncio.Lock()
        self.received_data = {}  # Store for received telemetry
        
        # Command system settings
        self.heartbeat_enabled = True
        self.command_buffer = ""
        
        # Initialize hardware
        self.led = Pin("LED", Pin.OUT)
        self.led.on()
        
        print('MANHA Ground Station initializing')
        
        # Initialize LoRa directly instead of lazily
        try:
            # Initialize SPI for LoRa communication
            spi = SPI(_LORA_SPI_CHANNEL, baudrate=5000000, polarity=0, phase=0, 
                     miso=Pin(_LORA_MISO), mosi=Pin(_LORA_MOSI), sck=Pin(_LORA_SCK))
            cs_pin = Pin(_LORA_CS, Pin.OUT)
            reset_pin = Pin(_LORA_RESET, Pin.OUT)
            
            # Force garbage collection before LoRa initialization to maximize available memory
            gc.collect()
            
            # Add timeout parameter to prevent hanging
            self.lora = LoRa(
                device_id=self.lora_address_from, 
                cs_pin=cs_pin, 
                spi=spi, 
                reset_pin=reset_pin, 
                freq=868.0, 
                tx_power=14,
                timeout_ms=500  # Add 500ms timeout to prevent hanging
            )
        
            # Register command handler for message reception
            self.lora.on_receive = self.handle_received_data
            print('LoRa Initialized')
            
            # Run garbage collection after LoRa setup
            gc.collect()
            
        except Exception as e:
            print(f"LoRa setup error: {e}")
            import sys
            sys.print_exception(e)  # Print the full exception details including traceback
            # Set lora to None to allow the system to continue without LoRa
            self.lora = None
        
        # Run garbage collection after initialization
        gc.collect()
        
        # Print welcome message
        self.print_welcome()
    
    def print_welcome(self):
        """Print the welcome message and command instructions"""
        print("\n" + "=" * 40)
        print("MANHA Ground Station Command Interface")
        print("=" * 40)
        print("Type 'help' for available commands")
        print(">" + " ", end="")
    
    async def send_heartbeat(self, message="GS alive", interval=_TRANSMIT_INTERVAL):
        """
        Task that periodically transmits commands to the satellite.
        
        This method runs as an asyncio task, sending message to the satellite at a regular interval (defined by _TRANSMIT_INTERVAL).
        Each message is tagged with a sequence number to track transmission order.
        
        Args:
            message (str): The message to send to the satellite.
            interval (float): The time interval between transmissions in seconds.
        """
        
        while True:
            try:
                # Skip transmission if LoRa is not initialized or heartbeats are disabled
                if self.lora is None or not self.heartbeat_enabled:
                    await asyncio.sleep(interval)
                    continue
                    
                # Send the message using the new async send method
                result = await self.lora.send_async(message, self.lora_address_to)
                
                if not result:
                    raise Exception("Failed to send message")
                    
                self.sequence += 1
                
                # Run garbage collection after sending
                gc.collect()
                
                # Wait for next transmission cycle
                await asyncio.sleep(interval)
                
            except Exception as e:
                print(f"Transmit error: {e}")
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
            print("Cannot send command: LoRa not initialized")
            return False
            
        try:
            # Format the command with "CMD:" prefix to distinguish from heartbeats
            formatted_command = f"CMD:{command}"
            print(f"Sending command: {formatted_command}")
            
            # Send the command
            result = await self.lora.send_async(formatted_command, self.lora_address_to)
            return result
            
        except Exception as e:
            print(f"Command send error: {e}")
            return False
    
    async def serial_command_task(self):
        """
        Task that listens for serial commands and processes them
        
        This method runs as an asyncio task, checking for input on the serial
        console and parsing commands when received. Commands are then sent to
        the satellite via LoRa.
        """
        print("\nCommand interface ready. Type 'help' for available commands.")
        print("> ", end="")
        
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
                    print("> ", end="")
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
        
        # Process built-in commands
        if command == "help":
            self.show_help()
        elif command == "heartbeat":
            if args and args[0].lower() in ("on", "off"):
                self.heartbeat_enabled = args[0].lower() == "on"
                print(f"Heartbeat messages {'enabled' if self.heartbeat_enabled else 'disabled'}")
            else:
                print(f"Current heartbeat status: {'enabled' if self.heartbeat_enabled else 'disabled'}")
        elif command == "quit":
            print("Command interface cannot be terminated. Use Ctrl+C to exit program.")
        else:
            # Forward other commands to the satellite
            success = await self.send_command(command_str)
            if success:
                print("Command sent successfully")
            else:
                print("Failed to send command")
    
    def show_help(self):
        """Display help information for available commands"""
        print("\nAvailable Commands:")
        print("------------------")
        for cmd, desc in COMMANDS.items():
            print(f"{cmd:<12} - {desc}")
        print("\nCommand Format: command [arguments]")
        print("Example: tx-power 15\n")
    
    async def sysmon_task(self, interval=10):
        """
        Task that periodically reports system status.
        
        Runs as an asyncio task and prints the current system uptime
        every 10 seconds. This provides regular confirmation that
        the ground station is operating normally.
        """
        uptime = 0
        while True:
            print(f"\nSystem status: Running (uptime: {uptime}s)")
            print(f"Memory free: {gc.mem_free()}")
            print("> ", end="")
            uptime += interval
            await asyncio.sleep(interval)
            # Run garbage collection periodically
            gc.collect()

    async def handle_received_data(self, message, from_address):
        """
        Process data received from the satellite
        
        Args:
            message (str): The message received from the satellite
            from_address (int): The address of the sender
        """
        # Only process messages from the satellite address
        if from_address != self.lora_address_to:
            return
            
        print(f"\nRX :: From {from_address} :: {message}")
        
        # Parse the message based on its prefix
        if message.startswith("STATUS:"):
            # Handle status response
            status_data = message[7:].strip()
            async with self.data_lock:
                self.received_data["status"] = status_data
            print(f"Satellite status: {status_data}")
            
        elif message.startswith("SENSORS:"):
            # Handle sensor data
            sensor_data = message[8:].strip()
            async with self.data_lock:
                self.received_data["sensors"] = sensor_data
            print(f"Sensor data: {sensor_data}")
            
        elif message.startswith("PING:"):
            # Handle ping response
            ping_data = message[5:].strip()
            print(f"Ping response received: {ping_data}")
            
        elif message.startswith("ACK:"):
            # Handle command acknowledgment
            ack_data = message[4:].strip()
            print(f"Command acknowledged: {ack_data}")
            
        elif message.startswith("ERR:"):
            # Handle error response
            err_data = message[4:].strip()
            print(f"Error from satellite: {err_data}")
            
        else:
            # Handle generic message
            print(f"Message from satellite: {message}")
            
        # Add prompt back after receiving message
        print("> ", end="")
    
    async def shutdown(self):
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
            print(f"Error during shutdown: {e}")
    
    async def run(self):
        """
        Main entry point to run all ManhaGS tasks.
        
        Initializes the LoRa receiver, creates and schedules the periodic
        transmission and status reporting tasks, and waits for all tasks to complete.
        This is designed to run indefinitely until an exception occurs.
        """
        print("Starting LoRa Ground Station system...")
        
        # Start the LoRa receiver if initialized
        if self.lora is not None:
            await self.lora.start_receiver()
            print("LoRa receiver started")
        else:
            print("WARNING: LoRa not initialized, receiver not started")
        
        # Create and schedule tasks
        heartbeat_task = asyncio.create_task(self.send_heartbeat())
        status_task = asyncio.create_task(self.sysmon_task())
        command_task = asyncio.create_task(self.serial_command_task())
        
        # Wait for all tasks (this will run forever)
        await asyncio.gather(heartbeat_task, status_task, command_task)


# Main function to instantiate and run the ManhaGS class
async def _run_gs():
    """
    Async implementation of the ground station main function.
    
    Creates a ManhaGS instance, runs it, and handles any exceptions that
    may occur during operation. In case of errors, attempts a graceful
    shutdown.
    
    Returns:
        bool: True if shutdown was clean, False if an error occurred
    """
    # Run garbage collection before creating instance
    gc.collect()
    
    gs = ManhaGS()
    try:
        await gs.run()
        return True
    except Exception as e:
        print(f"Main loop error: {e}")
        # Attempt graceful shutdown
        try:
            await gs.shutdown()
        except:
            pass
        return False

def sample_gs_main():
    """
    Main function to initialize and run the ground station.
    
    Creates a ManhaGS instance, runs it, and handles any exceptions that
    may occur during operation. In case of errors, it attempts a graceful
    shutdown before resetting the device.
    """
    # Run garbage collection before startup
    gc.collect()
    
    # Run the async implementation with a single asyncio.run call
    success = asyncio.run(_run_gs())
    
    # Reset if there was an error
    if not success:
        reset()