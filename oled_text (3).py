from microbit import Image
import oled
scr = oled.s
def clear_box(x, y, count=1):
    i0 = y * 128 + x * 10 + 1
    for i in range(i0, min(i0 + count * 10, 1025)): scr[i] = 0
def invert_row(y, draw=1):
    st=y*128+1
    if st + 128 <= 1025:
        for i in range(st, st + 128): scr[i] = ~scr[i] & 0xFF
    if draw:oled.draw_screen()
def add_text(x,y,text,scale=1,draw=1):
    cp=x*(5 if scale==1 else 10)
    for char in text:
        try:img=Image(char)
        except: continue
        fc,lc=5,-1
        for c in range(5):
            for r in range(5):
                if img.get_pixel(c,r):
                    if c<fc:fc=c
                    if c>lc:lc=c
        if lc==-1:cp+=2*scale;continue
        for c in range(fc,lc+1):
            if cp>=120:break
            if scale==1:
                col=sum((1<<r) for r in range(1,6) if img.get_pixel(c,r-1))
                ind=y*128+cp+1
                if ind<1024:scr[ind]=col
                cp+=1
            else:
                bits= sum((1<<(r-1))for r in range(1,6) if img.get_pixel(c,r-1))
                bt=sum((0b11<<(r*2))for r in range(4) if bits&(1<<r))
                bb=0b11 if bits & 0x10 else 0
                it,ib=y*128+cp+1,(y+1)*128+cp+1
                if it<1024: scr[it]=scr[it + 1]=bt
                if ib<1024 and y<7:scr[ib]=scr[ib+1]=bb
                cp+=2
        cp+=scale
    if draw:oled.draw_screen()