import pygame
import socket
import struct
import sys

# --- CONFIG ---
UDP_PORT = 20777
WINDOW_SIZE = (1280, 720)
FPS = 60

# COLORS
BLACK = (10, 10, 15)
GREEN = (0, 255, 0)
NEON_GREEN = (50, 255, 50)
RED = (255, 50, 50)
CYAN = (0, 255, 255)
WHITE = (220, 220, 220)
GRAY = (60, 60, 60)
ORANGE = (255, 165, 0)
DARK_BG = (20, 20, 25)

# PACKET NAMES
PACKET_NAMES = {
    0: "Motion", 1: "Session", 2: "Lap Data", 3: "Event",
    4: "Partic.", 5: "Setups", 6: "Telem.", 7: "Status",
    8: "Class", 9: "Lobby", 10: "Damage", 11: "History"
}

class TrackMap:
    def __init__(self, rect):
        self.rect = rect
        self.points = []
        self.min_x = -500; self.max_x = 500
        self.min_z = -500; self.max_z = 500

    def add_point(self, x, z):
        if not self.points or (abs(x - self.points[-1][0]) > 1 or abs(z - self.points[-1][1]) > 1):
            self.points.append((x, z))
            if x < self.min_x: self.min_x = x
            if x > self.max_x: self.max_x = x
            if z < self.min_z: self.min_z = z
            if z > self.max_z: self.max_z = z

    def to_screen(self, x, z):
        w = max(1, self.max_x - self.min_x)
        h = max(1, self.max_z - self.min_z)
        nx = (x - self.min_x) / w
        nz = (z - self.min_z) / h
        
        sx = self.rect.x + 20 + (nx * (self.rect.width - 40))
        sy = self.rect.y + self.rect.height - 20 - (nz * (self.rect.height - 40))
        return int(sx), int(sy)

def main():
    pygame.init()
    screen = pygame.display.set_mode(WINDOW_SIZE)
    pygame.display.set_caption("F1 Telemetry Dashboard (Header Fix)")
    clock = pygame.time.Clock()
    
    font = pygame.font.SysFont("Consolas", 14)
    header_font = pygame.font.SysFont("Consolas", 20, bold=True)
    grid_font = pygame.font.SysFont("Consolas", 16)

    # SOCKET
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("0.0.0.0", UDP_PORT))
    sock.setblocking(False)

    # STATE
    cars = {} 
    track = TrackMap(pygame.Rect(500, 60, 760, 640))
    player_idx = 0
    packet_counts = {i: 0 for i in range(12)}
    
    current_speed = 0
    current_throttle = 0

    running = True
    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT: running = False

        # --- 1. DATA INGESTION ---
        try:
            while True:
                data, _ = sock.recvfrom(2048)
                if len(data) < 24: continue
                
                # --- THE FIX IS HERE ---
                # We read Byte 5 directly. No unpacking guesswork.
                pid = data[5] 
                packet_counts[pid] = packet_counts.get(pid, 0) + 1

                # PACKET 0: MOTION
                if pid == 0:
                    player_idx = data[20]
                    for i in range(22):
                        off = 24 + (i * 60)
                        x, y, z = struct.unpack('<fff', data[off:off+12])
                        if x != 0:
                            if i not in cars: cars[i] = {'dist': 0, 'raw_pos': 0}
                            cars[i]['x'] = x; cars[i]['z'] = z
                            if i == player_idx: track.add_point(x, z)

                # PACKET 2: LAP DATA
                elif pid == 2:
                    for i in range(22):
                        off = 24 + (i * 43)
                        dist = struct.unpack('<f', data[off+16:off+20])[0]
                        raw_pos = data[off+33]
                        if i in cars:
                            cars[i]['dist'] = dist
                            cars[i]['raw_pos'] = raw_pos

                # PACKET 6: TELEMETRY
                elif pid == 6:
                    p_off = 24 + (player_idx * 60)
                    current_speed = struct.unpack('<H', data[p_off:p_off+2])[0]
                    current_throttle = struct.unpack('<f', data[p_off+2:p_off+6])[0]

        except BlockingIOError: pass

        # --- 2. RENDER ---
        screen.fill(BLACK)

        # LEFT: Packet Flow
        pygame.draw.rect(screen, DARK_BG, (10, 10, 200, 700))
        screen.blit(header_font.render("PACKET FLOW", True, CYAN), (20, 20))
        y = 60
        for i in range(12):
            cnt = packet_counts[i]
            col = GREEN if cnt > 0 else GRAY
            screen.blit(font.render(f"{PACKET_NAMES.get(i)}: {cnt}", True, col), (20, y))
            y += 25

        # MIDDLE: Live Grid
        pygame.draw.rect(screen, DARK_BG, (220, 10, 270, 700))
        screen.blit(header_font.render("LIVE GRID", True, ORANGE), (230, 20))
        screen.blit(font.render(f"SPD: {current_speed} KPH", True, WHITE), (230, 50))
        screen.blit(font.render(f"THR: {int(current_throttle*100)}%", True, WHITE), (360, 50))
        pygame.draw.line(screen, GRAY, (230, 80), (480, 80), 1)

        y = 100
        # Sort Grid by Distance
        active_cars = {k: v for k, v in cars.items() if v.get('dist', 0) > 1}
        sorted_grid = sorted(active_cars.items(), key=lambda x: x[1]['dist'], reverse=True)
        
        rank = 1
        for idx, car in sorted_grid:
            is_player = (idx == player_idx)
            dist_km = car['dist'] / 1000.0
            txt = f"P{rank:02d} | Car {idx:02d} | {dist_km:.2f}km"
            col = NEON_GREEN if is_player else WHITE
            screen.blit(grid_font.render(txt, True, col), (230, y))
            y += 25
            rank += 1
            if y > 700: break

        # RIGHT: Map
        pygame.draw.rect(screen, GRAY, track.rect, 2)
        if len(track.points) > 2:
            pts = [track.to_screen(p[0], p[1]) for p in track.points]
            pygame.draw.lines(screen, (80, 80, 80), False, pts, 3)

        for idx, car in active_cars.items():
            if 'x' in car:
                sx, sy = track.to_screen(car['x'], car['z'])
                col = NEON_GREEN if idx == player_idx else RED
                pygame.draw.circle(screen, col, (sx, sy), 5)

        pygame.display.flip()
        clock.tick(FPS)

    pygame.quit()

if __name__ == "__main__":
    main()