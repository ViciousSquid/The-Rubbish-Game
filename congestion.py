"""
congestion.py
=============

Lightweight ambient road congestion.

Civilian traffic is never simulated as individual AI vehicles for gameplay
purposes — that would be far too expensive. Instead each road tile carries a
scalar congestion level in [0, 1] derived from cheap, aggregate factors:

  * population/building density around the tile (the busy urban core is slow;
    quiet estate roads are clear) — computed once per city and cached,
  * road works nearby (traffic backs up around a closed junction),
  * the borough's own RCV traffic and passing events (a global bump),

and mapped to a simple state — free / busy / congested — that scales how fast
lorries can travel and, a little, how long a stop takes (crews threading through
traffic). This makes road layout and the placement of road works strategically
meaningful: a round through a congested core is genuinely slower to service than
one on open roads.

Cost: the density base is one pass over road tiles at city bind time. The
dynamic overlay (road works proximity + global bumps) is recomputed only when it
changes (road works added/removed, or on a coarse timer), and truck lookups are
O(1) dict reads.
"""

_KERNEL_RADIUS = 3

# Per-building-style pull on nearby congestion (mirrors ambient traffic density).
_DENSITY = {
    "tower": 10, "highrise": 10, "flats": 6, "office": 5, "shop": 4,
    "warehouse": 3, "semi": 2, "terrace": 2, "detached": 2, "bungalow": 1,
}


def _classify(c):
    if c < 0.25:
        return "free"
    if c < 0.55:
        return "busy"
    return "congested"


class TrafficField:
    """Per-road congestion field for a city. Bind once; refresh the dynamic
    overlay when road works change or on a coarse cadence."""

    def __init__(self):
        self._base = {}          # {(x,y): base congestion 0..1} static per city
        self._level = {}         # {(x,y): combined congestion 0..1} live
        self._built_for = None
        self._roadworks_sig = None
        self._global_bump = 0.0
        self._timer = 0.0

    # ---------------------------------------------------------------- binding
    def _build_base(self, city):
        roads = [(x, y) for y in range(city.height) for x in range(city.width)
                 if city.tiles[y][x].type == "road"]
        base = {}
        R = _KERNEL_RADIUS
        get = city.get_tile
        peak = 1.0
        for (rx, ry) in roads:
            score = 0.0
            for dy in range(-R, R + 1):
                for dx in range(-R, R + 1):
                    if dx == 0 and dy == 0:
                        continue
                    t = get(rx + dx, ry + dy)
                    if t is None:
                        continue
                    if t.type in ("residential", "commercial"):
                        d = abs(dx) + abs(dy)
                        score += _DENSITY.get(t.building_style, 1) / d
            base[(rx, ry)] = score
            if score > peak:
                peak = score
        # Normalise with a power curve so quiet estate roads stay near-free and
        # only genuinely dense cores approach the "busy" band — the average road
        # should barely be slowed. Peak base ~0.55 leaves headroom for the
        # dynamic overlay (road works, events) to reach "congested".
        self._base = {k: 0.55 * (v / peak) ** 1.7 for k, v in base.items()}
        self._level = dict(self._base)
        self._built_for = city
        self._roadworks_sig = None

    # ----------------------------------------------------------------- update
    def update(self, dt, city, economy=None, fleet=None):
        if self._built_for is not city:
            self._build_base(city)

        # Global bump from RCV traffic and busy-day events (cheap scalars).
        bump = 0.0
        if fleet is not None:
            active = sum(1 for t in fleet.trucks if t.get("crew", 0) >= 1
                         and not t.get("broken"))
            bump += min(0.12, active * 0.015)
        if economy is not None:
            ev = getattr(economy, "active_event", None)
            if ev and ev.get("id") in ("festival", "bank_holiday", "new_residents"):
                bump += 0.15
        self._global_bump = bump

        # Rebuild the road-works overlay only when the set of works changes.
        rw = getattr(city, "road_works_tiles", None) or set()
        sig = id(city), len(rw), (min(rw) if rw else None)
        self._timer += dt
        if sig != self._roadworks_sig or self._timer > 2.0:
            self._roadworks_sig = sig
            self._timer = 0.0
            self._recompute(rw)

    def _recompute(self, roadworks):
        # Traffic backs up on roads within 2 tiles of any road works.
        penalty = {}
        if roadworks:
            for (wx, wy) in roadworks:
                for dy in range(-2, 3):
                    for dx in range(-2, 3):
                        d = abs(dx) + abs(dy)
                        if 0 < d <= 2:
                            k = (wx + dx, wy + dy)
                            add = 0.45 if d == 1 else 0.25
                            if add > penalty.get(k, 0.0):
                                penalty[k] = add
        b = self._global_bump
        level = {}
        for k, base in self._base.items():
            level[k] = min(1.0, base + b + penalty.get(k, 0.0))
        self._level = level

    # ----------------------------------------------------------------- queries
    def congestion_at(self, x, y):
        return self._level.get((x, y), 0.0)

    def speed_factor(self, x, y):
        """Multiplier on lorry travel speed at a tile (1.0 free .. ~0.55 gridlock)."""
        c = self._level.get((x, y), 0.0)
        return 1.0 - 0.42 * c

    def state_at(self, x, y):
        return _classify(self._level.get((x, y), 0.0))

    def average(self):
        if not self._level:
            return 0.0
        return sum(self._level.values()) / len(self._level)
