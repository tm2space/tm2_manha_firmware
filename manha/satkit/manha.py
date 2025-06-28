"""TM2 MANHA Satellite Control System"""

import machine
import asyncio
import time
import gc
import json

from collections import namedtuple

from manha.utils import calculate_checksum

# Import all needed modules upfront
from manha.satkit.peripherals import LEDMatrix, PixelColors
from manha.internals.drivers import GPSParser, NeoGPS, ADXL345, BME680_I2C, INA219, UVS12SD
from .lora import LoRa
from . import i2c

from manha.config import *
from .constants import *


class MANHA:
    @property
    def i2c(self):
        """Get I2C Instance"""
        return i2c.m_i2c

    def __init__(self, lora_address_to=LORA_ADDR, lora_address_self=LORA_ADDR):
        """Initialize the MANHA class with aggressive memory management
        
        Args:
            lora_address_to (int): LoRa address to send data to
            lora_address_self (int): LoRa address for this device
        """
        # Force aggressive garbage collection at startup
        gc.collect()
        startup_memory = gc.mem_free()
        print(f"MANHA init - Free memory: {startup_memory}")
        
        if startup_memory < 60000:
            print("CRITICAL: Very low memory at startup")
            # Try to free some memory by forcing collection again
            gc.collect()
            
        # Configuration
        self.lora_address_to = lora_address_to
        self.lora_address_self = lora_address_self
        
        # Initialize minimal sensor lists
        self.essential_sensors = []
        self.non_essential_sensors = []
        self.low_power_mode = False
        self.power_threshold = 50
        
        # Minimal command system
        self.commands = {}
        
        # Memory check before creating locks
        gc.collect()
        if gc.mem_free() < 50000:
            print("ERROR: Insufficient memory for initialization")
            raise MemoryError("Cannot initialize - insufficient memory")
        
        # Create minimal telemetry system
        self.telemetry_lock = asyncio.Lock()
        self.telemetry_data = {}
        
        # Command handling flags
        self.command_flag = False
        self.command_response = None
        self._packet_count = 0
        self._tlm_generator = None
        
        # Pre-allocated buffers for memory optimization
        self._temp_dict = {}  # Reusable dict for telemetry
        
        # Initialize hardware with memory checks
        gc.collect()
        self.led = machine.Pin("LED", machine.Pin.OUT)
        
        # Initialize I2C
        i2c.init_i2c()
        gc.collect()
        
        # Initialize LED Matrix
        self.led_matrix = LEDMatrix(8, 8, 3)
        self.led_matrix.fill(PixelColors.WHITE)
        gc.collect()
        
        # Setup SPI for LoRa with memory check
        if gc.mem_free() < 40000:
            print("WARNING: Low memory before LoRa init")
            gc.collect()
        
        spi = machine.SPI(LORA_SPI_CHANNEL, baudrate=5_000_000, polarity=0, phase=0,
                  sck=machine.Pin(LORA_SPI_SCK), mosi=machine.Pin(LORA_SPI_MOSI), miso=machine.Pin(LORA_SPI_MISO))
        cs_pin = machine.Pin(LORA_SPI_CS, machine.Pin.OUT)
        gc.collect()
        
        # Initialize LoRa with new driver
        self.lora = LoRa(
            device_id=self.lora_address_self, 
            cs_pin=cs_pin, 
            reset_pin=None,
            spi=spi,
            freq=868.0,
            tx_power=14,
            led_matrix=self.led_matrix
        )
        
        print('LoRa Initialized')
        gc.collect()
        final_memory = gc.mem_free()
        print(f"MANHA init complete - Free memory: {final_memory}")
    
    
    
    
    
    
    
    
    async def cmd_lpm(self, command, from_address):
        """Handle LPM=<0/1> command - force low power mode"""
        try:
            # Extract LPM value from LPM=<0/1> format
            lpm_str = command.split('=')[1]
            lpm_value = int(lpm_str)
            
            if lpm_value == 1:
                # Force enter low power mode
                if not self.low_power_mode:
                    await self.enter_low_power_mode()
                response = "Low power mode enabled"
            elif lpm_value == 0:
                # Force exit low power mode
                if self.low_power_mode:
                    await self.exit_low_power_mode()
                response = "Low power mode disabled"
            else:
                response = "LPM value must be 0 or 1"
        except (IndexError, ValueError):
            response = "Invalid LPM command format. Use LPM=<0/1>"
        
        # Send response
        response_data = {"type": "LPM", "message": response}
        await self._send_response_direct(json.dumps(response_data), from_address)
        return True
    
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
    
    def setup_default_sensors(self):
        """Initialize sensors using base drivers directly"""
        gc.collect()
        initial_memory = gc.mem_free()
        print(f"Setting up sensors - Free memory: {initial_memory}")
        
        # Power Monitor function (essential) - using INA219 directly
        def read_power():
            try:
                if not hasattr(self, '_ina219'):
                    self._ina219 = INA219(shunt_ohms=0.1, i2c=i2c.m_i2c, max_expected_amps=3.0)
                    self._ina219.configure()
                voltage = self._ina219.voltage()
                # Convert to percentage (assuming 3.7V nominal for Li-ion)
                percentage = min(100, max(0, (voltage - 3.0) / 1.2 * 100))
                return {'v_p': percentage, 'v_raw': voltage}
            except Exception as e:
                return {'v_p': 50, 'v_raw': 3.7}  # Default safe values
        
        # GPS function (essential) - using NeoGPS and GPSParser directly
        def read_gps():
            try:
                if not hasattr(self, '_gps_uart'):
                    self._gps_uart = NeoGPS()
                    self._gps_parser = GPSParser(location_formatting='dd')
                
                gps_data = self._gps_uart.read_gps()
                if gps_data:
                    for byte in gps_data:
                        self._gps_parser.update(chr(byte))
                
                lat = self._gps_parser.latitude
                lon = self._gps_parser.longitude
                return {
                    'lat': lat[0] if lat else 0.0,
                    'lng': lon[0] if lon else 0.0,
                    'alt': self._gps_parser.altitude,
                    'sats': self._gps_parser.satellites_in_use
                }
            except Exception as e:
                return {'lat': 0.0, 'lng': 0.0, 'alt': 0, 'sats': 0}
        
        # Add essential sensors
        try:
            self.add_sensor(read_power, essential=True)
            print('INA219 power monitor OK')
            gc.collect()
        except Exception as e:
            print(f'Power monitor failed: {e}')
        
        try:
            self.add_sensor(read_gps, essential=True)
            print('GPS UART OK')
            gc.collect()
        except Exception as e:
            print(f'GPS failed: {e}')
        
        # Only add non-essential if we have memory
        if gc.mem_free() > 40000:
            # IMU function - using ADXL345 directly
            def read_imu():
                try:
                    if not hasattr(self, '_adxl345'):
                        self._adxl345 = ADXL345(i2c=i2c.m_i2c)
                    return {
                        'a_x': self._adxl345.xValue,
                        'a_y': self._adxl345.yValue,
                        'a_z': self._adxl345.zValue
                    }
                except:
                    return {'a_x': 0, 'a_y': 0, 'a_z': 0}
            
            # Environmental sensor - using BME680 directly
            def read_env():
                try:
                    if not hasattr(self, '_bme680'):
                        self._bme680 = BME680_I2C(i2c=i2c.m_i2c, address=0x77)
                    return {
                        'temp': self._bme680.temperature,
                        'pres': self._bme680.pressure,
                        'hum': self._bme680.humidity
                    }
                except:
                    return {'temp': 25, 'pres': 1013, 'hum': 50}
            
            try:
                self.add_sensor(read_imu, essential=False)
                print('ADXL345 IMU OK')
                gc.collect()
            except:
                print('IMU failed')
            
            try:
                self.add_sensor(read_env, essential=False)
                print('BME680 ENV OK')
                gc.collect()
            except:
                print('ENV failed')
        
        final_memory = gc.mem_free()
        print(f"Sensor setup complete - Free memory: {final_memory}")
    
    def add_sensor(self, sensor, essential: bool = False):
        """Add a sensor with memory check
        
        Args:
            sensor: Function that returns sensor data dict OR object with read() method
            essential (bool): True if this is an essential sensor (GPS or PowerMon)
        """
        # Memory check before adding sensor
        if gc.mem_free() < 25000:
            print("Cannot add sensor - insufficient memory")
            return -1
            
        if essential:
            self.essential_sensors.append(sensor)
            return len(self.essential_sensors) - 1
        else:
            self.non_essential_sensors.append(sensor)
            return len(self.non_essential_sensors) - 1
    
    
    
    async def blink_led_matrix(self, color):
        """Only blink LED matrix if not in low power mode"""
        if not self.low_power_mode:
            self.led_matrix.fill(color)
            await asyncio.sleep(0.5)
            self.led_matrix.clear()
        
    
    async def _listen_for_commands(self, listen_time_ms: int):
        """Listen for incoming commands for specified time - using bytes comparisons"""
        self.lora._modem.set_mode_rx()
        start_time = time.ticks_ms()
        
        while time.ticks_diff(time.ticks_ms(), start_time) < listen_time_ms:
            # Check for RX_DONE
            if self.lora._modem._is_flag_set(0x40):  # RX_DONE
                recv_result = self.lora._modem.recv_data()
                if recv_result:
                    raw_data, rssi, snr = recv_result
                    from manha.internals.comms.packet import Packet
                    packet = Packet.decode(raw_data, rssi, snr)
                    if packet and packet.is_valid_checksum():
                        # Use bytes comparison instead of string
                        if packet.message.startswith(b'CMD:'):
                            command_bytes = packet.message[4:].strip()
                            await self._process_command_bytes(command_bytes, packet.addr_from)
                        # Return early if we received something
                        return
            
            await asyncio.sleep_ms(10)
    
    async def _process_command_bytes(self, command_bytes: bytes, sender_addr: int):
        """Process command using bytes - set flag for generator to handle response"""
        try:
            # Visual indication of command reception
            self.led_matrix.fill(PixelColors.BLUE)
            await asyncio.sleep(0.1)
            self.led_matrix.clear()
            
            # Convert bytes to string for processing
            command = command_bytes.decode('utf-8')
            
            # Process standard commands first
            if command == "PING":
                self.command_response = "PONG"
                self.command_flag = True
            elif command == "RESET":
                self.command_response = "RESET_ACK"
                self.command_flag = True
                # Schedule reset after sending response
                asyncio.create_task(self._delayed_reset())
            else:
                # Handle custom commands and set response
                response = await self._handle_custom_command_with_response(command, sender_addr)
                if response:
                    self.command_response = response
                    self.command_flag = True
            
        except Exception as e:
            print(f"Command processing error: {e}")
    
    async def _handle_custom_command_with_response(self, command: str, sender_addr: int) -> str:
        """Handle custom commands and return response string"""
        try:
            if command.startswith("TXPOW="):
                # Extract power value from TXPOW=<v> format
                power_str = command.split('=')[1]
                power = int(power_str)
                
                if 5 <= power <= 23:
                    self.lora.set_tx_power(power)
                    return f"TX power set to {power}dBm"
                else:
                    return "TX power must be between 5 and 23dBm"
                    
            elif command.startswith("LPM="):
                # Extract LPM value from LPM=<0/1> format
                lpm_str = command.split('=')[1]
                lmp_value = int(lpm_str)
                
                if lmp_value == 1:
                    if not self.low_power_mode:
                        await self.enter_low_power_mode()
                    return "Low power mode enabled"
                elif lmp_value == 0:
                    if self.low_power_mode:
                        await self.exit_low_power_mode()
                    return "Low power mode disabled"
                else:
                    return "LPM value must be 0 or 1"
            else:
                return f"Unknown command: {command}"
                
        except (IndexError, ValueError) as e:
            return f"Command format error: {e}"
        except Exception as e:
            return f"Command error: {e}"
    
    async def _delayed_reset(self):
        """Reset system after small delay"""
        await asyncio.sleep_ms(1000)
        try:
            with open('/RMT_RESET', 'w') as f:
                f.write(str(time.time()))
            machine.reset()
        except:
            machine.reset()
    
    async def _send_response_direct(self, response: str, target_addr: int):
        """Send command response using direct modem access"""
        try:
            message = f"CMD:{response}\r\n".encode('utf-8')
            from manha.internals.comms.packet import Packet
            packet = Packet(target_addr, self.lora_address_self, message)
            
            self.lora._modem.set_mode_idle()
            if self.lora._modem.send(packet.encode()):
                # Wait for TX_DONE
                start_time = time.ticks_ms()
                while True:
                    irq_flags = self.lora._modem._spi_read(0x12)  # REG_12_IRQ_FLAGS
                    if irq_flags & 0x08:  # TX_DONE
                        self.lora._modem.clear_irq_flags()
                        break
                    if time.ticks_diff(time.ticks_ms(), start_time) > 2000:
                        break
                    await asyncio.sleep_ms(10)
        except Exception as e:
            print(f"Response send error: {e}")
                
    async def enter_low_power_mode(self):
        """Enter Low Power Mode"""
        print("ENTERING LOW POWER MODE")
        # Enter low power mode (no WiFi/web server to shut down)
        self.low_power_mode = True
        
        # Final LED matrix notification before shutdown
        await self.blink_led_matrix(PixelColors.YELLOW)

    async def exit_low_power_mode(self):
        """Exit Low Power Mode"""
        print("EXITING LOW POWER MODE")
        self.low_power_mode = False
        
        # Re-enable LED matrix
        await self.blink_led_matrix(PixelColors.MAGENTA)  # Indicate normal mode
        
    def _check_memory_pressure(self) -> bool:
        """Check if memory pressure is high and return True if we should skip operations"""
        free_mem = gc.mem_free()
        if free_mem < 50000:  # Less than 50KB free
            print(f"Memory pressure: {free_mem} bytes free")
            gc.collect()  # Force collection
            return free_mem < 30000  # Critical if still less than 30KB
        return False
    
    async def read_sensors_task(self, interval: int=1):
        """Task to read sensors sequentially with memory optimization
        
        Args:
            interval (int): Base time in seconds between sensor readings
        """
        self._sensor_read_interval = interval
        
        while True:
            try:
                # Force garbage collection before starting
                gc.collect()
                
                # Check memory pressure and skip if critical
                if self._check_memory_pressure():
                    print("Skipping sensor read due to memory pressure")
                    await asyncio.sleep_ms(5000)  # Wait longer before retry
                    continue
                
                if self.low_power_mode:
                    await asyncio.sleep(10)
                else:
                    await asyncio.sleep(self._sensor_read_interval)
                
                # Read sensors sequentially to reduce memory pressure
                temp_telemetry = {}
                
                # Always read essential sensors one by one
                for i, sensor in enumerate(self.essential_sensors):
                    try:
                        # Memory check before each sensor
                        if self._check_memory_pressure():
                            print(f"Memory pressure during essential sensor {i}")
                            break
                            
                        # Read sensor data
                        data = None
                        if callable(sensor):
                            data = sensor()
                        elif hasattr(sensor, 'read'):
                            data = sensor.read()
                        
                        if data:
                            # Check power threshold immediately
                            if 'v_p' in data:
                                if data['v_p'] < self.power_threshold and not self.low_power_mode:
                                    await self.enter_low_power_mode()
                                elif self.low_power_mode and data['v_p'] >= self.power_threshold:
                                    await self.exit_low_power_mode()
                            
                            temp_telemetry.update(data)
                            data = None  # Clear reference immediately
                        
                        # Garbage collect after each sensor
                        gc.collect()
                        
                    except Exception:
                        print(f"Sensor error: essential {i}")  # Minimal string allocation
                
                # Read non-essential sensors if not in low power mode
                if not self.low_power_mode:
                    for i, sensor in enumerate(self.non_essential_sensors):
                        try:
                            # Memory check before each sensor
                            if self._check_memory_pressure():
                                print(f"Memory pressure during sensor {i}")
                                break
                                
                            # Read sensor data
                            data = None
                            if callable(sensor):
                                data = sensor()
                            elif hasattr(sensor, 'read'):
                                data = sensor.read()
                            
                            if data:
                                temp_telemetry.update(data)
                                data = None  # Clear reference immediately
                            
                            # Garbage collect after each sensor
                            gc.collect()
                            
                        except Exception:
                            print(f"Sensor error: non-essential {i}")  # Minimal string allocation
                
                # Update global telemetry dict with lock
                if temp_telemetry:  # Only update if we have data
                    async with self.telemetry_lock:
                        self.telemetry_data.update(temp_telemetry)
                    temp_telemetry.clear()  # Clear immediately
                
                # Final garbage collection after cycle
                gc.collect()
                
            except Exception:
                print("Sensor task error")  # Minimal string allocation
                if not self.low_power_mode:
                    await self.blink_led_matrix(PixelColors.RED)
                await asyncio.sleep_ms(2000)  # Longer delay on error

    def _prepare_telemetry_generator(self, tlm_data_copy):
        """Simplified generator for telemetry data <= 200 bytes"""
        try:
            if self._check_memory_pressure():
                yield b'{}'
                return
            
            # Reuse temp dict
            self._temp_dict.clear()
            self._temp_dict.update(tlm_data_copy)
            self._temp_dict['ts'] = time.ticks_ms()
            self._temp_dict['lpm'] = self.low_power_mode
            
            # Try single JSON
            try:
                full_json = json.dumps(self._temp_dict)
                if len(full_json) <= 200:
                    yield full_json.encode('utf-8')
                    return
            except MemoryError:
                yield b'{"err":"mem"}'
                return
            
            # Split into parts
            keys = list(self._temp_dict.keys())
            current_part = {}
            
            for key in keys:
                if self._check_memory_pressure():
                    break
                current_part[key] = self._temp_dict[key]
                test_json = json.dumps(current_part)
                if len(test_json) > 200 and len(current_part) > 1:
                    current_part.pop(key)
                    yield json.dumps(current_part).encode('utf-8')
                    current_part = {key: self._temp_dict[key]}
            
            if current_part:
                yield json.dumps(current_part).encode('utf-8')
                    
        except Exception:
            yield b'{"err":"gen"}'
        finally:
            if hasattr(self, '_temp_dict'):
                self._temp_dict.clear()
            gc.collect()
    
    async def _prepare_telemetry_async(self):
        """Memory-optimized async wrapper for telemetry preparation"""
        if self._check_memory_pressure():
            return b'{"mem":"low"}'
        
        # Check command response
        if self.command_flag and self.command_response:
            try:
                response_bytes = self.command_response.encode('utf-8')
                self.command_flag = False
                self.command_response = None
                return response_bytes
            except MemoryError:
                self.command_flag = False
                self.command_response = None
                return b'{"cmd":"mem_err"}'
        
        # Get telemetry
        try:
            async with self.telemetry_lock:
                if not self.telemetry_data:
                    return b'{}'
                tlm_data_copy = self.telemetry_data.copy()
            
            if not hasattr(self, '_tlm_generator') or self._tlm_generator is None:
                self._tlm_generator = self._prepare_telemetry_generator(tlm_data_copy)
            
            try:
                return next(self._tlm_generator)
            except StopIteration:
                self._tlm_generator = self._prepare_telemetry_generator(tlm_data_copy)
                try:
                    return next(self._tlm_generator)
                except StopIteration:
                    return b'{}'
                    
        except MemoryError:
            return b'{"tlm":"mem_err"}'
        except Exception:
            return b'{"tlm":"err"}'
    
    async def lora_tlm_task(self, interval=3):
        """Memory-optimized LoRa telemetry task using generator function"""
        last_telemetry_time = time.ticks_ms()
        
        while True:
            try:
                # Aggressive memory management
                gc.collect()
                
                # Check memory pressure and adapt behavior
                if self._check_memory_pressure():
                    print("LoRa task: memory pressure detected")
                    await asyncio.sleep_ms(2000)  # Wait longer when memory is low
                    continue
                
                current_time = time.ticks_ms()
                time_since_last_tlm = time.ticks_diff(current_time, last_telemetry_time)
                
                # Check if it's time to send telemetry or we have a command to send
                if time_since_last_tlm >= (interval * 1000) or self.command_flag:
                    target_addr = self.lora_address_to
                    ack_received = False
                    
                    # Get telemetry data using async generator
                    tlm_bytes = await self._prepare_telemetry_async()
                    
                    if tlm_bytes and len(tlm_bytes) > 2:  # More than just '{}'
                        try:
                            # Create packet with memory check
                            from manha.internals.comms.packet import Packet
                            packet = Packet(target_addr, self.lora_address_self, tlm_bytes)
                            
                            # Send packet using direct modem access
                            self.lora._modem.set_mode_idle()
                            if self.lora._modem.send(packet.encode()):
                                # Wait for TX_DONE
                                if await self._wait_tx_done():
                                    # Wait for ACK
                                    if await self._wait_for_simple_ack(2000):
                                        ack_received = True
                            
                            # Clear packet reference immediately
                            packet = None
                            
                        except MemoryError:
                            print("LoRa: packet creation failed - memory")
                            await self.blink_led_matrix(PixelColors.RED)
                    
                    if ack_received:
                        last_telemetry_time = current_time
                        self._packet_count += 1
                        if not self.low_power_mode:
                            await self.blink_led_matrix(PixelColors.GREEN)
                    else:
                        await self.blink_led_matrix(PixelColors.MAGENTA)
                    
                    # Clear variables and collect garbage after transmission
                    tlm_bytes = None
                    gc.collect()
                
                # Listen for commands with memory check
                if not self._check_memory_pressure():
                    await self._listen_for_commands(300)
                
                # Adaptive sleep based on memory pressure
                sleep_time = 1000 if self._check_memory_pressure() else 500
                await asyncio.sleep_ms(sleep_time)
                
            except MemoryError:
                print("LoRa task: memory allocation failed")
                gc.collect()  # Force cleanup
                await asyncio.sleep_ms(3000)  # Longer wait on memory error
            except Exception:
                print("LoRa task: general error")
                await asyncio.sleep_ms(1500)
    
    async def _wait_tx_done(self, timeout_ms=2000):
        """Wait for TX_DONE flag"""
        start_time = time.ticks_ms()
        while True:
            irq_flags = self.lora._modem._spi_read(0x12)  # REG_12_IRQ_FLAGS
            if irq_flags & 0x08:  # TX_DONE
                self.lora._modem.clear_irq_flags()
                return True
            if time.ticks_diff(time.ticks_ms(), start_time) > timeout_ms:
                return False
            await asyncio.sleep_ms(10)

    
    async def _wait_for_simple_ack(self, timeout_ms: int) -> bool:
        """Wait for ACK with minimal memory usage"""
        self.lora._modem.set_mode_rx()
        start_time = time.ticks_ms()
        
        while time.ticks_diff(time.ticks_ms(), start_time) < timeout_ms:
            if self.lora._modem._is_flag_set(0x40):  # RX_DONE
                recv_result = self.lora._modem.recv_data()
                if recv_result:
                    raw_data, _, _ = recv_result
                    # Quick check for ACK without full packet decode
                    if len(raw_data) >= 6 and raw_data[3:6] == b'ACK':
                        return True
                    # CMD also counts as ACK
                    elif len(raw_data) >= 6 and raw_data[3:6] == b'CMD':
                        return True
            await asyncio.sleep_ms(20)
        
        return False

    # Add proper cleanup method for graceful shutdown
    async def _shutdown(self):
        """Clean up resources before shutdown"""
        try:
            # Stop the LoRa receiver
            await self.lora.stop_receiver()
            # Set the LED matrix to indicate shutdown
            self.led_matrix.clear()
        except Exception as e:
            print(f"Error during shutdown: {e}")

    def run(self):
        # Aggressive memory cleanup before starting
        gc.collect()
        initial_memory = gc.mem_free()
        print(f"Starting MANHA - Free memory: {initial_memory}")
        
        # Check if we have enough memory to start
        if initial_memory < 40000:
            print("WARNING: Low memory at startup - expect issues")
        
        # Create tasks with staggered timing to reduce concurrent memory usage
        sensor_task = asyncio.create_task(self.read_sensors_task(3))  # Slower sensor reading
        lora_task = asyncio.create_task(self.lora_tlm_task(5))  # Slower telemetry rate
        
        try:
            asyncio.run(asyncio.gather(sensor_task, lora_task))
        except MemoryError:
            print("CRITICAL: Memory allocation failed in main tasks")
            self._shutdown()
        except Exception as e:
            print(f"Main task error: {e}")
            self._shutdown()