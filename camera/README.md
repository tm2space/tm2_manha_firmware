# ManhaCam - ESP32-CAM WiFi AP Image Server

Firmware for the ESP32-CAM module used on the MANHA satellite. Runs as a WiFi
access point with a web UI and HTTP/JSON API for image capture, management, and
camera configuration. Also exposes a serial command interface for integration
with the Satkit Pico.

## Hardware

The ManhaCam uses an **ESP32-CAM AI-Thinker** module (`CAMERA_MODEL_AI_THINKER`
in `board_config.h`). It has PSRAM.

PSRAM is required for UXGA resolution and high JPEG quality. Use the **Minimal
SPIFFS (1.9MB APP with OTA/190KB SPIFFS)** partition scheme — this gives two
1.9MB OTA-capable app slots. Do **not** use Huge APP (3MB), which has no OTA
slot.

## Build & Flash

Open the project in the Arduino IDE. Required libraries:

- **ArduinoJson** (v7+)
- **ESP32 Board Support** — follow the
  [Espressif setup guide](https://docs.espressif.com/projects/arduino-esp32/en/latest/installing.html)
  to add ESP32 boards to the IDE

In the IDE:

1. Go to **Tools > Board** and select **AI Thinker ESP32-CAM**.
2. Go to **Tools > Partition Scheme** and select **Minimal SPIFFS (1.9MB APP with OTA/190KB SPIFFS)**.
3. Select your serial port under **Tools > Port**.
4. Click **Upload**.

### Flashing the AI-Thinker

The AI-Thinker module doesn't have auto-reset circuitry, so you need to put it
into download mode manually:

1. Connect **GPIO 0** to **GND**.
2. Press the **RST** button (or power-cycle the board).
3. Flash using the upload command above.
4. Disconnect **GPIO 0** from GND.
5. Press **RST** again to boot into the firmware.

If you're using a USB-to-serial adapter (FTDI, CP2102, etc.), wire it up as:

| Adapter | ESP32-CAM |
|---------|-----------|
| TX      | U0R (RX)  |
| RX      | U0T (TX)  |
| GND     | GND       |
| 5V      | 5V        |

Make sure the adapter is **5V-tolerant** or use the 3.3V rail if your adapter
only supports that. The board needs 5V for stable camera operation though, so
powering via 5V is recommended.

## Boot Behaviour

The firmware boots in **flight mode** — WiFi and the HTTP server are off. This
saves power and avoids RF interference during satellite operation.

To enable the web UI, send the `0x05` (WEBUI_ON) command over UART. To disable
it again, send `0x06` (WEBUI_OFF). See the serial command table below.

## WiFi Access Point

When the web UI is enabled, the module creates a WiFi AP:

| Parameter      | Default       |
|----------------|---------------|
| SSID           | `Manha-CAM`   |
| Password       | `space1234`   |
| Channel        | 6             |
| Max clients    | 4             |
| IP             | `192.168.4.1` |

A captive portal can be enabled by setting `ENABLE_CAPTIVE_PORTAL 1` in
`board_config.h` (disabled by default) so the web UI opens automatically when
a device connects.

## Web UI

Open `http://192.168.4.1/` in a browser after connecting to the AP. The
single-page interface (served from PROGMEM via `web_ui.h`) provides:

- Live image gallery with thumbnails
- One-click capture
- Per-image view and delete
- Camera settings editor (resolution, quality, brightness, contrast, etc.)
- Named presets (Default, High Quality, Low Light, Fast Capture)
- Factory reset
- OTA firmware update with cancel support
- Log viewer

## HTTP/JSON API

All API endpoints return JSON.

### Images

| Method   | Endpoint              | Description                          |
|----------|-----------------------|--------------------------------------|
| `GET`    | `/api/status`         | SD status, image count, free MB      |
| `GET`    | `/api/images`         | List all images (name, size)         |
| `GET`    | `/api/image?name=...` | Download a single image (JPEG)       |
| `POST`   | `/api/capture`        | Capture a new photo, return filename |
| `DELETE` | `/api/image?name=...` | Delete a single image                |
| `DELETE` | `/api/images`         | Delete all images                    |

### Camera Settings

| Method | Endpoint                | Description                       |
|--------|-------------------------|-----------------------------------|
| `GET`  | `/api/settings`         | Current camera settings (JSON)    |
| `POST` | `/api/settings`         | Update settings (partial JSON OK) |
| `POST` | `/api/settings/reset`   | Factory-reset all settings        |
| `GET`  | `/api/presets`          | List named presets with values    |
| `GET`  | `/api/camera/info`      | Sensor PID, supported framesizes  |

### Logs

| Method   | Endpoint              | Description                           |
|----------|-----------------------|---------------------------------------|
| `GET`    | `/api/logs?offset=N`  | Read log file from byte offset N      |
| `DELETE` | `/api/logs`           | Clear log buffer and log file         |

### Settings JSON Fields

```json
{
  "framesize": 9,
  "quality": 12,
  "brightness": 0,
  "contrast": 0,
  "saturation": 0,
  "special_effect": 0,
  "wb_mode": 0,
  "awb": 1,
  "awb_gain": 1,
  "aec": 1,
  "aec2": 1,
  "ae_level": 0,
  "agc": 1,
  "agc_gain": 0,
  "gainceiling": 2,
  "bpc": 1,
  "wpc": 1,
  "raw_gma": 1,
  "lenc": 1,
  "hmirror": 0,
  "vflip": 0
}
```

`POST /api/settings` accepts a partial object -- only the fields you send are
updated; the rest keep their current values.

## OTA Firmware Update

The camera supports over-the-air firmware updates through the web UI. This
lets you flash new firmware over WiFi without a serial connection.

### How to update

1. In the Arduino IDE, go to **Sketch > Export Compiled Binary**. This produces
   build output in `build/<board>/`. The file you need is `camera.ino.bin`
   (the app binary, ~1.2MB).
2. Connect to the `Manha-CAM` WiFi network and open `http://192.168.4.1/`.
3. Go to the **System** tab and find **Firmware Update**.
4. Select the `.bin` file and click **Upload & Flash**.
5. A confirmation dialog will appear — confirm to proceed.
6. The progress bar shows upload status. Click **Cancel** at any time to abort.
7. Once complete, the camera reboots automatically into the new firmware.

Do **not** upload `.elf`, `.merged.bin`, `.bootloader.bin`, or
`.partitions.bin` — only the app binary (`camera.ino.bin`) works with OTA.

### API

| Method | Endpoint    | Body                     | Description                  |
|--------|-------------|--------------------------|------------------------------|
| `POST` | `/api/ota`  | Raw `.bin` (octet-stream) | Flash firmware and reboot   |

Returns `{"ok": true, "msg": "..."}` on success or `{"ok": false, "error": "..."}` on failure.

### Partition scheme

OTA requires two app slots in flash. Use the **Minimal SPIFFS (1.9MB APP with
OTA/190KB SPIFFS)** partition scheme — the firmware is ~1.2MB, so it fits
comfortably. Do **not** use Huge APP, which has no OTA slot.

## Serial Command Interface (Satkit Integration)

The ESP32-CAM listens for single-byte commands on **Serial (UART0, 115200
baud)**. This is how the Satkit Pico triggers captures and queries status.

| Byte   | Command      | Payload              | Response                                     |
|--------|--------------|----------------------|----------------------------------------------|
| `0x01` | CAPTURE      | —                    | `ACK:<filename>\n` or `NACK:capture_failed\n` |
| `0x02` | STATUS       | —                    | `ACK:count=<N>\n`                             |
| `0x03` | SET_SETTINGS | key-value pairs + `0x00` | `ACK:settings=<N>\n` or `NACK:<reason>\n` |
| `0x04` | GET_SETTINGS | —                    | `0x04` + key-value pairs + `0x00\n`           |
| `0x05` | WEBUI_ON     | —                    | `ACK:webui=on,ip=<IP>\n`                      |
| `0x06` | WEBUI_OFF    | —                    | `ACK:webui=off\n`                             |
| other  | unknown      | —                    | `NACK:unknown_cmd=0xNN\n`                     |

### Binary Settings Key IDs

Settings are sent as key-value byte pairs. Keys are `0x01`–`0x15`, values are
single unsigned bytes (signed fields like brightness use two's complement).

| Key    | Field          | Type  | Range      |
|--------|----------------|-------|------------|
| `0x01` | framesize      | enum  | 0–11       |
| `0x02` | quality        | uint8 | 10–63      |
| `0x03` | brightness     | int8  | -2 to 2    |
| `0x04` | contrast       | int8  | -2 to 2    |
| `0x05` | saturation     | int8  | -2 to 2    |
| `0x06` | special_effect | enum  | 0–6        |
| `0x07` | wb_mode        | enum  | 0–4        |
| `0x08` | awb            | bool  | 0/1        |
| `0x09` | awb_gain       | bool  | 0/1        |
| `0x0A` | aec            | bool  | 0/1        |
| `0x0B` | aec2           | bool  | 0/1        |
| `0x0C` | ae_level       | int8  | -2 to 2    |
| `0x0D` | agc            | bool  | 0/1        |
| `0x0E` | agc_gain       | uint8 | 0–30       |
| `0x0F` | gainceiling    | enum  | 0–6        |
| `0x10` | bpc            | bool  | 0/1        |
| `0x11` | wpc            | bool  | 0/1        |
| `0x12` | raw_gma        | bool  | 0/1        |
| `0x13` | lenc           | bool  | 0/1        |
| `0x14` | hmirror        | bool  | 0/1        |
| `0x15` | vflip          | bool  | 0/1        |

Example — set JPEG quality to 10:
```
TX: 0x03 0x02 0x0A 0x00
     cmd  key  val  end
RX: ACK:settings=1\n
```

### Satkit Peripheral

On the Pico side, the `ManhaCam` satkit peripheral
(`manha/satkit/peripherals/camera.py`) wraps this protocol:

```python
from manha.satkit.peripherals import ManhaCam

cam = ManhaCam()                      # UART1, TX=4, RX=5, 115200 baud
data = cam.read()                     # {"cam_count": N}
fname = cam.capture()                 # "/images/img_00042.jpg" or None
cam.configure_remote(b'\x02\x0A')     # set quality=10 (raw bytes passthrough)
raw = cam.read_settings()             # raw binary key-value pairs (44 bytes)
```

Enable automatic telemetry reporting by setting `ENABLE_CAM = True` in
`manha/config.py`. LoRa commands:

- `CAM=1` -- trigger a capture (returns `CAM:<filename>` or `CAM:FAIL`)
- `CAM=0` -- query image count (returns `CAM:count=<N>`)
- `CAMSET=02:0A,16:01` -- set settings via hex key:value pairs
- `CAMGET` -- read all settings (returns `CAMGET:01:06,02:0C,...`)

## Configuration Reference

Compile-time options in `board_config.h`:

| Define                  | Default        | Description                         |
|-------------------------|----------------|-------------------------------------|
| `CAMERA_MODEL_*`        | `AI_THINKER`   | Board/pin mapping selection         |
| `ENABLE_CAPTIVE_PORTAL` | `0`            | Auto-redirect to web UI on connect  |
| `ENABLE_SERIAL_LOG`     | `0`            | Echo logs to UART ^[1]              |
| `LOG_FILE`              | `"/logs.txt"`  | SD card log file path               |
| `MAX_LOG_BYTES`         | `16384`        | Max log file size before truncation |
| `LOG_BUF_SIZE`          | `512`          | RAM log buffer (flushed every 5 s)  |

^[1]: `ENABLE_SERIAL_LOG` outputs debug logs on UART0 — the same UART used for
the serial command interface with the Satkit Pico. Log output will interfere
with command responses and cause the ManhaCam peripheral to misparse replies.
Set this to `0` when the camera is connected to the Pico. Only enable it for
standalone debugging over USB.

## File Structure

```
camera/
  camera.ino       Main sketch: setup, loop, camera/SD/WiFi init, serial cmds
  app_httpd.h      Shared types (CamSettings, Preset), function declarations
  app_httpd.cpp    HTTP server routes and API handlers
  board_config.h   Board selection, captive portal & logging options
  camera_pins.h    GPIO pin maps for all supported boards
  web_ui.h         Inlined HTML/CSS/JS served from PROGMEM
  mockup.html      Development mockup of web UI (not included in firmware)
```
