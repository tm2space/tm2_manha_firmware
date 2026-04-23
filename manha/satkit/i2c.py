from machine import Pin, SoftI2C, I2C

I2C1_SCL_PIN = 19
I2C1_SDA_PIN = 18

I2C2_SCL_PIN = 21
I2C2_SDA_PIN = 20


def init_i2c():
    global m_i2c1, m_i2c2
    m_i2c1 = I2C(1, scl=Pin(I2C1_SCL_PIN), sda=Pin(I2C1_SDA_PIN), freq=100_000)
    m_i2c2 = I2C(0, scl=Pin(I2C2_SCL_PIN), sda=Pin(I2C2_SDA_PIN), freq=100_000)
