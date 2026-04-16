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
from . import i2c, uart, gpio

from manha.config import *
from .constants import *


class MANHA:
    @property
    def i2c(self):
        """Get I2C Instance"""
        return i2c.m_i2c

    @property
    def uart0(self):
        """Get UART0 Instance"""
        return uart.m_uart0

    @property
    def gp1(self):
        """Get GP1 pin number"""
        return gpio.GP1_PIN

    @property
    def gp2(self):
        """Get GP2 pin number"""
        return gpio.GP2_PIN

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
        self._setup_default_commands()

        gc.collect()
        if gc.mem_free() < 50000:
            # print("ERROR: Insufficient memory for initialization")
            raise MemoryError("Cannot initialize - insufficient memory")

        self.telemetry_lock = asyncio.Lock()
        self.telemetry_data = {}

        # Command handling flags

        self._packet_count = 0
        self._tlm_generator = None

        self._temp_dict = {}  # Reusable dict for telemetry preparation
        self._seq_number = 0  # Packet sequence number (0-255)

        gc.collect()
        self.led = machine.Pin("LED", machine.Pin.OUT)

        i2c.init_i2c()
        uart.init_uart()
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

    def _setup_default_commands(self):
        """Register built-in command handlers"""
        self.add_command("PING", self._cmd_ping)
        self.add_command("RESET", self._cmd_reset)
        self.add_command("TXPOW", self._cmd_txpow)
        self.add_command("LPM", self._cmd_lpm)
        self.add_command("HDRM", self._cmd_hdrm)
        self.add_command("CAM", self._cmd_cam)
        self.add_command("CAMSET", self._cmd_camset)
        self.add_command("CAMGET", self._cmd_camget)
        self.add_command("WEBUI", self._cmd_webui)

    def _cmd_ping(self, command, sender_addr):
        """Handle PING command"""
        return "PONG"

    def _cmd_reset(self, command, sender_addr):
        """Handle RESET command - schedule device reset"""
        asyncio.create_task(self._delayed_reset())
        return "RESET_ACK"

    def _cmd_txpow(self, command, sender_addr):
        """Handle TXPOW=<value> command - set LoRa TX power"""
        try:
            power_str = command.split("=")[1]
            power = int(power_str)
            if 5 <= power <= 23:
                self.lora.set_tx_power(power)
                return f"TX power set to {power}dBm"
            else:
                return "TX power must be between 5 and 23dBm"
        except (IndexError, ValueError) as e:
            return f"Command format error: {e}"

    async def _cmd_lpm(self, command, sender_addr):
        """Handle LPM=<0/1> command - force low power mode"""
        try:
            lpm_str = command.split("=")[1]
            lpm_value = int(lpm_str)
            if lpm_value == 1:
                if not self.low_power_mode:
                    await self.enter_low_power_mode()
                return "Low power mode enabled"
            elif lpm_value == 0:
                if self.low_power_mode:
                    await self.exit_low_power_mode()
                return "Low power mode disabled"
            else:
                return "LPM value must be 0 or 1"
        except (IndexError, ValueError):
            return "Invalid LPM command format. Use LPM=<0/1>"

    def _cmd_hdrm(self, command, sender_addr):
        """Handle HDRM=<0/1> command - hold/release mechanism"""
        try:
            if not ENABLE_HDRM:
                return "HDRM not enabled"
            hdrm_val = int(command.split("=")[1])
            if not hasattr(self, "_hdrm"):
                from manha.satkit.peripherals import MHDRM

                self._hdrm = MHDRM(self.gp1)
            if hdrm_val == 1:
                self._hdrm.release()
                return "HDRM released"
            elif hdrm_val == 0:
                self._hdrm.hold()
                return "HDRM held"
            else:
                return "HDRM value must be 0 or 1"
        except (IndexError, ValueError) as e:
            return f"Command format error: {e}"

    def _cmd_cam(self, command, sender_addr):
        """Handle CAM=<0/1> command - 1=capture, 0=status"""
        try:
            if not ENABLE_CAM:
                return "CAM not enabled"
            val = int(command.split("=")[1])
            if not hasattr(self, "_cam"):
                from manha.satkit.peripherals import ManhaCam

                self._cam = ManhaCam(self.uart0)
            if val == 1:
                fname, err = self._cam.capture()
                return f"CAM:{fname}" if fname else f"CAM:FAIL({err})"
            else:
                data = self._cam.read()
                if "error" in data:
                    return f"CAM:FAIL({data['error']})"
                return f"CAM:count={data['cam_count']}"
        except (IndexError, ValueError) as e:
            return f"Command format error: {e}"

    def _cmd_camset(self, command, sender_addr):
        """Handle CAMSET=02:0A,14:01 command - set camera settings via hex key:value pairs"""
        try:
            if not ENABLE_CAM:
                return "CAM not enabled"
            if not hasattr(self, "_cam"):
                from manha.satkit.peripherals import ManhaCam

                self._cam = ManhaCam(self.uart0)
            # Parse hex key:value pairs from command
            # Format: CAMSET=02:0A,14:01
            pairs = command.split("=")[1].split(",")
            raw = b""
            for pair in pairs:
                k, v = pair.split(":")
                raw += bytes([int(k, 16), int(v, 16)])
            resp = self._cam.configure_remote(raw)
            return f"CAMSET:{resp}" if resp else "CAMSET:FAIL"
        except (IndexError, ValueError) as e:
            return f"Command format error: {e}"

    def _cmd_camget(self, command, sender_addr):
        """Handle CAMGET command - read all camera settings as hex key:value pairs"""
        try:
            if not ENABLE_CAM:
                return "CAM not enabled"
            if not hasattr(self, "_cam"):
                from manha.satkit.peripherals import ManhaCam

                self._cam = ManhaCam(self.uart0)
            raw = self._cam.read_settings()
            if raw is None or len(raw) < 2:
                return "CAMGET:FAIL"
            # Format raw bytes as hex key:value pairs (truncate to even length)
            count = len(raw) // 2
            pairs = []
            for i in range(count):
                pairs.append(f"{raw[i * 2]:02X}:{raw[i * 2 + 1]:02X}")
            return "CAMGET:" + ",".join(pairs)
        except Exception as e:
            return f"Command format error: {e}"

    def _cmd_webui(self, command, sender_addr):
        """Handle WEBUI=<0/1> command - toggle ESP32-CAM WiFi AP + HTTP server"""
        try:
            if not ENABLE_CAM:
                return "CAM not enabled"
            val = int(command.split("=")[1])
            if not hasattr(self, "_cam"):
                from manha.satkit.peripherals import ManhaCam
                self._cam = ManhaCam(self.uart0)
            if val == 1:
                return self._cam.webui_on()
            else:
                return self._cam.webui_off()
        except (IndexError, ValueError) as e:
            return f"Command format error: {e}"

    def add_command(self, command_name: str, callback) -> None:
        """Add a new command to the command registry.

        Args:
            command_name: The name of the command (string)
            callback: The function to call when the command is received.
                      Can be sync or async — dispatch auto-detects.
        """
        self.commands[command_name] = (callback, False)

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
                    return self._uv_sensor.read()
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

                        self._hdrm = MHDRM(self.gp1)
                    return self._hdrm.read()
                except:
                    return {"hdrm": -1}

            try:
                self.add_sensor(read_hdrm, essential=False)
                print("MHDRM OK")
                gc.collect()
            except:
                print("MHDRM failed")

        # Camera setup (guarded by config flag)
        if ENABLE_CAM:
            try:
                from manha.satkit.peripherals import ManhaCam

                self._cam = ManhaCam(self.uart0)
                print(f"ManhaCam: {self._cam.probe()}")

                def read_cam():
                    try:
                        return self._cam.read()
                    except Exception as e:
                        return {"cam_count": -1, "error": str(e)}

                self.add_sensor(read_cam, essential=False)
                gc.collect()
            except Exception as e:
                print(f"ManhaCam failed: {e}")

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
        from manha.internals.comms.packet import Packet, MSG_TC

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
                            if packet.msg_type == MSG_TC:
                                command_bytes = packet.message.strip()
                                await self._process_command_bytes(
                                    command_bytes, packet.addr_from
                                )
                        # Resume RX after processing (TC_ACK TX switches to Standby)
                        self.lora._modem.set_mode_rx()

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

            # Look up command handler from registry
            cmd_key = command.split("=")[0] if "=" in command else command

            if cmd_key in self.commands:
                handler, _ = self.commands[cmd_key]
                result = handler(command, sender_addr)
                # async def returns a coroutine — await it
                if hasattr(result, 'send'):
                    response = await result
                else:
                    response = result
            else:
                response = f"Unknown command: {command}"

            if response:
                await self._send_response_direct(response, sender_addr)

        except Exception as e:
            print(f"Command processing error: {e}")

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
            from manha.internals.comms.packet import Packet, MSG_TC_ACK

            if USE_LEGACY_PACKETIZATION:
                message = f"CMD:{response}\r\n".encode("utf-8")
                packet = Packet(target_addr, self.lora_address_self, message)
            else:
                message = response.encode("utf-8")
                packet = Packet(
                    target_addr, self.lora_address_self, message, msg_type=MSG_TC_ACK
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

                # Keep ESP32-CAM watchdog alive even in LPM
                if ENABLE_CAM and self.low_power_mode and hasattr(self, "_cam"):
                    if self._cam.needs_keepalive:
                        self._cam.keepalive()

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

    def _log_tx(self, data):
        """Log transmitted packet to console and/or file if enabled."""
        msg = (
            ",".join(str(v) for v in data.values())
            if isinstance(data, dict)
            else str(data)
        )
        if SATKIT_LOG_TELEMETRY_TO_CONSOLE:
            print(msg)
        if SATKIT_LOG_TELEMETRY_TO_FILE:
            try:
                with open(SATKIT_LOG_TELEMETRY_TO_FILE, "a") as f:
                    f.write(msg + "\n")
            except Exception:
                pass

    async def _prepare_telemetry_async(self):
        """Prepare telemetry payload

        Returns:
            tuple: (bytes, msg_type) where msg_type is used for binary packet header
        """
        from manha.internals.comms.packet import MSG_TM

        # Get telemetry
        try:
            async with self.telemetry_lock:
                if not self.telemetry_data:
                    if USE_LEGACY_PACKETIZATION:
                        return b"{}", MSG_TM
                    return None, MSG_TM
                tlm_data_copy = self.telemetry_data.copy()

            self._log_tx(tlm_data_copy)

            if USE_LEGACY_PACKETIZATION:
                # Legacy JSON path
                if not hasattr(self, "_tlm_generator") or self._tlm_generator is None:
                    self._tlm_generator = self._prepare_telemetry_generator(
                        tlm_data_copy
                    )
                try:
                    return next(self._tlm_generator), MSG_TM
                except StopIteration:
                    self._tlm_generator = self._prepare_telemetry_generator(
                        tlm_data_copy
                    )
                    try:
                        return next(self._tlm_generator), MSG_TM
                    except StopIteration:
                        return b"{}", MSG_TM
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
                return tlm_bytes, MSG_TM

        except MemoryError:
            if USE_LEGACY_PACKETIZATION:
                return b'{"tlm":"mem_err"}', MSG_TM
            return None, MSG_TM
        except Exception as e:
            print(f"TLM prepare error: {e}")
            if USE_LEGACY_PACKETIZATION:
                return b'{"tlm":"err"}', MSG_TM
            return None, MSG_TM

    async def lora_tlm_task(self, interval=3):
        """Async task that transmits telemetry over LoRa and listens for commands"""
        last_telemetry_time = time.ticks_ms()

        while True:
            try:
                gc.collect()

                current_time = time.ticks_ms()
                time_since_last_tlm = time.ticks_diff(current_time, last_telemetry_time)

                if time_since_last_tlm >= self._sensor_read_interval:
                    target_addr = self.lora_address_to

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
                                    self._packet_count += 1
                                    if not self.low_power_mode:
                                        await self.blink_led_matrix(PixelColors.GREEN)
                                else:
                                    await self.blink_led_matrix(PixelColors.MAGENTA)

                            packet = None

                        except MemoryError:
                            await self.blink_led_matrix(PixelColors.RED)

                    last_telemetry_time = current_time
                    tlm_bytes = None
                    gc.collect()

                # Listen for commands for remaining time in TM interval
                elapsed = time.ticks_diff(time.ticks_ms(), last_telemetry_time)
                listen_time = max(MIN_CMD_LISTEN_MS, self._sensor_read_interval - elapsed - 50)
                await self._listen_for_commands(listen_time)

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
