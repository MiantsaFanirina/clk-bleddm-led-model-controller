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
import math

# -------------------------
# Configuration
# -------------------------
ADDRESS = "BE:27:62:00:3E:91"
CHAR_UUID = "0000fff3-0000-1000-8000-00805f9b34fb"

DEFAULT_BRIGHTNESS = 100
MIN_WRITE_INTERVAL = 0.01     # BLE write throttle

ANIM_INTERVAL_MS = 10         # animation timer tick (smoother transitions)
ANIM_SPEED = 0.2              # 0..1 lerp factor per tick (higher = faster)
AUDIO_ANIM_SPEED = 0.5  # More rapid slide out for audio reactive

PREDEFINED_COLORS = [
    "FF0000", "00FF00", "0000FF", "FFFFFF", "FFFF00", "00FFFF", "FF00FF",
    "FFA500", "800080", "FFC0CB", "00FF7F", "008080", "E6E6FA", "800000",
    "000080", "808000", "000000"
]

# -------------------------
# BLE Client
# -------------------------
client = BleakClient(ADDRESS)
ble_connected = False
last_sent_color = None
last_write_time = 0

async def connect_ble():
    global ble_connected
    try:
        await client.connect()
        ble_connected = True
        print("Connected to LED strip")
        # power on / ready command (device-specific)
        await client.write_gatt_char(CHAR_UUID, bytes.fromhex("7E00040201EF"), response=False)
        await asyncio.sleep(0.01)
    except Exception as e:
        print("BLE connection failed:", e)

async def send_color(rgb_hex):
    """
    Send RGB (hex like 'RRGGBB') with device command framing.
    Throttled and deduped.
    """
    global last_sent_color, last_write_time
    if not ble_connected:
        return
    now = time.time()
    if last_sent_color == rgb_hex and (now - last_write_time) < MIN_WRITE_INTERVAL:
        return
    seq = f"7E000503{rgb_hex}00EF"
    try:
        await client.write_gatt_char(CHAR_UUID, bytes.fromhex(seq), response=False)
        last_sent_color = rgb_hex
        last_write_time = now
    except Exception as e:
        print("Failed to send command:", e)

def schedule_task(coro):
    asyncio.run_coroutine_threadsafe(coro, loop)

# -------------------------
# Animation state / Color helpers
# -------------------------
# Targets (where we want to go)
target_hue = 0.0            # 0..1
target_sat = 0.0            # 0..1
target_brightness = DEFAULT_BRIGHTNESS  # 0..100
target_mix_white = 0.0      # 0..1

# Displayed (what we are currently showing/sending)
display_hue = 0.0
display_sat = 0.0
display_brightness = DEFAULT_BRIGHTNESS
display_mix_white = 0.0

# UI control state (manual entries)
manual_brightness = DEFAULT_BRIGHTNESS  # slider value (feeds target_brightness unless audio reactive overwrites)
mix_white_ratio = 0.0                   # slider value (feeds target_mix_white)

def lerp(a, b, t):
    return a + (b - a) * t

def lerp_hue(a, b, t):
    """
    Lerp hue on circle (0..1), shortest path.
    """
    diff = (b - a + 0.5) % 1.0 - 0.5
    return (a + diff * t) % 1.0

def almost_equal(a, b, eps=1e-3):
    return abs(a - b) < eps

def scale_rgb(rgb_hex, brightness):
    r = int(rgb_hex[0:2], 16)
    g = int(rgb_hex[2:4], 16)
    b = int(rgb_hex[4:6], 16)
    factor = max(0, min(1, brightness / 100))
    r = int(r * factor)
    g = int(g * factor)
    b = int(b * factor)
    return f"{r:02X}{g:02X}{b:02X}"

