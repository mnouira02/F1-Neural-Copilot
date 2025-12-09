import socket
import struct
import time
import cv2
import numpy as np
import mss
import json
import os

# --- LOAD CONFIGURATION ---
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(BASE_DIR, "config", "settings.json")

if not os.path.exists(CONFIG_PATH):
    print(f"❌ Error: {CONFIG_PATH} not found.")
    exit()

with open(CONFIG_PATH, "r") as f:
    config = json.load(f)

# MAP CONFIG KEYS
TARGET_IP = config["network"]["target_brain_ip"] # <--- UPDATED
TARGET_PORT = config["network"]["vision_port"]

# --- SETUP SCREEN CAPTURE ---
sct = mss.mss()
try:
    monitor = sct.monitors[1] # Monitor 1
except IndexError:
    monitor = sct.monitors[0] # Fallback

# Region of Interest (Center of screen)
width = monitor["width"]
height = monitor["height"]
roi = {
    "top": int(height * 0.2),    
    "left": int(width * 0.1),    
    "width": int(width * 0.8),   
    "height": int(height * 0.6)  
}

print(f"👁️ Eye Sender Online.")
print(f"🎯 Target Brain: {TARGET_IP}:{TARGET_PORT}")

while True:
    try:
        client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        client_socket.connect((TARGET_IP, TARGET_PORT))
        connection = client_socket.makefile('wb')

        print("✅ Linked to Brain. Streaming Vision...")

        while True:
            # 1. Grab & Convert
            raw_img = sct.grab(roi)
            img_np = np.array(raw_img)
            
            # 2. Resize (640x360 standard for Vision Models)
            frame = cv2.resize(img_np, (640, 360))
            
            # 3. Compress (JPEG Q80)
            encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), 80]
            result, encimg = cv2.imencode('.jpg', frame, encode_param)
            data = encimg.tobytes()
            size = len(data)

            # 4. Send Header + Data
            client_socket.sendall(struct.pack(">L", size) + data)
            
            # 5. Throttle (1 FPS)
            time.sleep(1.0) 

    except Exception as e:
        print(f"⚠️ Connection lost: {e}. Retrying in 3s...")
        time.sleep(3)