"""
MANHA Ground Station (ManhaGS) module for LoRa communication with MANHA satellite.

This module implements the ground station side of the MANHA communication system,
providing functionality to send commands to and receive telemetry from the satellite.
"""

from machine import Pin, reset, SPI
import time
import asyncio
import gc
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
                # Skip transmission if LoRa is not initialized
                if self.lora is None:
                    print("Cannot transmit :: LoRa not initialized")
                    await asyncio.sleep(interval)
                    continue
                    
                print(f"TX :: Sending :: {message}")
                
                # Send the message using the new async send method
                result = await self.lora.send_async(message, self.lora_address_to)
                
                if result:
                    print("TX :: Success")
                else:
                    print("TX :: Failed")
                    
                self.sequence += 1
                
                # Run garbage collection after sending
                gc.collect()
                
                # Wait for next transmission cycle
                await asyncio.sleep(interval)
                
            except Exception as e:
                print(f"Transmit error: {e}")
                await asyncio.sleep(1)
    
    async def sysmon_task(self, interval=10):
        """
        Task that periodically reports system status.
        
        Runs as an asyncio task and prints the current system uptime
        every 10 seconds. This provides regular confirmation that
        the ground station is operating normally.
        """
        uptime = 0
        while True:
            print(f"System status: Running (uptime: {uptime}s)")
            print(f"Memory free: {gc.mem_free()}")
            uptime += interval
            await asyncio.sleep(interval)
            # Run garbage collection periodically
            gc.collect()

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
        # transmit_task = asyncio.create_task(self.periodic_transmit())
        status_task = asyncio.create_task(self.sysmon_task())
        
        # Wait for all tasks (this will run forever)
        await asyncio.gather(status_task)


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