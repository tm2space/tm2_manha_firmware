# TM2Space MANHA Firmware

The repository contains the firmware that powers the [MANHA](https://manha.tm2.space) kit from TM2Space. The MANHA OBC (On-Board Computer) and GS (Ground Station) are powered by Raspberry Pi Pico and MicroPython framework.

## Overview

MANHA is a satellite development kit featuring comprehensive sensor integration, LoRa communication, and real-time data collection capabilities. The firmware supports two main operational modes:

- **SatKit** (`satkit_main.py`) - Full satellite functionality with sensor monitoring
- **Ground Station** (`gs_main.py`) - Ground station communication interface

## Installation

1. Clone the repository:

   ```bash
   git clone https://github.com/tm2space/tm2_manha_firmware.git
   ```

2. Open the repository in Thonny IDE

3. Connect the MANHA OBC/GS to your computer via USB

4. In Thonny IDE:
   - Select "MicroPython (Raspberry Pi Pico)" as the interpreter
   - Right click on the `manha/` folder
   - Select 'Upload to /` from the Context menu

### SatKit

After following the above steps:

1. Create a file main.py
2. Copy contents of `satkit_main.py` to `main.py`
3. Right click the `qmc5883.py` file and select 'Upload to /'
4. Go to `manha/config.py` and modify the `LORA_ADDR` constant to match your GS

### Ground Station

To finish flashing the groundstation:

1. Create a file main.py on the Pico
2. Copy contents of `gs_main.py` to `main.py`
3. Go to `manha/config.py` and modify the `LORA_ADDR` constant to match your Manha SatKit

## Project Structure

```txt
manha/
├── satkit/            # MANHA class
│   ├── manha.py       # Main MANHA class
│   ├── lora.py        # LoRa interface for satkit
│   └── peripherals/   # Example sensor drivers
├── gs/                # Ground station functionality
│   ├── manha.py       # ManhaGS class
│   ├── lora.py        # LoRa interface for GS
├── internals/         # Core system components
│   ├── comms/         # Communication protocols
│   │   └── packet.py  # Packet Storage Class Specification
│   ├── drivers/       # Hardware drivers
│   └── microdot/      # Web server framework
└── utils/             # Utility functions
satkit_main.py         # Main script for SatKit mode
gs_main.py             # Main script for Ground Station mode
qmc5883.py             # QMC5883 compass driver
```

## JSON Fields

The following JSON fields are transmitted over LoRa from the satkit to the ground station:

**NOTE:** (JSON Reading) x (Conversion Factor) = (Reading in Units)

| Field | Type | Default | Description | Conversion Factor | Units |
|-------|------|---------|-------------|-------------------|-------|
| `v_p` | float | -1 | Battery voltage percentage (Battery) | 1 | % |
| `i` | float | -1 | Current consumption in amperes (Solar Panel) | 1 | mA |
| `s_v` | float | -1 | Shunt voltage measurement (Solar Panel) | 1 | mV |
| `b_v` | float | -1 | Bus voltage measurement (Solar Panel) | 1 | V |
| `lat` | float | 0.0 | Latitude in decimal degrees | 1 | degrees |
| `lng` | float | 0.0 | Longitude in decimal degrees | 1 | degrees |
| `alt` | int | 0 | Altitude in meters (from GPS) | 1 | m |
| `sats` | int | 0 | Number of satellites in use | 1 | count |
| `a_x` | float | 0 | X-axis acceleration | 0.039 | m/s² |
| `a_y` | float | 0 | Y-axis acceleration | 0.039 | m/s² |
| `a_z` | float | 0 | Z-axis acceleration | 0.039 | m/s² |
| `uv` | float | -1 | UV intensity measurement (transmitted as {"uv":{"uv": <value>}}) | 1 | V |
| `temp` | float | -1 | Temperature in Celsius | 1 | °C |
| `pres` | float | -1 | Atmospheric pressure | 1 | hPa |
| `hum` | float | -1 | Humidity percentage | 1 | % |
| `ts` | int | current_time | Timestamp in milliseconds | 1 | ms |
| `lpm` | bool | false | Low power mode status | 1 | boolean |
| `cs_x` | float | -1 | X-axis Magnetometer Reading | 0.10 | µT |
| `cs_y` | float | -1 | Y-axis Magnetometer Reading | 0.10 | µT |
| `cs_z` | float | -1 | Z-axis Magnetometer Reading | 0.10 | µT |
| `gas`  | float | -1 | Gas Resistance in Ohms | 1 | Ohms |

## LED Matrix Status Indicators

The SatKit 8x8 WS2812 LED matrix (data pin GPIO 3) signals runtime state through color. Blink events are ~50 ms fill then clear, and are suppressed while low-power mode is active (except the command-RX indicator and boot/shutdown states).

| Color | Event | Source |
|-------|-------|--------|
| `WHITE` | Boot / init (fill, held) | `manha/satkit/manha.py:102` |
| `BLUE` | LoRa command received (100 ms hold) | `manha/satkit/manha.py:527` |
| `GREEN` | Telemetry packet TX success | `manha/satkit/manha.py:833` |
| `MAGENTA` | TX-done wait failed / exit low-power mode | `manha/satkit/manha.py:607`, `manha/satkit/manha.py:835` |
| `YELLOW` | Enter low-power mode | `manha/satkit/manha.py:598` |
| `RED` | Sensor task exception / MemoryError during TX | `manha/satkit/manha.py:684`, `manha/satkit/manha.py:840` |
| `CLEAR` | Shutdown | `manha/satkit/manha.py:877` |
