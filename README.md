# TM2Space MANHA Firmware

The repository contains the firmware that powers the [MANHA](https://manha.tm2.space) kit from TM2Space. The MANHA OBC (On-Board Computer) is powered by Raspberry Pi Pico and MicroPython framework.

## Overview

MANHA is a satellite development kit featuring comprehensive sensor integration, LoRa communication, and real-time data collection capabilities. The firmware supports two main operational modes:

- **SatKit Mode** (`satkit_main.py`) - Full satellite functionality with sensor monitoring
- **Ground Station Mode** (`gs_main.py`) - Ground station communication interface

## Features

### Sensor Integration
- **Accelerometer** (ADXL345) - Motion and orientation sensing
- **Environmental** (BME680) - Temperature, humidity, pressure, and gas sensing
- **GPS** (NeoGPS) - Location tracking and timing
- **UV Sensor** (UVS12SD) - Ultraviolet radiation monitoring
- **Power Monitor** (INA219) - Current and voltage monitoring
- **Compass** (QMC5883) - Magnetic field sensing
- **LED Matrix** (WS2812) - Visual status display

### Communication
- **LoRa** (RFM9x) - Long-range wireless communication
- **WebSocket** - Real-time data streaming
- **HTTP Server** - Web-based control interface

### Data Management
- Real-time sensor data collection and transmission
- Packet-based communication protocol
- Battery monitoring and power management
- Error handling and system recovery

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

### Ground Station

To finish flashing the groundstation:

1. Create a file main.py on the Pico
2. Copy contents of `gs_main.py` to `main.py`

## Project Structure

```
manha/
├── satkit/          # MANHA class
│   ├── manha.py     # Main MANHA class
│   ├── lora.py      # LoRa interface for satkit
│   └── peripherals/ # Example sensor drivers
├── gs/              # Ground station functionality
│   ├── manha.py     # ManhaGS class
│   ├── lora.py      # LoRa interface for GS
├── internals/       # Core system components
│   ├── comms/       # Communication protocols
│   ├── drivers/     # Hardware drivers
│   └── microdot/    # Web server framework
└── utils/           # Utility functions
satkit_main.py       # Main script for SatKit mode
gs_main.py           # Main script for Ground Station mode
qmc5883.py           # QMC5883 compass driver
```
