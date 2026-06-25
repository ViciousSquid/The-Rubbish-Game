import random
from roads import RoadGenerator

# ---------------------------------------------------------------------------
#  Collection areas (rounds)
# ---------------------------------------------------------------------------
# The borough is divided into a grid of AREA_COLS x AREA_ROWS "rounds". Every
# property in a round is emptied on the same weekday, exactly like a real UK
# council collection round. The player plans which day each round falls on.
AREA_COLS = 4
AREA_ROWS = 3                       # -> 12 rounds

DAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

# British-sounding ward names (a couple of Welsh ones for Cardiff flavour).
AREA_NAMES = [
    "Northgate", "Elmwood", "Riverside", "St Catherine's",
    "Oakfield", "Hillcrest", "Kingsbury", "Castell Coch",
    "Greenway", "Old Town", "Llanfair", "Brookside",
    "Cathedral", "Saltmarsh", "Maple Park", "Westbrook",
]

# ---------------------------------------------------------------------------
#  Building styles  (gives Transport-Tycoon-style variety)
# ---------------------------------------------------------------------------
# Each style carries its own silhouette (drawn in renderer.py), a palette set,
# a height band, a resident band and a per-second bin fill rate. Flats, towers
# and high-rises produce far more waste than a quiet bungalow, so a round full
# of tower blocks is a real planning headache.

RES_STYLE_WEIGHTS = {
    "terrace":  0.34,
    "semi":     0.24,
    "detached": 0.16,
    "bungalow": 0.10,
    "flats":    0.12,
    "tower":    0.04,
}
COM_STYLE_WEIGHTS = {
    "shop":      0.46,
    "office":    0.26,
    "warehouse": 0.18,
    "highrise":  0.10,
}

# height band, resident band, fill rate (%/second at 1x)
STYLE_DATA = {
    "bungalow": {"h": (12, 17),   "pop": (1, 2),   "fill": 0.090},
    "terrace":  {"h": (22, 27),   "pop": (2, 4),   "fill": 0.120},
    "semi":     {"h": (24, 31),   "pop": (2, 5),   "fill": 0.130},
    "detached": {"h": (28, 37),   "pop": (3, 6),   "fill": 0.140},
    "flats":    {"h": (46, 64),   "pop": (8, 16),  "fill": 0.180},
    "tower":    {"h": (92, 132),  "pop": (20, 40), "fill": 0.225},
    "shop":      {"h": (24, 30),  "pop": (0, 0),   "fill": 0.155},
    "office":    {"h": (50, 72),  "pop": (0, 0),   "fill": 0.140},
    "warehouse": {"h": (30, 40),  "pop": (0, 0),   "fill": 0.120},
    "highrise":  {"h": (108, 150),"pop": (0, 0),   "fill": 0.215},
}

# Palettes per style. Tones are deliberately British: red/buff brick, slate,
# pebbledash, render. Keys: light wall, dark wall, roof.
BRICK_RED = [
    {"light": "#b06a4a", "dark": "#8f5238", "roof": "#4b4f57"},
    {"light": "#a85f43", "dark": "#854a33", "roof": "#5a3b34"},
]
BRICK_BUFF = [
    {"light": "#c9b083", "dark": "#a8915f", "roof": "#4b4f57"},
    {"light": "#cdbb96", "dark": "#ad9a70", "roof": "#3f4248"},
]
RENDER_PALE = [
    {"light": "#d7d2c4", "dark": "#bfb9a8", "roof": "#52555c"},
    {"light": "#cfd4d2", "dark": "#b4bab6", "roof": "#46494f"},
]
PAINTED = [
    {"light": "#b9c4cf", "dark": "#97a5b3", "roof": "#3c4a52"},
    {"light": "#c4cbbd", "dark": "#a3ad9b", "roof": "#43433f"},
]
CONCRETE = [
    {"light": "#b7b7b7", "dark": "#949494", "roof": "#5c5c5c"},
    {"light": "#a9adb2", "dark": "#878d92", "roof": "#54585c"},
]
GLASS = [
    {"light": "#8fa6bd", "dark": "#6a849f", "roof": "#3a4654"},
    {"light": "#9bb1c2", "dark": "#7793a4", "roof": "#384450"},
]
SHOPFRONT = [
    {"light": "#c8a55f", "dark": "#a8853f", "roof": "#5a4030"},
    {"light": "#9fb0a0", "dark": "#7d8e7e", "roof": "#3c4a3c"},
    {"light": "#b58a8a", "dark": "#946b6b", "roof": "#4a3535"},
]