def hsvw_to_rgb_hex(h, s, wmix):
    """
    HSV (v fixed to 1) + 'white mix' -> RGB hex without brightness scaling.
    wmix = 0 uses pure HSV color, wmix = 1 is pure white.
    """
    r_base, g_base, b_base = colorsys.hsv_to_rgb(h, s, 1.0)
    r = int(((1 - wmix) * r_base + wmix * 1.0) * 255)
    g = int(((1 - wmix) * g_base + wmix * 1.0) * 255)
    b = int(((1 - wmix) * b_base + wmix * 1.0) * 255)
    return f"{r:02X}{g:02X}{b:02X}"

def request_color_hs(h, s):
    """
    Set a new color target (smoothly animates to it).
    """
    global target_hue, target_sat
    target_hue = h % 1.0
    target_sat = max(0.0, min(1.0, s))
    draw_white_slider()  # update the white gradient for the new target color

def request_brightness(b):
    """
    Set a new brightness target (smoothly animates to it).
    """
    global target_brightness
    target_brightness = int(max(0, min(100, b)))

def request_white_mix(w):
    """
    Set a new white-mix target (smoothly animates to it).
    """
    global target_mix_white
    target_mix_white = max(0.0, min(1.0, w))

def update_color_preview_and_send():
    """
    Compute displayed color -> preview -> BLE send (throttled).
    """
    hex_code = hsvw_to_rgb_hex(display_hue, display_sat, display_mix_white)
    hex_scaled = scale_rgb(hex_code, display_brightness)

    # Update preview swatch
    selected_color_preview.configure(bg="#" + hex_code)

    # Send to device (scaled by brightness)
    schedule_task(send_color(hex_scaled))

def animation_step():
    """
    Animation loop: smoothly move displayed_* toward target_*.
    Always heads to the latest targets.
    """
    global display_hue, display_sat, display_brightness, display_mix_white

    # Lerp color HS + white mix
    new_h = lerp_hue(display_hue, target_hue, ANIM_SPEED)
    new_s = lerp(display_sat, target_sat, ANIM_SPEED)
    new_w = lerp(display_mix_white, target_mix_white, ANIM_SPEED)

    # Lerp brightness
    new_b = lerp(display_brightness, target_brightness, ANIM_SPEED)

    display_changed = (
        not (almost_equal(new_h, display_hue) and
             almost_equal(new_s, display_sat) and
             almost_equal(new_w, display_mix_white) and
             almost_equal(new_b, display_brightness))
    )

    display_hue = new_h
    display_sat = new_s
    display_mix_white = new_w
    display_brightness = new_b

    # Move the white selector with displayed_mix_white
    draw_white_selector(display_mix_white)

    # Update preview + send
    update_color_preview_and_send()

    # Update on-screen HEX/RGB readout
    update_one_color_display()

    # keep the loop running
    root.after(ANIM_INTERVAL_MS, animation_step)

def set_color_from_hex(hex_code):
    r, g, b = int(hex_code[:2],16)/255, int(hex_code[2:4],16)/255, int(hex_code[4:],16)/255
    h, s, v = colorsys.rgb_to_hsv(r, g, b)
    request_color_hs(h, s)

# -------------------------
# Tkinter GUI
# -------------------------
root = tk.Tk()
root.title("Smart LED Controller")
root.geometry("480x720")  # smaller window
root.configure(bg="#111111")  # deep black background

TITLE_FONT = ("Helvetica", 18, "bold")
BUTTON_FONT = ("Helvetica", 10, "bold")
LABEL_FONT = ("Helvetica", 11, "bold")
INPUT_FONT = ("Helvetica", 10)

# Title
tk.Label(root, text="Smart LED Controller", font=TITLE_FONT, fg="#FFFFFF", bg="#111111").pack(pady=10)

# Preset color buttons
frame_colors = tk.Frame(root, bg="#111111")
frame_colors.pack(pady=5)

def create_color_button(parent, hex_code, row, col):
    fg_color = "white" if sum(int(hex_code[i:i+2], 16) for i in [0,2,4])/3 < 128 else "black"
    btn = tk.Button(
        parent, bg="#" + hex_code, fg=fg_color,
        font=BUTTON_FONT, width=3, height=1, relief=tk.RAISED, bd=2,
        activebackground="#333333", activeforeground=fg_color,
        cursor="hand2",
        command=lambda c=hex_code: set_color_from_hex(c)
    )
    btn.grid(row=row, column=col, padx=2, pady=2)

