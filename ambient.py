import random
import math
from collections import deque

ADJ = [(1, 0), (-1, 0), (0, 1), (0, -1)]

# ── British car colours ──────────────────────────────────────────────────────
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
    (200,  90,  90),  # dark rose
    (255, 230, 200),  # cream
    (100,  80, 160),  # purple
    (150, 170, 150),  # muted green
]

# ── Pedestrian vest / coat colours ──────────────────────────────────────────
_VEST_COLORS = [
    (255, 160,   0),  # orange hi-vis
    (255, 220,   0),  # yellow hi-vis
    (200, 200, 200),  # grey (civilian)
    (  0, 180, 100),  # green hi-vis
    ( 50,  50, 200),  # blue jacket
    (180,  60,  60),  # red jacket
    (200, 200, 255),  # pale blue coat
    ( 80,  80,  80),  # dark anorak
]

# ── Density scoring per building style ──────────────────────────────────────
# Scores how much a neighbouring building attracts traffic to a road tile.
_BUILDING_DENSITY = {
    "tower":    10,
    "highrise": 10,
    "flats":     6,
    "office":    5,
    "shop":      4,
    "warehouse": 3,
    "semi":      2,
    "terrace":   2,
    "detached":  2,
    "bungalow":  1,
}
_GREEN_PENALTY  = -3    # green tiles actively suppress traffic
_DENSITY_RADIUS =  4    # Manhattan-distance kernel around each road tile
_DENSITY_FLOOR  = 0.05  # minimum weight so even quiet streets see a trickle


# ────────────────────────────────────────────────────────────────────────────
#  Internal helpers
# ────────────────────────────────────────────────────────────────────────────

def _road_list_from(city):
    return [
        (x, y)
        for y in range(city.height)
        for x in range(city.width)
        if city.tiles[y][x].type == "road"
    ]


def _build_density_weights(city, road_list):
    """Compute a positive density weight for every road tile.

    Inverse-distance weighting over a radius-4 kernel:
      building tiles contribute +score / Manhattan-distance
      green tiles contribute a negative penalty  / Manhattan-distance
    Result is clamped to [_DENSITY_FLOOR, ∞) so no tile is completely dead.
    """
    weights = []
    for (rx, ry) in road_list:
        score = 0.0
        for dy in range(-_DENSITY_RADIUS, _DENSITY_RADIUS + 1):
            for dx in range(-_DENSITY_RADIUS, _DENSITY_RADIUS + 1):
                if dx == 0 and dy == 0:
                    continue
                nx, ny = rx + dx, ry + dy
                tile = city.get_tile(nx, ny)
                if tile is None:
                    continue
                dist = abs(dx) + abs(dy)
                fall = 1.0 / dist
                if tile.type in ("residential", "commercial"):
                    score += _BUILDING_DENSITY.get(tile.building_style, 1) * fall
                elif tile.type == "green":
                    score += _GREEN_PENALTY * fall
        weights.append(max(_DENSITY_FLOOR, score))
    return weights


def _weighted_sample(candidates, weights):
    """Return one element chosen proportionally to its weight."""
    total = sum(weights)
    if total <= 0:
        return random.choice(candidates)
    r = random.random() * total
    cumulative = 0.0
    for item, w in zip(candidates, weights):
        cumulative += w
        if r <= cumulative:
            return item
    return candidates[-1]


def _bfs(start, goal, road_set, blocked=None):
    """BFS on a set of road tiles, optionally avoiding *blocked*."""
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


# ────────────────────────────────────────────────────────────────────────────
#  Civilian cars
# ────────────────────────────────────────────────────────────────────────────

