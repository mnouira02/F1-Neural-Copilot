import socket, pyaudio, threading, time, json, os, sys, ctypes
import numpy as np

print("\n🎧 F1 HEADSET | PRODUCTION CLIENT (RESAMPLING ACTIVE)")

# --- LOAD CONFIGURATION ---
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(BASE_DIR, "config", "settings.json")

try:
    with open(CONFIG_PATH, "r") as f: C = json.load(f)
    # MAPPING NEW KEYS
    BRAIN_IP = C["network"]["target_brain_ip"]
    RX_PORT = C["network"]["voice_target_port"] # 6666
    TX_PORT = C["network"]["ears_port"]         # 7777
    MIC_IDX = C.get("audio", {}).get("mic_index", 1)
except Exception as e:
    print(f"⚠️ Config Error: {e}")
    sys.exit(1)

# --- HARDWARE: XINPUT ---
try: xinput = ctypes.windll.xinput1_4
except: xinput = ctypes.windll.xinput9_1_0

class XINPUT_GAMEPAD(ctypes.Structure):
    _fields_ = [("wButtons", ctypes.c_ushort), ("bLeftTrigger", ctypes.c_ubyte),
                ("bRightTrigger", ctypes.c_ubyte), ("sThumbLX", ctypes.c_short),
                ("sThumbLY", ctypes.c_short), ("sThumbRX", ctypes.c_short),
                ("sThumbRY", ctypes.c_short)]

class XINPUT_STATE(ctypes.Structure): _fields_ = [("dwPacketNumber", ctypes.c_ulong), ("Gamepad", XINPUT_GAMEPAD)]

def is_rb_pressed(idx=0):
    state = XINPUT_STATE()
    if xinput.XInputGetState(idx, ctypes.byref(state)) == 0:
        return (state.Gamepad.wButtons & 0x0200) != 0 
    return False

# --- SYSTEM STATE ---
class Headset:
    def __init__(self):
        self.tx_socket = None
        self.talking = False
        self.lock = threading.Lock()
        self.pa = pyaudio.PyAudio()

    def audio_callback(self, in_data, frame_count, time_info, status):
        if self.talking:
            with self.lock:
                if self.tx_socket:
                    try: self.tx_socket.send(in_data)
                    except: pass
        return (None, pyaudio.paContinue)

    def start_receiver(self):
        def _listen():
            print(f"   ✅ RX Active (UDP {RX_PORT})")
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                s.bind(("0.0.0.0", RX_PORT))
                stream = self.pa.open(format=pyaudio.paInt16, channels=1, rate=24000, output=True)
                while True: 
                    try:
                        data, addr = s.recvfrom(4096)
                        stream.write(data)
                    except: pass
            except Exception as e: print(f"   ❌ RX Error: {e}")
        threading.Thread(target=_listen, daemon=True).start()

    def start_sender(self):
        print(f"   ✅ TX Active (Mic {MIC_IDX}) -> Hold RB to talk")
        try:
            self.pa.open(format=pyaudio.paInt16, channels=1, rate=16000, input=True,
                         input_device_index=MIC_IDX, frames_per_buffer=1024,
                         stream_callback=self.audio_callback).start_stream()
        except Exception as e:
            print(f"   ❌ Mic Error: {e}. Check 'mic_index' in settings.json.")
            return

        while True:
            if is_rb_pressed(0): 
                if not self.talking:
                    print("   🎙️  [LIVE]           ", end="\r")
                    try:
                        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                        s.settimeout(0.5); s.connect((BRAIN_IP, TX_PORT))
                        with self.lock: self.tx_socket = s
                        self.talking = True
                    except: pass 
            else:
                if self.talking:
                    print("   ✅ [SENT]           ", end="\r")
                    self.talking = False
                    with self.lock:
                        if self.tx_socket:
                            try: self.tx_socket.close()
                            except: pass
                            self.tx_socket = None
            time.sleep(0.01)

if __name__ == "__main__":
    if 'numpy' not in sys.modules:
        try: import numpy
        except ImportError: sys.exit(1)

    app = Headset()
    app.start_receiver()
    try: app.start_sender()
    except KeyboardInterrupt: print("\n   🛑 Shutdown.")