from machine import Pin, UART

UART0_TX_PIN = 12
UART0_RX_PIN = 13
UART0_BAUD = 115200


def init_uart():
    global m_uart0
    m_uart0 = UART(0, baudrate=UART0_BAUD, tx=Pin(UART0_TX_PIN), rx=Pin(UART0_RX_PIN))
