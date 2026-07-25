import gc
gc.threshold(256)
import os, sys, machine
gc.collect()
from microbit import *
import oled, oled_text
gc.collect()

def r_menu(s, px, py, c, t=0):
    for a in range(6):
        i=t+a
        oled_text.clear_box(px,py+ a, count=6)
        if i<len(s):oled_text.add_text(px+2,py+a,s[i][:18],draw=0)
    oled_text.add_text(px,py+c-t,"=",draw=0)
    oled.draw_screen()
def console():
    while not button_b.was_pressed():exec(input())
    machine.reset()
def menu(s, px, py, title="Micro OS"):
    oled.clear_oled(draw=0)
    oled_text.add_text(0,0,title[:10],draw=0)
    oled_text.invert_row(0,draw=0)
    c=t=0
    r_menu(s,px,py,c,t)
    while 1:
        a,b =button_a.was_pressed(),button_b.was_pressed()
        if a and b:
            break
        chg = 0
        if a:
            c-=1
            if c<0:c=len(s)-1;t=max(0,len(s)-6)
            elif c<t:t=c
            chg=1
        if b:
            c+=1
            if c>=len(s):c=t=0
            elif c>=t+6:t=c-2
            chg=1
        if chg:
            r_menu(s,px,py,c,t);gc.collect()
        sleep(50)
    return c
oled.initialize();oled.clear_oled();oled_text.add_text(0,0,"Pythensis",scale=2);oled_text.add_text(0,2,"By Ja1pr");oled_text.add_text(0,7,"v2.0 "+sys.version[:8])
while 1:
    c=menu(["Files","Stream","Console","Quit"],0,1)
    if c==0:fl=os.listdir();menu(fl,0,1,title="FILES");del fl;gc.collect()   
    elif c==3:oled.clear_oled();sys.exit()
    elif c==1:oled.clear_oled();gc.collect();import stream
    elif c==2:console()