row = col = 0
for hex_code in PREDEFINED_COLORS:
    create_color_button(frame_colors, hex_code, row, col)
    col += 1
    if col > 7:
        col = 0
        row += 1

# On/Off buttons
def turn_off():
    # Do not hard-set display; animate to off
    request_brightness(0)

def turn_on():
    # Restore to a visible neutral state (no forced hue/sat change)
    request_brightness(100)

tk.Button(frame_colors, text="ON", bg="#FFFFFF", fg="black", width=5, height=1, bd=2, cursor="hand2", command=turn_on).grid(row=row, column=0, padx=2, pady=2)
tk.Button(frame_colors, text="OFF", bg="#000000", fg="white", width=5, height=1, bd=2, cursor="hand2", command=turn_off).grid(row=row, column=1, padx=2, pady=2)

# Color wheel
canvas_size = 240
canvas = tk.Canvas(root, width=canvas_size, height=canvas_size, bg="#111111", highlightthickness=0, cursor="hand2")
canvas.pack(pady=10)
selector_radius = 8
selector = canvas.create_oval(0,0,0,0, outline="#FFFFFF", width=2)

wheel_img = tk.PhotoImage(width=canvas_size, height=canvas_size)
canvas.create_image((canvas_size//2, canvas_size//2), image=wheel_img)

def draw_color_wheel():
    radius = canvas_size//2 - 5
    cx, cy = canvas_size//2, canvas_size//2
    # Render once
    for y in range(canvas_size):
        for x in range(canvas_size):
            dx, dy = x-cx, y-cy
            dist = sqrt(dx**2 + dy**2)
            if dist <= radius:
                angle = (atan2(dy, dx) + pi) % (2*pi)
                hue = angle / (2*pi)
                sat = dist/radius
                r,g,b = colorsys.hsv_to_rgb(hue, sat, 1)
                color = f"#{int(r*255):02X}{int(g*255):02X}{int(b*255):02X}"
                wheel_img.put(color, (x,y))
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
    if dist > radius and dist != 0:
        dx *= radius/dist
        dy *= radius/dist
        x, y = cx+dx, cy+dy
    else:
        x, y = event.x, event.y

    angle = (atan2(dy, dx) + pi) % (2*pi)
    hue = angle / (2*pi)
    sat = sqrt(dx**2 + dy**2)/radius
    update_selector(x, y)
    request_color_hs(hue, sat)

canvas.bind("<Button-1>", pick_color)
canvas.bind("<B1-Motion>", pick_color)

# White shade slider
white_slider_width = 360
white_slider_height = 25
white_slider = tk.Canvas(root, width=white_slider_width, height=white_slider_height, bg="#111111", highlightthickness=0, cursor="hand2")
white_slider.pack(pady=5)

white_selector_radius = 5
white_selector = white_slider.create_oval(0,0,0,0, outline="#FFFFFF", width=2)

def draw_white_slider():
    white_slider.delete("gradient")
    # Use target color for the white gradient bar
    r_base, g_base, b_base = colorsys.hsv_to_rgb(target_hue, target_sat, 1.0)
    for i in range(white_slider_width):
        ratio = i / white_slider_width
        r = int((1 - ratio) * r_base * 255 + ratio * 255)
        g = int((1 - ratio) * g_base * 255 + ratio * 255)
        b = int((1 - ratio) * b_base * 255 + ratio * 255)
        color = f"#{r:02X}{g:02X}{b:02X}"
        white_slider.create_line(i, 0, i, white_slider_height, fill=color, tags="gradient")
    draw_white_selector(display_mix_white)

def draw_white_selector(value):
    x = value * white_slider_width
    white_slider.coords(white_selector, x-white_selector_radius, 0, x+white_selector_radius, white_slider_height)

def white_slider_click(event):
    global mix_white_ratio
    mix_white_ratio = max(0, min(1, event.x / white_slider_width))
    request_white_mix(mix_white_ratio)

white_slider.bind("<Button-1>", white_slider_click)
white_slider.bind("<B1-Motion>", white_slider_click)

draw_white_slider()

# HEX & RGB input fields
input_frame = tk.Frame(root, bg="#111111")
input_frame.pack(pady=5)

def update_from_hex_input():
    hex_val = hex_entry.get().strip().lstrip('#')
    if len(hex_val) == 6:
        set_color_from_hex(hex_val)

def update_from_rgb_input():
    try:
        r = int(rgb_entries["R"].get())
        g = int(rgb_entries["G"].get())
        b = int(rgb_entries["B"].get())
        r = max(0, min(255, r))
        g = max(0, min(255, g))
        b = max(0, min(255, b))
        set_color_from_hex(f"{r:02X}{g:02X}{b:02X}")
    except:
        pass

tk.Label(input_frame, text="HEX:", fg="#FFFFFF", bg="#111111", font=INPUT_FONT).grid(row=0, column=0, padx=3)
hex_entry = tk.Entry(input_frame, width=8, font=INPUT_FONT, bg="#222222", fg="#FFFFFF", insertbackground="#FFFFFF", relief=tk.FLAT)
hex_entry.grid(row=0, column=1)
tk.Button(input_frame, text="Set", font=INPUT_FONT, bg="#333333", fg="#FFFFFF", cursor="hand2", relief=tk.RAISED, bd=2, command=update_from_hex_input).grid(row=0, column=2, padx=3)

rgb_entries = {}
for i, color in enumerate(["R","G","B"]):
    tk.Label(input_frame, text=color+":", fg="#FFFFFF", bg="#111111", font=INPUT_FONT).grid(row=1, column=i*2, padx=2)
    entry = tk.Entry(input_frame, width=3, font=INPUT_FONT, bg="#222222", fg="#FFFFFF", insertbackground="#FFFFFF", relief=tk.FLAT)
    entry.grid(row=1, column=i*2+1)
    rgb_entries[color] = entry
tk.Button(input_frame, text="Set RGB", font=INPUT_FONT, bg="#333333", fg="#FFFFFF", cursor="hand2", relief=tk.RAISED, bd=2, command=update_from_rgb_input).grid(row=1, column=6, padx=3)

# Display current color HEX & RGB
color_display = tk.Label(root, text="", fg="#FFFFFF", bg="#111111", font=LABEL_FONT)
color_display.pack(pady=5)

def update_one_color_display():
    hex_code = hsvw_to_rgb_hex(display_hue, display_sat, display_mix_white)
    hex_scaled = scale_rgb(hex_code, int(display_brightness))
    r,g,b = int(hex_scaled[0:2],16), int(hex_scaled[2:4],16), int(hex_scaled[4:6],16)
    color_display.config(text=f"HEX: #{hex_scaled}  |  RGB: ({r},{g},{b})")

# Brightness slider at the end
tk.Label(root, text="Brightness", font=LABEL_FONT, fg="#FFFFFF", bg="#111111").pack(pady=3)
def on_brightness_slider(value):
    global manual_brightness
    manual_brightness = int(float(value))
    # User move -> set as new target (will slide)
    request_brightness(manual_brightness)

brightness_slider = tk.Scale(
    root, from_=0, to=100, orient=tk.HORIZONTAL, length=350,
    command=on_brightness_slider, bg="#111111", fg="#FFFFFF", troughcolor="#333333",
    highlightthickness=0, cursor="hand2"
)
brightness_slider.set(DEFAULT_BRIGHTNESS)
brightness_slider.pack(pady=5)

# -------------------------
# Smart Hue toggles
# -------------------------
smart_frame = tk.Frame(root, bg="#111111")
smart_frame.pack(pady=5)

smart_screen = tk.BooleanVar(value=False)
smart_audio = tk.BooleanVar(value=False)
smart_screen_brightness = tk.BooleanVar(value=True)  # new toggle for brightness control

# Callback to update toggle states
def update_brightness_toggle_state():
    if smart_screen.get() and not smart_audio.get():
        brightness_toggle.config(state=tk.NORMAL)
    else:
        brightness_toggle.config(state=tk.DISABLED)
        if smart_screen_brightness.get():
            smart_screen_brightness.set(False)
            # Restore brightness to slider value
            request_brightness(manual_brightness)

# Smart Screen toggle
screen_toggle = tk.Checkbutton(
    smart_frame, text="Smart Screen", font=INPUT_FONT, fg="#FFFFFF", bg="#111111",
    selectcolor="#333333", variable=smart_screen, cursor="hand2",
    command=update_brightness_toggle_state
)
screen_toggle.grid(row=0, column=0, padx=10)

# Audio Reactive toggle
audio_toggle = tk.Checkbutton(
    smart_frame, text="Audio Reactive", font=INPUT_FONT, fg="#FFFFFF", bg="#111111",
    selectcolor="#333333", variable=smart_audio, cursor="hand2",
    command=lambda: [update_brightness_toggle_state(), update_audio_band_visibility()]
)
audio_toggle.grid(row=0, column=1, padx=10)

# Smart Screen Brightness Control toggle
brightness_toggle = tk.Checkbutton(
    smart_frame, text="Screen Brightness Control", font=INPUT_FONT, fg="#FFFFFF", bg="#111111",
    selectcolor="#333333", variable=smart_screen_brightness, cursor="hand2"
)
brightness_toggle.grid(row=0, column=2, padx=10)
update_brightness_toggle_state()

# -------------------------
# Smart functionality
# -------------------------
def screen_color_loop():
    """
    Reads average screen color.
    Controls hue/sat always, and brightness only if Smart Screen Brightness Control is enabled and Audio Reactive is disabled.
    """
    while True:
        try:
            if smart_screen.get():
                img = ImageGrab.grab()
                img = img.resize((50,50))
                arr = np.array(img)
                r, g, b = arr[:,:,0].mean(), arr[:,:,1].mean(), arr[:,:,2].mean()

                # Extract HSV from average screen color
                rr, gg, bb = r/255.0, g/255.0, b/255.0
                h, s, v = colorsys.rgb_to_hsv(rr, gg, bb)

                # Always update color hue/saturation
                request_color_hs(h, s)

                # Only update brightness if brightness control is enabled and audio reactive is off
                if smart_screen_brightness.get() and not smart_audio.get():
                    brightness = int(np.clip(v * 100, 5, 100))
                    request_brightness(brightness)

            time.sleep(0.05)
        except Exception as e:
            print("Screen loop error:", e)
            time.sleep(0.2)


# Frequency band selection for audio reactive (checkboxes)
audio_band_vars = {
    "bass": tk.BooleanVar(value=True),
    "mid": tk.BooleanVar(value=False),
    "high": tk.BooleanVar(value=False)
}

def get_selected_bands():
    return [band for band, var in audio_band_vars.items() if var.get()]

freq_frame = tk.Frame(root, bg="#111111")
freq_frame.pack(pady=2)
audio_band_label = tk.Label(freq_frame, text="Audio Frequency Bands:", font=INPUT_FONT, fg="#FFFFFF", bg="#111111")
audio_band_label.pack(side=tk.LEFT)
checkbox_widgets = []
for band in ["bass", "mid", "high"]:
    cb = tk.Checkbutton(
        freq_frame,
        text=band.capitalize(),
        variable=audio_band_vars[band],
        font=INPUT_FONT,
        fg="#FFFFFF",
        bg="#111111",
        selectcolor="#333333",
        cursor="hand2"
    )
    cb.pack(side=tk.LEFT)
    checkbox_widgets.append(cb)

def update_audio_band_visibility():
    state = tk.NORMAL if smart_audio.get() else tk.HIDDEN
    # Hide/show label and checkboxes
    if state == tk.HIDDEN:
        audio_band_label.pack_forget()
        for cb in checkbox_widgets:
            cb.pack_forget()
        # Restore brightness to slider value
        request_brightness(manual_brightness)
    else:
        audio_band_label.pack(side=tk.LEFT)
        for cb in checkbox_widgets:
            cb.pack(side=tk.LEFT)

# Attach visibility update to audio toggle
audio_toggle = tk.Checkbutton(
    smart_frame, text="Audio Reactive", font=INPUT_FONT, fg="#FFFFFF", bg="#111111",
    selectcolor="#333333", variable=smart_audio, cursor="hand2",
    command=lambda: [update_brightness_toggle_state(), update_audio_band_visibility()]
)
audio_toggle.grid(row=0, column=1, padx=10)
update_audio_band_visibility()

# -------------------------
# Smart functionality
# -------------------------
def screen_color_loop():
    """
    Reads average screen color.
    Controls hue/sat always, and brightness only if Smart Screen Brightness Control is enabled and Audio Reactive is disabled.
    """
    while True:
        try:
            if smart_screen.get():
                img = ImageGrab.grab()
                img = img.resize((50,50))
                arr = np.array(img)
                r, g, b = arr[:,:,0].mean(), arr[:,:,1].mean(), arr[:,:,2].mean()

                # Extract HSV from average screen color
                rr, gg, bb = r/255.0, g/255.0, b/255.0
                h, s, v = colorsys.rgb_to_hsv(rr, gg, bb)

                # Always update color hue/saturation
                request_color_hs(h, s)

                # Only update brightness if brightness control is enabled and audio reactive is off
                if smart_screen_brightness.get() and not smart_audio.get():
                    brightness = int(np.clip(v * 100, 5, 100))
                    request_brightness(brightness)

            time.sleep(0.05)
        except Exception as e:
            print("Screen loop error:", e)
            time.sleep(0.2)


# Frequency band selection for audio reactive (checkboxes)
audio_band_vars = {
    "bass": tk.BooleanVar(value=True),
    "mid": tk.BooleanVar(value=False),
    "high": tk.BooleanVar(value=False)
}

def get_selected_bands():
    return [band for band, var in audio_band_vars.items() if var.get()]

freq_frame = tk.Frame(root, bg="#111111")
freq_frame.pack(pady=2)
audio_band_label = tk.Label(freq_frame, text="Audio Frequency Bands:", font=INPUT_FONT, fg="#FFFFFF", bg="#111111")
audio_band_label.pack(side=tk.LEFT)
checkbox_widgets = []
for band in ["bass", "mid", "high"]:
    cb = tk.Checkbutton(
        freq_frame,
        text=band.capitalize(),
        variable=audio_band_vars[band],
        font=INPUT_FONT,
        fg="#FFFFFF",
        bg="#111111",
        selectcolor="#333333",
        cursor="hand2"
    )
    cb.pack(side=tk.LEFT)
    checkbox_widgets.append(cb)

def update_audio_band_visibility():
    state = tk.NORMAL if smart_audio.get() else tk.HIDDEN
    # Hide/show label and checkboxes
    if state == tk.HIDDEN:
        audio_band_label.pack_forget()
        for cb in checkbox_widgets:
            cb.pack_forget()
        # Restore brightness to slider value
        request_brightness(manual_brightness)
    else:
        audio_band_label.pack(side=tk.LEFT)
        for cb in checkbox_widgets:
            cb.pack(side=tk.LEFT)

# Attach visibility update to audio toggle
audio_toggle = tk.Checkbutton(
    smart_frame, text="Audio Reactive", font=INPUT_FONT, fg="#FFFFFF", bg="#111111",
    selectcolor="#333333", variable=smart_audio, cursor="hand2",
    command=lambda: [update_brightness_toggle_state(), update_audio_band_visibility()]
)
audio_toggle.grid(row=0, column=1, padx=10)
update_audio_band_visibility()

def audio_reactive_loop():
    """
    Continuous-state audio reactive: brightness flows smoothly, mapped to sound intensity.
    """
    CHUNK = 1024
    RATE = 44100
    history = []
    HISTORY_LEN = 30
    MIN_BRIGHTNESS = 8
    MAX_BRIGHTNESS = 80
    SPIKE_THRESHOLD = 30  # Lower threshold for more sensitivity
    AUDIO_ANIM_SPEED = 0.18  # Lower for smoother flow
    COLOR_FADE_SPEED = 0.18
    # Target color for high/low state
    high_color = {'h': 0.0, 's': 1.0, 'w': 0.0}  # vivid color
    low_color = {'h': 0.0, 's': 0.2, 'w': 0.7}   # faded white
    global display_hue, display_sat, display_mix_white, display_brightness
    try:
        p = pyaudio.PyAudio()
        stream = p.open(format=pyaudio.paInt16, channels=1, rate=RATE, input=True, frames_per_buffer=CHUNK)
    except Exception as e:
        print("Audio init failed:", e)
        return

    while True:
        try:
            if smart_audio.get():
                data = np.frombuffer(stream.read(CHUNK, exception_on_overflow=False), dtype=np.int16)
                if data.size == 0:
                    target_brightness = MIN_BRIGHTNESS
                    target_color = low_color
                else:
                    fft = np.abs(np.fft.rfft(data))
                    bass_slice = fft[:150]
                    mid_slice = fft[150:2000]
                    high_slice = fft[2000:]
                    bass = np.mean(bass_slice) if bass_slice.size > 0 else 0
                    mid = np.mean(mid_slice) if mid_slice.size > 0 else 0
                    high = np.mean(high_slice) if high_slice.size > 0 else 0
                    bands = get_selected_bands()
                    values = []
                    if "bass" in bands:
                        values.append(bass)
                    if "mid" in bands:
                        values.append(mid)
                    if "high" in bands:
                        values.append(high)
                    avg_val = np.mean(values) if values else 0
                    history.append(avg_val)
                    if len(history) > HISTORY_LEN:
                        history.pop(0)
                    avg_history = np.mean(history) if history else 1
                    intensity = max(0, avg_val - avg_history)
                    # Map intensity to brightness using cubic scaling for smoothness
                    norm_intensity = min(1.0, intensity / (SPIKE_THRESHOLD * 3))
                    cubic = norm_intensity ** 3
                    target_brightness = MIN_BRIGHTNESS + (MAX_BRIGHTNESS - MIN_BRIGHTNESS) * cubic
                    # Color: lerp between low and high color based on cubic
                    target_color = {
                        'h': lerp_hue(low_color['h'], target_hue, cubic),
                        's': lerp(low_color['s'], max(0.7, target_sat), cubic),
                        'w': lerp(low_color['w'], min(0.3, target_mix_white), cubic)
                    }
                # Smoother slide for brightness (never reaches instantly)
                display_brightness = lerp(display_brightness, target_brightness, AUDIO_ANIM_SPEED)
                # Smoother color fade
                display_hue = lerp_hue(display_hue, target_color['h'], COLOR_FADE_SPEED)
                display_sat = lerp(display_sat, target_color['s'], COLOR_FADE_SPEED)
                display_mix_white = lerp(display_mix_white, target_color['w'], COLOR_FADE_SPEED)
                request_brightness(display_brightness)
            time.sleep(0.05)
        except Exception as e:
            print("Audio loop error:", e)
            time.sleep(0.2)

threading.Thread(target=screen_color_loop, daemon=True).start()
threading.Thread(target=audio_reactive_loop, daemon=True).start()

# -------------------------
# Asyncio + Threads
# -------------------------
loop = asyncio.new_event_loop()
def loop_thread():
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(connect_ble())
        loop.run_forever()
    finally:
        loop.close()

threading.Thread(target=loop_thread, daemon=True).start()

# Kick off the animation loop
root.after(ANIM_INTERVAL_MS, animation_step)

# Initialize UI readout
update_one_color_display()

root.mainloop()

# Initialize UI readout
update_one_color_display()

root.mainloop()
