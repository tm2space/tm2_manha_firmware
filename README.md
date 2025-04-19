# TM2Space MANHA Firmware
The repository is the firmware that powers the [MANHA](https://manha.tm2.space) kit from TM2Space. The MANHA OBC is powered by Raspberry Pico and Micro-python framework.

## Project Structure

The project is divided in the following structure:

```sh
$ tree manha

manha/                      # Main source code directory
├── __init__.py             # module export
├── gs/                     # Ground Station implementation - ManhaGS
│   ├── __init__.py
│   └── gs.py
├── internals/              # Internal modules, drivers and utilities
│   ├── __init__.py
│   ├── comms/              # Communication modules
│   │   ├── __init__.py
│   │   ├── lora/           # LoRa communication
│   │   │   ├── __init__.py
│   │   │   └── lora.py
│   │   └── wifi/           # WiFi communication
│   │       ├── __init__.py
│   │       └── microdot/   # Microdot web framework
│   ├── drivers/            # Hardware drivers
│   │   ├── __init__.py
│   │   ├── adxl345.py      # Accelerometer driver
│   │   ├── battery_adc.py  # Battery ADC driver
│   │   ├── bme680.py       # Environmental sensor driver
│   │   ├── ina219.py       # Power monitor driver
│   │   ├── neogps.py       # GPS driver
│   │   ├── rfm9x.py        # LoRa RF module driver
│   │   ├── uvs12sd.py      # UV sensor driver
│   │   └── ws2812matrix.py # LED matrix driver
│   └── parsers/           
│       └── GPSParser.py    # GPS NMEA data parser
└── satkit/                  # Satellite kit modules
    ├── __init__.py
    ├── i2c.py               # I2C utilities
    ├── index.html           # Web interface
    ├── manha.py             # Main satellite functionality
    └── peripherals/         # Peripheral device abstractions
        ├── __init__.py
        ├── accelerometer.py
        ├── base.py
        ├── gas.py
        ├── gps.py
        ├── ledmatrix.py
        ├── powermon.py
        └── uv.py

build/                      # Compiled output directory
└── manha/
    └── *.mpy                   # Compiled MicroPython files
```

## How to install
1. Clone the repository.
2. Open the repository on Thonny IDE.
3. Connect the MANHA OBC to the computer and select Pi Pico as the board on Thonny IDE.
4. Build the project as per [Building](#building)
5. Copy the `build/manha` folder to the detected Raspberry Pi Pico
6. Copy your `main.py` and any other files to the root of Raspberry Pi Pico

## Building
The firmware uses MicroPython's `.mpy` format for efficient execution on the Pico. To compile the Python files:

```bash
# Compile all Python files to .mpy
make build

# Clean the build directory
make clean
```