STYLE_PALETTES = {
    "bungalow": BRICK_RED + RENDER_PALE,
    "terrace":  BRICK_RED + BRICK_BUFF,
    "semi":     BRICK_RED + BRICK_BUFF + PAINTED,
    "detached": BRICK_RED + RENDER_PALE + PAINTED,
    "flats":    CONCRETE + RENDER_PALE,
    "tower":    CONCRETE,
    "shop":      SHOPFRONT,
    "office":    GLASS + CONCRETE,
    "warehouse": CONCRETE,
    "highrise":  GLASS,
}


def _weighted_choice(weights):
    r = random.random()
    acc = 0.0
    for key, w in weights.items():
        acc += w
        if r <= acc:
            return key
    return next(iter(weights))


class Tile:
    def __init__(self, tile_type):
        self.type = tile_type
        self.population = 0
        self.bin_fill = random.random() * 25      # start partly filled
        self.collection_due = 0                    # synced from the round's day
        self.area_id = -1

        self.building_style = "detached"
        self.building_height = 0
        self.building_variant = 0
        self.fill_rate = 0.0
        self.wall_color_light = "#d6d6d6"
        self.wall_color_dark = "#c5c5c5"
        self.roof_color = "#8b2d2d"
        self.seed = random.random()                # per-building visual jitter

    def get_collection_day_name(self):
        return DAY_NAMES[self.collection_due]


class Area:
    """A collection round: a rectangular block of the borough emptied on one
    weekday."""

    def __init__(self, area_id, name, col, row):
        self.id = area_id
        self.name = name
        self.col = col
        self.row = row
        self.collection_day = area_id % 5          # default: spread over Mon-Fri
        self.frequency = 1                          # 1 = weekly, 2 = fortnightly
        self.last_collected = -1                    # day number last fully serviced
        self.building_tiles = []                    # (x, y) of every property
        self.property_count = 0
        self.population = 0
        # Route type: "residential" or "commercial" or "mixed"
        self.route_type = "mixed"
        # Per-day route overrides (day -> list of area_ids to service together)
        self.route_partners = {}  # day -> [area_id, ...]

    def due_today(self, today, week_index):
        """Is this round scheduled for collection today? Fortnightly rounds are
        staggered by id so they don't all land in the same week."""
        if self.collection_day != today:
            return False
        if self.frequency <= 1:
            return True
        return (week_index % self.frequency) == (self.id % self.frequency)

    @property
    def freq_label(self):
        return "Weekly" if self.frequency <= 1 else "Fortnightly"

    def get_dominant_type(self, city):
        """Determine if this area is mostly residential or commercial."""
        res = 0
        com = 0
        for (x, y) in self.building_tiles:
            t = city.tiles[y][x]
            if t.type == "residential":
                res += 1
            elif t.type == "commercial":
                com += 1
        if res > com * 2:
            return "residential"
        elif com > res * 2:
            return "commercial"
        return "mixed"


