from machine import Pin, SoftI2C, I2C

I2C_SCL_PIN = 19
I2C_SDA_PIN = 18


def init_i2c():
    global m_i2c
    m_i2c = I2C(1, scl=Pin(I2C_SCL_PIN), sda=Pin(I2C_SDA_PIN), freq=100_000)
