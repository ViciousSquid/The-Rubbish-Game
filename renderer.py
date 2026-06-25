import pygame
import math
import os
from city import AREA_COLS, AREA_ROWS, DAY_NAMES

# Try to load truck.png for truck sprites
try:
    from PIL import Image
    _ico_path = "truck.png"
    _truck_icon = None
    if os.path.exists(_ico_path):
        img = Image.open(_ico_path)
        # Convert to RGBA and create pygame surface
        img = img.convert("RGBA")
        _truck_icon = pygame.image.fromstring(img.tobytes(), img.size, "RGBA")
except Exception:
    _truck_icon = None


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

# Zone type colors for ground tiles - clearly differentiated
RESIDENTIAL_ZONE = (104, 150, 86)      # Warm green for residential
COMMERCIAL_ZONE = (96, 116, 84)         # Cooler blue-green for commercial
ROAD_COLOR = (78, 80, 86)
GREEN_ZONE = (95, 145, 85)

# Area overlay colors by route type
RESIDENTIAL_AREA_COLOR = (200, 220, 180, 40)
COMMERCIAL_AREA_COLOR = (180, 200, 230, 40)
MIXED_AREA_COLOR = (220, 210, 180, 40)


class Renderer:
    def __init__(self, screen, camera):
        self.screen = screen
        self.camera = camera
        self.tile_w = 64
        self.tile_h = 32

        # Load truck icon if available
        self._truck_icon = None
        try:
            from PIL import Image
            png_path = "truck.png"
            if os.path.exists(png_path):
                img = Image.open(png_path).convert("RGBA")
                self._truck_icon = pygame.image.fromstring(img.tobytes(), img.size, "RGBA")
        except Exception:
            self._truck_icon = None

    # ----------------------------------------------------------------- render
    def render(self, city, fleet, selected_tile=None, today=0, show_areas=False, hovered_tile=None):
        cx = self.screen.get_width() // 2 + self.camera["x"]
        cy = 120 + self.camera["y"]
        zoom = self.camera["zoom"]
        sw, sh = self.screen.get_size()

        self._draw_ground_plane(cx, cy, city, zoom)
        self._draw_city_boundary(cx, cy, city, zoom)

        for y in range(city.height):
            for x in range(city.width):
                iso = self.to_iso(x, y)
                ix = cx + iso[0] * zoom
                iy = cy + iso[1] * zoom
                if ix < -80 * zoom or ix > sw + 80 * zoom:
                    continue
                if iy < -320 * zoom or iy > sh + 80 * zoom:
                    continue

                tile = city.get_tile(x, y)
                selected = selected_tile and selected_tile["x"] == x and selected_tile["y"] == y
                hovered = hovered_tile and hovered_tile["x"] == x and hovered_tile["y"] == y
                self.draw_tile(ix, iy, tile, selected, zoom, city)
                if tile.type not in ("road", "green", "landfill"):
                    self.draw_building(ix, iy, tile, zoom, today, hovered, selected)

        # Landfill site (large refuse mound in a corner)
        self.draw_landfill(cx, cy, city, zoom)

        # Depot
        depot_iso = self.to_iso(fleet.depot_x, fleet.depot_y)
        self.draw_depot(cx + depot_iso[0] * zoom, cy + depot_iso[1] * zoom, zoom)

        # Lorries + loaders
        for truck in fleet.trucks:
            iso = self.to_iso(truck["x"], truck["y"])
            self.draw_truck(cx + iso[0] * zoom, cy + iso[1] * zoom, truck, zoom)
            for w in truck.get("out_workers", []):
                wiso = self.to_iso(w["x"], w["y"])
                self.draw_worker(cx + wiso[0] * zoom, cy + wiso[1] * zoom, w, zoom)

        if show_areas:
            self.draw_area_overlay(cx, cy, city, zoom, today)

    # --------------------------------------------------------------- ground
    def _draw_ground_plane(self, cx, cy, city, zoom):
        corners = [
            self.to_iso(0, 0),
            self.to_iso(city.width, 0),
            self.to_iso(city.width, city.height),
            self.to_iso(0, city.height),
        ]
        points = [(cx + c[0] * zoom, cy + c[1] * zoom) for c in corners]
        pygame.draw.polygon(self.screen, (33, 38, 52), points)

    def _draw_city_boundary(self, cx, cy, city, zoom):
        self._draw_edge_line(cx, cy, 0, 0, city.width, 0, zoom, (120, 120, 130))
        self._draw_edge_line(cx, cy, city.width, 0, city.width, city.height, zoom, (100, 100, 110))
        self._draw_edge_line(cx, cy, city.width, city.height, 0, city.height, zoom, (80, 80, 90))
        self._draw_edge_line(cx, cy, 0, city.height, 0, 0, zoom, (100, 100, 110))

    def _draw_edge_line(self, cx, cy, x1, y1, x2, y2, zoom, color):
        start = self.to_iso(x1, y1)
        end = self.to_iso(x2, y2)
        pygame.draw.line(self.screen, color,
                         (cx + start[0] * zoom, cy + start[1] * zoom),
                         (cx + end[0] * zoom, cy + end[1] * zoom),
                         max(2, int(3 * zoom)))

    # ------------------------------------------------------------- iso maths
    def to_iso(self, x, y):
        return ((x - y) * (self.tile_w / 2), (x + y) * (self.tile_h / 2))

    def screen_to_tile(self, screen_x, screen_y, screen_w, screen_h):
        ix = (screen_x - screen_w // 2 - self.camera["x"]) / self.camera["zoom"]
        iy = (screen_y - 120 - self.camera["y"]) / self.camera["zoom"]
        tile_x = (ix / (self.tile_w / 2) + iy / (self.tile_h / 2)) / 2
        tile_y = (iy / (self.tile_h / 2) - ix / (self.tile_w / 2)) / 2
        return {"x": round(tile_x), "y": round(tile_y)}

    # ------------------------------------------------------------- tile floor
    def draw_tile(self, x, y, tile, is_selected, zoom, city=None):
        hw = (self.tile_w / 2) * zoom
        hh = (self.tile_h / 2) * zoom
        points = [(x, y), (x + hw, y + hh), (x, y + 2 * hh), (x - hw, y + hh)]

        # ---- ROAD  ----
        if tile.type == "road":
            pygame.draw.polygon(self.screen, ROAD_COLOR, points)
            if is_selected:
                pygame.draw.polygon(self.screen, (245, 245, 245), points, max(2, int(2 * zoom)))
            return

        # ---- GREEN SPACE ----
        if tile.type == "green":
            pygame.draw.polygon(self.screen, GREEN_ZONE, points)
            if zoom >= 0.8:
                cx = x
                cy = y + hh
                trunk_h = max(3, int(6 * zoom))
                trunk_w = max(2, int(3 * zoom))
                canopy_r = max(3, int(7 * zoom))
                # Trunk
                pygame.draw.rect(self.screen, (120, 90, 60),
                                 pygame.Rect(int(cx - trunk_w/2), int(cy - trunk_h),
                                             trunk_w, trunk_h))
                # Canopy
                pygame.draw.circle(self.screen, (70, 130, 60),
                                   (int(cx), int(cy - trunk_h)), canopy_r)
                pygame.draw.circle(self.screen, (100, 170, 85),
                                   (int(cx - canopy_r*0.3), int(cy - trunk_h - canopy_r*0.2)),
                                   int(canopy_r*0.7))
            if is_selected:
                pygame.draw.polygon(self.screen, (245, 245, 245), points, max(2, int(2 * zoom)))
            return

        # ---- LANDFILL ----
        if tile.type == "landfill":
            pygame.draw.polygon(self.screen, (74, 64, 48), points)   # churned earth
            if zoom >= 0.7:
                # a few scattered refuse specks so the ground reads as a tip
                seed = ((int(x) * 73856093) ^ (int(y) * 19349663)) & 0xffff
                for k in range(3):
                    sx = x + ((seed >> (k * 3)) % 7 - 3) * hw * 0.18
                    sy = y + hh + ((seed >> (k * 2)) % 5 - 2) * hh * 0.18
                    col = [(40, 40, 40), (120, 40, 40), (40, 80, 120)][k % 3]
                    pygame.draw.circle(self.screen, col, (int(sx), int(sy)),
                                       max(1, int(1.6 * zoom)))
            if is_selected:
                pygame.draw.polygon(self.screen, (245, 245, 245), points, max(2, int(2 * zoom)))
            return

        # ---- RESIDENTIAL / COMMERCIAL ----
        if tile.type == "commercial":
            base = COMMERCIAL_ZONE
        else:
            base = RESIDENTIAL_ZONE

        pygame.draw.polygon(self.screen, base, points)

        # Zone indicator dot
        if zoom >= 0.8:
            if tile.type == "commercial":
                indicator = (120, 145, 110)
            else:
                indicator = (130, 175, 110)
            cx = x
            cy = y + hh
            pygame.draw.circle(self.screen, indicator, (int(cx), int(cy)), max(1, int(2 * zoom)))

        detail = zoom >= 1.15

        # ---- SELECTION TINT ----
        if is_selected:
            tint_color = None
            if tile.type == "residential":
                tint_color = (120, 255, 120, 110)   # transparent green
            elif tile.type == "commercial":
                tint_color = (120, 200, 255, 110)   # transparent blue

            if tint_color:
                tint_surf = pygame.Surface((int(hw * 2.4), int(hh * 2.4)), pygame.SRCALPHA)
                tint_pts = [
                    (int(hw * 1.2), int(hh * 0.2)),
                    (int(hw * 2.2), int(hh * 1.2)),
                    (int(hw * 1.2), int(hh * 2.2)),
                    (int(hw * 0.2), int(hh * 1.2)),
                ]
                pygame.draw.polygon(tint_surf, tint_color, tint_pts)
                self.screen.blit(tint_surf, (int(x - hw * 0.2), int(y - hh * 0.2)))

            pygame.draw.polygon(self.screen, (245, 245, 245), points, max(2, int(2 * zoom)))
        elif detail:
            pygame.draw.polygon(self.screen, (40, 46, 40), points, max(1, int(zoom)))

    # ------------------------------------------------------------- buildings
    def _color_cache(self, tile):
        light = pygame.Color(tile.wall_color_light)
        dark = pygame.Color(tile.wall_color_dark)
        roof = pygame.Color(tile.roof_color)
        return {
            "wr": _shade(light, 1.0),
            "wl": _shade(dark, 0.78),
            "seam": _shade(dark, 0.55),
            "roof": _shade(roof, 1.0),
            "roof_l": _shade(roof, 0.78),
            "roof_d": _shade(roof, 0.6),
            "roof_h": _shade(roof, 1.22),
            "parapet": _shade(roof, 0.55),
        }

    def _box(self, x, y, hw, hh, f, H):
        cxc, cyc = x, y + hh
        B_top = (cxc, cyc - hh * f)
        B_right = (cxc + hw * f, cyc)
        B_bot = (cxc, cyc + hh * f)
        B_left = (cxc - hw * f, cyc)
        R_top = (B_top[0], B_top[1] - H)
        R_right = (B_right[0], B_right[1] - H)
        R_bot = (B_bot[0], B_bot[1] - H)
        R_left = (B_left[0], B_left[1] - H)
        right_face = (B_bot, B_right, R_right, R_bot)
        left_face = (B_bot, B_left, R_left, R_bot)
        return {
            "cxc": cxc, "cyc": cyc,
            "B_top": B_top, "B_right": B_right, "B_bot": B_bot, "B_left": B_left,
            "R_top": R_top, "R_right": R_right, "R_bot": R_bot, "R_left": R_left,
            "right": right_face, "left": left_face,
        }

    def draw_building(self, x, y, tile, zoom, today, is_hovered=False, is_selected=False):
        if tile.type in ("road", "green"):
            return

        hw = (self.tile_w / 2) * zoom
        hh = (self.tile_h / 2) * zoom
        style = tile.building_style
        f = STYLE_FOOTPRINT.get(style, 0.82)
        H = tile.building_height * zoom

        b = self._box(x, y, hw, hh, f, H)

        cc = getattr(tile, "_ccache", None)
        if cc is None:
            cc = self._color_cache(tile)
            tile._ccache = cc

        detail = zoom >= 1.55
        shadow = zoom >= 1.15

        if shadow:
            pygame.draw.polygon(self.screen, (20, 24, 34), [
                (b["cxc"] - hw * f, b["cyc"] + 1),
                (b["cxc"], b["cyc"] + hh * f + 1),
                (b["cxc"] + hw * f * 1.15, b["cyc"] + hh * 0.25),
                (b["cxc"] + hw * 0.1, b["cyc"] - hh * f * 0.3),
            ])

        # ---- SELECTION TINT & WIREFRAME ----
        if is_selected:
            if tile.type == "residential":
                sel_color = (120, 255, 120, 120)   # brighter green
                wire_color = (80, 220, 80)
            elif tile.type == "commercial":
                sel_color = (120, 200, 255, 120)   # brighter blue
                wire_color = (80, 170, 255)
            else:
                sel_color = None
                wire_color = (255, 255, 255)

            if sel_color:
                sel_surf = pygame.Surface((int(hw * 2.6), int(hh * 2.6 + H)), pygame.SRCALPHA)
                sel_pts = [
                    (int(hw * 1.3), int(hh * 1.3)),
                    (int(hw * 2.3), int(hh * 0.3)),
                    (int(hw * 2.3), int(hh * 0.3 - H)),
                    (int(hw * 1.3), int(hh * 1.3 - H)),
                    (int(hw * 0.3), int(hh * 1.3 - H)),
                    (int(hw * 0.3), int(hh * 1.3)),
                ]
                pygame.draw.polygon(sel_surf, sel_color, sel_pts)
                self.screen.blit(sel_surf, (int(x - hw * 1.3), int(y - hh * 1.3)))

            # Wireframe outline around the building silhouette
            outline_pts = [
                (x - hw * f, y + hh * f),       # B_left
                (x, y + 2 * hh * f),             # B_bot
                (x + hw * f, y + hh * f),        # B_right
                (x + hw * f, y + hh * f - H),    # R_right
                (x, y - H),                       # R_top (approx)
                (x - hw * f, y + hh * f - H),    # R_left
            ]
            for i in range(len(outline_pts)):
                p1 = outline_pts[i]
                p2 = outline_pts[(i + 1) % len(outline_pts)]
                pygame.draw.line(self.screen, wire_color, p1, p2, max(2, int(2 * zoom)))

        # ---- HOVER TINT ----
        elif is_hovered:
            if tile.type == "residential":
                hover_color = (120, 255, 120, 70)   # subtle green
            elif tile.type == "commercial":
                hover_color = (120, 200, 255, 70)   # subtle blue
            else:
                hover_color = None

            if hover_color:
                hover_surf = pygame.Surface((int(hw * 2.6), int(hh * 2.6 + H)), pygame.SRCALPHA)
                hover_pts = [
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
        pygame.draw.polygon(self.screen, cc["wr"], list(b["right"]))
        pygame.draw.polygon(self.screen, cc["wl"], list(b["left"]))
        if shadow:
            pygame.draw.line(self.screen, cc["seam"], b["B_bot"], b["R_bot"], max(1, int(zoom)))

        # Style-specific top + detailing
        if style in ("detached", "bungalow"):
            self._roof_hip(b, cc, zoom)
            if detail:
                self._house_details(tile, b, zoom, chimney=(style == "detached"))
        elif style in ("terrace", "semi"):
            self._roof_gable(b, cc, zoom)
            if detail:
                self._house_details(tile, b, zoom, chimney=(style == "semi"))
        elif style in ("flats", "tower"):
            self._roof_flat(b, cc, zoom)
            if detail:
                self._block_details(tile, b, zoom, tower=(style == "tower"))
            if style == "tower":
                self._rooftop_kit(b, zoom)
        elif style == "shop":
            self._roof_flat(b, cc, zoom)
            if detail:
                self._shop_details(tile, b, zoom)
        elif style == "warehouse":
            self._roof_mono(b, cc, zoom)
            if detail:
                self._warehouse_details(tile, b, zoom)
        else:  # office / highrise
            self._roof_flat(b, cc, zoom)
            if detail:
                self._glass_details(tile, b, zoom)
            if style == "highrise":
                self._rooftop_kit(b, zoom, mast=True)

        # Zone type indicator on building (small icon for commercial)
        if tile.type == "commercial" and zoom >= 1.3:
            # Small "£" indicator for commercial buildings
            font = pygame.font.SysFont("segoeui", max(6, int(8 * zoom)), bold=True)
            text = font.render("£", True, (255, 220, 100))
            text_rect = text.get_rect(center=(int(b["R_top"][0]), int(b["R_top"][1] + 8 * zoom)))
            self.screen.blit(text, text_rect)

        # Kerbside wheelie bin if due today (close-up only)
        if detail and tile.collection_due == today and tile.bin_fill > 20:
            self._draw_wheelie_bin(b["B_bot"], b["B_right"], zoom, tile.bin_fill)

        # Overflow alarm — cheap and gameplay-critical
        if tile.bin_fill > 85:
            pygame.draw.circle(self.screen, (235, 70, 70),
                               (int(b["R_top"][0]), int(b["R_top"][1] - 6 * zoom)),
                               max(2, int(3 * zoom)))

    # --------------------------------------------------------------- roofs
    def _roof_hip(self, b, cc, zoom):
        ridge = 14 * zoom
        apex = ((b["R_top"][0] + b["R_bot"][0]) / 2,
                ((b["R_top"][1] + b["R_bot"][1]) / 2) - ridge)
        pygame.draw.polygon(self.screen, cc["roof_d"], [b["R_top"], b["R_right"], apex])
        pygame.draw.polygon(self.screen, cc["roof_l"], [b["R_top"], b["R_left"], apex])
        pygame.draw.polygon(self.screen, cc["roof"], [b["R_right"], b["R_bot"], apex])
        pygame.draw.polygon(self.screen, cc["roof_l"], [b["R_left"], b["R_bot"], apex])
        pygame.draw.line(self.screen, cc["roof_h"], b["R_bot"], apex, max(1, int(zoom)))
        b["_apex"] = apex

    def _roof_gable(self, b, cc, zoom):
        # Ridge runs from the R_left..R_right axis, raised; two slopes + gables.
        rise = 15 * zoom
        m1 = ((b["R_top"][0] + b["R_left"][0]) / 2, (b["R_top"][1] + b["R_left"][1]) / 2 - rise)
        m2 = ((b["R_right"][0] + b["R_bot"][0]) / 2, (b["R_right"][1] + b["R_bot"][1]) / 2 - rise)
        # right slope (sunlit), left slope (shaded)
        pygame.draw.polygon(self.screen, cc["roof"], [b["R_top"], b["R_right"], m2, m1])
        pygame.draw.polygon(self.screen, cc["roof_l"], [b["R_left"], b["R_bot"], m2, m1])
        # gable ends
        pygame.draw.polygon(self.screen, cc["roof_d"], [b["R_top"], b["R_left"], m1])
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
        # Single-pitch (warehouse): raise the far edge only.
        rise = 12 * zoom
        far_t = (b["R_top"][0], b["R_top"][1] - rise)
        far_r = (b["R_right"][0], b["R_right"][1] - rise)
        pygame.draw.polygon(self.screen, cc["roof"],
                            [far_t, far_r, b["R_bot"], b["R_left"]])
        pygame.draw.polygon(self.screen, cc["roof_d"],
                            [b["R_top"], b["R_right"], far_r, far_t])
        # corrugation lines
        for u in (0.3, 0.5, 0.7):
            p1 = (far_t[0] + (b["R_left"][0] - far_t[0]) * u,
                  far_t[1] + (b["R_left"][1] - far_t[1]) * u)
            p2 = (far_r[0] + (b["R_bot"][0] - far_r[0]) * u,
                  far_r[1] + (b["R_bot"][1] - far_r[1]) * u)
            pygame.draw.line(self.screen, cc["roof_l"], p1, p2, max(1, int(zoom)))
        b["_apex"] = (b["R_top"][0], far_t[1])

    # ------------------------------------------------------------ detailing
    def _house_details(self, tile, b, zoom, chimney):
        right, left = b["right"], b["left"]
        apex = b.get("_apex")
        if chimney and apex and zoom > 0.45:
            ch_w = 3 * zoom
            chx = apex[0] + 5 * zoom
            chy = apex[1] - 2 * zoom
            pygame.draw.rect(self.screen, (90, 70, 64),
                             pygame.Rect(int(chx), int(chy - 9 * zoom),
                                         int(ch_w), int(9 * zoom)))
            pygame.draw.rect(self.screen, (60, 46, 42),
                             pygame.Rect(int(chx - 1), int(chy - 11 * zoom),
                                         int(ch_w + 2), int(2.5 * zoom)))

        glass = (150, 196, 230)
        frame = (238, 238, 238)
        for u in (0.28, 0.66):
            q = _face_quad(right, u, 0.42, 0.16, 0.32)
            pygame.draw.polygon(self.screen, frame, self._grow(q, 1.3 * zoom))
            pygame.draw.polygon(self.screen, glass, q)
        door = _face_quad(right, 0.06, 0.0, 0.16, 0.40)
        pygame.draw.polygon(self.screen, (70, 48, 38), door)
        q = _face_quad(left, 0.5, 0.48, 0.18, 0.30)
        pygame.draw.polygon(self.screen, frame, self._grow(q, 1.3 * zoom))
        pygame.draw.polygon(self.screen, _shade(glass, 0.85), q)

    def _block_details(self, tile, b, zoom, tower):
        glass = (158, 196, 224)
        rows = max(3, int(tile.building_height // (9 if tower else 12)))
        cols = 4 if tower else 3
        for face, tone in ((b["right"], 1.0), (b["left"], 0.8)):
            for r in range(rows):
                v = 0.1 + r * (0.82 / rows)
                for c in range(cols):
                    u = 0.12 + c * (0.78 / cols)
                    lit = ((r * 7 + c * 3 + int(tile.seed * 100)) % 5 == 0)
                    col = (250, 240, 180) if lit else _shade(glass, tone)
                    q = _face_quad(face, u, v, 0.78 / cols * 0.62, 0.82 / rows * 0.55)
                    pygame.draw.polygon(self.screen, col, q)
        # entrance canopy
        ent = _face_quad(b["right"], 0.34, 0.0, 0.30, 0.08)
        pygame.draw.polygon(self.screen, (60, 64, 72), ent)

    def _shop_details(self, tile, b, zoom):
        # Fascia signboard band + glazed shopfront + awning.
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
            pygame.draw.polygon(self.screen, _shade((150, 196, 220), tone), front)
            # awning stripes
            for i in range(4):
                u = 0.08 + i * 0.21
                stripe = [
                    _face_pt(face, u, 0.30), _face_pt(face, u + 0.105, 0.30),
                    _face_pt(face, u + 0.105, 0.36), _face_pt(face, u, 0.36),
                ]
                col = (200, 90, 80) if i % 2 == 0 else (235, 235, 235)
                pygame.draw.polygon(self.screen, _shade(col, tone), stripe)

    def _warehouse_details(self, tile, b, zoom):
        face = b["right"]
        # big roller door
        door = _face_quad(face, 0.20, 0.0, 0.40, 0.62)
        pygame.draw.polygon(self.screen, (70, 74, 82), door)
        for i in range(1, 5):
            v = i * 0.12
            p1 = _face_pt(face, 0.20, v)
            p2 = _face_pt(face, 0.60, v)
            pygame.draw.line(self.screen, (52, 56, 62), p1, p2, max(1, int(zoom)))
        # side personnel door + window
        pd = _face_quad(face, 0.70, 0.0, 0.12, 0.34)
        pygame.draw.polygon(self.screen, (60, 64, 72), pd)
        win = _face_quad(b["left"], 0.4, 0.5, 0.3, 0.18)
        pygame.draw.polygon(self.screen, (150, 190, 214), win)

    def _glass_details(self, tile, b, zoom):
        glass = (150, 198, 236)
        rows = max(3, int(tile.building_height // 14))
        cols = 3
        for face, tone in ((b["right"], 1.0), (b["left"], 0.82)):
            for r in range(rows):
                v = 0.14 + r * (0.78 / rows)
                for c in range(cols):
                    u = 0.14 + c * (0.74 / cols)
                    q = _face_quad(face, u, v, 0.66 / cols * 0.7, 0.78 / rows * 0.55)
                    pygame.draw.polygon(self.screen, _shade(glass, tone), q)
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
                             (apex[0], apex[1] - 5 * zoom),
                             (apex[0], apex[1] - 18 * zoom), max(1, int(zoom)))
            pygame.draw.circle(self.screen, (235, 70, 70),
                               (int(apex[0]), int(apex[1] - 18 * zoom)), max(1, int(1.4 * zoom)))

    # ------------------------------------------------------------- wheelie bin
    def _draw_wheelie_bin(self, base_near, base_right, zoom, fill):
        bx = base_near[0] + (base_right[0] - base_near[0]) * 0.35 + 4 * zoom
        by = base_near[1] + (base_right[1] - base_near[1]) * 0.35 + 5 * zoom
        w = max(2, int(4 * zoom))
        h = max(3, int(7 * zoom))
        body = pygame.Rect(int(bx - w / 2), int(by - h), w, h)
        if fill > 85:
            lid = (210, 60, 60)
        elif fill > 60:
            lid = (220, 150, 50)
        else:
            lid = (70, 170, 90)
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

    # ------------------------------------------------------------- worker
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
                         (x - 2 * s, y - 4.5 * s), (x + 2 * s, y - 4.5 * s), max(1, int(s)))
        pygame.draw.circle(self.screen, (235, 200, 170),
                           (int(x), int(y - 8.5 * s)), max(1, int(1.6 * s)))
        pygame.draw.circle(self.screen, (255, 220, 0),
                           (int(x), int(y - 9.2 * s)), max(1, int(1.7 * s)),
                           max(1, int(s)))
        if w["state"] == "back" and w.get("carry", 0) > 0:
            pygame.draw.circle(self.screen, (40, 50, 45),
                               (int(x + 3 * s), int(y - 4 * s)), max(1, int(1.8 * s)))

    # ------------------------------------------------------------- landfill
    def draw_landfill(self, cx, cy, city, zoom):
        """A big refuse mound with a tipping gate and signage, sited in a
        corner. Deliberately earthy and messy so it reads instantly as the tip,
        distinct from the grey depot and the colourful streets."""
        lf = getattr(city, "landfill", None)
        if not lf:
            return
        iso = self.to_iso(lf["cx"], lf["cy"])
        x = cx + iso[0] * zoom
        y = cy + iso[1] * zoom
        hw = (self.tile_w / 2) * zoom
        hh = (self.tile_h / 2) * zoom
        base_w = hw * 3.0
        base_h = hh * 3.0

        # Stacked earthy layers form the heap.
        for i, (f, col) in enumerate([(1.0, (58, 52, 40)), (0.74, (78, 70, 52)),
                                      (0.48, (98, 88, 64)), (0.24, (120, 110, 78))]):
            ry = y - i * 7 * zoom
            pygame.draw.ellipse(self.screen, col, pygame.Rect(
                int(x - base_w * f), int(ry - base_h * f * 0.5),
                int(base_w * 2 * f), int(base_h * f)))

        # Scattered bin-bag specks (seeded so they don't shimmer each frame).
        rng = __import__("random").Random(0xB1A5)
        for _ in range(int(46 * zoom)):
            sx = x + rng.uniform(-base_w * 0.95, base_w * 0.95)
            sy = y + rng.uniform(-base_h * 0.45, base_h * 0.35) - rng.uniform(0, 20) * zoom
            c = rng.choice([(38, 38, 38), (120, 32, 32), (32, 90, 44),
                            (40, 64, 120), (150, 150, 150), (150, 130, 40)])
            pygame.draw.circle(self.screen, c, (int(sx), int(sy)), max(1, int(1.5 * zoom)))

        # Tipping gate / weighbridge marker.
        g = lf.get("gate")
        if g and zoom > 0.4:
            giso = self.to_iso(g[0], g[1])
            gx = cx + giso[0] * zoom
            gy = cy + giso[1] * zoom
            pygame.draw.rect(self.screen, (210, 188, 44), pygame.Rect(
                int(gx - 7 * zoom), int(gy - 3 * zoom), int(14 * zoom), int(3 * zoom)))
            pygame.draw.rect(self.screen, (40, 40, 44), pygame.Rect(
                int(gx - 7 * zoom), int(gy - 3 * zoom), int(14 * zoom), int(3 * zoom)),
                max(1, int(zoom)))

        # Signage on a post.
        if zoom > 0.4:
            font = pygame.font.SysFont("segoeui", max(7, int(9 * zoom)), bold=True)
            text = font.render("LANDFILL SITE", True, (245, 245, 245))
            rect = text.get_rect(center=(int(x), int(y - base_h - 20 * zoom)))
            board = pygame.Rect(rect.x - 6, rect.y - 3, rect.width + 12, rect.height + 6)
            pygame.draw.rect(self.screen, (38, 40, 48), board)
            pygame.draw.rect(self.screen, (200, 160, 60), board, 1)
            pygame.draw.line(self.screen, (120, 110, 80),
                             (x, board.bottom), (x, y - base_h * 0.5), max(1, int(2 * zoom)))
            self.screen.blit(text, rect)

    # ------------------------------------------------------------- depot
    def draw_depot(self, x, y, zoom):
        """A distinctive council waste depot: a wide industrial shed with a
        pitched roof, roller doors, a yard and signage. Deliberately grey and
        utilitarian so it reads instantly against the colourful streets."""
        hw = (self.tile_w / 2) * zoom
        hh = (self.tile_h / 2) * zoom
        f = 1.25                       # larger than a normal building
        H = 30 * zoom
        b = self._box(x, y, hw, hh, f, H)

        # Yard slab
        pygame.draw.polygon(self.screen, (74, 78, 86), [
            b["B_top"], b["B_right"], b["B_bot"], b["B_left"]])

        wall_r = (120, 124, 130)
        wall_l = (96, 100, 106)
        roof_c = (150, 154, 160)
        roof_d = (110, 114, 120)

        pygame.draw.polygon(self.screen, wall_r, list(b["right"]))
        pygame.draw.polygon(self.screen, wall_l, list(b["left"]))

        # Gable roof
        rise = 16 * zoom
        m1 = ((b["R_top"][0] + b["R_left"][0]) / 2, (b["R_top"][1] + b["R_left"][1]) / 2 - rise)
        m2 = ((b["R_right"][0] + b["R_bot"][0]) / 2, (b["R_right"][1] + b["R_bot"][1]) / 2 - rise)
        pygame.draw.polygon(self.screen, roof_c, [b["R_top"], b["R_right"], m2, m1])
        pygame.draw.polygon(self.screen, roof_d, [b["R_left"], b["R_bot"], m2, m1])
        pygame.draw.polygon(self.screen, (88, 92, 98), [b["R_top"], b["R_left"], m1])
        pygame.draw.polygon(self.screen, (88, 92, 98), [b["R_right"], b["R_bot"], m2])

        if zoom >= 1.0:
            # Two roller doors on the sunlit face
            for u in (0.14, 0.56):
                door = _face_quad(b["right"], u, 0.0, 0.30, 0.66)
                pygame.draw.polygon(self.screen, (66, 70, 78), door)
                for i in range(1, 5):
                    v = i * 0.13
                    pygame.draw.line(self.screen, (48, 52, 58),
                                     _face_pt(b["right"], u, v),
                                     _face_pt(b["right"], u + 0.30, v), max(1, int(zoom)))
            # Hazard stripe along the base
            stripe = [
                _face_pt(b["right"], 0.0, 0.0), _face_pt(b["right"], 1.0, 0.0),
                _face_pt(b["right"], 1.0, 0.06), _face_pt(b["right"], 0.0, 0.06),
            ]
            pygame.draw.polygon(self.screen, (220, 196, 60), stripe)

        # Sign board on a post
        if zoom > 0.4:
            font = pygame.font.SysFont("segoeui", max(7, int(9 * zoom)), bold=True)
            text = font.render("COUNCIL DEPOT", True, (245, 245, 245))
            rect = text.get_rect(center=(int(x), int(b["R_top"][1] - 30 * zoom)))
            board = pygame.Rect(rect.x - 6, rect.y - 3, rect.width + 12, rect.height + 6)
            pygame.draw.rect(self.screen, (38, 40, 48), board)
            pygame.draw.rect(self.screen, (200, 204, 210), board, 1)
            pygame.draw.line(self.screen, (120, 124, 130),
                             (x, board.bottom), (x, b["R_top"][1] - 4 * zoom), max(1, int(2 * zoom)))
            self.screen.blit(text, rect)

    # ------------------------------------------------------------- truck
    def draw_truck(self, x, y, truck, zoom):
        # If icon.ico is available, use it as the truck sprite
        if self._truck_icon is not None:
            s = zoom * 1.2
            flip = truck.get("facing", 1)
            # Scale the icon to appropriate size
            icon_size = int(32 * s)
            scaled = pygame.transform.scale(self._truck_icon, (icon_size, icon_size))
            if flip < 0:
                scaled = pygame.transform.flip(scaled, True, False)
            rect = scaled.get_rect(center=(int(x), int(y - 5 * s)))
            self.screen.blit(scaled, rect)

            # Draw truck ID label below
            if zoom > 0.35:
                font = pygame.font.SysFont("monospace", max(5, int(6 * s)), bold=True)
                text = font.render(f"L{truck['id']}", True, (255, 255, 255))
                self.screen.blit(text, text.get_rect(center=(int(x), int(y + 6 * s))))
            return

        # Fallback: draw the original truck sprite
        state = truck["state"]
        if state == "depot":
            cab_color = (80, 80, 80)
            body_color = (110, 110, 110)
        elif state == "to_depot":
            cab_color = (40, 110, 60)
            body_color = (224, 106, 0)
        else:
            cab_color = (40, 120, 60)
            body_color = (210, 190, 40)

        s = zoom * 1.2
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
            fh = 8 * s * load_pct
            fill_color = (255, 70, 70) if load_pct > 0.8 else (255, 160, 0) if load_pct > 0.5 else (70, 220, 70)
            fr = pygame.Rect(0, 0, int(7 * s), int(fh))
            fr.x = int(min(px(2.5), px(9.5)))
            fr.y = int(y - 2 * s - fh)
            pygame.draw.rect(self.screen, fill_color, fr)
        wr = max(2, int(2.4 * s))
        pygame.draw.circle(self.screen, (26, 26, 26), (int(px(-6)), int(y)), wr)
        pygame.draw.circle(self.screen, (90, 90, 90), (int(px(-6)), int(y)), max(1, int(s)))
        pygame.draw.circle(self.screen, (26, 26, 26), (int(px(7)), int(y)), wr)
        pygame.draw.circle(self.screen, (90, 90, 90), (int(px(7)), int(y)), max(1, int(s)))
        if state == "servicing":
            flash = math.sin(pygame.time.get_ticks() / 100) > 0
            beacon = (255, 60, 60) if flash else (150, 40, 40)
            pygame.draw.circle(self.screen, beacon, (int(px(-5)), int(y - 9 * s)), max(2, int(1.6 * s)))
        on_board = max(0, truck["crew"] - len(truck.get("out_workers", [])))
        for i in range(on_board):
            dot_x = x - (on_board - 1) * 3 * s + i * 6 * s
            pygame.draw.circle(self.screen, (255, 255, 255),
                               (int(dot_x), int(y - 13 * s)), max(1, int(1.8 * s)))
        if zoom > 0.35:
            font = pygame.font.SysFont("monospace", max(5, int(6 * s)), bold=True)
            text = font.render(f"L{truck['id']}", True, (255, 255, 255))
            self.screen.blit(text, text.get_rect(center=(int(x), int(y + 6 * s))))

    # ------------------------------------------------------------- area overlay
    def draw_area_overlay(self, cx, cy, city, zoom, today):
        """Boundary lines + a small monochrome tag per round (planning view).
        Now shows route type (residential/commercial/mixed) with color coding."""
        line = (235, 235, 235)
        for c in range(1, AREA_COLS):
            gx = city.width * c // AREA_COLS
            self._draw_edge_line(cx, cy, gx, 0, gx, city.height, zoom, line)
        for r in range(1, AREA_ROWS):
            gy = city.height * r // AREA_ROWS
            self._draw_edge_line(cx, cy, 0, gy, city.width, gy, zoom, line)

        font = pygame.font.SysFont("segoeui", max(9, int(11 * zoom)), bold=True)
        small = pygame.font.SysFont("segoeui", max(8, int(9 * zoom)))
        for area in city.areas:
            mid_x = (area.col + 0.5) * city.width / AREA_COLS
            mid_y = (area.row + 0.5) * city.height / AREA_ROWS
            iso = self.to_iso(mid_x, mid_y)
            sx = int(cx + iso[0] * zoom)
            sy = int(cy + iso[1] * zoom)

            # Route type indicator
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

            name = font.render(area.name, True, (245, 245, 245))
            day = small.render(DAY_NAMES[area.collection_day]
                               + ("  (today)" if area.collection_day == today else ""),
                               True, (210, 210, 210))
            type_surf = small.render(type_label, True, type_color)
            w = max(name.get_width(), day.get_width(), type_surf.get_width()) + 14
            h = name.get_height() + day.get_height() + type_surf.get_height() + 14
            box = pygame.Rect(sx - w // 2, sy - h // 2, w, h)
            pygame.draw.rect(self.screen, (24, 24, 24), box)
            pygame.draw.rect(self.screen,
                             (245, 245, 245) if area.collection_day == today else (250, 250, 250),
                             box, 2)
            # Draw route type colored bar on left
            pygame.draw.rect(self.screen, type_color, pygame.Rect(box.x, box.y, 4, box.height))
            self.screen.blit(name, (box.centerx - name.get_width() // 2, box.y + 4))
            self.screen.blit(type_surf, (box.centerx - type_surf.get_width() // 2, box.y + 6 + name.get_height()))
            self.screen.blit(day, (box.centerx - day.get_width() // 2, box.y + 8 + name.get_height() + type_surf.get_height()))

    # ------------------------------------------------------------- helpers
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
