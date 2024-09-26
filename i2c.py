from machine import Pin, SoftI2C

# Pin configuration for I2C communication with the BME680 sensor
I2C_SCL_PIN = 1  # SCL pin
I2C_SDA_PIN = 0  # SDA pin

def init_i2c():
    global m_i2c
    m_i2c = SoftI2C(scl=Pin(I2C_SCL_PIN), sda=Pin(I2C_SDA_PIN))
