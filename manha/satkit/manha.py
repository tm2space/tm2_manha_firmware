"""TM2 MANHA Satellite Control System"""

import machine
import asyncio
import time
import gc
import json

from collections import namedtuple

from manha.utils import calculate_checksum

# Import core modules
from manha.satkit.peripherals import LEDMatrix, PixelColors
from manha.internals.drivers import (
    GPSParser,
    NeoGPS,
    ADXL345,
    BME680_I2C,
    INA219,
    UVS12SD,
)
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
        """Initialize the MANHA satellite control system

        Args:
            lora_address_to (int): LoRa address to send data to
            lora_address_self (int): LoRa address for this device
        """
        gc.collect()
        startup_memory = gc.mem_free()
        # print(f"MANHA init - Free memory: {startup_memory}")

        if startup_memory < 60000:
            # print("CRITICAL: Very low memory at startup")
            gc.collect()

        # Configuration
        self.lora_address_to = lora_address_to
        self.lora_address_self = lora_address_self

        self.essential_sensors = []
        self.non_essential_sensors = []
        self.low_power_mode = False
        self.power_threshold = LOW_POWER_THRESHOLD

        self.commands = {}

        gc.collect()
        if gc.mem_free() < 50000:
            # print("ERROR: Insufficient memory for initialization")
            raise MemoryError("Cannot initialize - insufficient memory")

        self.telemetry_lock = asyncio.Lock()
        self.telemetry_data = {}

        # Command handling flags
        self.command_flag = False
        self.command_response = None
        self._packet_count = 0
        self._tlm_generator = None

        self._temp_dict = {}  # Reusable dict for telemetry preparation
        self._seq_number = 0  # Packet sequence number (0-255)

        gc.collect()
        self.led = machine.Pin("LED", machine.Pin.OUT)

        i2c.init_i2c()
        gc.collect()

        self.led_matrix = LEDMatrix(8, 8, 3)
        self.led_matrix.fill(PixelColors.WHITE)
        gc.collect()

        if gc.mem_free() < 40000:
            # print("WARNING: Low memory before LoRa init")
            gc.collect()

        spi = machine.SPI(
            LORA_SPI_CHANNEL,
            baudrate=5_000_000,
            polarity=0,
            phase=0,
            sck=machine.Pin(LORA_SPI_SCK),
            mosi=machine.Pin(LORA_SPI_MOSI),
            miso=machine.Pin(LORA_SPI_MISO),
        )
        cs_pin = machine.Pin(LORA_SPI_CS, machine.Pin.OUT)
        gc.collect()

        self.lora = LoRa(
            device_id=self.lora_address_self,
            cs_pin=cs_pin,
            reset_pin=None,
            spi=spi,
            freq=868.0,
            tx_power=14,
            led_matrix=self.led_matrix,
        )

        print("LoRa Initialized")
        gc.collect()
        # final_memory = gc.mem_free()
        # print(f"MANHA init complete - Free memory: {final_memory}")

    async def cmd_lpm(self, command, from_address):
        """Handle LPM=<0/1> command - force low power mode"""
        try:
            # Extract LPM value from LPM=<0/1> format
            lpm_str = command.split("=")[1]
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
        # initial_memory = gc.mem_free()
        # print(f"Setting up sensors - Free memory: {initial_memory}")

        # Power Monitor function (essential) - using INA219 directly
        def read_power():
            try:
                if not hasattr(self, "_pwr_mon"):
                    from manha.satkit.peripherals import PowerMonitor

                    self._pwr_mon = PowerMonitor(
                        shunt_ohms=0.1, i2c=i2c.m_i2c, max_expected_amps=3.0
                    )
                pwr_rd = self._pwr_mon.read()
                return pwr_rd
            except Exception as e:
                return {"v_p": -1, "v_raw": -1}  # Default safe values

        # GPS function (essential) - using NeoGPS and GPSParser directly
        def read_gps():
            try:
                if not hasattr(self, "_gps_uart"):
                    self._gps_uart = NeoGPS()
                    self._gps_parser = GPSParser(location_formatting="dd")

                gps_data = self._gps_uart.read_gps()
                if gps_data:
                    for byte in gps_data:
                        self._gps_parser.update(chr(byte))

                lat = self._gps_parser.latitude
                lon = self._gps_parser.longitude
                return {
                    "lat": lat[0] if lat else 0.0,
                    "lng": lon[0] if lon else 0.0,
                    "alt": self._gps_parser.altitude,
                    "sats": self._gps_parser.satellites_in_use,
                }
            except Exception as e:
                return {"lat": 0.0, "lng": 0.0, "alt": 0, "sats": 0}

        # Add essential sensors
        try:
            self.add_sensor(read_power, essential=True)
            print("INA219 power monitor OK")
            gc.collect()
        except Exception as e:
            print(f"Power monitor failed: {e}")

        try:
            self.add_sensor(read_gps, essential=True)
            print("GPS UART OK")
            gc.collect()
        except Exception as e:
            print(f"GPS failed: {e}")

        # Only add non-essential if we have memory
        if gc.mem_free() > 40000:
            # IMU function - using ADXL345 directly
            def read_imu():
                try:
                    if not hasattr(self, "_adxl345"):
                        self._adxl345 = ADXL345(i2c=i2c.m_i2c)
                    return {
                        "a_x": self._adxl345.xValue,
                        "a_y": self._adxl345.yValue,
                        "a_z": self._adxl345.zValue,
                    }
                except:
                    return {"a_x": 0, "a_y": 0, "a_z": 0}

            def read_uv():
                try:
                    if not hasattr(self, "_uv_sensor"):
                        from manha.satkit.peripherals import UVSensor

                        self._uv_sensor = UVSensor()
                    return {"uv": self._uv_sensor.read()}
                except:
                    return {"uv": -1}

            # Environmental sensor - using BME680 directly
            def read_env():
                try:
                    if not hasattr(self, "_bme680"):
                        self._bme680 = BME680_I2C(i2c=i2c.m_i2c, address=0x77)
                    return {
                        "temp": self._bme680.temperature,
                        "pres": self._bme680.pressure,
                        "hum": self._bme680.humidity,
                    }
                except:
                    return {"temp": -1, "pres": -1, "hum": -1}

            try:
                self.add_sensor(read_imu, essential=False)
                print("ADXL345 IMU OK")
                gc.collect()
            except:
                print("IMU failed")

            try:
                self.add_sensor(read_uv, essential=False)
                print("UVS12SD UV Sensor OK")
                gc.collect()
            except:
                print("UVS12SD failed")

            try:
                self.add_sensor(read_env, essential=False)
                print("BME680 ENV OK")
                gc.collect()
            except:
                print("ENV failed")

        # HDRM setup (guarded by config flag)
        if ENABLE_HDRM:

            def read_hdrm():
                try:
                    if not hasattr(self, "_hdrm"):
                        from manha.satkit.peripherals import MHDRM

                        self._hdrm = MHDRM()
                    return self._hdrm.read()
                except:
                    return {"hdrm": -1}

            try:
                self.add_sensor(read_hdrm, essential=False)
                print("MHDRM OK")
                gc.collect()
            except:
                print("MHDRM failed")

        # final_memory = gc.mem_free()
        # print(f"Sensor setup complete - Free memory: {final_memory}")

    def add_sensor(self, sensor, essential: bool = False):
        """Add a sensor to the telemetry system

        Args:
            sensor: Function that returns sensor data dict OR object with read() method
            essential (bool): If True, sensor is always read (even in low-power mode)
        """
        # Memory check before adding sensor
        if gc.mem_free() < 25000:
            # print("Cannot add sensor - insufficient memory")
            return -1

        if essential:
            self.essential_sensors.append(sensor)
            return len(self.essential_sensors) - 1
        else:
            self.non_essential_sensors.append(sensor)
            return len(self.non_essential_sensors) - 1

    async def blink_led_matrix(self, color):
        """Briefly flash the LED matrix with a color. Suppressed in low-power mode."""
        if not self.low_power_mode:
            self.led_matrix.fill(color)
            await asyncio.sleep(0.05)
            self.led_matrix.clear()

    async def _listen_for_commands(self, listen_time_ms: int):
        """Listen for incoming LoRa commands for a given duration"""
        from manha.internals.comms.packet import Packet, MSG_CMD

        self.lora._modem.set_mode_rx()
        start_time = time.ticks_ms()

        while time.ticks_diff(time.ticks_ms(), start_time) < listen_time_ms:
            if self.lora._modem._is_flag_set(0x40):  # RX_DONE
                recv_result = self.lora._modem.recv_data()
                if recv_result:
                    raw_data, rssi, snr = recv_result
                    packet = Packet.decode(raw_data, rssi, snr)
                    if packet and packet.is_valid_checksum():
                        if USE_LEGACY_PACKETIZATION:
                            if packet.message.startswith(b"CMD:"):
                                command_bytes = packet.message[4:].strip()
                                await self._process_command_bytes(
                                    command_bytes, packet.addr_from
                                )
                        else:
                            if packet.msg_type == MSG_CMD:
                                command_bytes = packet.message.strip()
                                await self._process_command_bytes(
                                    command_bytes, packet.addr_from
                                )
                        return

            await asyncio.sleep_ms(10)

    async def _process_command_bytes(self, command_bytes: bytes, sender_addr: int):
        """Process a received command and queue a response for the next telemetry cycle"""
        try:
            # Visual indication of command reception
            self.led_matrix.fill(PixelColors.BLUE)
            await asyncio.sleep(0.1)
            self.led_matrix.clear()

            # Convert bytes to string for processing
            command = command_bytes.decode("utf-8")

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
                response = await self._handle_custom_command_with_response(
                    command, sender_addr
                )
                if response:
                    self.command_response = response
                    self.command_flag = True

        except Exception as e:
            print(f"Command processing error: {e}")

    async def _handle_custom_command_with_response(
        self, command: str, sender_addr: int
    ) -> str:
        """Handle custom commands and return response string"""
        try:
            if command.startswith("TXPOW="):
                # Extract power value from TXPOW=<v> format
                power_str = command.split("=")[1]
                power = int(power_str)

                if 5 <= power <= 23:
                    self.lora.set_tx_power(power)
                    return f"TX power set to {power}dBm"
                else:
                    return "TX power must be between 5 and 23dBm"

            elif command.startswith("LPM="):
                # Extract LPM value from LPM=<0/1> format
                lpm_str = command.split("=")[1]
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

            elif command.startswith("HDRM="):
                if not ENABLE_HDRM:
                    return "HDRM not enabled"
                hdrm_val = int(command.split("=")[1])
                if not hasattr(self, "_hdrm"):
                    from manha.satkit.peripherals import MHDRM

                    self._hdrm = MHDRM()
                if hdrm_val == 1:
                    self._hdrm.release()
                    return "HDRM released"
                elif hdrm_val == 0:
                    self._hdrm.hold()
                    return "HDRM held"
                else:
                    return "HDRM value must be 0 or 1"
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
            with open("/RMT_RESET", "w") as f:
                f.write(str(time.time()))
            machine.reset()
        except:
            machine.reset()

    async def _send_response_direct(self, response: str, target_addr: int):
        """Send command response using direct modem access"""
        try:
            from manha.internals.comms.packet import Packet, MSG_CMD_RESP

            if USE_LEGACY_PACKETIZATION:
                message = f"CMD:{response}\r\n".encode("utf-8")
                packet = Packet(target_addr, self.lora_address_self, message)
            else:
                message = response.encode("utf-8")
                packet = Packet(
                    target_addr, self.lora_address_self, message, msg_type=MSG_CMD_RESP
                )

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
        self._sensor_read_interval = LOW_POWER_TELEMETRY_INTERVAL_MS

        await self.blink_led_matrix(PixelColors.YELLOW)
        self.low_power_mode = True

    async def exit_low_power_mode(self):
        """Exit Low Power Mode"""
        print("EXITING LOW POWER MODE")
        self.low_power_mode = False
        self._sensor_read_interval = TELEMETRY_INTERVAL_MS

        await self.blink_led_matrix(PixelColors.MAGENTA)

    async def read_sensors_task(self, interval: int = 1):
        """Task to periodically read all sensors

        Args:
            interval (int): Time in milliseconds between sensor readings
        """
        self._sensor_read_interval = interval

        while True:
            try:
                gc.collect()

                await asyncio.sleep_ms(self._sensor_read_interval)

                temp_telemetry = {}

                # Read essential sensors
                for i, sensor in enumerate(self.essential_sensors):
                    try:
                        data = None
                        if callable(sensor):
                            data = sensor()
                        elif hasattr(sensor, "read"):
                            data = sensor.read()

                        if data:
                            if "v_p" in data:
                                if (
                                    data["v_p"] < self.power_threshold
                                    and not self.low_power_mode
                                ):
                                    await self.enter_low_power_mode()
                                elif (
                                    self.low_power_mode
                                    and data["v_p"] >= self.power_threshold
                                ):
                                    await self.exit_low_power_mode()

                            temp_telemetry.update(data)
                            data = None

                    except Exception:
                        print(f"Sensor error: essential {i}")

                # Read non-essential sensors if not in low power mode
                if not self.low_power_mode:
                    for i, sensor in enumerate(self.non_essential_sensors):
                        try:
                            data = None
                            if callable(sensor):
                                data = sensor()
                            elif hasattr(sensor, "read"):
                                data = sensor.read()

                            if data:
                                temp_telemetry.update(data)
                                data = None

                        except Exception:
                            print(f"Sensor error: non-essential {i}")

                # Update global telemetry dict
                if temp_telemetry:
                    async with self.telemetry_lock:
                        self.telemetry_data.update(temp_telemetry)
                    temp_telemetry.clear()

            except Exception:
                print("Sensor task error")
                if not self.low_power_mode:
                    await self.blink_led_matrix(PixelColors.RED)
                await asyncio.sleep_ms(2000)

    def _prepare_telemetry_generator(self, tlm_data_copy):
        """Generator that yields telemetry as one or more chunks of <= 200 bytes"""
        try:
            # Reuse temp dict
            self._temp_dict.clear()
            self._temp_dict.update(tlm_data_copy)
            self._temp_dict["ts"] = time.ticks_ms()
            self._temp_dict["lpm"] = self.low_power_mode

            # Try single JSON
            try:
                full_json = json.dumps(self._temp_dict)
                if len(full_json) <= 200:
                    yield full_json.encode("utf-8")
                    return
            except MemoryError:
                yield b'{"err":"mem"}'
                return

            # Split into parts if > 200 bytes
            keys = list(self._temp_dict.keys())
            current_part = {}

            for key in keys:
                current_part[key] = self._temp_dict[key]
                test_json = json.dumps(current_part)
                if len(test_json) > 200 and len(current_part) > 1:
                    current_part.pop(key)
                    yield json.dumps(current_part).encode("utf-8")
                    current_part = {key: self._temp_dict[key]}

            if current_part:
                yield json.dumps(current_part).encode("utf-8")

        except Exception:
            yield b'{"err":"gen"}'
        finally:
            if hasattr(self, "_temp_dict"):
                self._temp_dict.clear()

    async def _prepare_telemetry_async(self):
        """Prepare telemetry payload, including any pending command response

        Returns:
            tuple: (bytes, msg_type) where msg_type is used for binary packet header
        """
        from manha.internals.comms.packet import MSG_TLM, MSG_CMD_RESP

        # Check command response
        if self.command_flag and self.command_response:
            try:
                response_bytes = self.command_response.encode("utf-8")
                self.command_flag = False
                self.command_response = None
                return response_bytes, MSG_CMD_RESP
            except MemoryError:
                self.command_flag = False
                self.command_response = None
                return b'{"cmd":"mem_err"}', MSG_CMD_RESP

        # Get telemetry
        try:
            async with self.telemetry_lock:
                if not self.telemetry_data:
                    if USE_LEGACY_PACKETIZATION:
                        return b"{}", MSG_TLM
                    return None, MSG_TLM
                tlm_data_copy = self.telemetry_data.copy()

            if USE_LEGACY_PACKETIZATION:
                # Legacy JSON path
                if not hasattr(self, "_tlm_generator") or self._tlm_generator is None:
                    self._tlm_generator = self._prepare_telemetry_generator(
                        tlm_data_copy
                    )
                try:
                    return next(self._tlm_generator), MSG_TLM
                except StopIteration:
                    self._tlm_generator = self._prepare_telemetry_generator(
                        tlm_data_copy
                    )
                    try:
                        return next(self._tlm_generator), MSG_TLM
                    except StopIteration:
                        return b"{}", MSG_TLM
            else:
                # Binary protocol path
                from manha.internals.comms.binary_tlm import encode_tlm

                tlm_bytes = encode_tlm(
                    tlm_data_copy,
                    self._seq_number,
                    self.low_power_mode,
                    time.ticks_ms(),
                )
                self._seq_number = (self._seq_number + 1) & 0xFF
                return tlm_bytes, MSG_TLM

        except MemoryError:
            if USE_LEGACY_PACKETIZATION:
                return b'{"tlm":"mem_err"}', MSG_TLM
            return None, MSG_TLM
        except Exception:
            if USE_LEGACY_PACKETIZATION:
                return b'{"tlm":"err"}', MSG_TLM
            return None, MSG_TLM

    async def lora_tlm_task(self, interval=3):
        """Async task that transmits telemetry over LoRa and listens for commands"""
        last_telemetry_time = time.ticks_ms()

        while True:
            try:
                gc.collect()

                current_time = time.ticks_ms()
                time_since_last_tlm = time.ticks_diff(current_time, last_telemetry_time)

                if (
                    time_since_last_tlm >= self._sensor_read_interval
                    or self.command_flag
                ):
                    target_addr = self.lora_address_to
                    ack_received = False

                    tlm_bytes, msg_type = await self._prepare_telemetry_async()

                    if tlm_bytes and len(tlm_bytes) > 2:
                        try:
                            from manha.internals.comms.packet import Packet

                            packet = Packet(
                                target_addr,
                                self.lora_address_self,
                                tlm_bytes,
                                msg_type=msg_type,
                            )

                            self.lora._modem.set_mode_idle()
                            if self.lora._modem.send(packet.encode()):
                                if await self._wait_tx_done():
                                    if await self._wait_for_simple_ack(300):
                                        ack_received = True

                            packet = None

                        except MemoryError:
                            await self.blink_led_matrix(PixelColors.RED)

                    last_telemetry_time = current_time
                    if ack_received:
                        self._packet_count += 1
                        if not self.low_power_mode:
                            await self.blink_led_matrix(PixelColors.GREEN)
                    else:
                        await self.blink_led_matrix(PixelColors.MAGENTA)

                    tlm_bytes = None
                    gc.collect()

                await self._listen_for_commands(100)

                await asyncio.sleep_ms(50)

            except MemoryError:
                # print("LoRa task: memory allocation failed")
                gc.collect()
                await asyncio.sleep_ms(3000)
            except Exception:
                print("LoRa task: general error")
                await asyncio.sleep_ms(1500)

    async def _wait_tx_done(self, timeout_ms=500):
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
        """Wait for ACK packet"""
        from manha.internals.comms.packet import MSG_ACK

        self.lora._modem.set_mode_rx()
        start_time = time.ticks_ms()

        while time.ticks_diff(time.ticks_ms(), start_time) < timeout_ms:
            if self.lora._modem._is_flag_set(0x40):  # RX_DONE
                recv_result = self.lora._modem.recv_data()
                if recv_result:
                    raw_data, _, _ = recv_result
                    if USE_LEGACY_PACKETIZATION:
                        # Legacy: check for ACK/CMD text at byte offset 3
                        if len(raw_data) >= 6 and raw_data[3:6] == b"ACK":
                            return True
                        elif len(raw_data) >= 6 and raw_data[3:6] == b"CMD":
                            return True
                    else:
                        # Binary: check msg_type byte at offset 2
                        if len(raw_data) >= 4 and raw_data[2] == MSG_ACK:
                            return True
            await asyncio.sleep_ms(20)

        return False

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
        """Start the sensor and telemetry tasks"""
        gc.collect()
        # initial_memory = gc.mem_free()
        # print(f"Starting MANHA - Free memory: {initial_memory}")

        # if initial_memory < 40000:
        #     print("WARNING: Low memory at startup - expect issues")

        sensor_task = asyncio.create_task(self.read_sensors_task(TELEMETRY_INTERVAL_MS))
        lora_task = asyncio.create_task(self.lora_tlm_task(TELEMETRY_INTERVAL_MS))

        try:
            asyncio.run(asyncio.gather(sensor_task, lora_task))
        except MemoryError:
            # print("CRITICAL: Memory allocation failed in main tasks")
            self._shutdown()
        except Exception as e:
            print(f"Main task error: {e}")
            self._shutdown()
