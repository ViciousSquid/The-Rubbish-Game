"""
ambient.py
==========

Purely cosmetic city-life systems.  Nothing here affects gameplay.

  AmbientTraffic  — civilian cars driving along the road network
  AmbientBirds    — seagulls orbiting the landfill
  AmbientPeds     — pedestrians ambling on road tiles
"""
import random
import math
from collections import deque

ADJ = [(1, 0), (-1, 0), (0, 1), (0, -1)]

# Believable British car colours
_CAR_COLORS = [
    (180, 40,  40),   # red
    (40, 100, 180),   # blue
    (60, 160,  80),   # green
    (220, 200,  40),  # yellow
    (165, 165, 165),  # silver
    (45,  45,  45),   # black
    (210, 125,  45),  # orange
    (170, 180, 220),  # pale blue
    (175, 155, 200),  # mauve
    (85, 135, 100),   # sage
    (230, 230, 230),  # white
]

# High-vis vest colours for pedestrians
_VEST_COLORS = [
    (255, 160,   0),  # orange
    (255, 220,   0),  # yellow
    (200, 200, 200),  # grey (civilian)
    (  0, 180, 100),  # green hi-vis
]


# ---------------------------------------------------------------------------
#  Helpers
# ---------------------------------------------------------------------------

def _road_list_from(city):
    return [
        (x, y)
        for y in range(city.height)
        for x in range(city.width)
        if city.tiles[y][x].type == "road"
    ]


def _bfs(start, goal, road_set, blocked=None):
    """BFS on a set of road tiles, optionally avoiding `blocked`."""
    if blocked is None:
        blocked = set()
    if start == goal:
        return []
    seen = {start}
    prev = {}
    q = deque([start])
    while q:
        cur = q.popleft()
        for ox, oy in ADJ:
            nb = (cur[0] + ox, cur[1] + oy)
            if nb in seen or nb not in road_set or nb in blocked:
                continue
            seen.add(nb)
            prev[nb] = cur
            if nb == goal:
                path = [nb]
                p = cur
                while p != start:
                    path.append(p)
                    p = prev[p]
                path.reverse()
                return path
            q.append(nb)
    return None


# ---------------------------------------------------------------------------
#  Civilian cars
# ---------------------------------------------------------------------------

class AmbientTraffic:
    """Cars that pick random road-to-road routes and drive them."""

    MAX_CARS  = 14
    MIN_PATH  = 6    # discard very short trips
    MAX_TRIES = 12

    def __init__(self):
        self.cars       = []
        self._road_set  = set()
        self._road_list = []
        self._built_for = None

    # -- road graph ----------------------------------------------------------
    def _rebuild(self, city):
        self._road_list = _road_list_from(city)
        self._road_set  = set(self._road_list)
        self._built_for = city

    # -- update --------------------------------------------------------------
    def update(self, dt, city):
        if self._built_for is not city:
            self._rebuild(city)
        if not self._road_list:
            return

        blocked = getattr(city, "road_works_tiles", set())

        # Spawn
        if len(self.cars) < self.MAX_CARS and random.random() < dt * 1.4:
            for _ in range(self.MAX_TRIES):
                start = random.choice(self._road_list)
                goal  = random.choice(self._road_list)
                if start == goal:
                    continue
                path = _bfs(start, goal, self._road_set, blocked)
                if path and len(path) >= self.MIN_PATH:
                    self.cars.append({
                        "x":      float(start[0]),
                        "y":      float(start[1]),
                        "path":   path,
                        "speed":  random.uniform(2.0, 5.0),
                        "color":  random.choice(_CAR_COLORS),
                        "facing": 1,
                    })
                    break

        # Move
        for car in list(self.cars):
            if not car["path"]:
                self.cars.remove(car)
                continue
            tx, ty = car["path"][0]
            dx, dy = tx - car["x"], ty - car["y"]
            dist   = math.hypot(dx, dy)
            if abs(dx) > 0.01:
                car["facing"] = 1 if dx > 0 else -1
            step = car["speed"] * dt
            if step >= dist:
                car["x"], car["y"] = float(tx), float(ty)
                car["path"].pop(0)
            else:
                car["x"] += dx / dist * step
                car["y"] += dy / dist * step


