# 🎨 Smart LED Controller

A **Tkinter-based desktop application** to control BLE (Bluetooth Low Energy) LED strips with advanced features like smooth animations, screen color sync, and audio-reactive lighting.  

This project uses **Python, Bleak (BLE), Tkinter, Numpy, Pillow, and PyAudio** to provide a complete LED control solution with a modern UI.  

---

## ✨ Features

- 🔗 **Bluetooth LE Control** – Connects to LED strips via BLE and sends color/brightness updates.  
- 🎨 **Color Picker** – Interactive HSV color wheel and white-mix slider for smooth color selection.  
- 🔴🟢🔵 **Preset Colors** – Quick access to predefined color buttons (red, green, blue, etc.).  
- 🌗 **Brightness Control** – Smooth slider control with animation.  
- 🔌 **On/Off Control** – Easily toggle the LED strip.  
- 🖥️ **Smart Screen Sync** – Sync LED colors with the average screen color.  
- 🔊 **Audio Reactive Mode** – LEDs react to music/audio frequencies in real-time.  
  - Choose **bass, mid, high** frequency bands.  
  - Smooth brightness fading and color transitions.  
- 🎚 **Custom Input** – Set colors manually using HEX or RGB input.  
- 🚀 **Smooth Animation Engine** – Lerp-based transitions for natural lighting effects.  

---

## 📦 Requirements

Make sure you have **Python 3.9+** installed. Then install the required dependencies:

```bash
pip install -r requirements.txt
```

▶️ How to Run

Clone this repository:


```bash
git clone https://github.com/MiantsaFanirina/clk-bleddm-led-model-controller.git
cd smart-led-controller
```

Edit the configuration section in the Python file:

```bash
ADDRESS = "BE:27:62:00:3E:91"  # your LED strip BLE address
CHAR_UUID = "0000fff3-0000-1000-8000-00805f9b34fb"
```

Run the app:

```bash
python main.py
```

