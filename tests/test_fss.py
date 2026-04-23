# Hardware probe for the Fine Sun Sensor (TSL2561 @ 0x39 on I2C1).
# Copy to the Pico as main.py, then open serial monitor in Thonny.
#
# Wiring: SCL=GP19, SDA=GP18, VCC=3V3, GND=GND, ADDR floating (=> 0x39).
#
# Cycles through the three integration-time modes; in each mode prints lux
# (via the peripheral wrapper) and raw (broadband, ir) channels (via the
# driver directly), so you can tell I2C faults from saturation.

from manha.satkit import i2c
from manha.satkit.peripherals import FineSunSensor
import time


i2c.init_i2c()
bus = i2c.m_i2c1

print("I2C1 scan:", [hex(a) for a in (bus.scan() or []) if a is not None])

fss = FineSunSensor(bus)
print("TSL2561 sensor_id:", hex(fss._tsl.sensor_id()))

INT_TIMES = (13, 101, 402)
N_PER_MODE = 5

for it in INT_TIMES:
    print("\n--- integration_time = {} ms ---".format(it))
    fss.configure(integration_time=it, gain=1)
    for _ in range(N_PER_MODE):
        try:
            raw = fss._tsl.read(raw=True)
            broadband, ir = raw  # type: ignore[misc]
        except Exception as e:
            broadband, ir = -1, -1
            print("raw read err:", e)
        rd = fss.read()
        print("lux={:>10} raw bb={} ir={}".format(rd["fss_lux"], broadband, ir))
        time.sleep(1)

print("\nautogain sweep (integration_time=101ms, 20 samples):")
fss.configure(integration_time=101)
for _ in range(20):
    rd = fss.read()
    print("lux={:>10} gain={}x".format(rd["fss_lux"], fss._tsl.gain()))
    time.sleep(0.5)

print("\ndone.")
