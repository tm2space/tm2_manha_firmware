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

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `v_p` | float | -1 | Battery voltage percentage (Battery) |
| `i` | float | -1 | Current consumption in amperes (Solar Panel) |
| `s_v` | float | -1 | Shunt voltage measurement (Solar Panel) |
| `b_v` | float | -1 | Bus voltage measurement (Solar Panel) |
| `lat` | float | 0.0 | Latitude in decimal degrees |
| `lng` | float | 0.0 | Longitude in decimal degrees |
| `alt` | int | 0 | Altitude in meters (from GPS) |
| `sats` | int | 0 | Number of satellites in use |
| `a_x` | float | 0 | X-axis acceleration |
| `a_y` | float | 0 | Y-axis acceleration |
| `a_z` | float | 0 | Z-axis acceleration |
| `uv` | float | -1 | UV intensity measurement (transmitted as {"uv":{"uv": <value>}}) |
| `temp` | float | -1 | Temperature in Celsius |
| `pres` | float | -1 | Atmospheric pressure |
| `hum` | float | -1 | Humidity percentage |
| `ts` | int | current_time | Timestamp in milliseconds |
| `lpm` | bool | false | Low power mode status |
| `cs_x` | float | -1 | X-axis Magnetometer Reading |
| `cs_y` | float | -1 | Y-axis Magnetometer Reading |
| `cs_z` | float | -1 | Z-axis Magnetometer Reading |
