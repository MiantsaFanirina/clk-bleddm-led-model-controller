import asyncio
import threading
import tkinter as tk
from bleak import BleakClient
from math import cos, sin, pi, atan2, sqrt
import colorsys
import time
import numpy as np
from PIL import ImageGrab
import pyaudio

# -------------------------
# Configuration
# -------------------------
ADDRESS = "BE:27:62:00:3E:91"  # BLE LED MAC
CHAR_UUID = "0000fff3-0000-1000-8000-00805f9b34fb"

DEFAULT_BRIGHTNESS = 100
MIN_WRITE_INTERVAL = 0.01  # BLE write throttle
ANIM_INTERVAL_MS = 10  # animation loop
ANIM_SPEED = 0.2
AUDIO_ANIM_SPEED = 0.18

PREDEFINED_COLORS = [
    "FF0000","00FF00","0000FF","FFFFFF","FFFF00","00FFFF","FF00FF",
    "FFA500","800080","FFC0CB","00FF7F","008080","E6E6FA","800000",
    "000080","808000","000000"
]

# -------------------------
# BLE Client
# -------------------------
client = BleakClient(ADDRESS)
ble_connected = False
last_write_time = 0

async def connect_ble():
    global ble_connected
    try:
        await client.connect()
        ble_connected = True
        print("Connected to LED")
    except Exception as e:
        print("BLE connection failed:", e)

async def send_color_generic(r, g, b):
    """Send RGB raw bytes (0-255 each) to LED characteristic."""
    global last_write_time
    if not ble_connected:
        return
    now = time.time()
    if (now - last_write_time) < MIN_WRITE_INTERVAL:
        return
    try:
        await client.write_gatt_char(CHAR_UUID, bytes([r, g, b]), response=False)
        last_write_time = now
    except Exception as e:
        print("Failed to send color:", e)

def schedule_task(coro):
    asyncio.run_coroutine_threadsafe(coro, loop)

# -------------------------
# Animation / Color helpers
# -------------------------
target_hue = 0.0
target_sat = 0.0
target_brightness = DEFAULT_BRIGHTNESS
target_white = 0.0

display_hue = 0.0
display_sat = 0.0
display_brightness = DEFAULT_BRIGHTNESS
display_white = 0.0

def lerp(a, b, t):
    return a + (b - a) * t

def lerp_hue(a, b, t):
    diff = (b - a + 0.5) % 1.0 - 0.5
    return (a + diff * t) % 1.0

def hsvw_to_rgb(h, s, wmix):
    r,g,b = colorsys.hsv_to_rgb(h, s, 1.0)
    r = int((1-wmix)*r*255 + wmix*255)
    g = int((1-wmix)*g*255 + wmix*255)
    b = int((1-wmix)*b*255 + wmix*255)
    return r,g,b

def request_color_hs(h, s):
    global target_hue, target_sat
    target_hue = h % 1.0
    target_sat = max(0.0, min(1.0, s))

def request_brightness(b):
    global target_brightness
    target_brightness = max(0, min(100, b))

def request_white_mix(w):
    global target_white
    target_white = max(0.0, min(1.0, w))

def update_color_send():
    r, g, b = hsvw_to_rgb(display_hue, display_sat, display_white)
    # scale brightness
    factor = max(0, min(1, display_brightness/100))
    r = int(r*factor)
    g = int(g*factor)
    b = int(b*factor)
    schedule_task(send_color_generic(r, g, b))

def animation_step():
    global display_hue, display_sat, display_brightness, display_white
    display_hue = lerp_hue(display_hue, target_hue, ANIM_SPEED)
    display_sat = lerp(display_sat, target_sat, ANIM_SPEED)
    display_white = lerp(display_white, target_white, ANIM_SPEED)
    display_brightness = lerp(display_brightness, target_brightness, ANIM_SPEED)

    # Update preview
    r,g,b = hsvw_to_rgb(display_hue, display_sat, display_white)
    factor = max(0, min(1, display_brightness/100))
    r_disp = int(r*factor)
    g_disp = int(g*factor)
    b_disp = int(b*factor)
    hex_disp = f"{r_disp:02X}{g_disp:02X}{b_disp:02X}"
    selected_color_preview.configure(bg="#" + hex_disp)
    update_color_display()
    update_color_send()
    root.after(ANIM_INTERVAL_MS, animation_step)

# -------------------------
# Tkinter GUI
# -------------------------
root = tk.Tk()
root.title("Generic LED Controller")
root.geometry("480x720")
root.configure(bg="#111111")

TITLE_FONT = ("Helvetica", 18, "bold")
BUTTON_FONT = ("Helvetica", 10, "bold")
LABEL_FONT = ("Helvetica", 11, "bold")
INPUT_FONT = ("Helvetica", 10)