class AmbientTraffic:
    """Cars that pick random road-to-road routes and drive them.

    Start and goal tiles are drawn from the density-weighted distribution, so
    high-density urban streets carry proportionally more traffic.  Urban cars
    also drive *slower* (traffic calming, junctions, pedestrian crossings).
    """

    MAX_CARS  = 28    # raised from 14; density weighting prevents ugly crowding
    MIN_PATH  = 6     # discard very short trips
    MAX_TRIES = 18

    def __init__(self):
        self.cars           = []
        self._road_set      = set()
        self._road_list     = []
        self._road_weights  = []
        self._road_density  = {}   # {tile: weight} for O(1) per-tile lookup
        self._built_for     = None

    # ── road graph ----------------------------------------------------------
    def _rebuild(self, city):
        self._road_list    = _road_list_from(city)
        self._road_set     = set(self._road_list)
        self._road_weights = _build_density_weights(city, self._road_list)
        self._road_density = dict(zip(self._road_list, self._road_weights))
        self._built_for    = city

    # ── update --------------------------------------------------------------
    def update(self, dt, city):
        if self._built_for is not city:
            self._rebuild(city)
        if not self._road_list:
            return

        blocked = getattr(city, "road_works_tiles", set())

        # Spawn: higher global rate to populate the city; density weighting
        # naturally concentrates cars on urban roads without extra logic.
        if len(self.cars) < self.MAX_CARS and random.random() < dt * 2.4:
            for _ in range(self.MAX_TRIES):
                start = _weighted_sample(self._road_list, self._road_weights)
                goal  = _weighted_sample(self._road_list, self._road_weights)
                if start == goal:
                    continue
                path = _bfs(start, goal, self._road_set, blocked)
                if path and len(path) >= self.MIN_PATH:
                    d = self._road_density.get(start, 1.0)
                    # Urban streets → slower (traffic calming & junctions)
                    if d > 6:
                        speed = random.uniform(1.6, 3.2)
                    elif d > 3:
                        speed = random.uniform(2.4, 4.2)
                    else:
                        speed = random.uniform(3.2, 5.8)
                    self.cars.append({
                        "x":      float(start[0]),
                        "y":      float(start[1]),
                        "path":   path,
                        "speed":  speed,
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


# ────────────────────────────────────────────────────────────────────────────
#  Landfill seagulls
# ────────────────────────────────────────────────────────────────────────────

class AmbientBirds:
    """Seagulls that orbit the landfill in lazy circles."""

    MAX_BIRDS = 10

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
                "lcx":    lcx,
                "lcy":    lcy,
                "wing":   0.0,
                "wing_sp": random.uniform(4.0, 8.0),
            })

        for b in self.birds:
            b["angle"]  += b["speed"]  * dt
            b["bob"]    += b["bob_sp"] * dt
            b["wing"]   += b["wing_sp"] * dt


# ────────────────────────────────────────────────────────────────────────────
#  Street pedestrians
# ────────────────────────────────────────────────────────────────────────────

