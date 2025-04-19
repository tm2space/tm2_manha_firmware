import time
import math
from collections import namedtuple
from machine import SPI, Pin

from .rfm9x_constants import *


class ModemConfig:
    Bw125Cr45Sf128 = (
        0x72,
        0x74,
        0x04,
    )  # < Bw = 125 kHz, Cr = 4/5, Sf = 128chips/symbol, CRC on. Default medium range
    Bw500Cr45Sf128 = (
        0x92,
        0x74,
        0x04,
    )  # < Bw = 500 kHz, Cr = 4/5, Sf = 128chips/symbol, CRC on. Fast+short range
    Bw31_25Cr48Sf512 = (
        0x48,
        0x94,
        0x04,
    )  # < Bw = 31.25 kHz, Cr = 4/8, Sf = 512chips/symbol, CRC on. Slow+long range
    Bw125Cr48Sf4096 = (
        0x78,
        0xC4,
        0x0C,
    )  # /< Bw = 125 kHz, Cr = 4/8, Sf = 4096chips/symbol, low data rate, CRC on. Slow+long range
    Bw125Cr45Sf2048 = (
        0x72,
        0xB4,
        0x04,
    )  # < Bw = 125 kHz, Cr = 4/5, Sf = 2048chips/symbol, CRC on. Slow+long range


