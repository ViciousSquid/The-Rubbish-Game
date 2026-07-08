import pygame
import math
import os
import random                           # was previously imported inline per-call
from city import AREA_COLS, AREA_ROWS, DAY_NAMES
from assets import asset_path

# ─── module-level font cache ──────────────────────────────────────────────────
# pygame.font.SysFont() is an OS call that can take several milliseconds.
# Calling it every frame (as the original code did) is the single biggest
# per-frame cost in the renderer.  Cache by (family, size, bold) and reuse.
_FONT_CACHE: dict = {}


def _get_font(name: str, size: int, bold: bool = False) -> pygame.font.Font:
    key = (name, size, bold)
    f = _FONT_CACHE.get(key)
    if f is None:
        f = pygame.font.SysFont(name, size, bold=bold)
        _FONT_CACHE[key] = f
    return f


# ─── shared helpers ───────────────────────────────────────────────────────────

def _shade(color, f):
    """Multiply an (r,g,b) or hex colour by factor f, clamped to 0..255."""
    if isinstance(color, str):
        c = pygame.Color(color)
        r, g, b = c.r, c.g, c.b
    else:
        r, g, b = color[0], color[1], color[2]
    return (
        max(0, min(255, int(r * f))),
        max(0, min(255, int(g * f))),
        max(0, min(255, int(b * f))),
    )


def _blend(c1, c2, t):
    """Linear-interpolate two (r,g,b) colours; t clamped to 0..1."""
    t = max(0.0, min(1.0, t))
    return (
        int(c1[0] + (c2[0] - c1[0]) * t),
        int(c1[1] + (c2[1] - c1[1]) * t),
        int(c1[2] + (c2[2] - c1[2]) * t),
    )


# ─── snow settling ─────────────────────────────────────────────────────────
# `snow` is the ambient snow-coverage level (0..1, see AmbientState.snow_level).
# Ground/road/roof colours are blended toward this white-blue at draw time so
# the whole city visibly whitens during a snow spell and thaws afterwards.
SNOW_WHITE = (236, 240, 246)


def _snow_ground(color, snow, strength=1.0):
    if snow <= 0.01:
        return color
    return _blend(color, SNOW_WHITE, min(1.0, snow * strength))


def _snow_cc(cc, snow):
    """Blend a building's cached wall/roof colours toward snow-white. Returns
    a new dict -- the cached original (tile._ccache) is left untouched so it
    is still correct once the snow melts."""
    if snow <= 0.01:
        return cc
    out = dict(cc)
    out["roof"]    = _blend(cc["roof"],    SNOW_WHITE, min(1.0, snow * 1.15))
    out["roof_l"]  = _blend(cc["roof_l"],  SNOW_WHITE, min(1.0, snow * 1.15))
    out["roof_h"]  = _blend(cc["roof_h"],  SNOW_WHITE, min(1.0, snow * 1.05))
    out["roof_d"]  = _blend(cc["roof_d"],  _shade(SNOW_WHITE, 0.82), min(1.0, snow * 0.95))
    out["parapet"] = _blend(cc["parapet"], _shade(SNOW_WHITE, 0.75), min(1.0, snow * 0.9))
    out["wr"]      = _blend(cc["wr"], SNOW_WHITE, snow * 0.28)
    out["wl"]      = _blend(cc["wl"], SNOW_WHITE, snow * 0.28)
    return out


# ─── day / night cycle ─────────────────────────────────────────────────────

def _daylight_brightness(day_progress):
    """0 (midnight) .. 1 (noon) brightness curve. `day_progress` (0..1) is the
    fraction of the current in-game day elapsed; collections nominally start
    around dawn, so day_progress=0 is mapped to 06:00 and the cycle runs
    forward 24h over one in-game day."""
    clock_hour = (6.0 + day_progress * 24.0) % 24.0
    return 0.5 + 0.5 * math.cos((clock_hour - 12.0) / 12.0 * math.pi)


def _face_pt(corners, u, v):
    """Bilinear point on a quad face.
    corners = (bl, br, tr, tl): bl=near-base, br=far-base, tr=far-top, tl=near-top."""
    bl, br, tr, tl = corners
    bx = bl[0] + (br[0] - bl[0]) * u
    by = bl[1] + (br[1] - bl[1]) * u
    tx = tl[0] + (tr[0] - tl[0]) * u
    ty = tl[1] + (tr[1] - tl[1]) * u
    return (bx + (tx - bx) * v, by + (ty - by) * v)


def _face_quad(corners, u, v, du, dv):
    return [
        _face_pt(corners, u, v),
        _face_pt(corners, u + du, v),
        _face_pt(corners, u + du, v + dv),
        _face_pt(corners, u, v + dv),
    ]


# Per-style footprint width factor (1.0 fills the tile; lower leaves a garden).
STYLE_FOOTPRINT = {
    "bungalow": 0.84, "terrace": 0.94, "semi": 0.86, "detached": 0.78,
    "flats": 0.82, "tower": 0.64,
    "shop": 0.90, "office": 0.80, "warehouse": 0.92, "highrise": 0.66,
}

# Zone type colors for ground tiles
RESIDENTIAL_ZONE  = (104, 150, 86)
COMMERCIAL_ZONE   = (96, 116, 84)
ROAD_COLOR        = (78, 80, 86)
GREEN_ZONE        = (95, 145, 85)

# Area overlay colors by route type
RESIDENTIAL_AREA_COLOR = (200, 220, 180, 40)
COMMERCIAL_AREA_COLOR  = (180, 200, 230, 40)
MIXED_AREA_COLOR       = (220, 210, 180, 40)


