from microbit import *
import micropython, sys
micropython.kbd_intr(-1)
i2c.init(freq=1000000)
uart.init(baudrate=115200)
A,buf=0x3C,bytearray(129)
buf[0]=0x40
sleep(300)
while uart.any():uart.read()
page=0
while True:
    if button_a.was_pressed() or button_b.was_pressed():display.show(Image.ASLEEP);sleep(1000);display.clear();sys.exit()
    ptr=1
    while ptr<129:
        if uart.any():
            chunk=uart.read(129 - ptr)
            if chunk:
                for b in chunk: buf[ptr]=b;ptr+=1
    i2c.write(A, bytes([0x00, 0xB0 + page, 0x00, 0x10]))
    i2c.write(A, buf)
    display.set_pixel(4,0,9 if page%2==0 else 0)
    uart.write(b"O")
    page=(page+1)%8