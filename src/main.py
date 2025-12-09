import pygame
import socket
import struct
import threading
import time
import math
import sys
import os
import wave
import json
import ollama
from faster_whisper import WhisperModel
from pydub import AudioSegment

# Import from the renamed voice_core module
from voice_core import RaceEngineerVoice 

# --- LOAD CONFIGURATION ---
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(BASE_DIR, "config", "settings.json")

# Safety check
if not os.path.exists(CONFIG_PATH):
    print(f"❌ ERROR: Config not found at {CONFIG_PATH}")
    sys.exit(1)

with open(CONFIG_PATH, "r") as f:
    CONFIG = json.load(f)

# --- APPLY CONFIGURATION ---
UDP_PORT = CONFIG["network"]["udp_telemetry_port"]
EARS_PORT = CONFIG["network"]["ears_port"]
DEFAULT_RES = (CONFIG["display"]["width"], CONFIG["display"]["height"])
FPS = CONFIG["display"]["fps"]
WHISPER_MODEL_NAME = CONFIG["ai"]["whisper_model"]
OLLAMA_MODEL_NAME = CONFIG["ai"]["ollama_model"]

# --- TEAM COLORS ---
TEAMS = {
    0: (0, 210, 190), 1: (220, 0, 0), 2: (6, 25, 147), 3: (0, 90, 255),
    4: (0, 110, 0), 5: (255, 128, 0), 6: (240, 240, 240), 7: (43, 69, 98),
    8: (155, 0, 0), 9: (0, 144, 255), 255: (180, 0, 255)
}

# --- COLORS ---
BLACK, DARK_BG = (8, 8, 10), (15, 15, 20)
WHITE, GREEN, RED = (240, 240, 240), (50, 255, 50), (255, 50, 50)
GRAY_DEFAULT = (80, 80, 80)
CYAN, YELLOW = (0, 255, 255), (255, 215, 0)

# --- SHARED STATE ---
class SharedState:
    def __init__(self):
        self.active = True
        self.cars = {} 
        self.player_idx = 0
        self.telemetry = {
            "speed": 0, "gear": 0, "throttle": 0, 
            "lap_time": 0, "sector": 0, "track_id": -1,
            "gap_ahead": 0.0, "gap_behind": 0.0,
            "pos": "P--"
        }
        self.packet_health = {0:0, 2:0, 4:0, 6:0} 

state = SharedState()

# --- TRACK MAPPER ---
class SmartTrackMap:
    def __init__(self):
        self.points = [] 
        self.min_x = -500; self.max_x = 500
        self.min_z = -500; self.max_z = 500

    def add_point(self, x, z, sector):
        if not self.points or (abs(x - self.points[-1][0]) > 2 or abs(z - self.points[-1][1]) > 2):
            self.points.append([x, z, sector])
            self.min_x = min(self.min_x, x); self.max_x = max(self.max_x, x)
            self.min_z = min(self.min_z, z); self.max_z = max(self.max_z, z)

    def to_screen(self, x, z, draw_rect):
        w = max(1, self.max_x - self.min_x)
        h = max(1, self.max_z - self.min_z)
        nx = (x - self.min_x) / w
        nz = (z - self.min_z) / h
        
        pad_w = draw_rect.width * 0.05
        pad_h = draw_rect.height * 0.05
        
        sx = draw_rect.x + pad_w + (nx * (draw_rect.width - (pad_w*2)))
        sy = draw_rect.y + draw_rect.height - pad_h - (nz * (draw_rect.height - (pad_h*2)))
        return int(sx), int(sy)