class CityGenerator:
    def __init__(self, width, height):
        self.width = width
        self.height = height
        self.tiles = []
        self.areas = []
        self.population = 0
        self.property_count = 0
        self.metrics = {"residential": 0, "commercial": 0, "roads": 0, "green": 0}

    # ------------------------------------------------------------------ areas
    def _area_index(self, x, y):
        col = min(AREA_COLS - 1, x * AREA_COLS // self.width)
        row = min(AREA_ROWS - 1, y * AREA_ROWS // self.height)
        return row * AREA_COLS + col, col, row

    def _build_areas(self):
        names = AREA_NAMES[:]
        random.shuffle(names)
        self.areas = []
        for i in range(AREA_COLS * AREA_ROWS):
            col = i % AREA_COLS
            row = i // AREA_COLS
            self.areas.append(Area(i, names[i % len(names)], col, row))

    def get_area(self, area_id):
        if 0 <= area_id < len(self.areas):
            return self.areas[area_id]
        return None

    def set_area_day(self, area_id, day):
        area = self.get_area(area_id)
        if not area:
            return
        area.collection_day = day % 7
        for (x, y) in area.building_tiles:
            self.tiles[y][x].collection_due = area.collection_day

    def set_area_frequency(self, area_id, frequency):
        area = self.get_area(area_id)
        if area:
            area.frequency = 2 if frequency >= 2 else 1

    def cycle_area_frequency(self, area_id):
        area = self.get_area(area_id)
        if area:
            area.frequency = 1 if area.frequency >= 2 else 2

    # -------------------------------------------------------------- generate
    def generate(self):
        self.tiles = []
        self.population = 0
        self.property_count = 0
        self.metrics = {"residential": 0, "commercial": 0, "roads": 0, "green": 0}
        self._build_areas()

        roads = RoadGenerator.generate_grid(self.width, self.height)

        # Randomise green space between 10% and 20%
        green_threshold = random.uniform(0.10, 0.20)
        building_threshold = 0.82 + (0.07 - green_threshold)  # keep total probability consistent

        for y in range(self.height):
            row = []
            for x in range(self.width):
                key = f"{x},{y}"
                area_id, _, _ = self._area_index(x, y)
                if key in roads:
                    tile = Tile("road")
                    tile.area_id = area_id
                    self.metrics["roads"] += 1
                else:
                    roll = random.random()
                    if roll < green_threshold:
                        tile = Tile("green")
                        tile.area_id = area_id
                        self.metrics["green"] = self.metrics.get("green", 0) + 1
                    elif roll < building_threshold:
                        tile = self._make_building("residential", area_id)
                    else:
                        tile = self._make_building("commercial", area_id)
                row.append(tile)
            self.tiles.append(row)

        # Cache per-round stats and sync each tile to its round's day.
        # Also determine route types (residential vs commercial clusters)
        for y in range(self.height):
            for x in range(self.width):
                tile = self.tiles[y][x]
                if tile.type in ("road", "green"):
                    continue
                area = self.areas[tile.area_id]
                area.building_tiles.append((x, y))
                area.property_count += 1
                area.population += tile.population
                tile.collection_due = area.collection_day

        # Set route types after all tiles are assigned
        for area in self.areas:
            area.route_type = area.get_dominant_type(self)

    def _make_building(self, kind, area_id):
        tile = Tile(kind)
        tile.area_id = area_id
        if kind == "residential":
            style = _weighted_choice(RES_STYLE_WEIGHTS)
            self.metrics["residential"] += 1
        else:
            style = _weighted_choice(COM_STYLE_WEIGHTS)
            self.metrics["commercial"] += 1

        data = STYLE_DATA[style]
        tile.building_style = style
        tile.building_height = random.randint(data["h"][0], data["h"][1])
        tile.population = random.randint(data["pop"][0], data["pop"][1])
        tile.fill_rate = data["fill"]

        palettes = STYLE_PALETTES[style]
        tile.building_variant = random.randint(0, len(palettes) - 1)
        pal = palettes[tile.building_variant]
        tile.wall_color_light = pal["light"]
        tile.wall_color_dark = pal["dark"]
        tile.roof_color = pal["roof"]

        self.population += tile.population
        self.property_count += 1
        return tile

    # ---------------------------------------------------------------- update
    def update(self, dt, bin_rate_multiplier=1):
        for row in self.tiles:
            for tile in row:
                if tile.type in ("road", "green"):
                    continue
                tile.bin_fill += dt * tile.fill_rate * bin_rate_multiplier
                if tile.bin_fill > 100:
                    tile.bin_fill = 100

    # ----------------------------------------------------------- area stats
    def area_stats(self, area_id, today, service_threshold=20, week_index=0):
        """Live snapshot of a round, for the planner/HUD."""
        area = self.get_area(area_id)
        if not area or not area.building_tiles:
            return None
        total = 0.0
        due = 0
        overflow = 0
        for (x, y) in area.building_tiles:
            t = self.tiles[y][x]
            total += t.bin_fill
            if t.bin_fill > service_threshold:
                due += 1
            if t.bin_fill > 85:
                overflow += 1
        n = len(area.building_tiles)
        avg = total / n
        is_today = area.due_today(today, week_index)
        scheduled_today = area.collection_day == today
        if overflow > 0 and not is_today:
            status = "OVERFLOW"
        elif avg > 70 and not is_today:
            status = "WATCH"
        elif is_today:
            status = "DUE TODAY"
        elif scheduled_today:
            status = "NEXT WEEK"
        else:
            status = "OK"
        return {
            "name": area.name,
            "day": area.collection_day,
            "frequency": area.frequency,
            "freq_label": area.freq_label,
            "props": area.property_count,
            "pop": area.population,
            "avg": avg,
            "due": due,
            "overflow": overflow,
            "status": status,
            "last": area.last_collected,
            "is_today": is_today,
            "route_type": area.route_type,
        }

    # ---------------------------------------------------------------- access
    def get_tile(self, x, y):
        if x < 0 or y < 0 or x >= self.width or y >= self.height:
            return None
        return self.tiles[y][x]

    def is_inside(self, x, y):
        return 0 <= x < self.width and 0 <= y < self.height