class RFM9x(object):
    def __init__(
        self,
        id: int,
        cs: Pin,
        spi: SPI,
        reset: Pin,
        modem_config: tuple = ModemConfig.Bw125Cr45Sf128,
        band: str = None,
        channel: int = None,
        freq: float = 868.0,
        tx_power: int = 14,
        timeout_ms: int = 500,
    ) -> None:
        """
        Initialize RM95/96/97 radio
        cs: chip select pin
        spi: SPI object to use
        reset: reset pin
        modem_config: ModemConfig object to use
        band: frequency band
        channel: channel setting for use with band
        freq: frequency in MHz
        tx_power: transmit power in dBm
        modem_config: Check ModemConfig. Default is compatible with the Radiohead library
        timeout_ms: timeout in milliseconds for operations
        """

        # Set ID for the LoRa object
        self._id = id

        # Store SPI and pins for later use
        self._cs = cs
        self._spi = spi
        self._reset = reset
        self._timeout = timeout_ms

        # Setup reset pin
        self.reset_pin = reset
        # send reset pulse
        self.set_reset(0)
        time.sleep_ms(100)
        self.set_reset(1)
        time.sleep_ms(100)  # Increased reset recovery time

        if band is not None and channel is not None:
            self._freq = LORA_CHAN_FREQ_LUT[band][channel]
        else:
            self._freq = freq

        self._cs_pin = cs
        self._mode = None
        self._modem_config = modem_config

        # Setup the module
        self.cs = cs
        self.cs.value(1)

        # baud rate to 5MHz
        self.spi = spi

        # Print version with timeout protection
        version = self._spi_read(REG_42_VERSION)
        print(f"LoRa chip version: {version:#02x}")

        # set mode with timeout protection
        self._spi_write(REG_01_OP_MODE, MODE_SLEEP)
        time.sleep(0.1)

        self._spi_write(REG_01_OP_MODE, LONG_RANGE_MODE)
        time.sleep(0.1)

        # check if mode is set
        lor_r1 = self._spi_read(REG_01_OP_MODE)
        if lor_r1 != (MODE_SLEEP | LONG_RANGE_MODE):
            print(
                f"Failed LoRa mode check: got {lor_r1}, expected {MODE_SLEEP | LONG_RANGE_MODE}"
            )
            raise ValueError("LoRa initialization failed - mode setting")

        self._spi_write(REG_0E_FIFO_TX_BASE_ADDR, 0)
        self._spi_write(REG_0F_FIFO_RX_BASE_ADDR, 0)

        self.set_mode_idle()

        # set modem config
        self._spi_write(REG_1D_MODEM_CONFIG1, self._modem_config[0])
        self._spi_write(REG_1E_MODEM_CONFIG2, self._modem_config[1])
        self._spi_write(REG_26_MODEM_CONFIG3, self._modem_config[2])

        # set preamble length (8)
        self._spi_write(REG_20_PREAMBLE_MSB, 0)
        self._spi_write(REG_21_PREAMBLE_LSB, 8)

        # set frequency
        frf = int((self._freq * 1000000.0) / FSTEP)
        self._spi_write(REG_06_FRF_MSB, (frf >> 16) & 0xFF)
        self._spi_write(REG_07_FRF_MID, (frf >> 8) & 0xFF)
        self._spi_write(REG_08_FRF_LSB, frf & 0xFF)

        # Set tx power
        self.set_tx_power(tx_power)

    def reset(self):
        """
        Reset the RFM9x radio module
        """
        self.set_reset(0)
        time.sleep_ms(100)
        self.set_reset(1)
        time.sleep_ms(100)

    def set_reset(self, level: int) -> None:
        """Set the reset pin level

        Args:
            level: 1 for high (normal operation), 0 for low (reset)
        """
        if level:
            self.reset_pin.on()
        else:
            self.reset_pin.off()

    def sleep(self) -> None:
        """Put the radio into sleep mode

        Configures the radio to enter sleep mode, which significantly reduces
        power consumption when the radio is not actively transmitting or receiving.
        """
        if self._mode != MODE_SLEEP:
            self._spi_write(REG_01_OP_MODE, MODE_SLEEP)
            self._mode = MODE_SLEEP

    def set_mode_tx(self) -> None:
        """Set the radio to transmission mode

        Configures the radio for packet transmission. Call this before
        sending data if the radio is not already in TX mode.
        """
        if self._mode != MODE_TX:
            self._spi_write(REG_01_OP_MODE, MODE_TX)
            self._mode = MODE_TX

    def set_mode_rx(self) -> None:
        """Set the radio to continuous reception mode

        Configures the radio for continuous packet reception. In this mode,
        the radio will continuously listen for incoming LoRa packets.
        """
        if self._mode != MODE_RXCONTINUOUS:
            self._spi_write(REG_01_OP_MODE, MODE_RXCONTINUOUS)
            self._mode = MODE_RXCONTINUOUS

    def set_mode_idle(self) -> None:
        """Set the radio to idle (standby) mode

        Configures the radio for standby operation, which reduces power consumption
        compared to active modes but allows for faster transition to TX or RX modes
        compared to sleep mode.
        """
        if self._mode != MODE_STDBY:
            self._spi_write(REG_01_OP_MODE, MODE_STDBY)
            self._mode = MODE_STDBY

    def set_mode_cad(self) -> None:
        """Set radio into CAD (Channel Activity Detection) mode"""
        if self._mode != MODE_CAD:
            self._spi_write(REG_01_OP_MODE, MODE_CAD)
            self._mode = MODE_CAD

    def set_tx_power(self, tx_power: int, dac: bool = None) -> None:
        """Set the transmission power of the radio

        Args:
            tx_power: Power in dBm (range 5-23)
            dac: Boolean to enable or disable PA_DAC

        Note:
            Values less than 5 dBm will be set to 5 dBm.
            Values greater than 23 dBm will be set to 23 dBm.
            For power values below 20 dBm, the PA_DAC register is enabled.
        """

        if tx_power < 5:
            tx_power = 5
        if tx_power > 23:
            tx_power = 23

        if tx_power < 20 or (dac is not None and dac):
            self._spi_write(REG_4D_PA_DAC, PA_DAC_ENABLE)
            tx_power -= 3
        else:
            self._spi_write(REG_4D_PA_DAC, PA_DAC_DISABLE)

        self._spi_write(REG_09_PA_CONFIG, PA_SELECT | (tx_power - 5))
        self._tx_power = tx_power

    def send(self, data: bytes) -> bool:
        """Send raw bytes data packet
        
        Args:
            data: Raw bytes data to be transmitted
            
        Returns:
            bool: True if data was successfully queued for transmission
        """
        self.set_mode_idle()

        # Convert data to list of bytes if not already
        if isinstance(data, bytes):
            data_bytes = [b for b in data]
        elif isinstance(data, list):
            data_bytes = [int(b) for b in data]
        elif isinstance(data, int):
            data_bytes = [data]
        elif isinstance(data, str):
            data_bytes = [ord(s) for s in data]
        else:
            print("Invalid data type")
            return False

        self._spi_write(REG_0D_FIFO_ADDR_PTR, 0)
        self._spi_write(REG_00_FIFO, data_bytes)
        self._spi_write(REG_22_PAYLOAD_LENGTH, len(data_bytes))

        self.set_mode_tx()
        return True

    def recv_data(self) -> tuple:
        """Receive data packet with RSSI and SNR information
        
        Returns:
            tuple: Contains (bytes, rssi, snr)
                - bytes: Raw received payload data
                - rssi: Received signal strength indicator
                - snr: Signal-to-noise ratio
                
            Returns None if no data is received
        """
        self.set_mode_rx()

        while True:
            irq_flags = self._spi_read(REG_12_IRQ_FLAGS)

            if irq_flags & RX_DONE:
                packet_len = self._spi_read(REG_13_RX_NB_BYTES)
                self._spi_write(
                    REG_0D_FIFO_ADDR_PTR, self._spi_read(REG_10_FIFO_RX_CURRENT_ADDR)
                )

                packet = self._spi_read(REG_00_FIFO, packet_len)
                self._spi_write(REG_12_IRQ_FLAGS, 0xFF)  # Clear all IRQ flags

                snr = self._spi_read(REG_19_PKT_SNR_VALUE) / 4
                rssi = self._spi_read(REG_1A_PKT_RSSI_VALUE)

                if snr < 0:
                    rssi = snr + rssi
                else:
                    rssi = rssi * 16 / 15

                if self._freq >= 779:
                    rssi = round(rssi - 157, 2)
                else:
                    rssi = round(rssi - 164, 2)

                # Return a tuple with raw bytes, rssi, and snr
                return bytes(packet), rssi, snr

    def is_channel_active(self) -> bool:
        """Check if the channel is currently active using CAD
        Returns: True if channel activity detected, False otherwise
        """
        self.set_mode_cad()

        irq_flags = self.wait_cad_done()

        return bool(irq_flags & CAD_DETECTED)

    def _is_flag_set(self, flag: int) -> bool:
        """Check if a specific flag is set in the IRQ register

        Args:
            flag: Flag bit to check

        Returns:
            bool: True if the flag is set, False otherwise
        """
        return bool(self._spi_read(REG_12_IRQ_FLAGS) & flag)

    def _wait_flag_set(self, flag: int, timeout: int = None) -> tuple:
        """Wait for a flag to be set in the IRQ register

        Args:
            flag: Flag bit to wait for
            timeout: Maximum time to wait (milliseconds), default increased to 500ms

        Returns:
            tuple: A tuple containing a boolean indicating success and the IRQ flags
        """
        if timeout is None:
            timeout = self._timeout

        start = time.ticks_ms()
        while not ((irq_flags := self._spi_read(REG_12_IRQ_FLAGS)) & flag):
            if time.ticks_diff(time.ticks_ms(), start) > timeout:
                return (False, irq_flags)
            time.sleep_ms(2)  # Increased delay to reduce CPU usage
        self._spi_write(REG_12_IRQ_FLAGS, flag)  # Clear the flag
        return (True, irq_flags)

    def wait_tx_done(self, timeout=None) -> int:
        """Wait for the transmission to complete

        Args:
            timeout: Maximum time to wait for transmission to complete (in milliseconds)

        Returns:
            int: The IRQ flags after waiting
        """
        if timeout is None:
            timeout = self._timeout

        irq_flags = self._wait_flag_set(TX_DONE, timeout)[1]

        self.clear_irq_flags()

        return irq_flags

    def wait_rx_done(self, timeout=None) -> int:
        """Wait for the reception to complete

        Args:
            timeout: Maximum time to wait for reception to complete (in milliseconds)

        Returns:
            int: The IRQ flags after waiting
        """
        if timeout is None:
            timeout = self._timeout

        irq_flags = self._wait_flag_set(RX_DONE, timeout)[1]

        self.clear_irq_flags()

        return irq_flags

    def wait_cad_done(self, timeout=None) -> int:
        """Wait for CAD to complete

        Args:
            timeout: Maximum time to wait for CAD to complete (in milliseconds)

        Returns:
            int: The IRQ flags after waiting
        """
        if timeout is None:
            timeout = self._timeout

        irq_flags = self._wait_flag_set(CAD_DONE, timeout)[1]

        self.clear_irq_flags()

        return irq_flags

    def clear_irq_flags(self) -> None:
        """Clear all IRQ flags"""
        self._spi_write(REG_12_IRQ_FLAGS, 0xFF)

    def _spi_write(self, register: int, payload) -> None:
        """Write data to a register over SPI

        Args:
            register: Register address to write to
            payload: Data to write (int, bytes, or string)
        """
        if type(payload) == int:
            payload = [payload]
        elif type(payload) == bytes:
            payload = [p for p in payload]
        elif type(payload) == str:
            payload = [ord(s) for s in payload]

        self.cs.value(0)
        self.spi.write(bytearray([register | 0x80] + payload))
        self.cs.value(1)

    def _spi_read(self, register: int, length: int = 1):
        """Read data from a register over SPI

        Args:
            register: Register address to read from
            length: Number of bytes to read (default: 1)

        Returns:
            Data read from the register (int for single byte, bytes for multiple)
        """
        self.cs.value(0)
        if length == 1:
            data = self.spi.read(length + 1, register)[1]
        else:
            data = self.spi.read(length + 1, register)[1:]
        self.cs.value(1)
        return data

    def close(self) -> None:
        """Clean up resources and close the SPI connection"""
        self.spi.deinit()
