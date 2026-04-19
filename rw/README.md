# RW Testbench

MicroPython reaction-wheel / ESC testbench for Raspberry Pi Pico W. Hosts a Wi-Fi AP + web UI to arm, disarm, and throttle up to 4 BLHeli (SiLabs Rev14.x) ESCs over PPM.

## Hardware

- Raspberry Pi Pico W
- Up to 4 BLHeli ESCs (PPM, 1–2 ms pulse)
- Default GPIOs: `0, 1, 7, 6` (M1..M4)
- Common ground between Pico and ESCs

## Deploy

Single file. Copy `main.py` to Pico root via Thonny. No dependencies beyond stock MicroPython.

On boot:
- AP SSID: `manha-spinner`
- Password: `space1234`
- Web UI: `http://192.168.4.1/`

Runtime config persists to `config.json` on the Pico. Delete it to restore defaults.

## Web UI

- **STOP** — disarm all, zero throttle
- **ARM ALL / DISARM ALL** — batch arm/disarm
- **Zero** — sliders → 0 (does not disarm)
- **Master slider** — drives all four
- Per-motor slider + ARM button
- Live telemetry: mode (idle/arming/armed), pulse us, ping ms

Arming sequence (per wheel): zero hold → small up-throttle → zero hold → armed. Duration = `arm_delay_ms`.

Deadman: if no WS message for `deadman_ms`, all armed wheels disarm.

## Config fields

| Key | Default | Notes |
|---|---|---|
| `gpios` | `[0,1,7,6]` | PWM output pins M1..M4 |
| `ssid` / `password` | `manha-spinner` / `space1234` | AP creds |
| `pwm_freq` | `400` Hz | ESC PPM rate |
| `min_us` | `1000` | Min pulse |
| `center_us` | `1490` | Zero throttle in bidir (trim if ESC arming stalls at first beep) |
| `max_us` | `2000` | Max pulse |
| `bidirectional` | `true` | Bidir 3D mode — must also be set in BLHeliSuite on the ESC |
| `deadman_ms` | `1500` | Disarm timeout on lost comms |
| `arm_delay_ms` | `1500` | Arming ramp duration |
| `http_port` | `80` | |

**Reboot required** for `ssid`, `password`, `gpios`, `pwm_freq`. `min/center/max_us` apply live.

## Throttle mapping

UI range `[-999, 999]`:
- Bidir: `-999 → min_us`, `0 → center_us`, `+999 → max_us`
- Forward-only: `v<0` clamps to 0; `0..999 → min_us..max_us`

## Finding `center_us`

If ESC stalls at first arming beep, the PPM zero-point is off. Slowly sweep the slider from 0, note the UI midpoint `v` where the motor does not respond, then set:

```
center_us = 1500 + 500 * v / 999
```