class Renderer:
    def __init__(self, screen, camera):
        self.screen = screen
        self.camera = camera
        self.tile_w = 64
        self.tile_h = 32

        # Pre-computed iso half-extents — avoids the division inside to_iso()
        # which is called thousands of times per frame.
        self._iso_hw = self.tile_w >> 1   # 32
        self._iso_hh = self.tile_h >> 1   # 16

        # Load truck icon — done once here only (original code also loaded at
        # module level, wasting an import + PIL decode before the display was ready).
        self._truck_icon = None
        try:
            from PIL import Image
            png_path = asset_path("truck.png")
            if os.path.exists(png_path):
                img = Image.open(png_path).convert("RGBA")
                self._truck_icon = pygame.image.fromstring(img.tobytes(), img.size, "RGBA")
        except Exception:
            self._truck_icon = None

        # Static cache for batch rendering
        self._static_cache = None
        self._cache_key    = None

        # ── per-frame SRCALPHA surface pool ───────────────────────────────────
        # Creating pygame.Surface(…, SRCALPHA) allocates memory every call.
        # We reuse surfaces of the same pixel dimensions by clearing them instead.
        # Each surface is draw→blit before being returned to the pool, so
        # concurrent reuse within a single frame is safe.
        self._surf_cache: dict = {}

        # ── weather overlay ───────────────────────────────────────────────────
        # Weather previously created 60-120 tiny SRCALPHA surfaces per frame.
        # Now we rebuild a single screen-sized surface every 80 ms (matching the
        # animation granularity of the original code) and blit it once.
        self._weather_surf: pygame.Surface | None = None
        self._weather_seed: int  = -1
        self._weather_size: tuple = (0, 0)

        # ── FPS limiter ───────────────────────────────────────────────────────
        self._clock = pygame.time.Clock()

    # ─── SRCALPHA surface pool ────────────────────────────────────────────────

    def _get_alpha_surf(self, w: int, h: int) -> pygame.Surface:
        """Return a cached, freshly-cleared SRCALPHA surface of size (w, h).

        Callers must follow the draw→blit→done pattern within the same scope
        before requesting the same (w, h) again, which all callers in this file do.
        """
        key = (w, h)
        s = self._surf_cache.get(key)
        if s is None:
            s = pygame.Surface((w, h), pygame.SRCALPHA)
            self._surf_cache[key] = s
        else:
            s.fill((0, 0, 0, 0))
        return s

    # ─── render ───────────────────────────────────────────────────────────────

    def render(self, city, fleet, selected_tile=None, today=0, show_areas=False,
               hovered_tile=None, economy=None, ambient=None):
        cx   = self.screen.get_width() // 2 + self.camera["x"]
        cy   = 120 + self.camera["y"]
        zoom = self.camera["zoom"]
        sw, sh = self.screen.get_size()

        snow = ambient.snow_level if ambient is not None else 0.0
        day_progress = economy.get_day_progress() if economy is not None else 0.25
        is_night = _daylight_brightness(day_progress) < 0.4

        # Build or reuse the static cache
        if self._static_cache is None or self._needs_static_cache_update(city, zoom, snow, is_night):
            self._static_cache = self._render_static(city, zoom, snow, is_night)

        use_cache = self._static_cache is not None
        if use_cache:
            cache = self._static_cache
            self.screen.blit(cache["surface"],
                             (int(cx - cache["offset_x"]), int(cy - cache["offset_y"])))

        # Pre-compute selection / hover grid positions for O(1) per-tile matching.
        sel_pos = (selected_tile["x"], selected_tile["y"]) if selected_tile else None
        hov_pos = (hovered_tile["x"],  hovered_tile["y"])  if hovered_tile  else None

        # Pre-multiply frustum-cull margins so they're not recomputed per tile.
        cull_x_lo = -80  * zoom
        cull_x_hi =  sw  + 80  * zoom
        cull_y_lo = -320 * zoom
        cull_y_hi =  sh  + 80  * zoom

        for y in range(city.height):
            for x in range(city.width):
                iso = self.to_iso(x, y)
                ix  = cx + iso[0] * zoom
                iy  = cy + iso[1] * zoom
                if ix < cull_x_lo or ix > cull_x_hi:
                    continue
                if iy < cull_y_lo or iy > cull_y_hi:
                    continue

                tile     = city.get_tile(x, y)
                selected = sel_pos == (x, y)
                hovered  = hov_pos == (x, y)

                if not use_cache:
                    self.draw_tile(ix, iy, tile, selected, zoom, city, snow=snow)
                    if tile.type not in ("road", "green", "landfill"):
                        self.draw_building(ix, iy, tile, zoom, today, hovered, selected,
                                           snow=snow, night=is_night)
                else:
                    if tile.type not in ("road", "green", "landfill"):
                        # Skip the dynamic pass entirely when there is nothing to
                        # draw — this avoids iterating every building tile every
                        # frame when most of them are in a neutral state.
                        days_ov = getattr(tile, "days_overflowing", 0)
                        if (selected or hovered
                                or tile.bin_fill > 85
                                or days_ov > 0
                                or (zoom >= 1.55
                                    and tile.collection_due == today
                                    and tile.bin_fill > 20)):
                            self._draw_building_dynamic(
                                ix, iy, tile, zoom, today, hovered, selected)

                # Selection outline for non-building tiles
                if selected and tile.type in ("road", "green", "landfill"):
                    hw     = (self.tile_w / 2) * zoom
                    hh     = (self.tile_h / 2) * zoom
                    points = [(ix, iy), (ix + hw, iy + hh),
                              (ix, iy + 2 * hh), (ix - hw, iy + hh)]
                    pygame.draw.polygon(self.screen, (245, 245, 245), points,
                                        max(2, int(2 * zoom)))

        # Landfill site (large refuse mound in a corner)
        self.draw_landfill(cx, cy, city, zoom, snow=snow)

        # Road works barriers (drawn before trucks so trucks appear on top)
        self.draw_road_works(cx, cy, city, zoom)

        # Ambient pedestrians
        if ambient:
            for ped in ambient.peds.peds:
                piso = self.to_iso(ped["x"], ped["y"])
                self.draw_ped(cx + piso[0] * zoom, cy + piso[1] * zoom, ped, zoom)

        # Depot
        depot_iso = self.to_iso(fleet.depot_x, fleet.depot_y)
        self.draw_depot(cx + depot_iso[0] * zoom, cy + depot_iso[1] * zoom,
                        zoom, fleet)

        # Ambient civilian cars
        if ambient:
            for car in ambient.traffic.cars:
                ciso = self.to_iso(car["x"], car["y"])
                self.draw_ambient_car(cx + ciso[0] * zoom, cy + ciso[1] * zoom,
                                      car, zoom)

        # Lorries + loaders
        for truck in fleet.trucks:
            iso = self.to_iso(truck["x"], truck["y"])
            self.draw_truck(cx + iso[0] * zoom, cy + iso[1] * zoom, truck, zoom)
            for w in truck.get("out_workers", []):
                wiso = self.to_iso(w["x"], w["y"])
                self.draw_worker(cx + wiso[0] * zoom, cy + wiso[1] * zoom, w, zoom)

        # Seagulls near landfill
        if ambient:
            self.draw_birds(cx, cy, ambient.birds, zoom)

        # Rare high-altitude aircraft crossing the map
        if ambient:
            self.draw_aircraft(cx, cy, ambient.aircraft, zoom)

        if show_areas:
            self.draw_area_overlay(cx, cy, city, zoom, today)

        # Day/night tint -- warm dusk/dawn, deep blue at night, clear at midday
        self.draw_daynight(day_progress)

        # Weather overlay (rain / snow)
        if economy:
            self.draw_weather(economy.weather, economy.day_timer, economy.day_duration)

        # ── 60 FPS cap ────────────────────────────────────────────────────────
        # Anything faster than 60 FPS is wasted work on this target hardware.
        self._clock.tick(60)

    # ─── static cache ─────────────────────────────────────────────────────────

    def _needs_static_cache_update(self, city, zoom, snow=0.0, night=False):
        key = (id(city), getattr(city, "version", 0), round(zoom, 2),
               round(snow, 1), bool(night))
        if self._cache_key != key:
            self._cache_key = key
            return True
        return False

    def _render_static(self, city, zoom, snow=0.0, night=False):
        """Render all static city geometry (ground tiles + buildings) to an
        off-screen surface.  Returns None if the cache would be too large."""
        corners = [
            self.to_iso(0, 0),
            self.to_iso(city.width, 0),
            self.to_iso(0, city.height),
            self.to_iso(city.width, city.height),
        ]
        min_ix = min(c[0] for c in corners)
        max_ix = max(c[0] for c in corners)
        min_iy = min(c[1] for c in corners)
        max_iy = max(c[1] for c in corners)

        pad     = 200
        cache_w = int((max_ix - min_ix) * zoom) + pad * 2
        cache_h = int((max_iy - min_iy) * zoom) + pad * 2 + int(160 * zoom)

        MAX_CACHE_PIXELS = 25_000_000
        if cache_w * cache_h > MAX_CACHE_PIXELS:
            return None

        offset_x = int(-min_ix * zoom) + pad
        offset_y = int(-min_iy * zoom) + pad

        surface = pygame.Surface((cache_w, cache_h), pygame.SRCALPHA)
        surface.fill((0, 0, 0, 0))

        old_screen  = self.screen
        self.screen = surface
        try:
            for y in range(city.height):
                for x in range(city.width):
                    iso = self.to_iso(x, y)
                    ix  = offset_x + iso[0] * zoom
                    iy  = offset_y + iso[1] * zoom
                    tile = city.get_tile(x, y)
                    self.draw_tile(ix, iy, tile, False, zoom, city, static_only=True, snow=snow)
                    if tile.type not in ("road", "green", "landfill"):
                        self.draw_building(ix, iy, tile, zoom, 0, False, False,
                                           static_only=True, snow=snow, night=night)
        finally:
            self.screen = old_screen

        return {"surface": surface, "offset_x": offset_x, "offset_y": offset_y}

    # ─── ground ───────────────────────────────────────────────────────────────

    def _draw_ground_plane(self, cx, cy, city, zoom):
        corners = [
            self.to_iso(0, 0),
            self.to_iso(city.width, 0),
            self.to_iso(0, city.height),
            self.to_iso(city.width, city.height),
        ]
        points = [(cx + c[0] * zoom, cy + c[1] * zoom) for c in corners]
        pygame.draw.polygon(self.screen, (33, 38, 52), points)

    def _draw_city_boundary(self, cx, cy, city, zoom):
        self._draw_edge_line(cx, cy, 0, 0, city.width, 0, zoom, (120, 120, 130))
        self._draw_edge_line(cx, cy, city.width, 0, city.width, city.height,
                             zoom, (100, 100, 110))
        self._draw_edge_line(cx, cy, city.width, city.height, 0, city.height,
                             zoom, (80, 80, 90))
        self._draw_edge_line(cx, cy, 0, city.height, 0, 0, zoom, (100, 100, 110))

    def _draw_edge_line(self, cx, cy, x1, y1, x2, y2, zoom, color):
        start = self.to_iso(x1, y1)
        end   = self.to_iso(x2, y2)
        pygame.draw.line(
            self.screen, color,
            (cx + start[0] * zoom, cy + start[1] * zoom),
            (cx + end[0]   * zoom, cy + end[1]   * zoom),
            max(2, int(3 * zoom)))

    # ─── iso maths ────────────────────────────────────────────────────────────

    def to_iso(self, x, y):
        # Use pre-computed half-extents instead of dividing tile_w/tile_h each call.
        hw, hh = self._iso_hw, self._iso_hh
        return ((x - y) * hw, (x + y) * hh)

    def screen_to_tile(self, screen_x, screen_y, screen_w, screen_h):
        ix     = (screen_x - screen_w // 2 - self.camera["x"]) / self.camera["zoom"]
        iy     = (screen_y - 120            - self.camera["y"]) / self.camera["zoom"]
        tile_x = (ix / (self.tile_w / 2) + iy / (self.tile_h / 2)) / 2
        tile_y = (iy / (self.tile_h / 2) - ix / (self.tile_w / 2)) / 2
        return {"x": round(tile_x), "y": round(tile_y)}

    def truck_screen_pos(self, truck):
        """Screen-space (x, y, icon_scale) for a lorry, matching the offsets
        used by draw_truck() so hit-testing lines up with what's on screen."""
        cx   = self.screen.get_width() // 2 + self.camera["x"]
        cy   = 120 + self.camera["y"]
        zoom = self.camera["zoom"]
        iso  = self.to_iso(truck["x"], truck["y"])
        s    = zoom * 1.2
        return cx + iso[0] * zoom, cy + iso[1] * zoom - 5 * s, s

    def truck_at_screen_pos(self, fleet, screen_x, screen_y):
        """Hit-test lorries against a screen-space click point. Returns the
        truck dict nearest the click if within its icon radius, else None."""
        best, best_d2 = None, None
        for truck in fleet.trucks:
            tx, ty, s = self.truck_screen_pos(truck)
            r  = max(15, 13 * s)
            dx = screen_x - tx
            dy = screen_y - ty
            d2 = dx * dx + dy * dy
            if d2 <= r * r and (best_d2 is None or d2 < best_d2):
                best, best_d2 = truck, d2
        return best

    def draw_unreachable(self, tiles, pulse=1.0):
        """Flag building tiles no lorry can reach with a hatched red overlay.
        `pulse` (0..1) gently modulates the fill alpha so the warning breathes."""
        if not tiles:
            return
        cx   = self.screen.get_width() // 2 + self.camera["x"]
        cy   = 120 + self.camera["y"]
        zoom = self.camera["zoom"]
        hw   = (self.tile_w / 2) * zoom
        hh   = (self.tile_h / 2) * zoom
        sw, sh = self.screen.get_size()
        overlay = self._get_alpha_surf(sw, sh)
        fill = int(60 + 45 * max(0.0, min(1.0, pulse)))
        lw = max(2, int(2 * zoom))
        for (x, y) in tiles:
            iso = self.to_iso(x, y)
            ix  = cx + iso[0] * zoom
            iy  = cy + iso[1] * zoom
            if ix < -hw or ix > sw + hw or iy < -hh or iy > sh + hh:
                continue
            pts = [(ix, iy), (ix + hw, iy + hh),
                   (ix, iy + 2 * hh), (ix - hw, iy + hh)]
            pygame.draw.polygon(overlay, (220, 50, 45, fill), pts)
            pygame.draw.polygon(overlay, (240, 70, 60, 235), pts, lw)
        self.screen.blit(overlay, (0, 0))

    def draw_editor_cursor(self, tiles, color):
        """Outline (and lightly fill) a set of map tiles under the editor brush
        so painting reads like SimCity zoning. `tiles` is an iterable of (x, y)
        grid coords; `color` is the RGB tint for the active tool."""
        if not tiles:
            return
        cx   = self.screen.get_width() // 2 + self.camera["x"]
        cy   = 120 + self.camera["y"]
        zoom = self.camera["zoom"]
        hw   = (self.tile_w / 2) * zoom
        hh   = (self.tile_h / 2) * zoom
        r, g, b = color
        sw, sh = self.screen.get_size()
        overlay = self._get_alpha_surf(sw, sh)
        lw = max(2, int(2 * zoom))
        for (x, y) in tiles:
            iso = self.to_iso(x, y)
            ix  = cx + iso[0] * zoom
            iy  = cy + iso[1] * zoom
            if ix < -hw or ix > sw + hw or iy < -hh or iy > sh + hh:
                continue
            pts = [(ix, iy), (ix + hw, iy + hh),
                   (ix, iy + 2 * hh), (ix - hw, iy + hh)]
            pygame.draw.polygon(overlay, (r, g, b, 55), pts)
            pygame.draw.polygon(overlay, (r, g, b, 230), pts, lw)
        self.screen.blit(overlay, (0, 0))

    # ─── tile floor ───────────────────────────────────────────────────────────

    def draw_tile(self, x, y, tile, is_selected, zoom, city=None, static_only=False, snow=0.0):
        hw     = (self.tile_w / 2) * zoom
        hh     = (self.tile_h / 2) * zoom
        points = [(x, y), (x + hw, y + hh), (x, y + 2 * hh), (x - hw, y + hh)]

        # ── ROAD ──
        if tile.type == "road":
            pygame.draw.polygon(self.screen, _snow_ground(ROAD_COLOR, snow, 0.8), points)
            if is_selected and not static_only:
                pygame.draw.polygon(self.screen, (245, 245, 245), points,
                                    max(2, int(2 * zoom)))
            return

        # ── GREEN SPACE ──
        if tile.type == "green":
            pygame.draw.polygon(self.screen, _snow_ground(GREEN_ZONE, snow, 0.55), points)
            if is_selected and not static_only:
                pygame.draw.polygon(self.screen, (245, 245, 245), points,
                                    max(2, int(2 * zoom)))
            return

        # ── LANDFILL ──
        if tile.type == "landfill":
            pygame.draw.polygon(self.screen, _snow_ground((74, 64, 48), snow, 0.75), points)
            if zoom >= 0.7 and not static_only:
                seed = ((int(x) * 73856093) ^ (int(y) * 19349663)) & 0xffff
                for k in range(3):
                    sx  = x + ((seed >> (k * 3)) % 7 - 3) * hw * 0.18
                    sy  = y + hh + ((seed >> (k * 2)) % 5 - 2) * hh * 0.18
                    col = [(40, 40, 40), (120, 40, 40), (40, 80, 120)][k % 3]
                    pygame.draw.circle(self.screen, col, (int(sx), int(sy)),
                                       max(1, int(1.6 * zoom)))
            if is_selected and not static_only:
                pygame.draw.polygon(self.screen, (245, 245, 245), points,
                                    max(2, int(2 * zoom)))
            return

        # ── RESIDENTIAL / COMMERCIAL ──
        base = COMMERCIAL_ZONE if tile.type == "commercial" else RESIDENTIAL_ZONE
        pygame.draw.polygon(self.screen, _snow_ground(base, snow, 0.35), points)

        if zoom >= 0.8 and not static_only:
            indicator = (120, 145, 110) if tile.type == "commercial" else (130, 175, 110)
            pygame.draw.circle(self.screen, indicator,
                               (int(x), int(y + hh)), max(1, int(2 * zoom)))

        detail = zoom >= 1.15

        if is_selected and not static_only:
            tint_color = None
            if tile.type == "residential":
                tint_color = (120, 255, 120, 110)
            elif tile.type == "commercial":
                tint_color = (120, 200, 255, 110)

            if tint_color:
                tint_surf = self._get_alpha_surf(int(hw * 2.4), int(hh * 2.4))
                tint_pts  = [
                    (int(hw * 1.2), int(hh * 0.2)),
                    (int(hw * 2.2), int(hh * 1.2)),
                    (int(hw * 1.2), int(hh * 2.2)),
                    (int(hw * 0.2), int(hh * 1.2)),
                ]
                pygame.draw.polygon(tint_surf, tint_color, tint_pts)
                self.screen.blit(tint_surf, (int(x - hw * 0.2), int(y - hh * 0.2)))

            pygame.draw.polygon(self.screen, (245, 245, 245), points,
                                max(2, int(2 * zoom)))
        elif detail and not static_only:
            pygame.draw.polygon(self.screen, (40, 46, 40), points, max(1, int(zoom)))

    # ─── buildings ────────────────────────────────────────────────────────────

    def _color_cache(self, tile):
        light = pygame.Color(tile.wall_color_light)
        dark  = pygame.Color(tile.wall_color_dark)
        roof  = pygame.Color(tile.roof_color)
        return {
            "wr":     _shade(light, 1.0),
            "wl":     _shade(dark,  0.78),
            "seam":   _shade(dark,  0.55),
            "roof":   _shade(roof,  1.0),
            "roof_l": _shade(roof,  0.78),
            "roof_d": _shade(roof,  0.6),
            "roof_h": _shade(roof,  1.22),
            "parapet":_shade(roof,  0.55),
        }

    def _box(self, x, y, hw, hh, f, H):
        cxc, cyc = x, y + hh
        B_top  = (cxc,          cyc - hh * f)
        B_right= (cxc + hw * f, cyc)
        B_bot  = (cxc,          cyc + hh * f)
        B_left = (cxc - hw * f, cyc)
        R_top  = (B_top[0],   B_top[1]   - H)
        R_right= (B_right[0], B_right[1] - H)
        R_bot  = (B_bot[0],   B_bot[1]   - H)
        R_left = (B_left[0],  B_left[1]  - H)
        return {
            "cxc": cxc, "cyc": cyc,
            "B_top": B_top, "B_right": B_right,
            "B_bot": B_bot, "B_left": B_left,
            "R_top": R_top, "R_right": R_right,
            "R_bot": R_bot, "R_left": R_left,
            "right": (B_bot, B_right, R_right, R_bot),
            "left":  (B_bot, B_left,  R_left,  R_bot),
        }

    def draw_building(self, x, y, tile, zoom, today, is_hovered=False,
                      is_selected=False, static_only=False, snow=0.0, night=False):
        if tile.type in ("road", "green"):
            return

        hw    = (self.tile_w / 2) * zoom
        hh    = (self.tile_h / 2) * zoom
        style = tile.building_style
        f     = STYLE_FOOTPRINT.get(style, 0.82)
        H     = tile.building_height * zoom

        b = self._box(x, y, hw, hh, f, H)

        cc = getattr(tile, "_ccache", None)
        if cc is None:
            cc = self._color_cache(tile)
            tile._ccache = cc
        # Snow-blended colours for this draw only -- the cached original is
        # left untouched so it's still correct once the snow melts.
        cc_draw = _snow_cc(cc, snow) if snow > 0.01 else cc

        detail = zoom >= 1.55
        shadow = zoom >= 1.15

        if shadow:
            pygame.draw.polygon(self.screen, (20, 24, 34), [
                (b["cxc"] - hw * f,        b["cyc"] + 1),
                (b["cxc"],                 b["cyc"] + hh * f + 1),
                (b["cxc"] + hw * f * 1.15, b["cyc"] + hh * 0.25),
                (b["cxc"] + hw * 0.1,      b["cyc"] - hh * f * 0.3),
            ])

        # Pre-compute building tint surface dimensions (shared by sel/hover/overflow)
        ts_w = int(hw * 2.6)
        ts_h = int(hh * 2.6 + H)

        # ── SELECTION TINT & WIREFRAME ──
        if is_selected and not static_only:
            if tile.type == "residential":
                sel_color  = (120, 255, 120, 120)
                wire_color = (80, 220, 80)
            elif tile.type == "commercial":
                sel_color  = (120, 200, 255, 120)
                wire_color = (80, 170, 255)
            else:
                sel_color  = None
                wire_color = (255, 255, 255)

            if sel_color:
                sel_surf = self._get_alpha_surf(ts_w, ts_h)
                sel_pts  = [
                    (int(hw * 1.3), int(hh * 1.3)),
                    (int(hw * 2.3), int(hh * 0.3)),
                    (int(hw * 2.3), int(hh * 0.3 - H)),
                    (int(hw * 1.3), int(hh * 1.3 - H)),
                    (int(hw * 0.3), int(hh * 1.3 - H)),
                    (int(hw * 0.3), int(hh * 1.3)),
                ]
                pygame.draw.polygon(sel_surf, sel_color, sel_pts)
                self.screen.blit(sel_surf, (int(x - hw * 1.3), int(y - hh * 1.3)))

            outline_pts = [
                (x - hw * f, y + hh * f),
                (x,          y + 2 * hh * f),
                (x + hw * f, y + hh * f),
                (x + hw * f, y + hh * f - H),
                (x,          y - H),
                (x - hw * f, y + hh * f - H),
            ]
            for i in range(len(outline_pts)):
                pygame.draw.line(self.screen, wire_color,
                                 outline_pts[i], outline_pts[(i + 1) % len(outline_pts)],
                                 max(2, int(2 * zoom)))

        # ── HOVER TINT ──
        elif is_hovered and not static_only:
            if tile.type == "residential":
                hover_color = (120, 255, 120, 70)
            elif tile.type == "commercial":
                hover_color = (120, 200, 255, 70)
            else:
                hover_color = None

            if hover_color:
                hover_surf = self._get_alpha_surf(ts_w, ts_h)
                hover_pts  = [
                    (int(hw * 1.3), int(hh * 1.3)),
                    (int(hw * 2.3), int(hh * 0.3)),
                    (int(hw * 2.3), int(hh * 0.3 - H)),
                    (int(hw * 1.3), int(hh * 1.3 - H)),
                    (int(hw * 0.3), int(hh * 1.3 - H)),
                    (int(hw * 0.3), int(hh * 1.3)),
                ]
                pygame.draw.polygon(hover_surf, hover_color, hover_pts)
                self.screen.blit(hover_surf, (int(x - hw * 1.3), int(y - hh * 1.3)))

        # Walls
        pygame.draw.polygon(self.screen, cc_draw["wr"], list(b["right"]))
        pygame.draw.polygon(self.screen, cc_draw["wl"], list(b["left"]))
        if shadow:
            pygame.draw.line(self.screen, cc_draw["seam"], b["B_bot"], b["R_bot"],
                             max(1, int(zoom)))

        # Style-specific top + detailing
        if style in ("detached", "bungalow"):
            self._roof_hip(b, cc_draw, zoom)
            if detail:
                self._house_details(tile, b, zoom, chimney=(style == "detached"), night=night)
        elif style in ("terrace", "semi"):
            self._roof_gable(b, cc_draw, zoom)
            if detail:
                self._house_details(tile, b, zoom, chimney=(style == "semi"), night=night)
        elif style in ("flats", "tower"):
            self._roof_flat(b, cc_draw, zoom)
            if detail:
                self._block_details(tile, b, zoom, tower=(style == "tower"), night=night)
            if style == "tower":
                self._rooftop_kit(b, zoom)
        elif style == "shop":
            self._roof_flat(b, cc_draw, zoom)
            if detail:
                self._shop_details(tile, b, zoom, night=night)
        elif style == "warehouse":
            self._roof_mono(b, cc_draw, zoom)
            if detail:
                self._warehouse_details(tile, b, zoom)
        else:   # office / highrise
            self._roof_flat(b, cc_draw, zoom)
            if detail:
                self._glass_details(tile, b, zoom, night=night)
            if style == "highrise":
                self._rooftop_kit(b, zoom, mast=True)

        # Zone type indicator (small £ for commercial buildings)
        if tile.type == "commercial" and zoom >= 1.3 and not static_only:
            font = _get_font("segoeui", max(6, int(8 * zoom)), bold=True)
            text = font.render("£", True, (255, 220, 100))
            self.screen.blit(text, text.get_rect(
                center=(int(b["R_top"][0]), int(b["R_top"][1] + 8 * zoom))))

        # Kerbside wheelie bin if due today (close-up only)
        if detail and not static_only and tile.collection_due == today and tile.bin_fill > 20:
            self._draw_wheelie_bin(b["B_bot"], b["B_right"], zoom, tile.bin_fill)

        # Overflow alarm — cheap and gameplay-critical
        if tile.bin_fill > 85 and not static_only:
            pygame.draw.circle(self.screen, (235, 70, 70),
                               (int(b["R_top"][0]), int(b["R_top"][1] - 6 * zoom)),
                               max(2, int(3 * zoom)))

        # Heatmap overflow tint: intensity grows with days_overflowing
        days_ov = getattr(tile, "days_overflowing", 0)
        if days_ov > 0 and not static_only:
            alpha    = min(170, 28 + days_ov * 35)
            tint_surf = self._get_alpha_surf(ts_w, ts_h)
            tint_pts  = [
                (int(hw * 1.3), int(hh * 1.3)),
                (int(hw * 2.3), int(hh * 0.3)),
                (int(hw * 2.3), int(hh * 0.3 - H)),
                (int(hw * 1.3), int(hh * 1.3 - H)),
                (int(hw * 0.3), int(hh * 1.3 - H)),
                (int(hw * 0.3), int(hh * 1.3)),
            ]
            pygame.draw.polygon(tint_surf, (210, 30, 30, alpha), tint_pts)
            self.screen.blit(tint_surf, (int(x - hw * 1.3), int(y - hh * 1.3)))

        # Litter bags accumulate outside overflowing buildings
        if days_ov > 0 and not static_only and zoom >= 0.9:
            self._draw_litter(b, days_ov, zoom)

    def _draw_building_dynamic(self, x, y, tile, zoom, today,
                               is_hovered=False, is_selected=False):
        """Draw only the dynamic parts of a building (selection, hover, bins, overflow).
        Called when the static cache is active."""
        if tile.type in ("road", "green"):
            return

        hw    = (self.tile_w / 2) * zoom
        hh    = (self.tile_h / 2) * zoom
        style = tile.building_style
        f     = STYLE_FOOTPRINT.get(style, 0.82)
        H     = tile.building_height * zoom
        b     = self._box(x, y, hw, hh, f, H)

        ts_w = int(hw * 2.6)
        ts_h = int(hh * 2.6 + H)

        if is_selected:
            if tile.type == "residential":
                sel_color  = (120, 255, 120, 120)
                wire_color = (80, 220, 80)
            elif tile.type == "commercial":
                sel_color  = (120, 200, 255, 120)
                wire_color = (80, 170, 255)
            else:
                sel_color  = None
                wire_color = (255, 255, 255)

            if sel_color:
                sel_surf = self._get_alpha_surf(ts_w, ts_h)
                sel_pts  = [
                    (int(hw * 1.3), int(hh * 1.3)),
                    (int(hw * 2.3), int(hh * 0.3)),
                    (int(hw * 2.3), int(hh * 0.3 - H)),
                    (int(hw * 1.3), int(hh * 1.3 - H)),
                    (int(hw * 0.3), int(hh * 1.3 - H)),
                    (int(hw * 0.3), int(hh * 1.3)),
                ]
                pygame.draw.polygon(sel_surf, sel_color, sel_pts)
                self.screen.blit(sel_surf, (int(x - hw * 1.3), int(y - hh * 1.3)))

            outline_pts = [
                (x - hw * f, y + hh * f),
                (x,          y + 2 * hh * f),
                (x + hw * f, y + hh * f),
                (x + hw * f, y + hh * f - H),
                (x,          y - H),
                (x - hw * f, y + hh * f - H),
            ]
            for i in range(len(outline_pts)):
                pygame.draw.line(self.screen, wire_color,
                                 outline_pts[i], outline_pts[(i + 1) % len(outline_pts)],
                                 max(2, int(2 * zoom)))

        elif is_hovered:
            if tile.type == "residential":
                hover_color = (120, 255, 120, 70)
            elif tile.type == "commercial":
                hover_color = (120, 200, 255, 70)
            else:
                hover_color = None

            if hover_color:
                hover_surf = self._get_alpha_surf(ts_w, ts_h)
                hover_pts  = [
                    (int(hw * 1.3), int(hh * 1.3)),
                    (int(hw * 2.3), int(hh * 0.3)),
                    (int(hw * 2.3), int(hh * 0.3 - H)),
                    (int(hw * 1.3), int(hh * 1.3 - H)),
                    (int(hw * 0.3), int(hh * 1.3 - H)),
                    (int(hw * 0.3), int(hh * 1.3)),
                ]
                pygame.draw.polygon(hover_surf, hover_color, hover_pts)
                self.screen.blit(hover_surf, (int(x - hw * 1.3), int(y - hh * 1.3)))

        if zoom >= 1.55 and tile.collection_due == today and tile.bin_fill > 20:
            self._draw_wheelie_bin(b["B_bot"], b["B_right"], zoom, tile.bin_fill)

        if tile.bin_fill > 85:
            pygame.draw.circle(self.screen, (235, 70, 70),
                               (int(b["R_top"][0]), int(b["R_top"][1] - 6 * zoom)),
                               max(2, int(3 * zoom)))

        days_ov = getattr(tile, "days_overflowing", 0)
        if days_ov > 0:
            alpha    = min(170, 28 + days_ov * 35)
            tint_surf = self._get_alpha_surf(ts_w, ts_h)
            tint_pts  = [
                (int(hw * 1.3), int(hh * 1.3)),
                (int(hw * 2.3), int(hh * 0.3)),
                (int(hw * 2.3), int(hh * 0.3 - H)),
                (int(hw * 1.3), int(hh * 1.3 - H)),
                (int(hw * 0.3), int(hh * 1.3 - H)),
                (int(hw * 0.3), int(hh * 1.3)),
            ]
            pygame.draw.polygon(tint_surf, (210, 30, 30, alpha), tint_pts)
            self.screen.blit(tint_surf, (int(x - hw * 1.3), int(y - hh * 1.3)))

        if days_ov > 0 and zoom >= 0.9:
            self._draw_litter(b, days_ov, zoom)

    # ─── roofs ────────────────────────────────────────────────────────────────

    def _roof_hip(self, b, cc, zoom):
        ridge = 14 * zoom
        apex  = ((b["R_top"][0] + b["R_bot"][0]) / 2,
                 ((b["R_top"][1] + b["R_bot"][1]) / 2) - ridge)
        pygame.draw.polygon(self.screen, cc["roof_d"], [b["R_top"], b["R_right"], apex])
        pygame.draw.polygon(self.screen, cc["roof_l"], [b["R_top"], b["R_left"],  apex])
        pygame.draw.polygon(self.screen, cc["roof"],   [b["R_right"], b["R_bot"], apex])
        pygame.draw.polygon(self.screen, cc["roof_l"], [b["R_left"],  b["R_bot"], apex])
        pygame.draw.line(self.screen, cc["roof_h"], b["R_bot"], apex, max(1, int(zoom)))
        b["_apex"] = apex

    def _roof_gable(self, b, cc, zoom):
        rise = 15 * zoom
        m1   = ((b["R_top"][0] + b["R_left"][0]) / 2,
                (b["R_top"][1] + b["R_left"][1]) / 2 - rise)
        m2   = ((b["R_right"][0] + b["R_bot"][0]) / 2,
                (b["R_right"][1] + b["R_bot"][1]) / 2 - rise)
        pygame.draw.polygon(self.screen, cc["roof"],   [b["R_top"], b["R_right"], m2, m1])
        pygame.draw.polygon(self.screen, cc["roof_l"], [b["R_left"], b["R_bot"],  m2, m1])
        pygame.draw.polygon(self.screen, cc["roof_d"], [b["R_top"],  b["R_left"], m1])
        pygame.draw.polygon(self.screen, cc["roof_d"], [b["R_right"], b["R_bot"], m2])
        pygame.draw.line(self.screen, cc["roof_h"], m1, m2, max(1, int(zoom)))
        b["_apex"] = ((m1[0] + m2[0]) / 2, (m1[1] + m2[1]) / 2)

    def _roof_flat(self, b, cc, zoom):
        pygame.draw.polygon(self.screen, cc["roof"],
                            [b["R_top"], b["R_right"], b["R_bot"], b["R_left"]])
        pygame.draw.polygon(self.screen, cc["parapet"],
                            [b["R_top"], b["R_right"], b["R_bot"], b["R_left"]],
                            max(1, int(1.5 * zoom)))
        b["_apex"] = ((b["R_top"][0] + b["R_bot"][0]) / 2,
                      (b["R_top"][1] + b["R_bot"][1]) / 2)

    def _roof_mono(self, b, cc, zoom):
        rise  = 12 * zoom
        far_t = (b["R_top"][0],   b["R_top"][1]   - rise)
        far_r = (b["R_right"][0], b["R_right"][1] - rise)
        pygame.draw.polygon(self.screen, cc["roof"],
                            [far_t, far_r, b["R_bot"], b["R_left"]])
        pygame.draw.polygon(self.screen, cc["roof_d"],
                            [b["R_top"], b["R_right"], far_r, far_t])
        for u in (0.3, 0.5, 0.7):
            p1 = (far_t[0] + (b["R_left"][0] - far_t[0]) * u,
                  far_t[1] + (b["R_left"][1] - far_t[1]) * u)
            p2 = (far_r[0] + (b["R_bot"][0]  - far_r[0]) * u,
                  far_r[1] + (b["R_bot"][1]  - far_r[1]) * u)
            pygame.draw.line(self.screen, cc["roof_l"], p1, p2, max(1, int(zoom)))
        b["_apex"] = (b["R_top"][0], far_t[1])

    # ─── detailing ────────────────────────────────────────────────────────────

    def _house_details(self, tile, b, zoom, chimney, night=False):
        right, left = b["right"], b["left"]
        apex = b.get("_apex")
        if chimney and apex and zoom > 0.45:
            ch_w = 3 * zoom
            chx  = apex[0] + 5 * zoom
            chy  = apex[1] - 2 * zoom
            pygame.draw.rect(self.screen, (90, 70, 64),
                             pygame.Rect(int(chx), int(chy - 9 * zoom),
                                         int(ch_w), int(9 * zoom)))
            pygame.draw.rect(self.screen, (60, 46, 42),
                             pygame.Rect(int(chx - 1), int(chy - 11 * zoom),
                                         int(ch_w + 2), int(2.5 * zoom)))

        glass     = (150, 196, 230)
        lit_glass = (255, 214, 120)
        frame     = (238, 238, 238)
        seed      = int(tile.seed * 997)
        win_idx   = 0
        for u in (0.28, 0.66):
            q = _face_quad(right, u, 0.42, 0.16, 0.32)
            pygame.draw.polygon(self.screen, frame, self._grow(q, 1.3 * zoom))
            lit = night and ((seed + win_idx * 31) % 5 < 2)   # ~40% of windows lit
            pygame.draw.polygon(self.screen, lit_glass if lit else glass, q)
            win_idx += 1
        door = _face_quad(right, 0.06, 0.0, 0.16, 0.40)
        pygame.draw.polygon(self.screen, (70, 48, 38), door)
        q = _face_quad(left, 0.5, 0.48, 0.18, 0.30)
        pygame.draw.polygon(self.screen, frame, self._grow(q, 1.3 * zoom))
        lit = night and ((seed + win_idx * 31) % 5 < 2)
        pygame.draw.polygon(self.screen, lit_glass if lit else _shade(glass, 0.85), q)

    def _block_details(self, tile, b, zoom, tower, night=False):
        glass     = (158, 196, 224)
        lit_glass = (255, 213, 125)
        rows  = max(3, int(tile.building_height // (9 if tower else 12)))
        cols  = 4 if tower else 3
        # Per-building occupancy: roughly 28-83% of windows lit at night,
        # varied by the tile's seed so blocks don't all light identically.
        occ_pct = int(28 + (tile.seed * 997 % 1.0) * 55)
        for face, tone in ((b["right"], 1.0), (b["left"], 0.8)):
            for r in range(rows):
                v = 0.1 + r * (0.82 / rows)
                for c in range(cols):
                    u   = 0.12 + c * (0.78 / cols)
                    lit = night and (((r * 13 + c * 7 + int(tile.seed * 1000)) % 100) < occ_pct)
                    col = lit_glass if lit else _shade(glass, tone)
                    q   = _face_quad(face, u, v, 0.78 / cols * 0.62, 0.82 / rows * 0.55)
                    pygame.draw.polygon(self.screen, col, q)
        ent = _face_quad(b["right"], 0.34, 0.0, 0.30, 0.08)
        pygame.draw.polygon(self.screen, (60, 64, 72), ent)

    def _shop_details(self, tile, b, zoom, night=False):
        # A minority of shops stay lit into the evening (chippy, off-licence).
        shop_lit = night and (int(tile.seed * 733) % 100 < 25)
        for face, tone in ((b["right"], 1.0), (b["left"], 0.82)):
            fascia = [
                _face_pt(face, 0.04, 0.30), _face_pt(face, 0.96, 0.30),
                _face_pt(face, 0.96, 0.44), _face_pt(face, 0.04, 0.44),
            ]
            pygame.draw.polygon(self.screen, _shade((54, 58, 70), tone), fascia)
            front = [
                _face_pt(face, 0.06, 0.02), _face_pt(face, 0.94, 0.02),
                _face_pt(face, 0.94, 0.28), _face_pt(face, 0.06, 0.28),
            ]
            front_col = (255, 200, 110) if shop_lit else (150, 196, 220)
            pygame.draw.polygon(self.screen, _shade(front_col, tone), front)
            for i in range(4):
                u      = 0.08 + i * 0.21
                stripe = [
                    _face_pt(face, u,        0.30), _face_pt(face, u + 0.105, 0.30),
                    _face_pt(face, u + 0.105, 0.36), _face_pt(face, u,       0.36),
                ]
                col = (200, 90, 80) if i % 2 == 0 else (235, 235, 235)
                pygame.draw.polygon(self.screen, _shade(col, tone), stripe)

    def _warehouse_details(self, tile, b, zoom):
        face = b["right"]
        door = _face_quad(face, 0.20, 0.0, 0.40, 0.62)
        pygame.draw.polygon(self.screen, (70, 74, 82), door)
        for i in range(1, 5):
            v  = i * 0.12
            p1 = _face_pt(face, 0.20, v)
            p2 = _face_pt(face, 0.60, v)
            pygame.draw.line(self.screen, (52, 56, 62), p1, p2, max(1, int(zoom)))
        pd  = _face_quad(face, 0.70, 0.0, 0.12, 0.34)
        pygame.draw.polygon(self.screen, (60, 64, 72), pd)
        win = _face_quad(b["left"], 0.4, 0.5, 0.3, 0.18)
        pygame.draw.polygon(self.screen, (150, 190, 214), win)

    def _glass_details(self, tile, b, zoom, night=False):
        glass     = (150, 198, 236)
        lit_glass = (255, 210, 120)
        rows  = max(3, int(tile.building_height // 14))
        cols  = 3
        # Offices: most are dark at night bar cleaners / late workers.
        occ_pct = int(6 + (tile.seed * 853 % 1.0) * 22)
        for face, tone in ((b["right"], 1.0), (b["left"], 0.82)):
            for r in range(rows):
                v = 0.14 + r * (0.78 / rows)
                for c in range(cols):
                    u = 0.14 + c * (0.74 / cols)
                    lit = night and (((r * 11 + c * 5 + int(tile.seed * 1500)) % 100) < occ_pct)
                    q = _face_quad(face, u, v, 0.66 / cols * 0.7, 0.78 / rows * 0.55)
                    pygame.draw.polygon(self.screen, lit_glass if lit else _shade(glass, tone), q)
            band = [
                _face_pt(face, 0.06, 0.0), _face_pt(face, 0.94, 0.0),
                _face_pt(face, 0.94, 0.12), _face_pt(face, 0.06, 0.12),
            ]
            pygame.draw.polygon(self.screen, _shade((60, 70, 90), tone), band)

    def _rooftop_kit(self, b, zoom, mast=False):
        apex = b.get("_apex")
        if not apex:
            return
        pygame.draw.rect(self.screen, (120, 124, 130),
                         pygame.Rect(int(apex[0] - 5 * zoom), int(apex[1] - 5 * zoom),
                                     int(10 * zoom), int(5 * zoom)))
        if mast:
            pygame.draw.line(self.screen, (160, 164, 170),
                             (apex[0], apex[1] - 5  * zoom),
                             (apex[0], apex[1] - 18 * zoom), max(1, int(zoom)))
            pygame.draw.circle(self.screen, (235, 70, 70),
                               (int(apex[0]), int(apex[1] - 18 * zoom)),
                               max(1, int(1.4 * zoom)))

    # ─── wheelie bin ──────────────────────────────────────────────────────────

    def _draw_wheelie_bin(self, base_near, base_right, zoom, fill):
        bx = base_near[0] + (base_right[0] - base_near[0]) * 0.35 + 4 * zoom
        by = base_near[1] + (base_right[1] - base_near[1]) * 0.35 + 5 * zoom
        w  = max(2, int(4 * zoom))
        h  = max(3, int(7 * zoom))
        body = pygame.Rect(int(bx - w / 2), int(by - h), w, h)
        lid  = ((210, 60, 60) if fill > 85 else
                (220, 150, 50) if fill > 60 else
                (70, 170, 90))
        pygame.draw.rect(self.screen, (45, 55, 50), body, border_radius=max(1, int(zoom)))
        pygame.draw.rect(self.screen, lid,
                         pygame.Rect(body.x - 1, body.y - max(1, int(1.5 * zoom)),
                                     w + 2, max(1, int(2 * zoom))),
                         border_radius=max(1, int(zoom)))
        if zoom > 0.6:
            pygame.draw.circle(self.screen, (20, 20, 20),
                               (body.x + 1, body.bottom), max(1, int(zoom)))
            pygame.draw.circle(self.screen, (20, 20, 20),
                               (body.right - 1, body.bottom), max(1, int(zoom)))

    # ─── worker ───────────────────────────────────────────────────────────────

    def draw_worker(self, x, y, w, zoom):
        s = max(0.7, zoom)
        pygame.draw.ellipse(self.screen, (18, 22, 30),
                            pygame.Rect(int(x - 4 * s), int(y - 1 * s),
                                        int(8 * s), int(3 * s)))
        pygame.draw.line(self.screen, (40, 44, 60),
                         (x - 1.5 * s, y - 2 * s), (x - 1.5 * s, y), max(1, int(1.4 * s)))
        pygame.draw.line(self.screen, (40, 44, 60),
                         (x + 1.5 * s, y - 2 * s), (x + 1.5 * s, y), max(1, int(1.4 * s)))
        vest = (255, 150, 0) if w["state"] == "out" else (255, 200, 40)
        pygame.draw.rect(self.screen, vest,
                         pygame.Rect(int(x - 2.5 * s), int(y - 7 * s),
                                     int(5 * s), int(5.5 * s)),
                         border_radius=max(1, int(s)))
        pygame.draw.line(self.screen, (240, 255, 255),
                         (x - 2 * s, y - 4.5 * s), (x + 2 * s, y - 4.5 * s),
                         max(1, int(s)))
        pygame.draw.circle(self.screen, (235, 200, 170),
                           (int(x), int(y - 8.5 * s)), max(1, int(1.6 * s)))
        pygame.draw.circle(self.screen, (255, 220, 0),
                           (int(x), int(y - 9.2 * s)), max(1, int(1.7 * s)),
                           max(1, int(s)))
        if w["state"] == "back" and w.get("carry", 0) > 0:
            pygame.draw.circle(self.screen, (40, 50, 45),
                               (int(x + 3 * s), int(y - 4 * s)), max(1, int(1.8 * s)))

    # ─── landfill ─────────────────────────────────────────────────────────────

    def draw_landfill(self, cx, cy, city, zoom, snow=0.0):
        lf = getattr(city, "landfill", None)
        if not lf:
            return
        iso = self.to_iso(lf["cx"], lf["cy"])
        x   = cx + iso[0] * zoom
        y   = cy + iso[1] * zoom
        hw  = (self.tile_w / 2) * zoom
        hh  = (self.tile_h / 2) * zoom
        base_w = hw * 3.0
        base_h = hh * 3.0

        for i, (f, col) in enumerate([(1.0, (58, 52, 40)), (0.74, (78, 70, 52)),
                                       (0.48, (98, 88, 64)), (0.24, (120, 110, 78))]):
            ry = y - i * 7 * zoom
            pygame.draw.ellipse(self.screen, _snow_ground(col, snow, 0.85), pygame.Rect(
                int(x - base_w * f), int(ry - base_h * f * 0.5),
                int(base_w * 2 * f), int(base_h * f)))

        # Seeded RNG so specks don't shimmer each frame — use module-level random
        rng = random.Random(0xB1A5)
        for _ in range(int(46 * zoom)):
            sx = x + rng.uniform(-base_w * 0.95, base_w * 0.95)
            sy = (y + rng.uniform(-base_h * 0.45, base_h * 0.35)
                    - rng.uniform(0, 20) * zoom)
            c  = rng.choice([(38, 38, 38), (120, 32, 32), (32, 90, 44),
                              (40, 64, 120), (150, 150, 150), (150, 130, 40)])
            pygame.draw.circle(self.screen, c, (int(sx), int(sy)),
                               max(1, int(1.5 * zoom)))

        g = lf.get("gate")
        if g and zoom > 0.4:
            giso = self.to_iso(g[0], g[1])
            gx   = cx + giso[0] * zoom
            gy   = cy + giso[1] * zoom
            pygame.draw.rect(self.screen, (210, 188, 44), pygame.Rect(
                int(gx - 7 * zoom), int(gy - 3 * zoom),
                int(14 * zoom), int(3 * zoom)))
            pygame.draw.rect(self.screen, (40, 40, 44), pygame.Rect(
                int(gx - 7 * zoom), int(gy - 3 * zoom),
                int(14 * zoom), int(3 * zoom)),
                max(1, int(zoom)))

        if zoom > 0.4:
            font = _get_font("segoeui", max(7, int(9 * zoom)), bold=True)
            text = font.render("LANDFILL SITE", True, (245, 245, 245))
            rect  = text.get_rect(center=(int(x), int(y - base_h - 20 * zoom)))
            board = pygame.Rect(rect.x - 6, rect.y - 3,
                                rect.width + 12, rect.height + 6)
            pygame.draw.rect(self.screen, (38, 40, 48), board)
            pygame.draw.rect(self.screen, (200, 160, 60), board, 1)
            pygame.draw.line(self.screen, (120, 110, 80),
                             (x, board.bottom), (x, y - base_h * 0.5),
                             max(1, int(2 * zoom)))
            self.screen.blit(text, rect)

    # ─── road works ───────────────────────────────────────────────────────────

    def draw_road_works(self, cx, cy, city, zoom):
        """Draw orange construction barriers on tiles blocked by road works."""
        rw = getattr(city, "road_works_tiles", None)
        if not rw:
            return
        sw, sh = self.screen.get_size()
        hw = (self.tile_w / 2) * zoom
        hh = (self.tile_h / 2) * zoom

        # Build the diamond tint stamp ONCE for all road-work tiles.
        # At a given zoom level every stamp is the same shape, so we draw it
        # once and blit the same surface N times.
        stamp_w  = int(hw * 2.2)
        stamp_h  = int(hh * 2.2)
        tint_stamp = self._get_alpha_surf(stamp_w, stamp_h)
        pygame.draw.polygon(tint_stamp, (255, 130, 0, 160), [
            (int(hw * 1.1), int(hh * 0.1)),
            (int(hw * 2.1), int(hh * 1.1)),
            (int(hw * 1.1), int(hh * 2.1)),
            (int(hw * 0.1), int(hh * 1.1)),
        ])

        cone_h = max(4, int(10 * zoom))
        cone_w = max(2, int(4  * zoom))
        offsets = [
            ( hw * 0.35,  hh * 0.55),
            (-hw * 0.35,  hh * 0.55),
            ( 0.0,        hh * 1.15),
        ]

        # Label font — fetched once from cache for all tiles
        label_font = _get_font("segoeui", max(6, int(7 * zoom)), bold=True) if zoom >= 1.2 else None

        for (tx, ty) in rw:
            iso = self.to_iso(tx, ty)
            ix  = cx + iso[0] * zoom
            iy  = cy + iso[1] * zoom
            if ix < -hw * 2 or ix > sw + hw * 2:
                continue
            if iy < -hh * 2 or iy > sh + hh * 2:
                continue

            self.screen.blit(tint_stamp, (int(ix - hw * 1.1), int(iy - hh * 1.1)))

            for ox, oy in offsets:
                bx = int(ix + ox)
                by = int(iy + hh + oy)
                pygame.draw.polygon(self.screen, (255, 100, 0), [
                    (bx,          by - cone_h),
                    (bx - cone_w, by),
                    (bx + cone_w, by),
                ])
                stripe_y = by - cone_h // 2
                pygame.draw.line(self.screen, (240, 240, 240),
                                 (bx - cone_w // 2, stripe_y),
                                 (bx + cone_w // 2, stripe_y),
                                 max(1, int(zoom)))

            if label_font:
                label = label_font.render("ROAD WORKS", True, (255, 220, 0))
                lrect = label.get_rect(center=(int(ix), int(iy + hh * 0.5)))
                bg    = pygame.Surface((label.get_width() + 4, label.get_height() + 2),
                                       pygame.SRCALPHA)
                bg.fill((30, 30, 30, 160))
                self.screen.blit(bg,    (lrect.x - 2, lrect.y - 1))
                self.screen.blit(label, lrect)

    # ─── depot ────────────────────────────────────────────────────────────────

    def draw_depot(self, x, y, zoom, fleet=None):
        hw = (self.tile_w / 2) * zoom
        hh = (self.tile_h / 2) * zoom
        f  = 1.25
        H  = 30 * zoom
        b  = self._box(x, y, hw, hh, f, H)

        pygame.draw.polygon(self.screen, (74, 78, 86),
                            [b["B_top"], b["B_right"], b["B_bot"], b["B_left"]])

        wall_r = (120, 124, 130)
        wall_l = (96,  100, 106)
        roof_c = (150, 154, 160)
        roof_d = (110, 114, 120)

        pygame.draw.polygon(self.screen, wall_r, list(b["right"]))
        pygame.draw.polygon(self.screen, wall_l, list(b["left"]))

        rise = 16 * zoom
        m1   = ((b["R_top"][0] + b["R_left"][0])  / 2,
                (b["R_top"][1] + b["R_left"][1])  / 2 - rise)
        m2   = ((b["R_right"][0] + b["R_bot"][0]) / 2,
                (b["R_right"][1] + b["R_bot"][1]) / 2 - rise)
        pygame.draw.polygon(self.screen, roof_c, [b["R_top"], b["R_right"], m2, m1])
        pygame.draw.polygon(self.screen, roof_d, [b["R_left"], b["R_bot"],  m2, m1])
        pygame.draw.polygon(self.screen, (88, 92, 98), [b["R_top"],   b["R_left"],  m1])
        pygame.draw.polygon(self.screen, (88, 92, 98), [b["R_right"], b["R_bot"],   m2])

        if zoom >= 1.0:
            for u in (0.14, 0.56):
                door = _face_quad(b["right"], u, 0.0, 0.30, 0.66)
                pygame.draw.polygon(self.screen, (66, 70, 78), door)
                for i in range(1, 5):
                    v = i * 0.13
                    pygame.draw.line(self.screen, (48, 52, 58),
                                     _face_pt(b["right"], u, v),
                                     _face_pt(b["right"], u + 0.30, v),
                                     max(1, int(zoom)))
            stripe = [
                _face_pt(b["right"], 0.0, 0.0), _face_pt(b["right"], 1.0, 0.0),
                _face_pt(b["right"], 1.0, 0.06), _face_pt(b["right"], 0.0, 0.06),
            ]
            pygame.draw.polygon(self.screen, (220, 196, 60), stripe)

        if zoom > 0.4:
            font = _get_font("segoeui", max(7, int(9 * zoom)), bold=True)
            text = font.render("COUNCIL DEPOT", True, (245, 245, 245))
            rect  = text.get_rect(center=(int(x), int(b["R_top"][1] - 30 * zoom)))
            board = pygame.Rect(rect.x - 6, rect.y - 3,
                                rect.width + 12, rect.height + 6)
            pygame.draw.rect(self.screen, (38, 40, 48), board)
            pygame.draw.rect(self.screen, (200, 204, 210), board, 1)
            pygame.draw.line(self.screen, (120, 124, 130),
                             (x, board.bottom), (x, b["R_top"][1] - 4 * zoom),
                             max(1, int(2 * zoom)))
            self.screen.blit(text, rect)

        if fleet and getattr(fleet, "on_strike", False) and zoom > 0.4:
            n_workers = min(8, max(2, fleet.workers))
            for i in range(n_workers):
                angle = (i / n_workers) * 3.14 + 0.3
                wx    = int(x + math.cos(angle) * hw * f * 1.4)
                wy    = int(y + hh + math.sin(angle) * hh * f * 1.4)
                s2    = max(0.6, zoom)
                pygame.draw.rect(self.screen, (255, 180, 0),
                                 pygame.Rect(wx - int(2.5 * s2), wy - int(7 * s2),
                                             int(5 * s2), int(5 * s2)))
                pygame.draw.circle(self.screen, (235, 200, 160),
                                   (wx, wy - int(8.5 * s2)), max(1, int(2 * s2)))
                pygame.draw.line(self.screen, (180, 150, 100),
                                 (wx, wy - int(10 * s2)), (wx, wy - int(16 * s2)),
                                 max(1, int(s2)))
                pygame.draw.rect(self.screen, (255, 60, 60),
                                 pygame.Rect(wx - int(4 * s2), wy - int(16 * s2),
                                             int(8 * s2), int(5 * s2)))

            font_s      = _get_font("segoeui", max(8, int(10 * zoom)), bold=True)
            strike_text = font_s.render("ON STRIKE", True, (255, 60, 60))
            srect       = strike_text.get_rect(
                center=(int(x), int(y - 30 * zoom * 1.25 - 28 * zoom)))
            bg_s = pygame.Surface(
                (strike_text.get_width() + 8, strike_text.get_height() + 4),
                pygame.SRCALPHA)
            bg_s.fill((0, 0, 0, 160))
            self.screen.blit(bg_s,        (srect.x - 4, srect.y - 2))
            self.screen.blit(strike_text,  srect)

    # ─── truck ────────────────────────────────────────────────────────────────

    def draw_truck(self, x, y, truck, zoom):
        if self._truck_icon is not None:
            s       = zoom * 1.2
            flip    = truck.get("facing", 1)
            icon_sz = int(32 * s)
            scaled  = pygame.transform.scale(self._truck_icon, (icon_sz, icon_sz))
            if flip < 0:
                scaled = pygame.transform.flip(scaled, True, False)
            self.screen.blit(scaled, scaled.get_rect(center=(int(x), int(y - 5 * s))))

            if zoom > 0.35:
                font = _get_font("monospace", max(5, int(6 * s)), bold=True)
                text = font.render(truck.get("nickname", f"L{truck['id']}"), True, (255, 255, 255))
                self.screen.blit(text, text.get_rect(center=(int(x), int(y + 6 * s))))
            return

        # Fallback sprite
        state = truck["state"]
        if state == "depot":
            cab_color  = (80,  80,  80)
            body_color = (110, 110, 110)
        elif state == "to_depot":
            cab_color  = (40,  110, 60)
            body_color = (224, 106, 0)
        else:
            cab_color  = (40,  120, 60)
            body_color = (210, 190, 40)

        s    = zoom * 1.2
        flip = truck.get("facing", 1)

        def px(dx):
            return x + dx * s * flip

        pygame.draw.ellipse(self.screen, (16, 20, 28),
                            pygame.Rect(int(x - 11 * s), int(y + 1 * s),
                                        int(22 * s), int(6 * s)))
        cab_pts = [(px(-8), y - 2 * s), (px(-2), y - 2 * s),
                   (px(-2), y - 8 * s), (px(-8), y - 8 * s)]
        pygame.draw.polygon(self.screen, cab_color, cab_pts)
        pygame.draw.polygon(self.screen, (28, 28, 28), cab_pts, max(1, int(s)))
        pygame.draw.polygon(self.screen, (185, 222, 255),
                            [(px(-7), y - 7 * s), (px(-3), y - 7 * s),
                             (px(-3), y - 4.2 * s), (px(-7), y - 4.2 * s)])
        body_pts = [(px(2), y - 2 * s), (px(10), y - 2 * s),
                    (px(10), y - 10 * s), (px(2), y - 10 * s)]
        pygame.draw.polygon(self.screen, body_color, body_pts)
        pygame.draw.polygon(self.screen, (28, 28, 28), body_pts, max(1, int(s)))

        load_pct = truck["load"] / truck["capacity"] if truck["capacity"] else 0
        if load_pct > 0:
            fh         = 8 * s * load_pct
            fill_color = ((255, 70, 70)  if load_pct > 0.8 else
                          (255, 160, 0)  if load_pct > 0.5 else
                          (70, 220, 70))
            fr   = pygame.Rect(0, 0, int(7 * s), int(fh))
            fr.x = int(min(px(2.5), px(9.5)))
            fr.y = int(y - 2 * s - fh)
            pygame.draw.rect(self.screen, fill_color, fr)

        wr = max(2, int(2.4 * s))
        pygame.draw.circle(self.screen, (26, 26, 26), (int(px(-6)), int(y)), wr)
        pygame.draw.circle(self.screen, (90, 90, 90), (int(px(-6)), int(y)), max(1, int(s)))
        pygame.draw.circle(self.screen, (26, 26, 26), (int(px( 7)), int(y)), wr)
        pygame.draw.circle(self.screen, (90, 90, 90), (int(px( 7)), int(y)), max(1, int(s)))

        if state == "servicing":
            flash  = math.sin(pygame.time.get_ticks() / 100) > 0
            beacon = (255, 60, 60) if flash else (150, 40, 40)
            pygame.draw.circle(self.screen, beacon,
                               (int(px(-5)), int(y - 9 * s)), max(2, int(1.6 * s)))

        on_board = max(0, truck["crew"] - len(truck.get("out_workers", [])))
        for i in range(on_board):
            dot_x = x - (on_board - 1) * 3 * s + i * 6 * s
            pygame.draw.circle(self.screen, (255, 255, 255),
                               (int(dot_x), int(y - 13 * s)), max(1, int(1.8 * s)))

        if zoom > 0.35:
            font = _get_font("monospace", max(5, int(6 * s)), bold=True)
            text = font.render(truck.get("nickname", f"L{truck['id']}"), True, (255, 255, 255))
            self.screen.blit(text, text.get_rect(center=(int(x), int(y + 6 * s))))

        if truck.get("broken"):
            t_ms   = pygame.time.get_ticks()
            tri_cx = int(x)
            tri_cy = int(y - 17 * s)
            tri_r  = max(4, int(6 * s))
            pygame.draw.polygon(self.screen, (220, 200, 0), [
                (tri_cx,                   tri_cy - tri_r),
                (tri_cx - int(tri_r * 0.9), tri_cy + int(tri_r * 0.5)),
                (tri_cx + int(tri_r * 0.9), tri_cy + int(tri_r * 0.5)),
            ])
            pygame.draw.polygon(self.screen, (40, 40, 40), [
                (tri_cx,                   tri_cy - tri_r),
                (tri_cx - int(tri_r * 0.9), tri_cy + int(tri_r * 0.5)),
                (tri_cx + int(tri_r * 0.9), tri_cy + int(tri_r * 0.5)),
            ], max(1, int(s)))
            bang   = _get_font("segoeui", max(5, int(5 * s)), bold=True)
            bang_t = bang.render("!", True, (40, 40, 40))
            self.screen.blit(bang_t, bang_t.get_rect(center=(tri_cx, tri_cy)))

            for k in range(3):
                phase   = (t_ms / 600.0 + k * 0.33) % 1.0
                smoke_x = int(x + (k - 1) * 3 * s)
                smoke_y = int(y - 10 * s - phase * 12 * s)
                alpha   = int(180 * (1.0 - phase))
                r       = max(1, int((1 + phase * 3) * s))
                if alpha > 20:
                    smoke_s = self._get_alpha_surf(r * 2 + 2, r * 2 + 2)
                    pygame.draw.circle(smoke_s, (160, 160, 160, alpha),
                                       (r + 1, r + 1), r)
                    self.screen.blit(smoke_s, (smoke_x - r - 1, smoke_y - r - 1))

    # ─── ambient cars ─────────────────────────────────────────────────────────

    def draw_ambient_car(self, x, y, car, zoom):
        s     = zoom * 0.7
        color = car["color"]
        flip  = car.get("facing", 1)

        def px(dx):
            return x + dx * s * flip

        pygame.draw.ellipse(self.screen, (16, 20, 28),
                            pygame.Rect(int(x - 7 * s), int(y + 1 * s),
                                        int(14 * s), int(4 * s)))
        pts = [(px(-5), y - 1 * s), (px(5), y - 1 * s),
               (px(5),  y - 5 * s), (px(-5), y - 5 * s)]
        pygame.draw.polygon(self.screen, color, pts)
        roof_pts = [(px(-3), y - 5 * s), (px(3),   y - 5 * s),
                    (px(2.5), y - 8 * s), (px(-2.5), y - 8 * s)]
        pygame.draw.polygon(self.screen, _shade(color, 0.75), roof_pts)
        pygame.draw.polygon(self.screen, (170, 210, 240),
                            [(px(-2.2), y - 5.1 * s), (px(2.2), y - 5.1 * s),
                             (px(1.8),  y - 7.6 * s), (px(-1.8), y - 7.6 * s)])
        wr = max(1, int(1.8 * s))
        for wx2 in (-3.5, 3.5):
            pygame.draw.circle(self.screen, (22, 22, 22), (int(px(wx2)), int(y)), wr)
            pygame.draw.circle(self.screen, (80, 80, 80), (int(px(wx2)), int(y)),
                               max(1, wr - 1))

    # ─── peds ─────────────────────────────────────────────────────────────────

    def draw_ped(self, x, y, ped, zoom):
        s   = zoom * 0.55
        bob = math.sin(ped.get("bob", 0)) * 1.0 * s
        col = ped.get("vest", (255, 160, 0))

        pygame.draw.rect(self.screen, col,
                         pygame.Rect(int(x - 1.5 * s), int(y - 6 * s + bob),
                                     int(3 * s), int(4 * s)),
                         border_radius=max(1, int(s)))
        pygame.draw.circle(self.screen, (230, 195, 160),
                           (int(x), int(y - 7.5 * s + bob)), max(1, int(1.4 * s)))
        leg = math.sin(ped.get("bob", 0) * 2)
        pygame.draw.line(self.screen, (60, 60, 80),
                         (int(x - s * 0.8), int(y - 2 * s)),
                         (int(x - s * 0.8 + leg * s), int(y + s)),
                         max(1, int(s * 0.8)))
        pygame.draw.line(self.screen, (60, 60, 80),
                         (int(x + s * 0.8), int(y - 2 * s)),
                         (int(x + s * 0.8 - leg * s), int(y + s)),
                         max(1, int(s * 0.8)))

    # ─── birds ────────────────────────────────────────────────────────────────

    def draw_birds(self, cx, cy, birds_sys, zoom):
        """Seagulls circling the landfill."""
        for b in birds_sys.birds:
            iso  = self.to_iso(b["lcx"], b["lcy"])
            lx   = cx + iso[0] * zoom
            ly   = cy + iso[1] * zoom
            bx   = lx + math.cos(b["angle"]) * b["radius"] * self.tile_w * zoom * 0.6
            by   = ly + math.sin(b["angle"]) * b["radius"] * self.tile_h * zoom * 0.4
            bob_y = math.sin(b["bob"]) * 3 * zoom
            bx, by = int(bx), int(by + bob_y)
            wing = math.sin(b["wing"]) * 0.5 + 0.5
            ws   = max(1, int(4 * zoom))
            wh   = max(1, int(2 * zoom * (0.3 + wing * 0.7)))
            pygame.draw.ellipse(self.screen, (240, 240, 240),
                                pygame.Rect(bx - ws // 2, by - 1, ws, max(1, int(2 * zoom))))
            pygame.draw.line(self.screen, (220, 220, 220),
                             (bx - ws, by - wh), (bx, by), max(1, int(zoom)))
            pygame.draw.line(self.screen, (220, 220, 220),
                             (bx + ws, by - wh), (bx, by), max(1, int(zoom)))

    # ─── aircraft ─────────────────────────────────────────────────────────────

    def draw_aircraft(self, cx, cy, aircraft_sys, zoom):
        """A rare, distant airliner crossing high above the borough, with a
        short fading contrail. Pure scenery."""
        for p in aircraft_sys.planes:
            sx, sy = p["start"]
            ex, ey = p["end"]
            t = p["t"]
            wx = sx + (ex - sx) * t
            wy = sy + (ey - sy) * t
            iso = self.to_iso(wx, wy)
            alt = 230 * zoom
            px = cx + iso[0] * zoom
            py = cy + iso[1] * zoom - alt
            dirx = 1 if ex >= sx else -1

            # Fading contrail behind the aircraft
            for i in range(1, 8):
                tt = t - i * 0.012
                if tt < 0:
                    break
                twx = sx + (ex - sx) * tt
                twy = sy + (ey - sy) * tt
                tiso = self.to_iso(twx, twy)
                tx = cx + tiso[0] * zoom
                ty = cy + tiso[1] * zoom - alt
                r = max(1, int((4 - i * 0.4) * zoom * 0.5))
                shade = max(55, 215 - i * 20)
                pygame.draw.circle(self.screen, (shade, shade, shade + 6), (int(tx), int(ty)), r)

            s = max(2.0, 3.2 * zoom)
            body_col = (28, 30, 36)
            pts = [
                (px - 6 * s * dirx, py),
                (px + 6 * s * dirx, py),
                (px + 2 * s * dirx, py - 1.4 * s),
                (px - 2 * s * dirx, py - 1.4 * s),
            ]
            pygame.draw.polygon(self.screen, body_col, pts)
            pygame.draw.line(self.screen, body_col,
                             (px, py + 4 * s), (px, py - 1 * s), max(1, int(s * 0.7)))
            if math.sin(pygame.time.get_ticks() / 250.0 + p["blink"]) > 0.6:
                pygame.draw.circle(self.screen, (235, 60, 60),
                                   (int(px + 6 * s * dirx), int(py)), max(1, int(s * 0.5)))

    # ─── day / night ──────────────────────────────────────────────────────────

    def draw_daynight(self, day_progress):
        """Full-screen day/night tint: warm at dusk/dawn, deep blue by night,
        nothing at midday. A single cheap alpha blit, same trick as the
        weather overlay."""
        darkness = 1.0 - _daylight_brightness(day_progress)
        if darkness <= 0.02:
            return
        alpha = min(165, int((darkness ** 1.4) * 170))
        dusk_col  = (235, 130, 70)
        night_col = (8, 14, 38)
        col = _blend(dusk_col, night_col, min(1.0, darkness * 1.3))
        sw, sh = self.screen.get_size()
        overlay = self._get_alpha_surf(sw, sh)
        overlay.fill((col[0], col[1], col[2], alpha))
        self.screen.blit(overlay, (0, 0))

    # ─── weather ──────────────────────────────────────────────────────────────

    def draw_weather(self, weather, day_timer, day_duration):
        """Rain streaks or snow flakes across the whole screen.

        Instead of allocating 60-120 tiny SRCALPHA surfaces per frame (the
        original approach), we maintain a single screen-sized overlay and
        rebuild it only every 80 ms — matching the animation granularity of
        the seeded RNG that was already baked into the original code.
        """
        if weather not in ("rain", "snow"):
            return

        sw, sh   = self.screen.get_size()
        t_seed   = int(pygame.time.get_ticks() / 80)
        cur_size = (sw, sh)

        if (self._weather_seed != t_seed
                or self._weather_size != cur_size
                or self._weather_surf is None):
            self._weather_seed = t_seed
            self._weather_size = cur_size

            # Allocate (or resize) the dedicated weather overlay
            if self._weather_surf is None or self._weather_surf.get_size() != cur_size:
                self._weather_surf = pygame.Surface(cur_size, pygame.SRCALPHA)

            self._weather_surf.fill((0, 0, 0, 0))
            rng = random.Random(t_seed)

            if weather == "rain":
                for _ in range(120):
                    rx = rng.randint(0, sw - 1)
                    ry = rng.randint(0, sh - 1)
                    ln = rng.randint(6, 14)
                    pygame.draw.line(self._weather_surf, (140, 160, 200, 55),
                                     (rx, ry), (rx, min(sh - 1, ry + ln)), 2)
            else:   # snow
                for _ in range(60):
                    rx = rng.randint(0, sw - 1)
                    ry = rng.randint(0, sh - 1)
                    r  = rng.randint(1, 3)
                    pygame.draw.circle(self._weather_surf, (230, 240, 255, 90),
                                       (rx, ry), r)

        self.screen.blit(self._weather_surf, (0, 0))

    # ─── litter ───────────────────────────────────────────────────────────────

    def _draw_litter(self, b, days_ov, zoom):
        """Scatter rubbish bags near base of overflowing buildings."""
        n_bags     = min(6, days_ov * 2)
        seed       = int(b["B_bot"][0] * 13 + b["B_bot"][1] * 7) & 0xffff
        rng        = random.Random(seed)
        bag_colors = [(35, 35, 35), (120, 30, 30), (40, 80, 120), (60, 110, 55)]
        for _ in range(n_bags):
            ox = rng.uniform(-0.6, 0.6)
            oy = rng.uniform(0.0, 0.5)
            bx = b["B_bot"][0] + ox * (b["B_right"][0] - b["B_bot"][0]) * 0.8
            by = b["B_bot"][1] + oy * zoom * 4
            r  = max(1, int(1.4 * zoom))
            pygame.draw.circle(self.screen, rng.choice(bag_colors), (int(bx), int(by)), r)

    # ─── area overlay ─────────────────────────────────────────────────────────

    def draw_area_overlay(self, cx, cy, city, zoom, today):
        """Boundary lines + a small monochrome tag per round (planning view)."""
        line = (235, 235, 235)
        for c in range(1, AREA_COLS):
            gx = city.width * c // AREA_COLS
            self._draw_edge_line(cx, cy, gx, 0, gx, city.height, zoom, line)
        for r in range(1, AREA_ROWS):
            gy = city.height * r // AREA_ROWS
            self._draw_edge_line(cx, cy, 0, gy, city.width, gy, zoom, line)

        font  = _get_font("segoeui", max(9, int(11 * zoom)), bold=True)
        small = _get_font("segoeui", max(8, int(9  * zoom)))

        for area in city.areas:
            mid_x = (area.col + 0.5) * city.width  / AREA_COLS
            mid_y = (area.row + 0.5) * city.height / AREA_ROWS
            iso   = self.to_iso(mid_x, mid_y)
            sx    = int(cx + iso[0] * zoom)
            sy    = int(cy + iso[1] * zoom)

            route_type = area.route_type
            if route_type == "residential":
                type_color = (150, 220, 150)
                type_label = "RES"
            elif route_type == "commercial":
                type_color = (150, 190, 220)
                type_label = "COM"
            else:
                type_color = (220, 210, 150)
                type_label = "MIX"

            name      = font.render(area.name, True, (245, 245, 245))
            day_str   = (DAY_NAMES[area.collection_day]
                         + ("  (today)" if area.collection_day == today else ""))
            day       = small.render(day_str, True, (210, 210, 210))
            type_surf = small.render(type_label, True, type_color)

            w   = max(name.get_width(), day.get_width(), type_surf.get_width()) + 14
            h   = (name.get_height() + day.get_height()
                   + type_surf.get_height() + 14)
            box = pygame.Rect(sx - w // 2, sy - h // 2, w, h)
            pygame.draw.rect(self.screen, (24, 24, 24), box)
            pygame.draw.rect(
                self.screen,
                (245, 245, 245) if area.collection_day == today else (250, 250, 250),
                box, 2)
            pygame.draw.rect(self.screen, type_color,
                             pygame.Rect(box.x, box.y, 4, box.height))
            self.screen.blit(name,
                             (box.centerx - name.get_width() // 2, box.y + 4))
            self.screen.blit(type_surf,
                             (box.centerx - type_surf.get_width() // 2,
                              box.y + 6 + name.get_height()))
            self.screen.blit(day,
                             (box.centerx - day.get_width() // 2,
                              box.y + 8 + name.get_height() + type_surf.get_height()))

    # ─── helpers ──────────────────────────────────────────────────────────────

    @staticmethod
    def _grow(quad, amount):
        cx = sum(p[0] for p in quad) / 4.0
        cy = sum(p[1] for p in quad) / 4.0
        out = []
        for px_, py_ in quad:
            dx, dy = px_ - cx, py_ - cy
            d = math.hypot(dx, dy) or 1.0
            out.append((px_ + dx / d * amount, py_ + dy / d * amount))
        return out