tk.Label(root, text="Generic BLE LED Controller", font=TITLE_FONT, fg="#FFFFFF", bg="#111111").pack(pady=10)

# Presets
frame_colors = tk.Frame(root, bg="#111111")
frame_colors.pack(pady=5)

def set_color_from_hex(hex_code):
    r = int(hex_code[:2],16)/255
    g = int(hex_code[2:4],16)/255
    b = int(hex_code[4:],16)/255
    h,s,_ = colorsys.rgb_to_hsv(r,g,b)
    request_color_hs(h,s)

def create_color_button(parent, hex_code, row, col):
    fg = "white" if sum(int(hex_code[i:i+2],16) for i in [0,2,4])/3 < 128 else "black"
    btn = tk.Button(parent, bg="#" + hex_code, fg=fg, font=BUTTON_FONT, width=3, height=1,
                    command=lambda c=hex_code: set_color_from_hex(c))
    btn.grid(row=row, column=col, padx=2, pady=2)

row=col=0
for hex_code in PREDEFINED_COLORS:
    create_color_button(frame_colors, hex_code, row, col)
    col+=1
    if col>7:
        col=0
        row+=1

tk.Button(frame_colors, text="ON", bg="#FFFFFF", fg="black", width=5, command=lambda: request_brightness(100)).grid(row=row, column=0)
tk.Button(frame_colors, text="OFF", bg="#000000", fg="white", width=5, command=lambda: request_brightness(0)).grid(row=row, column=1)