# --- AI ENGINEER THREAD ---
class RaceEngineer(threading.Thread):
    def __init__(self):
        super().__init__()
        self.daemon = True
        self.voice = RaceEngineerVoice()
        try:
            print(f"🧠 LOADING WHISPER MODEL: {WHISPER_MODEL_NAME}...")
            self.ears = WhisperModel(WHISPER_MODEL_NAME, device="cuda", compute_type="float16")
        except Exception as e: 
            print(f"❌ WHISPER FAILED TO LOAD: {e}")
            self.ears = None

    def run(self):
        print("🧠 ENGINEER: Core Online. Waiting for Driver...")
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind(("0.0.0.0", EARS_PORT))
        s.listen(1)
        
        while True:
            try:
                conn, _ = s.accept()
                conn.settimeout(3.0) 
                
                # --- READ LOOP ---
                raw_data = b""
                while True:
                    try:
                        chunk = conn.recv(4096)
                        if not chunk: break
                        raw_data += chunk
                    except socket.timeout:
                        break
                conn.close()
                
                if not state.active: continue
                
                # Only process if we got audio
                if len(raw_data) > 4096 and self.ears:
                    wav_path = os.path.join(BASE_DIR, "cmd.wav")
                    with wave.open(wav_path, 'wb') as wf:
                        wf.setnchannels(1); wf.setsampwidth(2); wf.setframerate(16000)
                        wf.writeframes(raw_data)
                    
                    # Transcribe
                    segs, _ = self.ears.transcribe(wav_path, beam_size=5, language="en")
                    text = " ".join([x.text for x in segs]).strip()
                    
                    # Simple empty check only - NO BAD WORD FILTERING
                    if len(text) < 2: 
                        continue

                    print(f"🎤 DRIVER: {text}")
                    
                    # --- LLM QUERY ---
                    t = state.telemetry
                    
                    if t['gap_ahead'] == 0.0:
                        gap_a = "Clear Air"
                    else:
                        gap_a = f"{t['gap_ahead']:.2f}s"
                    
                    prompt = (
                        f"You are a F1 Race Engineer. Driver asked: '{text}'. "
                        f"Telemetry: [Position: {t['pos']}, Gap Ahead: {gap_a}, Gap Behind: {t['gap_behind']:.2f}s, Speed: {t['speed']} KPH]. "
                        f"Instruction: Answer the driver using the telemetry. Be ultra concise. Max 10 words. "
                        f"Do not say 'Copy that'."
                    )
                    
                    res = ollama.chat(model=OLLAMA_MODEL_NAME, messages=[{'role':'user', 'content':prompt}])
                    response_text = res['message']['content']
                    
                    print(f"   🗣️  ENGINEER: {response_text}")
                    self.voice.speak(response_text)

            except Exception as e: 
                print(f"❌ Engineer Error: {e}")
                time.sleep(0.1)


