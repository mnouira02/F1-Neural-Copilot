import socket
import subprocess
import os
import json
import threading
import queue
import time
import uuid
from pydub import AudioSegment

try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False

# --- LOAD CONFIGURATION ---
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(BASE_DIR, "config", "settings.json")

with open(CONFIG_PATH, "r") as f:
    CONFIG = json.load(f)

# --- SETUP PATHS ---
PIPER_EXE = os.path.join(BASE_DIR, "tools", "piper", "piper.exe")
MODEL_PATH = os.path.join(BASE_DIR, "tools", "piper", "voice_model.onnx")
FFMPEG_DIR = os.path.join(BASE_DIR, "tools", "ffmpeg")

# Configure Pydub to use local FFmpeg
if os.name == 'nt': # Only add .exe on Windows
    AudioSegment.converter = os.path.join(FFMPEG_DIR, "ffmpeg.exe")
    AudioSegment.ffmpeg = os.path.join(FFMPEG_DIR, "ffmpeg.exe")
    AudioSegment.ffprobe = os.path.join(FFMPEG_DIR, "ffprobe.exe")

class RaceEngineerVoice:
    def __init__(self):
        # Load network settings from global CONFIG
        self.target_ip = CONFIG["network"]["voice_target_ip"]
        self.target_port = CONFIG["network"]["voice_target_port"]
        
        self.speech_queue = queue.Queue()
        self.worker_thread = threading.Thread(target=self._speech_worker, daemon=True)
        self.worker_thread.start()

        print(f"🎙️  Neural Piper Voice Online. Target: {self.target_ip}:{self.target_port}")

    def speak(self, text):
        clean_text = text.replace('"', '').replace("'", "")
        self.speech_queue.put(clean_text)

    def _apply_radio_effects(self, audio_segment):
        sound = audio_segment.set_frame_rate(22050).set_channels(1)
        if not HAS_NUMPY: return sound.raw_data

        samples = np.array(sound.get_array_of_samples())
        noise = np.random.normal(0, 200, samples.shape)
        mixed = samples + noise
        mixed = np.clip(mixed, -30000, 30000)
        return mixed.astype(np.int16).tobytes()

    def _speech_worker(self):
        # Validation
        if not os.path.exists(PIPER_EXE):
            print(f"❌ CRITICAL: Piper not found at {PIPER_EXE}")
            return

        while True:
            text = self.speech_queue.get()
            if text is None: break 

            print(f"      🗣️  Engineer: \"{text}\"")
            filename = f"voice_{uuid.uuid4()}.wav"
            
            try:
                cmd = [PIPER_EXE, '--model', MODEL_PATH, '--output_file', filename]
                
                process = subprocess.Popen(
                    cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE
                )
                stdout, stderr = process.communicate(input=text.encode('utf-8'))
                
                if os.path.exists(filename):
                    sound = AudioSegment.from_wav(filename)
                    sound = sound.speedup(playback_speed=1.1)
                    raw_data = self._apply_radio_effects(sound)

                    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                    chunk_size = 512 
                    for i in range(0, len(raw_data), chunk_size):
                        chunk = raw_data[i:i+chunk_size]
                        sock.sendto(chunk, (self.target_ip, self.target_port))
                        time.sleep(0.004)
                    sock.close()
            except Exception as e:
                print(f"      ❌ Audio Error: {e}")
            finally:
                if os.path.exists(filename):
                    try: os.remove(filename)
                    except: pass
            
            self.speech_queue.task_done()
            time.sleep(0.2)