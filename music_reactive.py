import numpy as np
import pyaudio
import time
from color_utils import lerp, lerp_hue

def audio_reactive_loop(
    smart_audio,
    get_selected_bands,
    target_hue,
    target_sat,
    target_mix_white,
    display_hue,
    display_sat,
    display_mix_white,
    display_brightness,
    request_brightness
):
    CHUNK = 1024
    RATE = 44100
    history = []
    HISTORY_LEN = 30
    MIN_BRIGHTNESS = 8
    MAX_BRIGHTNESS = 80
    SPIKE_THRESHOLD = 30
    AUDIO_ANIM_SPEED = 0.18
    COLOR_FADE_SPEED = 0.18
    low_color = {'h': 0.0, 's': 0.2, 'w': 0.7}
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
                    norm_intensity = min(1.0, intensity / (SPIKE_THRESHOLD * 3))
                    cubic = norm_intensity ** 3
                    target_brightness = MIN_BRIGHTNESS + (MAX_BRIGHTNESS - MIN_BRIGHTNESS) * cubic
                    target_color = {
                        'h': lerp_hue(low_color['h'], target_hue, cubic),
                        's': lerp(low_color['s'], max(0.7, target_sat), cubic),
                        'w': lerp(low_color['w'], min(0.3, target_mix_white), cubic)
                    }
                display_brightness = lerp(display_brightness, target_brightness, AUDIO_ANIM_SPEED)
                display_hue = lerp_hue(display_hue, target_color['h'], COLOR_FADE_SPEED)
                display_sat = lerp(display_sat, target_color['s'], COLOR_FADE_SPEED)
                display_mix_white = lerp(display_mix_white, target_color['w'], COLOR_FADE_SPEED)
                request_brightness(display_brightness)
            time.sleep(0.05)
        except Exception as e:
            print("Audio loop error:", e)
            time.sleep(0.2)