# Color wheel
canvas_size = 240
canvas = tk.Canvas(root, width=canvas_size, height=canvas_size, bg="#111111", highlightthickness=0)
canvas.pack(pady=10)
selector_radius = 8
selector = canvas.create_oval(0,0,0,0, outline="#FFFFFF", width=2)
wheel_img = tk.PhotoImage(width=canvas_size, height=canvas_size)
canvas.create_image((canvas_size//2, canvas_size//2), image=wheel_img)

def draw_color_wheel():
    radius = canvas_size//2 - 5
    cx, cy = canvas_size//2, canvas_size//2
    for y in range(canvas_size):
        for x in range(canvas_size):
            dx, dy = x-cx, y-cy
            dist = sqrt(dx**2 + dy**2)
            if dist <= radius:
                angle = (atan2(dy, dx) + pi) % (2*pi)
                hue = angle / (2*pi)
                sat = dist/radius
                r,g,b = colorsys.hsv_to_rgb(hue,sat,1)
                color = f"#{int(r*255):02X}{int(g*255):02X}{int(b*255):02X}"
                wheel_img.put(color,(x,y))
draw_color_wheel()

selected_color_preview = tk.Label(root, bg="#FFFFFF", width=10, height=1, bd=2, relief=tk.RAISED)
selected_color_preview.pack(pady=5)

def update_selector(x, y):
    canvas.coords(selector, x-selector_radius, y-selector_radius, x+selector_radius, y+selector_radius)

def pick_color(event):
    cx, cy = canvas_size//2, canvas_size//2
    dx, dy = event.x-cx, event.y-cy
    dist = sqrt(dx**2 + dy**2)
    radius = canvas_size//2 - 5
    if dist>radius and dist!=0:
        dx *= radius/dist
        dy *= radius/dist
        x, y = cx+dx, cy+dy
    else:
        x,y = event.x, event.y
    angle = (atan2(dy, dx)+pi)%(2*pi)
    hue = angle/(2*pi)
    sat = sqrt(dx**2+dy**2)/radius
    update_selector(x,y)
    request_color_hs(hue,sat)

canvas.bind("<Button-1>", pick_color)
canvas.bind("<B1-Motion>", pick_color)

# White slider
white_slider_width = 360
white_slider_height = 25
white_slider = tk.Canvas(root, width=white_slider_width, height=white_slider_height, bg="#111111", highlightthickness=0)
white_slider.pack(pady=5)
white_selector_radius = 5
white_selector = white_slider.create_oval(0,0,0,0, outline="#FFFFFF", width=2)

def draw_white_slider():
    white_slider.delete("gradient")
    r_base, g_base, b_base = colorsys.hsv_to_rgb(target_hue,target_sat,1)
    for i in range(white_slider_width):
        ratio = i/white_slider_width
        r = int((1-ratio)*r_base*255 + ratio*255)
        g = int((1-ratio)*g_base*255 + ratio*255)
        b = int((1-ratio)*b_base*255 + ratio*255)
        color = f"#{r:02X}{g:02X}{b:02X}"
        white_slider.create_line(i,0,i,white_slider_height,fill=color, tags="gradient")
    draw_white_selector(display_white)

def draw_white_selector(value):
    x = value*white_slider_width
    white_slider.coords(white_selector, x-white_selector_radius,0,x+white_selector_radius,white_slider_height)

def white_slider_click(event):
    mix = max(0, min(1, event.x/white_slider_width))
    request_white_mix(mix)

white_slider.bind("<Button-1>", white_slider_click)
white_slider.bind("<B1-Motion>", white_slider_click)
draw_white_slider()

# Brightness slider
tk.Label(root, text="Brightness", font=LABEL_FONT, fg="#FFFFFF", bg="#111111").pack(pady=3)
def on_brightness_slider(value):
    request_brightness(float(value))
brightness_slider = tk.Scale(root, from_=0, to=100, orient=tk.HORIZONTAL, length=350,
                             command=on_brightness_slider, bg="#111111", fg="#FFFFFF", troughcolor="#333333")
brightness_slider.set(DEFAULT_BRIGHTNESS)
brightness_slider.pack(pady=5)

# Color display
color_display = tk.Label(root, text="", fg="#FFFFFF", bg="#111111", font=LABEL_FONT)
color_display.pack(pady=5)

def update_color_display():
    r,g,b = hsvw_to_rgb(display_hue, display_sat, display_white)
    factor = display_brightness/100
    r=int(r*factor); g=int(g*factor); b=int(b*factor)
    hex_val = f"{r:02X}{g:02X}{b:02X}"
    color_display.config(text=f"HEX: #{hex_val} | RGB: ({r},{g},{b})")

# -------------------------
# Smart Screen Loop
# -------------------------
smart_screen = tk.BooleanVar(value=False)
smart_audio = tk.BooleanVar(value=False)
smart_screen_brightness = tk.BooleanVar(value=False)

def screen_loop():
    while True:
        try:
            if smart_screen.get():
                img = ImageGrab.grab().resize((50,50))
                arr = np.array(img)
                r,g,b = arr[:,:,0].mean(), arr[:,:,1].mean(), arr[:,:,2].mean()
                rr,gg,bb = r/255, g/255, b/255
                h,s,v = colorsys.rgb_to_hsv(rr,gg,bb)
                request_color_hs(h,s)
                if smart_screen_brightness.get() and not smart_audio.get():
                    request_brightness(np.clip(v*100,5,100))
            time.sleep(0.05)
        except:
            time.sleep(0.2)

threading.Thread(target=screen_loop,daemon=True).start()

# -------------------------
# Audio Reactive Loop
# -------------------------
audio_band_vars = {"bass": tk.BooleanVar(value=True),"mid":tk.BooleanVar(value=False),"high":tk.BooleanVar(value=False)}
def get_selected_bands():
    return [b for b,var in audio_band_vars.items() if var.get()]

def audio_loop():
    CHUNK = 1024; RATE = 44100
    history = []; HISTORY_LEN = 30; MIN_BRIGHTNESS=8; MAX_BRIGHTNESS=80; SPIKE_THRESHOLD=30
    global display_hue, display_sat, display_white, display_brightness
    try:
        p=pyaudio.PyAudio()
        stream=p.open(format=pyaudio.paInt16, channels=1, rate=RATE, input=True, frames_per_buffer=CHUNK)
    except:
        return
    while True:
        try:
            if smart_audio.get():
                data = np.frombuffer(stream.read(CHUNK,exception_on_overflow=False),dtype=np.int16)
                fft = np.abs(np.fft.rfft(data))
                bass, mid, high = fft[:150].mean(), fft[150:2000].mean(), fft[2000:].mean()
                values = [v for b,v in zip(["bass","mid","high"],[bass,mid,high]) if b in get_selected_bands()]
                avg_val = np.mean(values) if values else 0
                history.append(avg_val)
                if len(history)>HISTORY_LEN: history.pop(0)
                avg_hist = np.mean(history) if history else 1
                intensity = max(0, avg_val-avg_hist)
                cubic = min(1,intensity/(SPIKE_THRESHOLD*3))**3
                target_brightness_local = MIN_BRIGHTNESS + (MAX_BRIGHTNESS-MIN_BRIGHTNESS)*cubic
                display_brightness = lerp(display_brightness,target_brightness_local,AUDIO_ANIM_SPEED)
        except:
            time.sleep(0.2)
        time.sleep(0.05)

threading.Thread(target=audio_loop,daemon=True).start()

# -------------------------
# Asyncio + BLE Thread
# -------------------------
loop = asyncio.new_event_loop()
def loop_thread():
    asyncio.set_event_loop(loop)
    loop.run_until_complete(connect_ble())
    loop.run_forever()
threading.Thread(target=loop_thread, daemon=True).start()

# -------------------------
# Start animation
# -------------------------
root.after(ANIM_INTERVAL_MS, animation_step)
root.mainloop()