# ---------------------------------------------------------------------------
#  Landfill seagulls
# ---------------------------------------------------------------------------

class AmbientBirds:
    """Seagulls that orbit the landfill in lazy circles."""

    MAX_BIRDS = 8

    def __init__(self):
        self.birds = []

    def update(self, dt, city):
        lf = getattr(city, "landfill", None)
        if not lf:
            return
        lcx, lcy = lf["cx"], lf["cy"]

        while len(self.birds) < self.MAX_BIRDS:
            self.birds.append({
                "angle":  random.uniform(0, math.tau),
                "radius": random.uniform(1.8, 5.0),
                "speed":  random.uniform(0.22, 0.60) * random.choice([-1, 1]),
                "bob":    random.uniform(0, math.tau),
                "bob_sp": random.uniform(1.0, 2.2),
                "lcx": lcx, "lcy": lcy,
                "wing":   0.0,    # wing-flap phase
                "wing_sp":random.uniform(4.0, 8.0),
            })

        for b in self.birds:
            b["angle"]  += b["speed"]  * dt
            b["bob"]    += b["bob_sp"] * dt
            b["wing"]   += b["wing_sp"]* dt


# ---------------------------------------------------------------------------
#  Street pedestrians
# ---------------------------------------------------------------------------

class AmbientPeds:
    """Pedestrians who wander along road tiles and linger near buildings."""

    MAX_PEDS  = 20
    MIN_PATH  = 3
    MAX_TRIES = 8

    def __init__(self):
        self.peds       = []
        self._road_set  = set()
        self._road_list = []
        self._built_for = None

    def _rebuild(self, city):
        self._road_list = _road_list_from(city)
        self._road_set  = set(self._road_list)
        self._built_for = city

    def update(self, dt, city, on_strike=False):
        if self._built_for is not city:
            self._rebuild(city)
        if not self._road_list:
            return

        # During a strike, peds cluster near depot (handled visually in renderer)
        if on_strike:
            return

        blocked = getattr(city, "road_works_tiles", set())

        # Spawn
        if len(self.peds) < self.MAX_PEDS and random.random() < dt * 1.8:
            for _ in range(self.MAX_TRIES):
                start = random.choice(self._road_list)
                goal  = random.choice(self._road_list)
                if start == goal:
                    continue
                path = _bfs(start, goal, self._road_set, blocked)
                if path and len(path) >= self.MIN_PATH:
                    self.peds.append({
                        "x":      float(start[0]),
                        "y":      float(start[1]),
                        "path":   path,
                        "speed":  random.uniform(0.5, 1.4),
                        "vest":   random.choice(_VEST_COLORS),
                        "facing": 1,
                        "bob":    random.uniform(0, math.tau),
                        "bob_sp": random.uniform(5.0, 8.0),
                    })
                    break

        # Move
        for ped in list(self.peds):
            if not ped["path"]:
                self.peds.remove(ped)
                continue
            tx, ty = ped["path"][0]
            dx, dy = tx - ped["x"], ty - ped["y"]
            dist   = math.hypot(dx, dy)
            if abs(dx) > 0.01:
                ped["facing"] = 1 if dx > 0 else -1
            ped["bob"] += ped["bob_sp"] * dt
            step = ped["speed"] * dt
            if step >= dist:
                ped["x"], ped["y"] = float(tx), float(ty)
                ped["path"].pop(0)
            else:
                ped["x"] += dx / dist * step
                ped["y"] += dy / dist * step


# ---------------------------------------------------------------------------
#  Container
# ---------------------------------------------------------------------------

class AmbientState:
    """Single object wired into main.py update/render loops."""

    def __init__(self):
        self.traffic = AmbientTraffic()
        self.birds   = AmbientBirds()
        self.peds    = AmbientPeds()

    def update(self, dt, city, fleet=None):
        on_strike = getattr(fleet, "on_strike", False) if fleet else False
        self.traffic.update(dt, city)
        self.birds.update(dt, city)
        self.peds.update(dt, city, on_strike=on_strike)