class AmbientPeds:
    """Pedestrians who wander along road tiles.

    Urban roads (near towers, offices, shops) attract many more pedestrians;
    green-area roads are quiet.  Peds near high-density tiles also walk
    *slower*, simulating window-shoppers and commuters at junctions.
    """

    MAX_PEDS  = 42    # raised from 20
    MIN_PATH  = 3
    MAX_TRIES = 12

    def __init__(self):
        self.peds           = []
        self._road_set      = set()
        self._road_list     = []
        self._road_weights  = []
        self._road_density  = {}
        self._built_for     = None

    def _rebuild(self, city):
        self._road_list    = _road_list_from(city)
        self._road_set     = set(self._road_list)
        self._road_weights = _build_density_weights(city, self._road_list)
        self._road_density = dict(zip(self._road_list, self._road_weights))
        self._built_for    = city

    def update(self, dt, city, on_strike=False):
        if self._built_for is not city:
            self._rebuild(city)
        if not self._road_list:
            return

        # During a strike peds cluster near depot (handled visually in renderer)
        if on_strike:
            return

        blocked = getattr(city, "road_works_tiles", set())

        # Higher spawn rate than traffic; density weighting concentrates them
        # in commercial / residential cores.
        if len(self.peds) < self.MAX_PEDS and random.random() < dt * 3.4:
            for _ in range(self.MAX_TRIES):
                start = _weighted_sample(self._road_list, self._road_weights)
                goal  = _weighted_sample(self._road_list, self._road_weights)
                if start == goal:
                    continue
                path = _bfs(start, goal, self._road_set, blocked)
                if path and len(path) >= self.MIN_PATH:
                    d = self._road_density.get(start, 1.0)
                    # Shoppers in busy zones amble; walkers in quiet zones stride
                    if d > 6:
                        speed = random.uniform(0.35, 0.75)
                    elif d > 3:
                        speed = random.uniform(0.65, 1.20)
                    else:
                        speed = random.uniform(0.90, 1.60)
                    self.peds.append({
                        "x":      float(start[0]),
                        "y":      float(start[1]),
                        "path":   path,
                        "speed":  speed,
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


# ────────────────────────────────────────────────────────────────────────────
#  Red Phone Boxes
# ────────────────────────────────────────────────────────────────────────────

class AmbientPhoneBoxes:
    """Iconic British K6 red telephone kiosks scattered sparsely on street corners."""

    def __init__(self):
        self.boxes      = []
        self._built_for = None

    def _rebuild(self, city):
        self.boxes = []
        road_list = _road_list_from(city)
        road_set = set(road_list)
        corners = []

        for (x, y) in road_list:
            # Check adjacent tiles to discover true corner nodes
            neighbors = []
            for dx, dy in ADJ:
                if (x + dx, y + dy) in road_set:
                    neighbors.append((dx, dy))
            
            # A clean corner junction will feature exactly two adjacent perpendicular roads
            if len(neighbors) == 2:
                (dx1, dy1), (dx2, dy2) = neighbors
                if dx1 != dx2 and dy1 != dy2:
                    corners.append((x, y))

        # Maintain true scarcity: Sample roughly 1% of valid street corners
        if corners:
            num_boxes = max(1, len(corners) // 100)
            chosen_corners = random.sample(corners, min(len(corners), num_boxes))
            for (cx, cy) in chosen_corners:
                self.boxes.append({
                    "x":     float(cx),
                    "y":     float(cy),
                    "color": (210, 35, 35),  # Post Office Red
                })
        self._built_for = city

    def update(self, dt, city):
        if self._built_for is not city:
            self._rebuild(city)


# ────────────────────────────────────────────────────────────────────────────
#  Red Pillar Post Boxes
# ────────────────────────────────────────────────────────────────────────────

class AmbientPostBoxes:
    """Royal Mail-red pillar post boxes. Sparser than phone boxes and set
    along straight kerbside runs rather than junctions, so the two props
    don't cluster on top of each other."""

    def __init__(self):
        self.boxes      = []
        self._built_for = None

    def _rebuild(self, city):
        self.boxes = []
        road_list = _road_list_from(city)
        road_set = set(road_list)
        midstreet = []

        for (x, y) in road_list:
            neighbors = [(dx, dy) for dx, dy in ADJ if (x + dx, y + dy) in road_set]
            # A straight kerbside run has exactly two road neighbours running
            # in opposite directions -- not a junction, not a corner.
            if len(neighbors) == 2:
                (dx1, dy1), (dx2, dy2) = neighbors
                if dx1 == -dx2 and dy1 == -dy2:
                    midstreet.append((x, y))

        # Keep them rarer than phone boxes still: roughly 1 in every 140
        # eligible kerbside tiles.
        if midstreet:
            num_boxes = max(1, len(midstreet) // 140)
            chosen = random.sample(midstreet, min(len(midstreet), num_boxes))
            for (cx, cy) in chosen:
                self.boxes.append({
                    "x":     float(cx),
                    "y":     float(cy),
                    "color": (175, 25, 25),
                })
        self._built_for = city

    def update(self, dt, city):
        if self._built_for is not city:
            self._rebuild(city)


# ────────────────────────────────────────────────────────────────────────────
#  Aircraft
# ────────────────────────────────────────────────────────────────────────────

class AmbientAircraft:
    """A rare, distant airliner that crosses the sky above the borough from
    one side of the map to the opposite side, then disappears. Pure scenery
    -- no gameplay effect, just makes the city feel alive."""

    MIN_GAP = 70.0       # seconds of quiet between flights, minimum
    MAX_GAP = 190.0      # maximum

    def __init__(self):
        self.planes = []
        self._timer = random.uniform(25.0, self.MIN_GAP)

    def update(self, dt, city):
        self._timer -= dt
        if self._timer <= 0 and not self.planes:
            self._spawn(city)
            self._timer = random.uniform(self.MIN_GAP, self.MAX_GAP)

        for p in list(self.planes):
            p["t"] += dt / p["duration"]
            if p["t"] >= 1.0:
                self.planes.remove(p)

    def _spawn(self, city):
        w, h = city.width, city.height
        margin = 14
        axis = random.choice(("ns", "ew"))
        if axis == "ns":
            x = random.uniform(w * 0.15, w * 0.85)
            sy, ey = -margin, h + margin
            if random.random() < 0.5:
                sy, ey = ey, sy
            start, end = (x, sy), (x + random.uniform(-8, 8), ey)
        else:
            y = random.uniform(h * 0.15, h * 0.85)
            sx, ex = -margin, w + margin
            if random.random() < 0.5:
                sx, ex = ex, sx
            start, end = (sx, y), (ex, y + random.uniform(-8, 8))
        self.planes.append({
            "start":    start,
            "end":      end,
            "t":        0.0,
            "duration": random.uniform(24.0, 36.0),
            "blink":    random.uniform(0, math.tau),
        })


# ────────────────────────────────────────────────────────────────────────────
#  Container
# ────────────────────────────────────────────────────────────────────────────

class AmbientState:
    """Single object wired into main.py update/render loops."""

    SNOW_BUILD_SECONDS = 40.0   # seconds of snowfall to reach full settle
    SNOW_MELT_SECONDS  = 90.0   # seconds (no snow) to fully clear again

    def __init__(self):
        self.traffic     = AmbientTraffic()
        self.birds       = AmbientBirds()
        self.peds        = AmbientPeds()
        self.phone_boxes = AmbientPhoneBoxes()
        self.post_boxes  = AmbientPostBoxes()
        self.aircraft    = AmbientAircraft()
        self.snow_level  = 0.0   # 0..1, how deeply snow has settled on the city

    def update(self, dt, city, fleet=None, economy=None):
        on_strike = getattr(fleet, "on_strike", False) if fleet else False
        self.traffic.update(dt, city)
        self.birds.update(dt, city)
        self.peds.update(dt, city, on_strike=on_strike)
        self.phone_boxes.update(dt, city)
        self.post_boxes.update(dt, city)
        self.aircraft.update(dt, city)
        self._update_snow(dt, economy)

    def _update_snow(self, dt, economy):
        weather = getattr(economy, "weather", None) if economy else None
        if weather == "snow":
            self.snow_level = min(1.0, self.snow_level + dt / self.SNOW_BUILD_SECONDS)
        else:
            self.snow_level = max(0.0, self.snow_level - dt / self.SNOW_MELT_SECONDS)