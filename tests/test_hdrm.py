from manha.satkit.peripherals import MHDRM
import time

hdrm = MHDRM(2,hold_angle=40, release_angle=10)

for i in range(20):
    print("Release (180°)")
    hdrm.release()
    time.sleep(1)

    print("Hold (0°)")
    hdrm.hold()
    time.sleep(1)


# 
# print("Hold (0°)")
# hdrm.hold()
