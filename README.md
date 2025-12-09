# 🏎️ F1 Neural Copilot

![Python](https://img.shields.io/badge/Python-3.10%2B-blue)
![AI](https://img.shields.io/badge/AI-Llama3.2%20%7C%20Whisper-purple)
![Computer Vision](https://img.shields.io/badge/Vision-OpenCV-green)
![Status](https://img.shields.io/badge/Status-Operational-green)

**F1 Neural Copilot** is a local, privacy-first race engineer for F1 202x simulators. Unlike standard voice assistants, this system runs entirely on your local hardware using a distributed architecture to ensure zero FPS loss on the gaming rig.

It listens to your voice, "watches" the track conditions via computer vision, analyzes real-time telemetry packets (UDP), and delivers strategic advice using a custom LLM personality.

## 🧠 Architecture

The system is designed to run on a dedicated **"Brain PC" (Machine B)** while communicating with the **"Gaming Rig" (Machine A)** via a local network.

### The Brain (Machine B)
* **Core Logic:** Runs the `main.py` reasoning loop.
* **Ears (Whisper):** Transcribes voice commands in <500ms using CUDA.
* **Brain (Llama 3.2):** Interprets driver intent and queries live telemetry state.
* **Voice (Piper):** Synthesizes engineer-style audio with injected radio static effects.

### The Senses (Machine A)
* **Eyes (Vision Sender):** Captures the game screen, compresses it, and streams it to the Brain for weather/incident analysis (`src/vision_sender.py`).
* **Mouth (PTT Controller):** Captures microphone audio with a pre-roll buffer and sends it to the Brain via TCP (`src/ptt_controller.py`).

## ✨ Technical Highlights

### 1. Visual Weather Verification
While F1 telemetry provides "surface wetness" data, it can lag behind visual reality. The **Vision Sender** uses OpenCV to monitor the screen in real-time. This dual-verification system allows the AI to confirm "It looks like rain" visually before the track physics fully update, providing an early strategic advantage.

### 2. Solving the "Grey Car" Bug
Standard F1 telemetry libraries often fail to map driver names correctly. This project implements a manual byte-level decoder for Packet 4 (Participants), targeting specific offsets (Byte 24 + 54) to extract correct Team IDs and Names directly from the binary stream.

### 3. Distributed Networking
To handle high-frequency data without lag:
* **Telemetry:** 20Hz UDP Broadcasting (Game -> Dashboard).
* **Voice:** TCP stream with pre-roll buffers to prevent "cut-off" words.
* **Vision:** Compressed JPEG stream over TCP.

### 4. Dynamic Context Injection
Instead of generic responses, the system builds a dynamic system prompt for every query. It injects specific variables (Gap Ahead, Position, Tire Wear) into the LLM context window at the exact moment of inference.

## 🛠️ Installation

### 1. Clone & Setup (Do this on BOTH machines)
```bash
git clone [https://github.com/mnouira02/F1-Neural-Copilot.git](https://github.com/mnouira02/F1-Neural-Copilot.git)
cd F1-Neural-Copilot
pip install -r requirements.txt
```

### 2. Configuration (config/settings.json)
Edit config/settings.json on both machines to match your network:

```json
{
  "network": {
    "udp_telemetry_port": 20777,
    "ears_port": 7777,
    "vision_port": 5555,
    "voice_target_ip": "192.168.1.X"  <-- IP address of the BRAIN PC
  }
}
```

### 3. External Tools (Brain PC Only)
Create a tools/ folder in the root directory.

FFmpeg: Place ffmpeg.exe and ffprobe.exe in tools/ffmpeg/.

Piper: Place piper.exe, necessary DLLs, and voice_model.onnx in tools/piper/.

Ollama: Ensure Ollama is running: ollama run llama3.2.

### 🚀 Usage

#### On Machine B (The Brain)
Start the central nervous system:

```bash
python src/main.py
```

#### On Machine A (The Gaming Rig)
Start the Audio Link:

```bash
python src/ptt_controller.py
```
(Hold the mapped PTT button on your controller to talk)

Start the Vision Link:

```bash
python src/vision_sender.py
```

Start F1 202x:

Telemetry Settings: UDP On, Rate 20Hz, Format 2022/2023.

### 📝 Roadmap

- [ ] Fuel Strategist: Mass-per-lap tracking for pit window prediction.
- [ ] Overtake Assistant: ERS battery tracking vs. gap delta.
- [ ] Personality Fine-tuning: LoRA training on real F1 radio transcripts.

## 📜 License
MIT License.