from microbit import i2c
A=0x3C;s=bytearray(1025);s[0]=0x40
def command(c):
    if isinstance(c,int):c=[c]
    i2c.write(A,b"\x00"+bytes(c))
def initialize():
    command([0xAE, 0xA4, 0xD5, 0xF0, 0xA8, 0x3F, 0xD3, 0x00, 0x40, 0x8D, 0x14, 0x20, 0x00, 0x21, 0, 127, 0x22, 0, 63, 0xA1, 0xC8, 0xDA, 0x12, 0x81, 0x40, 0xD9, 0xF1, 0xDB, 0x40, 0xA6, 0xD6, 0, 0xAF])
def set_pos(col=0,page=0):
    command([0xB0 | page, col & 0x0F, 0x10 | (col >> 4)])
def draw_screen():
    if s is not None: set_pos();i2c.write(A, s)
def clear_oled(row=None, draw=1):
    if s is None: return
    if row is None:
        for i in range(1,1025): 
            s[i]=0
    else:
        st=row*128+1
        for i in range(st,st+128): 
            s[i]=0
    if draw:draw_screen()