# --- MAIN GUI ---
def main():
    eng = RaceEngineer()
    eng.start()

    pygame.init()
    screen = pygame.display.set_mode(DEFAULT_RES, pygame.RESIZABLE)
    pygame.display.set_caption("F1 NEURAL COPILOT v1.0")
    clock = pygame.time.Clock()
    
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("0.0.0.0", UDP_PORT))
    sock.setblocking(False)

    track_logic = SmartTrackMap()

    print(f"✅ DASHBOARD: Listening on UDP {UDP_PORT}")

    running = True
    while running:
        # --- DYNAMIC RESIZING ---
        W, H = screen.get_size()
        RECT_GRID = pygame.Rect(int(W * 0.02), int(H * 0.12), int(W * 0.25), int(H * 0.85))
        RECT_MAP = pygame.Rect(int(W * 0.29), int(H * 0.12), int(W * 0.69), int(H * 0.85))
        
        F_SMALL = pygame.font.SysFont("Consolas", int(H * 0.015))
        F_MED = pygame.font.SysFont("Consolas", int(H * 0.022), bold=True)
        F_LARGE = pygame.font.SysFont("Consolas", int(H * 0.05), bold=True)

        # INPUT
        mouse_pos = pygame.mouse.get_pos()
        click = False
        for event in pygame.event.get():
            if event.type == pygame.QUIT: running = False
            if event.type == pygame.MOUSEBUTTONDOWN:
                if event.button == 1: click = True
        
        btn_eng = pygame.Rect(int(W * 0.02), int(H * 0.02), int(W * 0.15), int(H * 0.06))
        if click and btn_eng.collidepoint(mouse_pos):
            state.active = not state.active

        # DATA INGESTION
        try:
            while True:
                data, _ = sock.recvfrom(2048)
                if len(data) < 24: continue
                pid = data[5]
                state.packet_health[pid] = time.time()

                if pid == 0: # Motion
                    state.player_idx = data[20]
                    for i in range(22):
                        off = 24 + (i * 60)
                        x, _, z = struct.unpack('<fff', data[off:off+12])
                        if x != 0:
                            if i not in state.cars: 
                                state.cars[i] = {'dist':0, 'team':-1, 'name': f"CAR {i}"}
                            state.cars[i]['x'] = x; state.cars[i]['z'] = z
                            if i == state.player_idx:
                                track_logic.add_point(x, z, state.telemetry['sector'])

                elif pid == 2: # Lap Data
                    for i in range(22):
                        off = 24 + (i * 43)
                        dist = struct.unpack('<f', data[off+16:off+20])[0]
                        if i in state.cars: state.cars[i]['dist'] = dist
                    
                    p_off = 24 + (state.player_idx * 43)
                    state.telemetry['sector'] = data[p_off+28]
                    state.telemetry['lap_time'] = struct.unpack('<I', data[p_off+4:p_off+8])[0]

                elif pid == 4: # Participants
                    num_cars = data[24]
                    for i in range(num_cars):
                        start_byte = 25 + (i * 56)
                        team_id = data[start_byte + 3]
                        name_bytes = data[start_byte + 7 : start_byte + 7 + 48]
                        name_str = "UNK"
                        try:
                            decoded = name_bytes.decode('utf-8', errors='ignore').split('\x00')[0]
                            if len(decoded) > 1:
                                parts = decoded.split()
                                name_str = parts[-1][:3].upper() if parts else decoded[:3].upper()
                        except: pass

                        if i in state.cars:
                            state.cars[i]['team'] = team_id
                            if name_str != "UNK": state.cars[i]['name'] = name_str

                elif pid == 6: # Physics
                    p_off = 24 + (state.player_idx * 60)
                    state.telemetry['speed'] = struct.unpack('<H', data[p_off:p_off+2])[0]

        except BlockingIOError: pass

        # RENDER
        screen.fill(BLACK)

        # HEADER
        col = GREEN if state.active else RED
        pygame.draw.rect(screen, col, btn_eng, border_radius=8)
        eng_txt = F_MED.render(f"COPILOT: {'ON' if state.active else 'OFF'}", True, BLACK)
        screen.blit(eng_txt, (btn_eng.centerx - eng_txt.get_width()//2, btn_eng.centery - eng_txt.get_height()//2))

        # Time
        sec = state.telemetry['lap_time'] / 1000.0
        m, s = int(sec // 60), sec % 60
        t_str = f"LAP: {m}:{s:05.2f}"
        time_lbl = F_LARGE.render(t_str, True, WHITE)
        screen.blit(time_lbl, (W - time_lbl.get_width() - 40, int(H * 0.02)))

        # GRID PANEL
        pygame.draw.rect(screen, DARK_BG, RECT_GRID)
        grid_title = F_MED.render("LIVE STANDINGS", True, CYAN)
        screen.blit(grid_title, (RECT_GRID.x + 20, RECT_GRID.y + 10))
        
        y_offset = RECT_GRID.y + 50
        row_h = int(RECT_GRID.height / 22)
        rank = 1
        
        for idx, car in sorted_grid:
            tid = car.get('team', -1)
            t_col = TEAMS.get(tid, GRAY_DEFAULT)
            is_player = (idx == state.player_idx)
            
            gap_txt = "Leader" if rank == 1 else ""
            if rank > 1:
                d_delta = sorted_grid[rank-2][1]['dist'] - car['dist']
                t_gap = d_delta / spd_ms
                gap_txt = f"+{t_gap:.2f}s"

            bg_col = (40, 40, 60) if is_player else DARK_BG
            r_rect = pygame.Rect(RECT_GRID.x + 10, y_offset, RECT_GRID.width - 20, row_h - 4)
            pygame.draw.rect(screen, bg_col, r_rect)
            pygame.draw.rect(screen, t_col, (r_rect.x + 5, r_rect.y + 5, 5, r_rect.height - 10))
            
            name = car.get('name', f"CAR {idx}")
            row_txt = f"P{rank:02d} {name:<4} {gap_txt}"
            txt_surf = F_SMALL.render(row_txt, True, WHITE if not is_player else CYAN)
            screen.blit(txt_surf, (r_rect.x + 20, r_rect.centery - txt_surf.get_height()//2))

            y_offset += row_h
            rank += 1
            if y_offset > RECT_GRID.bottom: break

        # MAP PANEL
        pygame.draw.rect(screen, (20, 20, 25), RECT_MAP, 2)
        
        if len(track_logic.points) > 2:
            pts = track_logic.points
            step = 1 if len(pts) < 1000 else 2
            for i in range(0, len(pts)-step, step):
                p1 = track_logic.to_screen(pts[i][0], pts[i][1], RECT_MAP)
                p2 = track_logic.to_screen(pts[i+step][0], pts[i+step][1], RECT_MAP)
                if pts[i][2] != pts[i+step][2]: pygame.draw.circle(screen, WHITE, p1, 3)
                pygame.draw.line(screen, WHITE, p1, p2, 2)

        for idx, car in state.cars.items():
            if 'x' in car:
                sx, sy = track_logic.to_screen(car['x'], car['z'], RECT_MAP)
                tid = car.get('team', -1)
                t_col = TEAMS.get(tid, GRAY_DEFAULT)
                
                if idx == state.player_idx:
                    pygame.draw.circle(screen, WHITE, (sx, sy), 8, 2)
                    pygame.draw.circle(screen, CYAN, (sx, sy), 5)
                else:
                    pygame.draw.rect(screen, t_col, (sx-3, sy-3, 6, 6))
                    if 'name' in car:
                        lbl = F_SMALL.render(car['name'], True, t_col)
                        screen.blit(lbl, (sx, sy-15))

        pygame.display.flip()
        clock.tick(FPS)

if __name__ == "__main__":
    main()