"""Memory profiler for MANHA satkit imports.

Copy to Pico as main.py (or run via Thonny). Reports mem_free delta
per import step — identifies which modules dominate heap.

Method: gc.collect() before baseline, import one module, gc.collect(),
read mem_free(). Delta = that import's net cost (bytecode + class
dicts + const tables + any module-level allocations).
"""

import gc
import time


def _snap(label, prev):
    gc.collect()
    now = gc.mem_free()
    delta = now - prev
    sign = "+" if delta >= 0 else ""
    print(f"{label:45s} free={now:>7d}  d={sign}{delta}")
    return now


def main():
    time.sleep(1)  # let serial settle

    gc.collect()
    baseline = gc.mem_free()
    print(f"{'baseline (gc only)':45s} free={baseline:>7d}")
    prev = baseline

    # ── stdlib / machine ────────────────────────────────────────────────
    import machine                                     ; prev = _snap("machine", prev)
    import asyncio                                     ; prev = _snap("asyncio", prev)
    import json                                        ; prev = _snap("json", prev)
    import binascii                                    ; prev = _snap("binascii", prev)
    import struct                                      ; prev = _snap("struct", prev)
    from collections import namedtuple                 ; prev = _snap("collections.namedtuple", prev)

    # ── MANHA utils / config ────────────────────────────────────────────
    from manha.utils import calculate_checksum         ; prev = _snap("manha.utils.calculate_checksum", prev)
    from manha.config import LORA_ADDR                 ; prev = _snap("manha.config", prev)

    # ── Drivers (each separately) ───────────────────────────────────────
    from manha.internals.drivers.ws2812matrix import WS2812Matrix, PixelColors
    prev = _snap("drivers.ws2812matrix (+PixelColors)", prev)
    from manha.internals.drivers.neogps import NeoGPS, GPSParser
    prev = _snap("drivers.neogps (+GPSParser)", prev)
    from manha.internals.drivers.adxl345 import ADXL345
    prev = _snap("drivers.adxl345", prev)
    from manha.internals.drivers.bme680 import BME680_I2C
    prev = _snap("drivers.bme680", prev)
    from manha.internals.drivers.ina219 import INA219
    prev = _snap("drivers.ina219", prev)
    from manha.internals.drivers.uvs12sd import UVS12SD
    prev = _snap("drivers.uvs12sd", prev)
    from manha.internals.drivers.battery_adc import BatteryVoltage
    prev = _snap("drivers.battery_adc", prev)
    from manha.internals.drivers.servo import Servo
    prev = _snap("drivers.servo", prev)
    from manha.internals.drivers import rfm9x_constants
    prev = _snap("drivers.rfm9x_constants", prev)
    from manha.internals.drivers.rfm9x import RFM9x, ModemConfig
    prev = _snap("drivers.rfm9x (LoRa)", prev)

    # ── Comms ───────────────────────────────────────────────────────────
    from manha.internals.comms.packet import Packet    ; prev = _snap("comms.packet", prev)
    from manha.internals.comms.binary_tlm import encode_tlm
    prev = _snap("comms.binary_tlm", prev)

    # ── Peripherals (each separately) ───────────────────────────────────
    from manha.satkit.peripherals.base import ManhaSensor
    prev = _snap("peripherals.base", prev)
    from manha.satkit.peripherals.ledmatrix import LEDMatrix
    prev = _snap("peripherals.ledmatrix", prev)
    from manha.satkit.peripherals.uv import UVSensor
    prev = _snap("peripherals.uv", prev)
    from manha.satkit.peripherals.gas import GasSensor
    prev = _snap("peripherals.gas", prev)
    from manha.satkit.peripherals.accelerometer import Accelerometer
    prev = _snap("peripherals.accelerometer", prev)
    from manha.satkit.peripherals.powermon import PowerMonitor
    prev = _snap("peripherals.powermon", prev)
    from manha.satkit.peripherals.gps import GPS
    prev = _snap("peripherals.gps", prev)
    from manha.satkit.peripherals.hdrm import MHDRM
    prev = _snap("peripherals.hdrm", prev)
    from manha.satkit.peripherals.camera import ManhaCam
    prev = _snap("peripherals.camera", prev)

    # ── Satkit bus helpers (each instantiates a bus object at import) ──
    from manha.satkit import i2c                       ; prev = _snap("satkit.i2c (creates m_i2c1, m_i2c2)", prev)
    from manha.satkit import uart                      ; prev = _snap("satkit.uart (creates m_uart0)", prev)
    from manha.satkit import gpio                      ; prev = _snap("satkit.gpio", prev)
    from manha.satkit.lora import LoRa                 ; prev = _snap("satkit.lora", prev)
    from manha.satkit import constants                 ; prev = _snap("satkit.constants", prev)

    # ── Top-level MANHA class (imports manha.py module body) ───────────
    from manha.satkit.manha import MANHA               ; prev = _snap("satkit.manha (MANHA class)", prev)

    # ── Deprecated Microdot (per CLAUDE.md) ─────────────────────────────
    try:
        from manha.internals.microdot.microdot import Microdot
        prev = _snap("microdot.microdot (DEPRECATED)", prev)
    except Exception as e:
        print(f"microdot skipped: {e}")

    # ── QMC5883 compass ─────────────────────────────────────────────────
    try:
        from qmc5883 import QMC5883
        prev = _snap("qmc5883", prev)
    except Exception as e:
        print(f"qmc5883 skipped: {e}")

    print("-" * 72)
    print(f"{'TOTAL imports consumed':45s} {baseline - prev} bytes")
    print(f"{'Remaining free':45s} {prev} bytes")


main()
