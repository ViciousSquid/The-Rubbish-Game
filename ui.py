import pygame
import math
import os
from city import AREA_COLS, AREA_ROWS, RES_STYLE_WEIGHTS, COM_STYLE_WEIGHTS
import xmlio
import savegame
from procurement import VEHICLE_CATALOGUE
from assets import asset_path

DAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
HUD_W = 280

PLANNER_TABS = [
    ("rounds",  "Rounds"),
    ("waste",   "Waste"),
    ("fleet",   "Fleet"),
    ("staff",   "Staff"),
    ("finance", "Finance"),
    ("data",    "Data"),
]

STYLE_LABELS = {
    "terrace": "Terraced house", "semi": "Semi-detached", "detached": "Detached house",
    "bungalow": "Bungalow", "flats": "Block of flats", "tower": "Tower block",
    "shop": "Shop / retail", "office": "Office", "warehouse": "Warehouse",
    "highrise": "High-rise",
}

ROUTE_TYPE_LABELS = {
    "residential": "Residential",
    "commercial": "Commercial",
    "mixed": "Mixed",
}

ROUTE_TYPE_COLORS = {
    "residential": (120, 200, 120),
    "commercial": (100, 170, 220),
    "mixed": (220, 200, 120),
}

# ── Floating windows (Chris Sawyer style) ────────────────────────────────────
# The old modal TAB planner is replaced by a set of independently openable,
# draggable, overlapping windows. Each entry: key, short toolbar label, title
# bar caption, default width, default height. The window CONTENT is rendered by
# the existing `_tab_<key>` methods, which already draw into an (x,y,w,h) rect.
WINDOW_DEFS = [
    ("rounds",  "Rounds",  "Collection Rounds",    764, 462),
    ("waste",   "Waste",   "Waste Streams",        660, 466),
    ("fleet",   "Fleet",   "Fleet & Procurement",  800, 548),
    ("staff",   "Staff",   "Staff & Vehicles",     864, 560),
    ("finance", "Finance", "Finance",              788, 640),
    ("charts",  "Charts",  "Financial Charts",     760, 560),
    ("data",    "Data",    "Data & Plan I/O",      620, 420),
]
WINDOW_TITLEBAR_H = 34
WINDOW_PAD        = 16
TOOLBAR_H         = 40
EDITOR_BAR_H      = 64  # height of the bottom editor toolbar when active


class FloatingWindow:
    """A draggable, closable panel. Holds its own click-target lists so clicks
    resolve against the correct (top-most) window rather than a global frame."""

    def __init__(self, key, title, x, y, w, h):
        self.key   = key
        self.title = title
        self.rect  = pygame.Rect(x, y, w, h)
        self.widgets = []      # (rect, fn) click targets collected during draw
        self.cells   = []      # (rect, area_id, day) round-day cells
        self.close_rect = None

    def titlebar_rect(self):
        return pygame.Rect(self.rect.x, self.rect.y, self.rect.w, WINDOW_TITLEBAR_H)

    def body_rect(self):
        r = self.rect
        return pygame.Rect(
            r.x + WINDOW_PAD,
            r.y + WINDOW_TITLEBAR_H + 8,
            r.w - 2 * WINDOW_PAD,
            r.h - WINDOW_TITLEBAR_H - 8 - WINDOW_PAD,
        )



class ColorSystem:
    """A cohesive, accessible color palette inspired by modern dark-mode games."""
    BG_DEEP = (14, 16, 22)
    BG_PANEL = (24, 28, 36)
    BG_CARD = (32, 38, 48)
    BG_HOVER = (42, 50, 64)
    BG_ACTIVE = (52, 62, 80)
    BORDER_SUBTLE = (48, 56, 72)
    BORDER = (72, 84, 108)
    BORDER_BRIGHT = (120, 140, 170)
    TEXT_PRIMARY = (245, 248, 252)
    TEXT_SECONDARY = (180, 190, 210)
    TEXT_MUTED = (175, 185, 205)
    TEXT_DIM = (135, 145, 165)
    ACCENT_AMBER = (255, 190, 80)
    ACCENT_AMBER_DIM = (200, 150, 60)
    ACCENT_TEAL = (80, 200, 190)
    ACCENT_CORAL = (255, 120, 100)
    ACCENT_CORAL_DIM = (200, 90, 80)
    ACCENT_SAGE = (140, 200, 130)
    STATUS_GOOD = (120, 210, 130)
    STATUS_WARN = (255, 180, 80)
    STATUS_BAD = (255, 100, 100)


class FontSystem:
    """Centralized font management with better sizing and fallbacks."""
    def __init__(self):
        self._fonts = {}
        self._load_fonts()
    def _load_fonts(self):
        font_names = ["segoeui", "arial", "helvetica", "liberationsans", "dejavusans"]
        base_font = None
        for name in font_names:
            try:
                base_font = name
                pygame.font.SysFont(name, 12)
                break
            except:
                continue
        if base_font is None:
            base_font = "freesans"
        mono_names = ["consolas", "couriernew", "liberationmono", "dejavusansmono"]
        mono_font = None
        for name in mono_names:
            try:
                mono_font = name
                pygame.font.SysFont(name, 12)
                break
            except:
                continue
        if mono_font is None:
            mono_font = base_font
        self.base = base_font
        self.mono = mono_font
        specs = {
            "display": (base_font, 28, True),
            "display_sub": (base_font, 18, True),
            "h1": (base_font, 20, True),
            "h2": (base_font, 16, True),
            "h3": (base_font, 14, True),
            "body": (base_font, 14, False),
            "body_b": (base_font, 14, True),
            "body_s": (base_font, 12, False),
            "body_xs": (base_font, 11, False),
            "mono": (mono_font, 13, False),
            "mono_b": (mono_font, 13, True),
            "mono_s": (mono_font, 11, False),
            "label": (base_font, 11, True),
            "caption": (base_font, 10, False),
            "badge": (base_font, 10, True),
        }
        for key, (name, size, bold) in specs.items():
            self._fonts[key] = pygame.font.SysFont(name, size, bold=bold)
    def get(self, key):
        return self._fonts.get(key, self._fonts["body"])

    def _find_anton(self):
        # Preferred: the bundled _internal folder (dev + frozen build).
        p = asset_path("Anton-Regular.ttf")
        if os.path.isfile(p):
            return p
        # Legacy fallbacks kept so an un-moved copy still loads.
        here = os.path.dirname(os.path.abspath(__file__))
        for base in (os.getcwd(), here):
            for rel in ("assets/fonts/Anton-Regular.ttf",
                        "fonts/Anton-Regular.ttf",
                        "Anton-Regular.ttf"):
                p = os.path.join(base, rel)
                if os.path.isfile(p):
                    return p
        return None

    def title(self, size):
        """The Anton display face at `size` (cached). Falls back to the bold
        system font if the Anton TTF isn't bundled."""
        key = ("__title__", size)
        f = self._fonts.get(key)
        if f is None:
            if not hasattr(self, "_anton_path"):
                self._anton_path = self._find_anton()
            if self._anton_path:
                f = pygame.font.Font(self._anton_path, size)
            else:
                f = pygame.font.SysFont(self.base, size, bold=True)
            self._fonts[key] = f
        return f

    def custom(self, size, bold=False):
        """A cached SysFont at an arbitrary size (used for the menu title)."""
        key = ("__custom__", size, bold)
        f = self._fonts.get(key)
        if f is None:
            f = pygame.font.SysFont(self.base, size, bold=bold)
            self._fonts[key] = f
        return f
    def render(self, key, text, color):
        return self._fonts[key].render(text, True, color)
    def size(self, key, text):
        return self._fonts[key].size(text)


class UIPrimitives:
    """Low-level drawing primitives for consistent UI styling."""
    def __init__(self, screen, fonts):
        self.screen = screen
        self.fonts = fonts
        self.c = ColorSystem
    def panel(self, x, y, w, h, fill=None, border=True, border_radius=4):
        color = fill or self.c.BG_PANEL
        rect = pygame.Rect(x, y, w, h)
        pygame.draw.rect(self.screen, color, rect, border_radius=border_radius)
        if border:
            pygame.draw.rect(self.screen, self.c.BORDER_SUBTLE, rect, 1, border_radius=border_radius)
        return rect
    def card(self, x, y, w, h, hover=False, selected=False):
        if selected:
            fill = self.c.BG_ACTIVE
            border_color = self.c.ACCENT_AMBER
            border_width = 2
        elif hover:
            fill = self.c.BG_HOVER
            border_color = self.c.BORDER
            border_width = 1
        else:
            fill = self.c.BG_CARD
            border_color = self.c.BORDER_SUBTLE
            border_width = 1
        rect = pygame.Rect(x, y, w, h)
        pygame.draw.rect(self.screen, fill, rect, border_radius=6)
        pygame.draw.rect(self.screen, border_color, rect, border_width, border_radius=6)
        return rect
    def inset_panel(self, x, y, w, h):
        rect = pygame.Rect(x, y, w, h)
        pygame.draw.rect(self.screen, self.c.BG_DEEP, rect, border_radius=3)
        pygame.draw.rect(self.screen, self.c.BORDER_SUBTLE, rect, 1, border_radius=3)
        inner = rect.inflate(-2, -2)
        pygame.draw.rect(self.screen, (30, 35, 45), inner, border_radius=2)
        return rect
    def text(self, key, text, color, x, y, align="left"):
        surf = self.fonts.render(key, text, color)
        if align == "left":
            self.screen.blit(surf, (x, y))
        elif align == "right":
            self.screen.blit(surf, (x - surf.get_width(), y))
        elif align == "center":
            self.screen.blit(surf, (x - surf.get_width() // 2, y))
        return surf.get_width()
    def label(self, text, x, y, color=None):
        return self.text("label", text, color or self.c.TEXT_MUTED, x, y)
    def value(self, text, x, y, color=None, align="left"):
        return self.text("body_b", text, color or self.c.TEXT_PRIMARY, x, y, align)
    def button(self, rect, label, enabled=True, accent=False, hovered=False, pressed=False, icon=None, color=None):
        if not enabled:
            fill = self.c.BG_PANEL
            border = self.c.BORDER_SUBTLE
            text_color = self.c.TEXT_DIM
        elif pressed:
            fill = self.c.BG_ACTIVE
            border = self.c.ACCENT_AMBER
            text_color = self.c.ACCENT_AMBER
        elif accent and color:
            # Selected state with custom colour — brighten it and add amber border
            fill = tuple(min(255, int(c * 1.3)) for c in color)
            border = self.c.ACCENT_AMBER
            text_color = self.c.BG_DEEP
        elif accent:
            fill = self.c.ACCENT_AMBER_DIM if hovered else (220, 165, 70)
            border = self.c.ACCENT_AMBER
            text_color = self.c.BG_DEEP
        elif color:
            if hovered:
                fill = tuple(min(255, int(c * 1.15)) for c in color)
                border = tuple(min(255, int(c * 1.35)) for c in color)
            else:
                fill = color
                border = tuple(min(255, int(c * 1.25)) for c in color)
            text_color = self.c.TEXT_PRIMARY
        elif hovered:
            fill = self.c.BG_HOVER
            border = self.c.BORDER_BRIGHT
            text_color = self.c.TEXT_PRIMARY
        else:
            fill = self.c.BG_CARD
            border = self.c.BORDER
            text_color = self.c.TEXT_SECONDARY
        pygame.draw.rect(self.screen, fill, rect, border_radius=5)
        pygame.draw.rect(self.screen, border, rect, 1, border_radius=5)
        if enabled and not pressed:
            highlight = pygame.Rect(rect.x + 1, rect.y + 1, rect.w - 2, rect.h // 3)
            hl_surf = pygame.Surface((highlight.w, highlight.h), pygame.SRCALPHA)
            hl_surf.fill((255, 255, 255, 15))
            self.screen.blit(hl_surf, highlight)
        surf = self.fonts.render("body_b", label, text_color)
        text_x = rect.centerx - surf.get_width() // 2
        text_y = rect.centery - surf.get_height() // 2
        self.screen.blit(surf, (text_x, text_y))
        return rect
    def icon_button(self, rect, icon_text, tooltip="", enabled=True, hovered=False, pressed=False):
        if not enabled:
            fill = self.c.BG_PANEL
            text_color = self.c.TEXT_DIM
        elif pressed:
            fill = self.c.BG_ACTIVE
            text_color = self.c.ACCENT_AMBER
        elif hovered:
            fill = self.c.BG_HOVER
            text_color = self.c.TEXT_PRIMARY
        else:
            fill = self.c.BG_CARD
            text_color = self.c.TEXT_SECONDARY
        pygame.draw.rect(self.screen, fill, rect, border_radius=4)
        pygame.draw.rect(self.screen, self.c.BORDER_SUBTLE, rect, 1, border_radius=4)
        surf = self.fonts.render("body_b", icon_text, text_color)
        self.screen.blit(surf, surf.get_rect(center=rect.center))
        return rect
    def progress_bar(self, x, y, w, h, value, max_value, color=None, bg_color=None, show_text=True):
        color = color or self.c.ACCENT_AMBER
        bg = bg_color or self.c.BG_DEEP
        rect = pygame.Rect(x, y, w, h)
        pygame.draw.rect(self.screen, bg, rect, border_radius=h // 2)
        if max_value > 0:
            pct = min(1.0, max(0.0, value / max_value))
            fill_w = int(w * pct)
            if fill_w > 0:
                fill_rect = pygame.Rect(x, y, fill_w, h)
                pygame.draw.rect(self.screen, color, fill_rect, border_radius=h // 2)
                shine = pygame.Surface((fill_w, h // 2), pygame.SRCALPHA)
                shine.fill((255, 255, 255, 30))
                self.screen.blit(shine, (x, y))
        pygame.draw.rect(self.screen, self.c.BORDER_SUBTLE, rect, 1, border_radius=h // 2)
        if show_text:
            pct_text = f"{int(pct * 100)}%"
            surf = self.fonts.render("mono_s", pct_text, self.c.TEXT_PRIMARY)
            self.screen.blit(surf, (x + w + 6, y))
    def stat_bar(self, x, y, w, value, max_value, low_color=None, mid_color=None, high_color=None):
        if max_value <= 0:
            return
        pct = value / max_value
        if pct < 0.3:
            color = low_color or self.c.STATUS_BAD
        elif pct < 0.7:
            color = mid_color or self.c.STATUS_WARN
        else:
            color = high_color or self.c.STATUS_GOOD
        self.progress_bar(x, y, w, 6, value, max_value, color, show_text=False)
    def badge(self, x, y, text, color=None, bg_color=None):
        color = color or self.c.TEXT_PRIMARY
        bg = bg_color or self.c.BG_ACTIVE
        surf = self.fonts.render("badge", text, color)
        pad_x, pad_y = 8, 3
        bw, bh = surf.get_width() + pad_x * 2, surf.get_height() + pad_y * 2
        rect = pygame.Rect(x, y, bw, bh)
        pygame.draw.rect(self.screen, bg, rect, border_radius=bh // 2)
        self.screen.blit(surf, (x + pad_x, y + pad_y))
        return rect
    def status_pill(self, x, y, status_text, status_type="neutral"):
        colors = {
            "good": (self.c.STATUS_GOOD, (30, 60, 35)),
            "warn": (self.c.STATUS_WARN, (60, 50, 30)),
            "bad": (self.c.STATUS_BAD, (60, 35, 35)),
            "neutral": (self.c.TEXT_MUTED, self.c.BG_ACTIVE),
            "info": (self.c.ACCENT_TEAL, (30, 50, 55)),
        }
        text_color, bg_color = colors.get(status_type, colors["neutral"])
        return self.badge(x, y, status_text, text_color, bg_color)
    def h_line(self, x, y, w, color=None):
        color = color or self.c.BORDER_SUBTLE
        pygame.draw.line(self.screen, color, (x, y), (x + w, y), 1)
    def section_header(self, x, y, label, w=None):
        self.text("h3", label, self.c.TEXT_MUTED, x, y)
        if w:
            label_w = self.fonts.size("h3", label)[0]
            self.h_line(x + label_w + 10, y + 8, w - label_w - 10)
    def tooltip(self, x, y, text, max_width=240):
        words = text.split(" ")
        lines = []
        current = ""
        for word in words:
            test = current + " " + word if current else word
            if self.fonts.size("body_s", test)[0] <= max_width:
                current = test
            else:
                if current:
                    lines.append(current)
                current = word
        if current:
            lines.append(current)
        if not lines:
            return
        line_h = self.fonts.get("body_s").get_height() + 2
        th = len(lines) * line_h + 8
        tw = max(self.fonts.size("body_s", line)[0] for line in lines) + 16
        rect = pygame.Rect(x, y, tw, th)
        if rect.right > self.screen.get_width():
            rect.x = self.screen.get_width() - tw - 10
        if rect.bottom > self.screen.get_height():
            rect.y = self.screen.get_height() - th - 10
        shadow = pygame.Rect(rect.x + 2, rect.y + 2, rect.w, rect.h)
        pygame.draw.rect(self.screen, (0, 0, 0, 100), shadow, border_radius=4)
        pygame.draw.rect(self.screen, self.c.BG_CARD, rect, border_radius=4)
        pygame.draw.rect(self.screen, self.c.BORDER, rect, 1, border_radius=4)
        for i, line in enumerate(lines):
            surf = self.fonts.render("body_s", line, self.c.TEXT_SECONDARY)
            self.screen.blit(surf, (rect.x + 8, rect.y + 4 + i * line_h))


class UIManager:
    def __init__(self, game):
        self.game = game
        self._event_visible = False
        self._event_timer_active = 0
        self._event_duration = 5.5
        self._current_event = None
        self._insufficient_funds_flash = False
        self._flash_timer = 0
        self._flash_duration = 2.2
        self.fonts = FontSystem()
        self.ui = None
        self._hovered_button = None
        self._pressed_button = None
        self._tooltip_text = None
        self._tooltip_pos = None
        self._tooltip_timer = 0
        self._button_presses = {}
        self._pulse_values = {}
        self.buttons = []
        self.planner_cells = []
        self.planner_widgets = []
        self._planner_close = None
        # Truck rename state
        self._renaming_truck_id = None
        self._rename_buffer = ""
        # Staff tab fleet scroll state
        self._staff_fleet_scroll = 0
        self._staff_fleet_max_scroll = 0
        self._staff_fleet_clip = None

        # ── Debug tools (Ctrl+Shift+D) ───────────────────────────────────────
        self._debug_tab = "tools"        # "tools" | "editor" (editor only shown in bar)
        self.editor_tool = None          # current map-editor brush, or None
        self.editor_selected_area = None # round targeted by district tools
        self._debug_status = ""          # short feedback line in the debug window
        # Bottom-bar editor mode: replaces the old floating editor sub-tab.
        self._editor_mode = False        # True while the editor bar is visible
        self._editor_bar_widgets = []    # (rect, fn) rebuilt each draw

        # ── Floating-window system ───────────────────────────────────────────
        self.windows = []              # open windows, back-to-front (front last)
        self._win_index = {}           # key -> FloatingWindow (persistent pos)
        self._win_drag = None          # (window, grab_dx, grab_dy) while dragging
        self.toolbar_buttons = []      # (rect, action) rebuilt each draw
        self._screen_size = (1280, 720)
        self._content_renderers = {
            "rounds":  self._tab_rounds,
            "waste":   self._tab_waste,
            "fleet":   self._tab_fleet,
            "staff":   self._tab_staff,
            "finance": self._tab_finance,
            "charts":  self._tab_charts,
            "data":    self._tab_data,
            "debug":   self._tab_debug,
        }
        self._setup_buttons()

        # ── Main menu ─────────────────────────────────────────────────────────
        self.menu_buttons = []           # (rect, action) rebuilt each menu draw
        self._menu_settings_open = False
        self._title_cache = None         # cached grungy title surface
        self._title_cache_w = None       # screen width it was built for

    def _setup_buttons(self):
        # Toolbar buttons are rebuilt each frame in _draw_toolbar (they depend on
        # the live window width); nothing to pre-build here. Kept as a method so
        # the existing VIDEORESIZE hook in main.py stays valid.
        self.toolbar_buttons = []

    # =====================================================================
    #  Floating-window management
    # =====================================================================
    def _make_window(self, key):
        for k, _short, title, ww, hh in WINDOW_DEFS:
            if k == key:
                w, h = self._screen_size
                # Cascade new windows down-right from the top-left of the map
                # area. A steady 30px step keeps every title bar's top strip
                # grabbable even when several windows overlap.
                idx = len(self._win_index)
                x = HUD_W + 40 + idx * 28
                y = TOOLBAR_H + 24 + idx * 30
                x = min(x, max(HUD_W + 4, w - ww - 8))
                y = min(y, max(TOOLBAR_H + 4, h - hh - 8))
                return FloatingWindow(key, title, x, y, ww, hh)
        return None

    def open_window(self, key):
        win = self._win_index.get(key)
        if win is None:
            win = self._make_window(key)
            if win is None:
                return
            self._win_index[key] = win
        if win in self.windows:
            self._bring_to_front(win)
        else:
            self.windows.append(win)   # appended == front-most

    def close_window(self, win_or_key):
        win = (win_or_key if isinstance(win_or_key, FloatingWindow)
               else self._win_index.get(win_or_key))
        if win in self.windows:
            self.windows.remove(win)

    def toggle_window(self, key):
        if any(w.key == key for w in self.windows):
            self.close_window(key)
        else:
            self.open_window(key)

    # ----- debug window (Ctrl+Shift+D) --------------------------------------
    def toggle_debug_window(self):
        if any(w.key == "debug" for w in self.windows):
            self.close_window("debug")
            return
        win = self._win_index.get("debug")
        if win is None:
            w, h = self._screen_size
            ww, hh = 760, 676
            x = min(HUD_W + 80, max(HUD_W + 4, w - ww - 8))
            y = min(TOOLBAR_H + 40, max(TOOLBAR_H + 4, h - hh - 8))
            win = FloatingWindow("debug", "Debug Tools (Ctrl+Shift+D)", x, y, ww, hh)
            self._win_index["debug"] = win
        if win in self.windows:
            self._bring_to_front(win)
        else:
            self.windows.append(win)

    def editor_active(self):
        """True while the bottom editor bar is visible. main.py routes map
        clicks to the editor brush instead of normal tile selection."""
        return self._editor_mode

    def apply_editor_brush(self, tx, ty):
        """Apply the current editor brush to map tile (tx, ty). Called from
        main.py's handle_map_click. Returns True if a tile was changed."""
        tool = self.editor_tool
        if not tool:
            return False
        city = self.game.city
        mode = tool.get("mode")
        changed = False
        if mode == "bulldoze":
            changed = city.editor_bulldoze(tx, ty)
            if changed:
                self._debug_status = f"Bulldozed ({tx},{ty})."
        elif mode == "green":
            changed = city.editor_place_green(tx, ty)
            if changed:
                self._debug_status = f"Placed green square at ({tx},{ty})."
        elif mode == "clear_green":
            changed = city.editor_clear_green(tx, ty, tool.get("kind", "residential"))
            if changed:
                self._debug_status = f"Redeveloped green square at ({tx},{ty})."
        elif mode == "build":
            style = tool.get("style")
            changed = city.editor_place_building(tx, ty, style)
            if changed:
                self._debug_status = f"Built {STYLE_LABELS.get(style, style)} at ({tx},{ty})."
        if not changed:
            self._debug_status = "Can't apply that tool there."
        return changed

    # ----- per-vehicle inspect windows (opened by clicking a lorry) --------
    def _truck_window_title(self, truck):
        nickname = truck.get("nickname", f"L{truck['id']}")
        return f"{nickname}  —  {truck.get('model_name', 'Lorry')}"

    def open_truck_window(self, truck_id):
        """Open (or focus) a draggable inspect window for one lorry. Several
        of these can be open at once, independently of the six fixed
        planner windows."""
        key = f"truck_{truck_id}"
        win = self._win_index.get(key)
        if win is None:
            truck = self.game.fleet.get_truck(truck_id)
            if truck is None:
                return
            w, h = self._screen_size
            ww, hh = 372, 640
            n = sum(1 for k in self._win_index if k.startswith("truck_"))
            x = HUD_W + 60 + n * 26
            y = TOOLBAR_H + 30 + n * 26
            x = min(x, max(HUD_W + 4, w - ww - 8))
            y = min(y, max(TOOLBAR_H + 4, h - hh - 8))
            win = FloatingWindow(key, self._truck_window_title(truck), x, y, ww, hh)
            self._win_index[key] = win
        if win in self.windows:
            self._bring_to_front(win)
        else:
            self.windows.append(win)

    def _prune_truck_windows(self):
        """Drop the cached window for any lorry that's been scrapped, and
        keep open titles in sync with renames."""
        fleet = self.game.fleet
        stale = []
        for key, win in self._win_index.items():
            if not key.startswith("truck_"):
                continue
            truck = fleet.get_truck(int(key.split("_", 1)[1]))
            if truck is None:
                stale.append(key)
            else:
                win.title = self._truck_window_title(truck)
        for key in stale:
            win = self._win_index.pop(key)
            if win in self.windows:
                self.windows.remove(win)

    def _center_on_truck(self, truck_id):
        truck = self.game.fleet.get_truck(truck_id)
        if truck:
            self.game.center_camera_on(truck["x"], truck["y"])

    def _bring_to_front(self, win):
        if win in self.windows and self.windows[-1] is not win:
            self.windows.remove(win)
            self.windows.append(win)

    def any_window_open(self):
        return bool(self.windows)

    def _clamp_window(self, win):
        w, h = self._screen_size
        r = win.rect
        r.x = max(HUD_W + 4, min(r.x, w - r.w - 4))
        # keep the title bar reachable below the toolbar and above the bottom;
        # if the editor bar is visible, leave room for it too.
        bottom_margin = (EDITOR_BAR_H + 4) if self._editor_mode else 4
        r.y = max(TOOLBAR_H + 4, min(r.y, h - WINDOW_TITLEBAR_H - bottom_margin))

    def window_at(self, pos):
        for win in reversed(self.windows):
            if win.rect.collidepoint(pos):
                return win
        return None

    def _in_toolbar(self, pos):
        return pos[1] < TOOLBAR_H and pos[0] >= HUD_W

    # ----- mouse routing (called from main.py) -----------------------------
    def on_mouse_down(self, pos):
        """Press handling. Returns True if the UI consumed the press (so the
        map must not start a camera drag)."""
        if self.game.economy.has_lost:
            return False
        win = self.window_at(pos)
        if win is not None:
            self._bring_to_front(win)
            # The close box lives inside the title bar — pressing it must not
            # begin a drag; the actual close happens on mouse-up.
            if win.close_rect and win.close_rect.collidepoint(pos):
                return True
            if win.titlebar_rect().collidepoint(pos):
                self._win_drag = (win, pos[0] - win.rect.x, pos[1] - win.rect.y)
            return True
        if self._in_editor_bar(pos):
            return True            # consume so it doesn't start a camera drag
        if self._in_toolbar(pos) or pos[0] < HUD_W:
            return True            # consume; act on release
        return False

    def on_mouse_motion(self, rel, pos):
        """Returns True while dragging a window (suppresses camera pan)."""
        if self._win_drag is not None:
            win, gx, gy = self._win_drag
            win.rect.x = pos[0] - gx
            win.rect.y = pos[1] - gy
            self._clamp_window(win)
            return True
        return False

    def on_mouse_up(self, pos, was_click):
        """Release handling. Returns True if the UI consumed the event."""
        was_dragging_window = self._win_drag is not None
        self._win_drag = None
        if was_dragging_window:
            return True
        if self.game.economy.has_lost:
            return False
        if not was_click:
            return False
        win = self.window_at(pos)
        if win is not None:
            self._resolve_window_click(win, pos)
            return True
        if self._in_editor_bar(pos):
            self._editor_bar_resolve(pos)
            return True
        if self._toolbar_click(pos):
            return True
        if pos[0] < HUD_W:
            return True            # clicked the HUD status panel — no map action
        return False

    def on_scroll(self, button, pos):
        """Route a mousewheel into a window (currently only the staff fleet
        list scrolls). Returns True if consumed."""
        win = self.window_at(pos)
        if win is not None and win.key == "staff" and self._staff_fleet_clip is not None:
            delta = -50 if button == 4 else 50
            self._staff_fleet_scroll = max(
                0, min(self._staff_fleet_max_scroll,
                       self._staff_fleet_scroll + delta))
            return True
        return False

    def _resolve_window_click(self, win, pos):
        if win.close_rect and win.close_rect.collidepoint(pos):
            self.close_window(win)
            return
        # Resolve against THIS window's collected click targets.
        self.planner_widgets = win.widgets
        self.planner_cells = win.cells
        for rect, fn in win.widgets:
            if rect.collidepoint(pos):
                fn()
                return
        for rect, area_id, day in win.cells:
            if rect.collidepoint(pos):
                self.game.city.set_area_day(area_id, day)
                return

    def _toolbar_click(self, pos):
        for rect, action in self.toolbar_buttons:
            if rect.collidepoint(pos):
                if action == "pause":
                    self.game.running = not self.game.running
                elif action == "speed":
                    self.game.speed = {1: 2, 2: 5, 5: 10}.get(self.game.speed, 1)
                elif isinstance(action, tuple) and action[0] == "win":
                    self.toggle_window(action[1])
                return True
        return False

    def _pbtn_in_clip(self, screen, rect, label, fn, clip_rect,
                      enabled=True, fkey="body_b", accent=False):
        """Like _pbtn but only registers the click widget when the rect
        intersects the visible clip region (prevents ghost clicks on
        scrolled-off buttons)."""
        ui = self.ui
        mouse = pygame.mouse.get_pos()
        hovered = rect.collidepoint(mouse) and enabled
        ui.button(rect, label, enabled=enabled, accent=accent, hovered=hovered)
        if enabled and clip_rect.colliderect(rect):
            self.planner_widgets.append((rect, fn))

    def show_event(self, event):
        self._current_event = event
        self._event_visible = True
        self._event_timer_active = 0
        # Critical events get a longer initial display window; they also persist
        # in the banner for as long as they remain the active_event (see
        # _draw_event_banner), so the transient duration only matters for the
        # first appearance before the active_event is set.
        critical = event.get("effect") in ("crewStrike", "truckBreakdown")
        self._event_duration = 10.0 if critical else 5.5
        # Drop to 1x so the player can react — skip procurement notices which
        # are purely informational (vehicle deliveries, O-licence delays, etc.).
        if event.get("effect") != "procurement":
            self.game.speed = 1

    # ----------------------------------------------------------------- rename
    def handle_key(self, event):
        """Route keyboard events to the truck rename field when active."""
        if self._renaming_truck_id is None:
            return False
        if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
            self._commit_rename()
        elif event.key == pygame.K_ESCAPE:
            self._cancel_rename()
        elif event.key == pygame.K_BACKSPACE:
            self._rename_buffer = self._rename_buffer[:-1]
        elif event.unicode and event.unicode.isprintable():
            if len(self._rename_buffer) < 12:
                self._rename_buffer += event.unicode
        return True

    def _start_rename(self, truck_id, current_nickname):
        self._renaming_truck_id = truck_id
        self._rename_buffer = current_nickname

    def _commit_rename(self):
        name = self._rename_buffer.strip()
        if name and self._renaming_truck_id is not None:
            for t in self.game.fleet.trucks:
                if t["id"] == self._renaming_truck_id:
                    t["nickname"] = name
                    break
        self._renaming_truck_id = None
        self._rename_buffer = ""

    def _cancel_rename(self):
        self._renaming_truck_id = None
        self._rename_buffer = ""

    def _flash_insufficient(self):
        self._insufficient_funds_flash = True
        self._flash_timer = 0

    # =====================================================================
    #  Main menu  (title card over the live, animating city)
    # =====================================================================
    MAIN_MENU_ITEMS = [
        ("new",      "NEW GAME"),
        ("load",     "LOAD GAME"),
        ("settings", "SETTINGS"),
        ("quit",     "QUIT"),
    ]

    _DAY_LENGTH_LABEL = {"short": "Short", "normal": "Normal", "long": "Long"}
    _EVENTS_LABEL = {"calm": "Calm", "normal": "Normal", "chaotic": "Chaotic"}

    # Title styling
    _TITLE_LINES = ["THE", "RUBBISH", "GAME"]
    _TITLE_FACE = (240, 196, 42)      # spray-can yellow
    _TITLE_OUTLINE = (16, 14, 10)     # near-black keyline
    _TITLE_SPECK = (34, 28, 16)       # grunge fleck colour

    def _outlined_title_line(self, font, text, radius, shadow_off):
        """One title line: soft drop shadow + thick black keyline + yellow face.
        Padding is asymmetric (extra room down-right for the shadow) so the
        lines can be stacked tightly, the way the reference reads."""
        face = font.render(text, True, self._TITLE_FACE)
        key = font.render(text, True, self._TITLE_OUTLINE)
        bw, bh = face.get_size()
        pad_tl = radius + 4
        pad_br = radius + shadow_off + 4
        surf = pygame.Surface((bw + pad_tl + pad_br, bh + pad_tl + pad_br),
                              pygame.SRCALPHA)
        cx, cy = pad_tl, pad_tl
        shadow = key.copy()
        shadow.set_alpha(165)
        surf.blit(shadow, (cx + shadow_off, cy + shadow_off))
        r2 = radius * radius
        for dx in range(-radius, radius + 1):
            for dy in range(-radius, radius + 1):
                if dx * dx + dy * dy <= r2:
                    surf.blit(key, (cx + dx, cy + dy))
        surf.blit(face, (cx, cy))
        return surf

    @staticmethod
    def _is_title_yellow(px):
        return px[3] > 0 and px[0] > 150 and px[1] > 120 and px[2] < 120

    def _apply_distress(self, surf):
        """Chew up the yellow faces with stable grain, erosion bites and a few
        scratches so the title reads as a distressed stencil (seeded, so it
        never flickers). Transparent bites reveal the black keyline beneath."""
        import random as _random
        rng = _random.Random(0xB1A5)
        mask = pygame.mask.from_surface(surf, 40)
        w, h = surf.get_size()

        # 1. Fine grain — dark opaque flecks over the yellow.
        for _ in range((w * h) // 110):
            x, y = rng.randint(0, w - 1), rng.randint(0, h - 1)
            if mask.get_at((x, y)) and self._is_title_yellow(surf.get_at((x, y))):
                sz = 1 if rng.random() < 0.78 else 2
                surf.fill(self._TITLE_SPECK + (255,), (x, y, sz, sz))

        # 2. Erosion bites — small transparent holes exposing the keyline.
        for _ in range((w * h) // 1900):
            x, y = rng.randint(0, w - 1), rng.randint(0, h - 1)
            if mask.get_at((x, y)) and self._is_title_yellow(surf.get_at((x, y))):
                pygame.draw.circle(surf, (0, 0, 0, 0), (x, y),
                                   rng.choice([1, 1, 2, 2, 3]))

        # 3. Scratches — thin near-horizontal streaks scored through the paint.
        for _ in range(max(8, w // 34)):
            x0, y0 = rng.randint(0, w - 1), rng.randint(0, h - 1)
            length = rng.randint(w // 12, w // 4)
            ang = rng.uniform(-0.22, 0.22)
            ca, sa = math.cos(ang), math.sin(ang)
            for t in range(length):
                x, y = int(x0 + t * ca), int(y0 + t * sa)
                if 0 <= x < w and 0 <= y < h and mask.get_at((x, y)) \
                        and self._is_title_yellow(surf.get_at((x, y))):
                    if rng.random() < 0.55:
                        surf.set_at((x, y), (0, 0, 0, 0))

    def _title_line_height(self, size):
        f = self.fonts.title(size)
        radius = max(3, size // 20)
        shadow_off = max(4, size // 12)
        return f.get_height() + 2 * radius + shadow_off + 8

    def _menu_title_surface(self, screen_w, screen_h):
        if self._title_cache is not None and self._title_cache_w == (screen_w, screen_h):
            return self._title_cache

        max_w = min(screen_w * 0.64, 1120)
        max_h = screen_h * 0.72
        # Grow the (condensed) Anton size until the widest line fills the width
        # budget or the stacked block would exceed the height budget.
        size = 40
        line_gap_frac = -0.16     # negative: pull the tight Anton lines together
        while size < 320:
            nxt = size + 4
            too_wide = self.fonts.title(nxt).size("RUBBISH")[0] > max_w
            stack_h = 3 * self._title_line_height(nxt) + 2 * int(nxt * line_gap_frac)
            if too_wide or stack_h > max_h:
                break
            size += 4
        font = self.fonts.title(size)
        radius = max(3, size // 20)
        shadow_off = max(4, size // 12)
        line_gap = int(size * line_gap_frac)

        parts = [self._outlined_title_line(font, ln, radius, shadow_off)
                 for ln in self._TITLE_LINES]
        total_w = max(p.get_width() for p in parts)
        total_h = sum(p.get_height() for p in parts) + line_gap * (len(parts) - 1)
        surf = pygame.Surface((total_w, total_h), pygame.SRCALPHA)
        y = 0
        for p in parts:
            surf.blit(p, ((total_w - p.get_width()) // 2, y))
            y += p.get_height() + line_gap
        self._apply_distress(surf)

        self._title_cache = surf
        self._title_cache_w = (screen_w, screen_h)
        return surf

    MENU_BAR_H = 46

    def draw_main_menu(self, screen):
        """Title card over the live city: a top toolbar of menu actions (as in
        the reference) and the big distressed Anton title centred below."""
        self.ui = UIPrimitives(screen, self.fonts)
        c = self.ui.c
        w, h = screen.get_size()
        self._screen_size = (w, h)
        self.menu_buttons = []

        # Faint bottom vignette for depth (top is covered by the bar).
        vig = pygame.Surface((w, h), pygame.SRCALPHA)
        for i in range(80):
            a = int(140 * (1 - i / 80))
            pygame.draw.line(vig, (8, 10, 16, a), (0, h - 1 - i), (w, h - 1 - i))
        screen.blit(vig, (0, 0))

        # Title, centred in the area below the top bar.
        title = self._menu_title_surface(w, h)
        tx = (w - title.get_width()) // 2
        region_top = self.MENU_BAR_H + 8
        region_h = h - region_top - 24
        ty = region_top + max(0, (region_h - title.get_height()) // 2)
        screen.blit(title, (tx, ty))

        # Top toolbar bar with the menu actions (drawn last so it sits on top).
        self._draw_top_menu_bar(screen, w)

        if getattr(self.game, "toast", "") and self.game.toast_timer > 0:
            tw = self.fonts.size("body_s", self.game.toast)[0]
            self.ui.text("body_s", self.game.toast, c.ACCENT_CORAL,
                         (w - tw) // 2, h - 32)

        if self._menu_settings_open:
            self._draw_menu_settings(screen, w, h, region_top)

    def _draw_top_menu_bar(self, screen, w):
        c = self.ui.c
        mouse = pygame.mouse.get_pos()
        bar_h = self.MENU_BAR_H
        bar = pygame.Surface((w, bar_h), pygame.SRCALPHA)
        bar.fill((14, 16, 22, 236))
        screen.blit(bar, (0, 0))
        pygame.draw.line(screen, c.BORDER_SUBTLE, (0, bar_h), (w, bar_h), 1)

        x = 14
        bh = 32
        by = (bar_h - bh) // 2
        for action, label in self.MAIN_MENU_ITEMS:
            bw = self.fonts.size("body_b", label)[0] + 34
            rect = pygame.Rect(x, by, bw, bh)
            self.ui.button(rect, label, hovered=rect.collidepoint(mouse),
                           accent=(action == "new"))
            self.menu_buttons.append((rect, action))
            x += bw + 8

    def _draw_menu_settings(self, screen, w, h, below):
        c = self.ui.c
        mouse = pygame.mouse.get_pos()
        s = getattr(self.game, "settings", {})

        pw, ph = 480, 300
        px = (w - pw) // 2
        py = max(below + 24, int(h * 0.40))
        py = min(py, h - ph - 30)
        self.ui.panel(px, py, pw, ph, border=True)

        ix = px + 28
        iy = py + 22
        self.ui.text("h2", "Settings", c.TEXT_PRIMARY, ix, iy)
        iy += 44
        rows = [
            ("set_day_length", "Day length",
             self._DAY_LENGTH_LABEL.get(s.get("day_length", "normal"), "Normal")),
            ("set_events", "Event frequency",
             self._EVENTS_LABEL.get(s.get("events", "normal"), "Normal")),
            ("set_areas", "Show collection areas",
             "On" if s.get("show_areas", True) else "Off"),
        ]
        for action, label, value in rows:
            self.ui.text("body", label, c.TEXT_SECONDARY, ix, iy + 8)
            chip = pygame.Rect(px + pw - 28 - 150, iy, 150, 34)
            self.ui.button(chip, value, hovered=chip.collidepoint(mouse))
            self.menu_buttons.append((chip, action))
            iy += 50
        iy += 8
        back = pygame.Rect(ix, iy, 150, 46)
        self.ui.button(back, "BACK", hovered=back.collidepoint(mouse), accent=True)
        self.menu_buttons.append((back, "menu_back"))

    def menu_resolve(self, pos):
        """Return the action string for a click at `pos`, or None."""
        for rect, action in self.menu_buttons:
            if rect.collidepoint(pos):
                return action
        return None

    def draw(self, screen):
        self.ui = UIPrimitives(screen, self.fonts)
        w, h = screen.get_size()
        self._screen_size = (w, h)
        self._draw_hud(screen, w, h)
        self._draw_toolbar(screen, w, h)
        self._draw_conditions_strip(screen, w, h)
        self._draw_crisis_banner(screen, w, h)
        self._draw_win_banner(screen, w, h)
        self._draw_inspect_panel(screen, w, h)
        # Floating windows sit above the map/HUD but below transient banners.
        self._draw_windows(screen, w, h)
        # Editor bar sits below windows but above toasts/banners.
        if self._editor_mode:
            self._draw_editor_bar(screen, w, h)
        self._draw_toast(screen, w, h)
        # Procurement bar drawn before event banner so events always render on top.
        self._draw_procurement_bar(screen, w)
        self._draw_event_banner(screen, w)
        # Game-over overlay sits on top of everything else.
        self._draw_game_over(screen, w, h)

    # ----- toolbar & floating windows --------------------------------------
    def _draw_toolbar(self, screen, w, h):
        """Persistent top toolbar across the map area: game speed plus a toggle
        button for each floating window (highlighted while its window is open)."""
        ui = self.ui
        c = ui.c
        if self.game.economy.has_lost:
            return
        x0 = HUD_W
        pygame.draw.rect(screen, c.BG_PANEL, pygame.Rect(x0, 0, w - x0, TOOLBAR_H))
        pygame.draw.line(screen, c.BORDER_SUBTLE, (x0, TOOLBAR_H), (w, TOOLBAR_H), 1)

        self.toolbar_buttons = []
        mouse = pygame.mouse.get_pos()
        bx = x0 + 12
        by = (TOOLBAR_H - 28) // 2
        bh = 28

        # Pause / resume
        pr = pygame.Rect(bx, by, 84, bh)
        ui.button(pr, "Resume" if not self.game.running else "Pause",
                  hovered=pr.collidepoint(mouse), accent=not self.game.running)
        self.toolbar_buttons.append((pr, "pause"))
        bx = pr.right + 8

        # Speed cycle
        sr = pygame.Rect(bx, by, 64, bh)
        ui.button(sr, f"{self.game.speed}x", hovered=sr.collidepoint(mouse))
        self.toolbar_buttons.append((sr, "speed"))
        bx = sr.right + 14

        pygame.draw.line(screen, c.BORDER_SUBTLE, (bx - 7, 8), (bx - 7, TOOLBAR_H - 8), 1)

        # One toggle per window
        for key, short, title, ww, hh in WINDOW_DEFS:
            tw = ui.fonts.size("body_b", short)[0] + 26
            rect = pygame.Rect(bx, by, tw, bh)
            is_open = any(win.key == key for win in self.windows)
            hovered = rect.collidepoint(mouse)
            ui.button(rect, short, hovered=hovered, pressed=is_open)
            self.toolbar_buttons.append((rect, ("win", key)))
            bx += tw + 6

    def _draw_windows(self, screen, w, h):
        self._prune_truck_windows()
        for win in self.windows:
            self._clamp_window(win)
            self._draw_window(screen, win)

    def _draw_window(self, screen, win):
        ui = self.ui
        c = ui.c
        r = win.rect
        focused = self.windows and self.windows[-1] is win

        # Drop shadow + body
        shadow = pygame.Surface((r.w, r.h), pygame.SRCALPHA)
        shadow.fill((0, 0, 0, 70))
        screen.blit(shadow, (r.x + 4, r.y + 5))
        pygame.draw.rect(screen, c.BG_PANEL, r, border_radius=8)
        border_col = c.ACCENT_AMBER if focused else c.BORDER
        pygame.draw.rect(screen, border_col, r, 2 if focused else 1, border_radius=8)

        # Title bar
        tb = win.titlebar_rect()
        pygame.draw.rect(screen, c.BG_ACTIVE if focused else c.BG_CARD,
                         tb, border_radius=8)
        pygame.draw.rect(screen, c.BG_ACTIVE if focused else c.BG_CARD,
                         pygame.Rect(tb.x, tb.y + tb.h - 10, tb.w, 10))
        ui.text("body_b", win.title,
                c.ACCENT_AMBER if focused else c.TEXT_SECONDARY,
                tb.x + 14, tb.y + 9)

        # Close box
        cb = pygame.Rect(tb.right - 30, tb.y + 5, 24, 24)
        mouse = pygame.mouse.get_pos()
        ui.icon_button(cb, "X", hovered=cb.collidepoint(mouse))
        win.close_rect = cb

        # Content — point the shared widget lists at THIS window, then render.
        win.widgets = []
        win.cells = []
        self.planner_widgets = win.widgets
        self.planner_cells = win.cells
        body = win.body_rect()
        renderer = self._content_renderers.get(win.key)
        if renderer:
            renderer(screen, body.x, body.y, body.w, body.h)
        elif win.key.startswith("truck_"):
            self._truck_window_content(screen, body.x, body.y, body.w, body.h,
                                       int(win.key.split("_", 1)[1]))

    def _draw_toast(self, screen, w, h):
        if not getattr(self.game, "toast", "") or self.game.toast_timer <= 0:
            return
        msg = self.game.toast
        ui = self.ui
        pad = 16
        surf = ui.fonts.render("body_b", msg, ui.c.TEXT_PRIMARY)
        bw = surf.get_width() + pad * 2
        bh = 40
        bx = HUD_W + (w - HUD_W - bw) // 2
        by = h - 80
        pygame.draw.rect(screen, (0, 0, 0, 60), pygame.Rect(bx + 2, by + 2, bw, bh), border_radius=6)
        pygame.draw.rect(screen, ui.c.BG_CARD, pygame.Rect(bx, by, bw, bh), border_radius=6)
        pygame.draw.rect(screen, ui.c.ACCENT_AMBER, pygame.Rect(bx, by, 4, bh), border_radius=6)
        pygame.draw.rect(screen, ui.c.BORDER, pygame.Rect(bx, by, bw, bh), 1, border_radius=6)
        screen.blit(surf, (bx + pad, by + (bh - surf.get_height()) // 2))

    def _draw_conditions_strip(self, screen, w, h):
        """No-op. Weather and other variables have been relocated to the bottom-right of the screen."""
        pass

    def _draw_game_over(self, screen, w, h):
        """Section 114 insolvency screen. The simulation is already frozen by
        the main loop; this is the overlay explaining what happened and how to
        start a fresh term (main.py handles the R / Esc keys)."""
        eco = self.game.economy
        if not eco.has_lost:
            return
        ui = self.ui
        c = ui.c

        t = min(1.0, getattr(eco, "game_over_timer", 0.0) / 1.2)
        scrim = pygame.Surface((w, h), pygame.SRCALPHA)
        scrim.fill((8, 6, 10, int(225 * t)))
        screen.blit(scrim, (0, 0))

        bw = min(620, w - 80)
        bh = 300
        bx = (w - bw) // 2
        by = (h - bh) // 2
        pygame.draw.rect(screen, (28, 20, 22), pygame.Rect(bx, by, bw, bh), border_radius=12)
        pygame.draw.rect(screen, c.STATUS_BAD, pygame.Rect(bx, by, bw, bh), 2, border_radius=12)
        pygame.draw.rect(screen, c.STATUS_BAD, pygame.Rect(bx, by, bw, 6), border_radius=12)

        title = ui.fonts.render("display", "SECTION 114 NOTICE", c.STATUS_BAD)
        screen.blit(title, title.get_rect(center=(w // 2, by + 44)))
        sub = ui.fonts.render("h2", "The borough is bankrupt.", c.TEXT_PRIMARY)
        screen.blit(sub, sub.get_rect(center=(w // 2, by + 78)))

        reason = (getattr(eco, "lost_reason", "") or
                  "The council can no longer meet its financial obligations.")
        self._draw_wrapped_text(screen, reason, bx + 40, by + 104, bw - 80,
                                ui.fonts.get("body"), c.TEXT_SECONDARY)

        sy = by + 170
        stats = [
            ("DAYS IN OFFICE",      str(getattr(eco, "lost_day", eco.day))),
            ("FINAL SATISFACTION",  f"{int(eco.satisfaction)}%"),
            ("LIFETIME COMPLAINTS", f"{eco.complaints_total:,}"),
            ("POPULATION SERVED",   f"{self.game.city.population:,}"),
        ]
        col_w = (bw - 80) // 2
        for i, (label, val) in enumerate(stats):
            lx = bx + 40 + (i % 2) * col_w
            ly = sy + (i // 2) * 38
            ui.label(label, lx, ly)
            ui.text("h2", val, c.TEXT_PRIMARY, lx, ly + 12)

        prompt = ui.fonts.render(
            "body_b", "Press  R  to start a new term      ·      Esc  to quit",
            c.ACCENT_AMBER)
        screen.blit(prompt, prompt.get_rect(center=(w // 2, by + bh - 24)))


    def _draw_procurement_bar(self, screen, w):
        """Show a notification bar at the bottom for pending vehicle orders."""
        fleet = self.game.fleet
        if not fleet.orders:
            return
        eco = self.game.economy
        ui = self.ui
        c = ui.c
        today = eco.day

        # Build lines for each pending order
        lines = []
        for o in fleet.orders:
            rem = o.days_remaining(today)
            if rem > 0:
                name = o.vehicle.name
                tier = getattr(o, 'display_tier_name', o.tier_id)
                lines.append(f"{name} ({tier}) arriving in {rem} day{'s' if rem != 1 else ''}")

        if not lines:
            return

        msg = "  |  ".join(lines)
        pad = 16
        surf = ui.fonts.render("body_b", msg, c.TEXT_PRIMARY)
        bw = min(surf.get_width() + pad * 2, w - 40)
        bh = 36
        bx = (w - bw) // 2

        # Anchor to the very bottom of the window with a 10px margin
        by = screen.get_height() - bh - 10

        # Background
        pygame.draw.rect(screen, (0, 0, 0, 80), pygame.Rect(bx + 2, by + 2, bw, bh), border_radius=6)
        pygame.draw.rect(screen, c.BG_CARD, pygame.Rect(bx, by, bw, bh), border_radius=6)
        pygame.draw.rect(screen, c.ACCENT_TEAL, pygame.Rect(bx, by, 4, bh), border_radius=6)
        pygame.draw.rect(screen, c.BORDER, pygame.Rect(bx, by, bw, bh), 1, border_radius=6)

        # Truncate text if too wide
        text_x = bx + pad
        text_y = by + (bh - surf.get_height()) // 2
        if surf.get_width() > bw - pad * 2:
            # Simple truncation with ellipsis
            ellipsis = ui.fonts.render("body_b", "...", c.TEXT_PRIMARY)
            max_w = bw - pad * 2 - ellipsis.get_width()
            clip_surf = pygame.Surface((max_w, surf.get_height()), pygame.SRCALPHA)
            clip_surf.blit(surf, (0, 0))
            screen.blit(clip_surf, (text_x, text_y))
            screen.blit(ellipsis, (text_x + max_w, text_y))
        else:
            screen.blit(surf, (text_x, text_y))

    def _draw_hud(self, screen, w, h):
        eco = self.game.economy
        fleet = self.game.fleet
        city = self.game.city
        ui = self.ui
        c = ui.c
        x = 14
        right = HUD_W - 14
        pygame.draw.rect(screen, c.BG_DEEP, pygame.Rect(0, 0, HUD_W, h))
        pygame.draw.line(screen, c.BORDER_SUBTLE, (HUD_W, 0), (HUD_W, h), 1)
        y = 16
        ui.text("h2", f"Day {eco.day}", c.TEXT_PRIMARY, x, y)
        ui.text("body", eco.get_day_of_week_name(), c.TEXT_MUTED, x + 80, y + 4)
        trend = eco.budget_trend
        if trend != 0:
            sign = "+" if trend >= 0 else ""
            trend_color = c.STATUS_GOOD if trend >= 0 else c.STATUS_BAD
            ui.text("body_s", f"{sign}£{int(trend):,}", trend_color, right, y + 4, align="right")
        y += 28
        bar_w = HUD_W - 28
        p = eco.get_day_progress()
        ui.progress_bar(x, y, bar_w, 5, int(p * 100), 100, color=c.ACCENT_AMBER, show_text=False)
        y += 14
        crisis = eco.is_budget_crisis()
        card_h = 56
        ui.card(x, y, HUD_W - 28, card_h, hover=False, selected=crisis)
        ui.label("BUDGET", x + 12, y + 8)
        budget_color = c.STATUS_BAD if crisis else c.TEXT_PRIMARY
        ui.text("display", f"£{int(eco.budget):,}", budget_color, x + 12, y + 24)
        if crisis:
            ui.status_pill(right - 80, y + 8, "CRISIS", "bad")
        y += card_h + 10
        ui.card(x, y, HUD_W - 28, 50)
        ui.label("PUBLIC SATISFACTION", x + 12, y + 6)
        sat_color = c.STATUS_GOOD if eco.satisfaction >= 70 else c.STATUS_WARN if eco.satisfaction >= 40 else c.STATUS_BAD
        ui.text("h2", f"{int(eco.satisfaction)}%", sat_color, right - 12, y + 4, align="right")
        ui.text("body_s", eco.satisfaction_label(), c.TEXT_MUTED, right - 12, y + 26, align="right")
        ui.stat_bar(x + 12, y + 44, HUD_W - 52, eco.satisfaction, 100)
        y += 58
        target = max(1, getattr(eco, "win_streak_target", 14))
        if not eco.has_won:
            ui.card(x, y, HUD_W - 28, 44, selected=False)
            ui.label("PERFECT SERVICE STREAK", x + 12, y + 6)
            streak = eco.perfect_days_streak
            ui.text("body_b", f"{streak}/{target}", c.STATUS_GOOD, right - 12, y + 6, align="right")
            ui.progress_bar(x + 12, y + 28, HUD_W - 52, 4, streak, target, color=c.STATUS_GOOD, show_text=False)
            y += 52
        else:
            ui.card(x, y, HUD_W - 28, 44, selected=True)
            ui.label("STATUS", x + 12, y + 6)
            ui.text("h2", "CHAMPION", c.ACCENT_AMBER, right - 12, y + 6, align="right")
            ui.progress_bar(x + 12, y + 28, HUD_W - 52, 4, 1, 1, color=c.ACCENT_AMBER, show_text=False)
            y += 52
        ui.card(x, y, HUD_W - 28, 100)
        stats = [
            ("Population", f"{city.population:,}", c.TEXT_SECONDARY),
            ("Properties", f"{city.property_count:,}", c.TEXT_SECONDARY),
            ("Lorries", str(len(fleet.trucks)), c.ACCENT_TEAL),
            ("Crew", str(fleet.workers), c.ACCENT_TEAL),
        ]
        sy = y + 10
        for label, value, val_color in stats:
            ui.label(label, x + 12, sy)
            ui.value(value, right - 12, sy, val_color, align="right")
            sy += 22
        y += 110
        if eco.active_event and eco.active_event.get("duration", 0) > 0:
            ui.card(x, y, HUD_W - 28, 32, selected=True)
            txt = f"{eco.active_event['name']} - {eco.active_event['remaining_days']}d"
            ui.text("body_s", txt, c.ACCENT_AMBER, x + 12, y + 8)
            y += 40
        y += 6
        # ── Startup loan status ──────────────────────────────────────────────
        if not eco.loan_cleared():
            ui.card(x, y, HUD_W - 28, 50)
            ui.label("STARTUP LOAN", x + 12, y + 6)
            bal = eco.loan_balance()
            ui.text("body_b", f"£{int(bal):,}", c.ACCENT_CORAL, right - 12, y + 4, align="right")
            ui.text("caption", f"-£{int(eco.loan_daily_payment())}/day", c.TEXT_DIM, x + 12, y + 24)
            ui.progress_bar(x + 110, y + 30, HUD_W - 150, 5, int(eco.loan_progress() * 100), 100,
                            color=c.ACCENT_CORAL, show_text=False)
            y += 58
        else:
            ui.card(x, y, HUD_W - 28, 32, selected=True)
            ui.text("body_s", "Startup loan cleared", c.STATUS_GOOD, x + 12, y + 8)
            y += 40
        ui.section_header(x, y, "COLLECTIONS", w=HUD_W - 28)
        y += 24
        due = fleet.get_total_full_bins()
        unscheduled = fleet.get_unscheduled_overflows()
        ui.label("Bins due today", x, y)
        ui.value(str(due), right, y, c.TEXT_PRIMARY, align="right")
        y += 22
        ui.label("Overflowing", x, y)
        overflow_color = c.STATUS_BAD if unscheduled > 0 else c.TEXT_SECONDARY
        ui.value(str(unscheduled), right, y, overflow_color, align="right")
        y += 22
        ui.label("Complaints (today)", x, y)
        ui.value(str(eco.complaints_today), right, y, c.TEXT_PRIMARY, align="right")
        y += 22
        karen_n = getattr(eco, 'karen_complaints_today', 0)
        ui.label("Baseline gripes", x, y)
        ui.value(str(karen_n), right, y,
                 c.TEXT_DIM if karen_n == 0 else c.STATUS_WARN, align="right")
        y += 26

    def _draw_event_banner(self, screen, w):
        active = self.game.economy.active_event
        CRITICAL_EFFECTS = ("crewStrike", "truckBreakdown")

        # Determine which event (if any) to display.
        # Priority: transient visible banner > persistent critical active event.
        is_critical_active = active and active.get("effect") in CRITICAL_EFFECTS
        if not self._event_visible and not is_critical_active:
            return

        event = self._current_event if self._event_visible else active
        if not event:
            return

        ui = self.ui
        c = ui.c

        # Choose accent colour by severity.
        effect = event.get("effect", "")
        if effect == "crewStrike":
            accent = c.STATUS_BAD          # red  — most severe
        elif effect == "truckBreakdown":
            accent = c.STATUS_WARN         # orange — serious
        elif effect == "achievement":
            accent = c.ACCENT_SAGE         # green — celebratory
        else:
            accent = c.ACCENT_AMBER        # amber  — standard

        # Animation progress: slide in/out for the transient window.
        # For persistent critical events (active but transient expired), hold fully open.
        if self._event_visible:
            progress = min(1.0, self._event_timer_active / 0.45)
            if self._event_timer_active > self._event_duration - 0.45:
                progress = 1.0 - min(1.0,
                    (self._event_timer_active - (self._event_duration - 0.45)) / 0.45)
        else:
            progress = 1.0  # persistent: fully open, no animation

        bw = min(520, max(360, w // 2))
        bh = 80
        bx = (w - bw) // 2
        by = int(-100 + (130 * progress))

        pygame.draw.rect(screen, (0, 0, 0, 80), pygame.Rect(bx + 3, by + 3, bw, bh), border_radius=8)
        pygame.draw.rect(screen, c.BG_CARD,     pygame.Rect(bx, by, bw, bh),         border_radius=8)
        pygame.draw.rect(screen, accent,         pygame.Rect(bx, by, 5, bh),          border_radius=8)
        pygame.draw.rect(screen, c.BORDER,       pygame.Rect(bx, by, bw, bh), 1,      border_radius=8)

        ui.text("h2",   event["name"], accent,        bx + 20, by + 14)
        ui.text("body", event["desc"], c.TEXT_SECONDARY, bx + 20, by + 44)

    def _draw_crisis_banner(self, screen, w, h):
        if not self._insufficient_funds_flash and not self.game.economy.is_budget_crisis():
            return
        ui = self.ui
        text = "Insufficient funds" if self._insufficient_funds_flash else "Budget crisis - overspending detected"
        bw, bh = 480, 42
        bx = (w - bw) // 2
        by = h - 60
        pygame.draw.rect(screen, (0, 0, 0, 80), pygame.Rect(bx + 2, by + 2, bw, bh), border_radius=6)
        pygame.draw.rect(screen, ui.c.BG_CARD, pygame.Rect(bx, by, bw, bh), border_radius=6)
        pygame.draw.rect(screen, ui.c.STATUS_BAD, pygame.Rect(bx, by, 4, bh), border_radius=6)
        pygame.draw.rect(screen, ui.c.STATUS_BAD, pygame.Rect(bx, by, bw, bh), 1, border_radius=6)
        surf = ui.fonts.render("body_b", text, ui.c.STATUS_BAD)
        screen.blit(surf, surf.get_rect(center=(w // 2, by + bh // 2)))

    def _draw_win_banner(self, screen, w, h):
        eco = self.game.economy
        if not eco.has_won:
            return
        eco.win_celebration_timer -= 0.016
        if eco.win_celebration_timer <= 0:
            return
        alpha = min(1.0, eco.win_celebration_timer / 3.0)
        if alpha <= 0:
            return
        ui = self.ui
        bw = min(600, w - 100)
        bh = 130
        bx = (w - bw) // 2
        by = (h - bh) // 2 - 50
        pygame.draw.rect(screen, (35, 30, 18), pygame.Rect(bx, by, bw, bh), border_radius=10)
        pygame.draw.rect(screen, ui.c.ACCENT_AMBER, pygame.Rect(bx, by, bw, bh), 2, border_radius=10)
        title = ui.fonts.render("display", "BOROUGH CHAMPION", ui.c.ACCENT_AMBER)
        screen.blit(title, title.get_rect(center=(w // 2, by + 40)))
        sub = ui.fonts.render("h2", f"{eco.win_streak_target} consecutive days at full service! Day {eco.win_day}.", ui.c.TEXT_PRIMARY)
        screen.blit(sub, sub.get_rect(center=(w // 2, by + 75)))
        hint = ui.fonts.render("body_s", "Keep it up to maintain your perfect record!", ui.c.TEXT_MUTED)
        screen.blit(hint, hint.get_rect(center=(w // 2, by + 100)))

    def _draw_inspect_panel(self, screen, w, h):
        if not self.game.selected_tile:
            self._draw_bottom_right_conditions(screen, w, h)
            return
        ui = self.ui
        c = ui.c
        pw, ph = 280, 260
        px = w - pw - 20
        py = h - ph - 20
        pygame.draw.rect(screen, (0, 0, 0, 60), pygame.Rect(px + 3, py + 3, pw, ph), border_radius=8)
        ui.card(px, py, pw, ph)
        tile = self.game.selected_tile["tile"]
        tx, ty = self.game.selected_tile["x"], self.game.selected_tile["y"]
        rx = px + 16
        rr = px + pw - 16
        if tile.type == "road":
            ui.text("h2", "Road", c.TEXT_PRIMARY, rx, py + 14)
            ui.text("body_s", "Part of the collection network.", c.TEXT_MUTED, rx, py + 44)
            return
        if tile.type == "green":
            ui.text("h2", "Green Space", c.TEXT_PRIMARY, rx, py + 14)
            ui.text("body_s", "Park or garden area.", c.TEXT_MUTED, rx, py + 44)
            return
        if tile.type == "landfill":
            ui.text("h2", "Landfill Site", c.TEXT_PRIMARY, rx, py + 14)
            ui.text("body_s", "Where full lorries tip their loads.", c.TEXT_MUTED, rx, py + 44)
            ui.text("body_xs", "Disposal gate fees charged here.", c.TEXT_DIM, rx, py + 66)
            return
        label = STYLE_LABELS.get(tile.building_style, tile.type.title())
        ui.text("h2", label, c.TEXT_PRIMARY, rx, py + 12)
        ui.text("caption", f"({tx}, {ty})", c.TEXT_DIM, rr, py + 14, align="right")
        area = self.game.city.get_area(tile.area_id)
        row = py + 44
        lh = 24
        if area:
            ui.label("Round", rx, row)
            ui.value(area.name, rr, row, c.ACCENT_TEAL, align="right")
            row += lh
            ui.label("Collection day", rx, row)
            ui.value(DAY_NAMES[area.collection_day], rr, row, c.TEXT_PRIMARY, align="right")
            row += lh
            rt = area.route_type
            rt_label = ROUTE_TYPE_LABELS.get(rt, rt)
            rt_color = ROUTE_TYPE_COLORS.get(rt, c.TEXT_SECONDARY)
            ui.label("Route type", rx, row)
            ui.value(rt_label, rr, row, rt_color, align="right")
            row += lh + 6
        pct = int(tile.bin_fill)
        if pct < 50:
            status = "Low"
            status_type = "good"
        elif pct < 75:
            status = "Filling up"
            status_type = "neutral"
        elif pct < 90:
            status = "Nearly full"
            status_type = "warn"
        else:
            status = "Overflowing"
            status_type = "bad"
        ui.label("Bin fill", rx, row)
        ui.value(f"{pct}%", rr, row, c.TEXT_PRIMARY, align="right")
        row += 18
        ui.progress_bar(rx, row, pw - 32, 8, pct, 100,
                       color=c.STATUS_BAD if pct > 85 else c.STATUS_WARN if pct > 60 else c.STATUS_GOOD,
                       show_text=False)
        ui.status_pill(rr - 70, row - 16, status, status_type)
        row += 22
        if tile.population:
            ui.label("Residents", rx, row)
            ui.value(str(tile.population), rr, row, c.TEXT_SECONDARY, align="right")
            row += lh
        ui.text("body_xs", "Open the Rounds window to reschedule.", c.TEXT_DIM, rx, py + ph - 24)

    def _draw_bottom_right_conditions(self, screen, w, h):
        """Alternative readout placed in the bottom-right context when no tile 
        is actively inspected."""
        ui = self.ui
        c = ui.c
        eco = self.game.economy

        weather_map = {
            "dry":      ("Dry",      c.TEXT_SECONDARY),
            "rain":     ("Rain",     c.ACCENT_TEAL),
            "snow":     ("Snow",     (200, 220, 255)),
            "overcast": ("Overcast", c.TEXT_DIM),
        }
        wlabel, wcol = weather_map.get(eco.weather, ("Dry", c.TEXT_SECONDARY))

        tr = getattr(eco, "fuel_index_trend", 0.0)
        arrow = "+" if tr > 0.002 else "-" if tr < -0.002 else "="
        idx = getattr(eco, "fuel_index", 1.0)
        dcol = (c.STATUS_BAD if idx >= 1.15 else
                c.STATUS_GOOD if idx <= 0.92 else c.TEXT_SECONDARY)

        morale = eco.worker_morale
        mcol = (c.STATUS_GOOD if morale >= 65 else
                c.STATUS_WARN if morale >= 40 else c.STATUS_BAD)

        segs = [
            ("WEATHER", wlabel, wcol),
            ("SEASON",  eco.season_name(), c.ACCENT_SAGE),
            ("DIESEL",  f"£{eco.fuel_price():.2f}/L {arrow}", dcol),
            ("MORALE",  f"{int(morale)}%", mcol),
        ]

        pad, gap = 12, 18
        seg_surfs = []
        total_w = pad
        for label, val, col in segs:
            lsurf = ui.fonts.render("caption", label, c.TEXT_DIM)
            vsurf = ui.fonts.render("body_b", val, col)
            sw = max(lsurf.get_width(), vsurf.get_width())
            seg_surfs.append((lsurf, vsurf, sw))
            total_w += sw + gap
        total_w += pad - gap

        bh = 46
        bx = w - total_w - 20
        by = h - bh - 20
        pygame.draw.rect(screen, (0, 0, 0, 70), pygame.Rect(bx + 2, by + 2, total_w, bh), border_radius=8)
        pygame.draw.rect(screen, c.BG_CARD, pygame.Rect(bx, by, total_w, bh), border_radius=8)
        pygame.draw.rect(screen, c.BORDER, pygame.Rect(bx, by, total_w, bh), 1, border_radius=8)

        cxp = bx + pad
        for i, (lsurf, vsurf, sw) in enumerate(seg_surfs):
            screen.blit(lsurf, (cxp, by + 8))
            screen.blit(vsurf, (cxp, by + 22))
            cxp += sw + gap
            if i < len(seg_surfs) - 1:
                dxp = cxp - gap // 2
                pygame.draw.line(screen, c.BORDER_SUBTLE,
                                 (dxp, by + 8), (dxp, by + bh - 8), 1)

    def _pbtn(self, screen, rect, label, fn, enabled=True, fkey="body_b", fill=None, accent=False):
        ui = self.ui
        mouse = pygame.mouse.get_pos()
        hovered = rect.collidepoint(mouse) and enabled
        ui.button(rect, label, enabled=enabled, accent=accent, hovered=hovered)
        if enabled:
            self.planner_widgets.append((rect, fn))

    def _stepper(self, screen, x, y, label, value_str, dec_fn, inc_fn, label_w=190, val_w=92):
        ui = self.ui
        ui.label(label, x, y + 6)
        minus = pygame.Rect(x + label_w, y, 28, 28)
        valr = pygame.Rect(minus.right + 4, y, val_w, 28)
        plus = pygame.Rect(valr.right + 4, y, 28, 28)
        ui.icon_button(minus, "-", hovered=False)
        ui.inset_panel(valr.x, valr.y, valr.w, valr.h)
        ui.text("mono_b", value_str, ui.c.TEXT_PRIMARY, valr.centerx, valr.y + 6, align="center")
        ui.icon_button(plus, "+", hovered=False)
        self.planner_widgets.append((minus, dec_fn))
        self.planner_widgets.append((plus, inc_fn))
        return y + 36

    def _tab_rounds(self, screen, x, y, w, h):
        ui = self.ui
        c = ui.c
        eco = self.game.economy
        city = self.game.city
        fleet = self.game.fleet
        today = eco.get_day_of_week()
        week = eco.week_index
        ui.text("body_s", "Click a weekday to move a round. FREQ toggles weekly/fortnightly.", c.TEXT_MUTED, x, y)
        ty = y + 24
        name_w = 160
        day_w = 38
        freq_w = 90
        type_w = 80
        left_cols = name_w + 7 * day_w + freq_w + type_w
        rest = {"props": 60, "due": 60, "status": 110}
        ui.label("ROUND", x, ty)
        cxp = x + name_w
        for i, d in enumerate(DAY_NAMES):
            cell = pygame.Rect(cxp + i * day_w, ty - 2, day_w, 18)
            if i == today:
                pygame.draw.rect(screen, c.BG_ACTIVE, cell, border_radius=3)
            ui.text("caption", d, c.ACCENT_AMBER if i == today else c.TEXT_DIM, cell.centerx, ty, align="center")
        fx = cxp + 7 * day_w
        ui.text("caption", "FREQ", c.TEXT_DIM, fx + freq_w // 2, ty, align="center")
        tx = fx + freq_w
        ui.text("caption", "TYPE", c.TEXT_DIM, tx + type_w // 2, ty, align="center")
        sx = tx + type_w
        for label, key in (("PROPS", "props"), ("LEFT", "due"), ("STATUS", "status")):
            ui.text("caption", label, c.TEXT_DIM, sx + rest[key] // 2, ty, align="center")
            sx += rest[key]
        ty += 20
        ui.h_line(x, ty, left_cols + sum(rest.values()))
        ty += 6
        per_day_rounds = [0] * 7
        for area in city.areas:
            st = city.area_stats(area.id, today, fleet.service_threshold, week)
            if not st:
                continue
            per_day_rounds[area.collection_day] += 1
            rowrect = pygame.Rect(x, ty - 2, left_cols + sum(rest.values()), 26)
            if st["is_today"]:
                pygame.draw.rect(screen, (40, 50, 65), rowrect, border_radius=3)
            ui.text("body_s", area.name, c.TEXT_PRIMARY, x, ty + 2)
            for i in range(7):
                cell = pygame.Rect(cxp + i * day_w + 3, ty, day_w - 6, 20)
                if i == area.collection_day:
                    pygame.draw.rect(screen, c.ACCENT_AMBER, cell, border_radius=4)
                    ui.text("body_b", "o", c.BG_DEEP, cell.centerx, ty + 2, align="center")
                else:
                    pygame.draw.rect(screen, c.BG_CARD, cell, border_radius=4)
                    pygame.draw.rect(screen, c.BORDER_SUBTLE, cell, 1, border_radius=4)
                self.planner_cells.append((cell, area.id, i))
            frect = pygame.Rect(fx + 6, ty + 1, freq_w - 12, 20)
            self._pbtn(screen, frect, st["freq_label"], (lambda a=area.id: self._cycle_round_freq(a)), fkey="caption")
            rt = area.route_type
            rt_label = ROUTE_TYPE_LABELS.get(rt, rt)
            trect = pygame.Rect(tx + 6, ty + 1, type_w - 12, 20)
            ui.status_pill(trect.x, trect.y, rt_label, "good" if rt == "residential" else "info" if rt == "commercial" else "neutral")
            sx = tx + type_w
            ui.text("mono_s", str(st["props"]), c.TEXT_SECONDARY, sx + rest["props"] // 2, ty + 2, align="center")
            sx += rest["props"]
            left = fleet.area_due_count(area.id)
            left_color = c.STATUS_BAD if left > 5 else c.STATUS_WARN if left > 0 else c.TEXT_MUTED
            ui.text("mono_s", str(left), left_color, sx + rest["due"] // 2, ty + 2, align="center")
            sx += rest["due"]
            stcol = c.STATUS_BAD if st["status"] in ("OVERFLOW", "DUE TODAY") else c.STATUS_WARN if st["status"] in ("WATCH", "NEXT WEEK") else c.TEXT_MUTED
            stkey = "body_s" if st["status"] in ("OVERFLOW", "DUE TODAY") else "caption"
            ui.text(stkey, st["status"], stcol, sx + rest["status"] // 2, ty + 2, align="center")
            ty += 26
        ty += 8
        ui.h_line(x, ty, left_cols + sum(rest.values()))
        ty += 10
        ui.label("Rounds / day", x, ty)
        for i in range(7):
            ui.text("mono_b", str(per_day_rounds[i]), c.ACCENT_AMBER if i == today else c.TEXT_SECONDARY, cxp + i * day_w + day_w // 2, ty, align="center")
        ty += 28
        ty = self._stepper(screen, x, ty, "Service threshold (% full)", f"{int(fleet.service_threshold)}%",
                          (lambda: self._adjust_threshold(-5)), (lambda: self._adjust_threshold(5)))
        demand = fleet.get_today_demand()
        capacity = fleet.estimated_daily_capacity()
        verdict = "within capacity" if demand <= capacity else "OVER CAPACITY"
        vcolor = c.STATUS_GOOD if demand <= capacity else c.STATUS_BAD
        ui.text("body_s", f"Today: {fleet.active_lorries()} lorries  |  capacity {capacity}  |  demand {demand}  ->  ", c.TEXT_SECONDARY, x, ty + 2)
        ui.text("body_b", verdict, vcolor, x + 420, ty + 2)

    def _tab_waste(self, screen, x, y, w, h):
        ui = self.ui
        c = ui.c
        waste = self.game.waste
        ui.text("body_s", "Choose which streams the borough collects. More streams lift satisfaction but fill bins faster.", c.TEXT_MUTED, x, y)
        ty = y + 28
        for s in waste.streams:
            card = pygame.Rect(x, ty, w, 80)
            ui.card(card.x, card.y, card.w, card.h, hover=False)
            on = s.enabled
            tgl = pygame.Rect(x + 12, ty + 14, 64, 26)
            if s.can_disable:
                self._pbtn(screen, tgl, "ON" if on else "OFF", (lambda sid=s.id: self._toggle_stream(sid)), accent=on, fkey="body_b")
            else:
                ui.status_pill(tgl.x, tgl.y, "ON", "good")
            name_col = c.TEXT_PRIMARY if on else c.TEXT_DIM
            ui.text("body_b", s.name, name_col, x + 88, ty + 8)
            ui.text("body_s", s.blurb, c.TEXT_MUTED if on else c.TEXT_DIM, x + 88, ty + 30)
            econ = (f"gate £{s.gate_fee:.3f}/u  |  "
                   f"{'credit' if s.id != 'garden' else 'charge'} £{s.credit:.3f}/u  |  "
                   f"+{s.satisfaction} satis")
            ui.text("caption", econ, c.TEXT_DIM, x + 88, ty + 52)
            frect = pygame.Rect(x + w - 120, ty + 14, 108, 26)
            if on:
                self._pbtn(screen, frect, s.freq_label, (lambda sid=s.id: self._cycle_stream_freq(sid)), fkey="body_s")
            else:
                pygame.draw.rect(screen, c.BG_PANEL, frect, border_radius=4)
                pygame.draw.rect(screen, c.BORDER_SUBTLE, frect, 1, border_radius=4)
                ui.text("body_s", s.freq_label, c.TEXT_DIM, frect.centerx, ty + 18, align="center")
            ty += 88
        ty += 6
        ui.h_line(x, ty, w)
        ty += 12
        ui.label("Bin fill rate", x, ty)
        ui.value(f"x{waste.fill_multiplier():.2f}", x + 140, ty, c.ACCENT_TEAL)
        ui.label("Satisfaction ceiling", x + 280, ty)
        ui.value(f"{int(waste.satisfaction_ceiling())}%", x + 450, ty, c.ACCENT_TEAL)
        ty += 26
        cont = waste.contamination_rate()
        cont_col = c.ACCENT_TEAL if cont < 0.10 else (c.TEXT_MUTED if cont < 0.16 else c.ACCENT_CORAL)
        ui.label("Recycling rejected", x, ty)
        ui.value(waste.contamination_label(), x + 140, ty, cont_col)
        if cont >= 0.10:
            ui.text("caption", "Add food/garden caddies to keep loads clean.", c.TEXT_DIM, x + 280, ty + 2)

    def _tab_fleet(self, screen, x, y, w, h):
        ui = self.ui
        c = ui.c
        eco = self.game.economy
        fleet = self.game.fleet
        ui.text("body_s", "Choose a procurement method, then select a vehicle model and place your order.", c.TEXT_MUTED, x, y)
        ty = y + 24
        tier_w = (w - 24) // 3
        tier_h = 64
        tier_data = [
            ("factory", "Factory Custom", "180-220 days", "-35% price", c.STATUS_GOOD,
             "Bespoke build. Cheapest but plan 6+ months ahead."),
            ("dealer", "Dealer Stock", "14-18 days", "+15% premium", c.ACCENT_TEAL,
             "Pre-built. MOT, O-License & delivery. Watch for delays."),
            ("rental", "Spot Rental", "1-2 days", "4.5x daily cost", c.STATUS_BAD,
             "Emergency hire. Arrives fast, burns budget fast."),
        ]
        if not hasattr(self.game, '_selected_procurement_tier'):
            self.game._selected_procurement_tier = "dealer"
        selected_tier = self.game._selected_procurement_tier
        for i, (tid, tname, ttime, tprice, tcolour, tblurb) in enumerate(tier_data):
            tx = x + 8 + i * (tier_w + 8)
            rect = pygame.Rect(tx, ty, tier_w, tier_h)
            is_sel = selected_tier == tid
            ui.card(tx, ty, tier_w, tier_h, selected=is_sel)
            if is_sel:
                pygame.draw.rect(screen, tcolour, pygame.Rect(tx, ty, 4, tier_h), border_radius=4)
            name_col = c.ACCENT_AMBER if is_sel else c.TEXT_PRIMARY
            ui.text("body_b", tname, name_col, tx + 10, ty + 8)
            ui.text("caption", ttime, c.TEXT_MUTED, tx + 10, ty + 26)
            ui.text("caption", tprice, tcolour, tx + 10, ty + 42)
            self.planner_widgets.append((rect, (lambda t=tid: setattr(self.game, '_selected_procurement_tier', t))))
        ty += tier_h + 12
        tier_blurbs = {
            "factory": ("Factory Custom Order: Order a bespoke RCV direct from the manufacturer. "
                       "Cheapest upfront cost (-35%), but 180-220 day wait. Best for long-term planning."),
            "dealer": ("Dealer Stock Purchase: Pre-built chassis and body. 2-week wait covers MOT, "
                      "O-License and delivery. Premium price (+15%). Watch for paperwork delays."),
            "rental": ("Spot Rental: Emergency hire for breakdowns. 1-2 day arrival, 4.5x daily cost. "
                      "Use sparingly -- rent only while other orders are in transit."),
        }
        blurb = tier_blurbs.get(selected_tier, "")
        self._draw_wrapped_text(screen, blurb, x + 8, ty, w - 16, ui.fonts._fonts["caption"], c.TEXT_MUTED)
        ty += 44
        col_w = (w - 16) // 2
        col2_x = x + col_w + 16
        cat_y = ty
        for idx, v in enumerate(VEHICLE_CATALOGUE):
            cx = x if idx % 2 == 0 else col2_x
            if idx % 2 == 0:
                row_y = cat_y
            from procurement import get_tier
            tier = get_tier(selected_tier)
            adj_price = v.get_price_for_tier(selected_tier) if hasattr(v, 'get_price_for_tier') else v.price
            adj_run = v.get_running_cost_for_tier(selected_tier) if hasattr(v, 'get_running_cost_for_tier') else v.running_cost
            lead = tier.random_lead_time() if tier else v.lead_time
            card = pygame.Rect(cx, row_y, col_w, 120)
            ui.card(cx, row_y, card.w, card.h)
            ui.text("body_b", v.name, c.TEXT_PRIMARY, cx + 12, row_y + 8)
            ui.text("body_s", f"cap {v.capacity:,}  crew {v.crew_cap}  spd x{v.speed_factor:.2f}", c.TEXT_MUTED, cx + 12, row_y + 28)
            ui.text("caption", f"run £{adj_run}/day  |  lead {lead}d", c.TEXT_DIM, cx + 12, row_y + 46)
            if selected_tier == "rental":
                price_label = f"Rent £{adj_price//1000 or 1}k deposit"
                can_afford = eco.budget >= adj_price
                btn = pygame.Rect(cx + 12, row_y + 68, col_w - 24, 30)
                self._pbtn(screen, btn, price_label, (lambda vid=v.id: self._buy_vehicle(vid, selected_tier, False)), enabled=can_afford, fkey="body_b", accent=True)
            else:
                buy = pygame.Rect(cx + 12, row_y + 68, (col_w - 32) // 2, 30)
                lease = pygame.Rect(buy.right + 8, row_y + 68, (col_w - 32) // 2, 30)
                can_buy = eco.budget >= adj_price
                can_lease = eco.budget >= v.deposit()
                self._pbtn(screen, buy, f"Buy £{adj_price//1000}k", (lambda vid=v.id: self._buy_vehicle(vid, selected_tier, False)), enabled=can_buy, fkey="body_s")
                self._pbtn(screen, lease, f"Lease £{v.deposit()//1000 or 1}k", (lambda vid=v.id: self._buy_vehicle(vid, selected_tier, True)), enabled=can_lease, fkey="body_s")
            if idx % 2 == 1:
                cat_y += 128
        if len(VEHICLE_CATALOGUE) % 2 == 1:
            cat_y += 128
        ty = cat_y + 8
        ui.h_line(x, ty, w)
        ty += 12
        owned = len(fleet.trucks)
        leased_n = sum(1 for t in fleet.trucks if t.get("leased"))
        rental_n = sum(1 for t in fleet.trucks if t.get("tier_id") == "rental")
        ui.text("h3", "Current fleet", c.TEXT_PRIMARY, x, ty)
        fleet_info = f"{owned} lorries"
        if leased_n:
            fleet_info += f" ({leased_n} leased)"
        if rental_n:
            fleet_info += f"  [Rental: {rental_n}]"
        fleet_info += f"  |  {fleet.workers} crew  |  £{int(fleet.daily_vehicle_cost())}/day"
        ui.text("body_s", fleet_info, c.TEXT_MUTED, x, ty + 22)
        hire = pygame.Rect(x, ty + 50, 130, 28)
        fire = pygame.Rect(hire.right + 10, ty + 50, 130, 28)
        self._pbtn(screen, hire, "Hire crew £2.5k", self._hire, enabled=eco.budget >= 2500, fkey="body_s")
        self._pbtn(screen, fire, "Release crew", self._fire, enabled=fleet.workers > 0, fkey="body_s")
        ox = x + w - 300
        ui.text("h3", "On order", c.TEXT_PRIMARY, ox, ty)
        oy = ty + 24
        if not fleet.orders:
            ui.text("body_s", "Nothing on order.", c.TEXT_DIM, ox, oy)
        else:
            for o in fleet.orders[:5]:
                rem = o.days_remaining(eco.day)
                tier_name = getattr(o, 'display_tier_name', 'Buy') if hasattr(o, 'display_tier_name') else 'Buy'
                tag = f"{tier_name}"
                if o.leased:
                    tag += " lease"
                line = f"{o.vehicle.name} ({tag}) - {rem}d"
                if hasattr(o, 'event_name') and o.event_name and not o.event_triggered:
                    line += f"  !{o.event_name}"
                    col = c.STATUS_BAD
                elif hasattr(o, 'event_triggered') and o.event_triggered:
                    line += "  (delayed)"
                    col = c.TEXT_MUTED
                else:
                    col = c.TEXT_MUTED
                ui.text("body_s", line, col, ox, oy)
                oy += 20


    def _tab_staff(self, screen, x, y, w, h):
        """Deep staff & vehicle cost management tab."""
        ui    = self.ui
        c     = ui.c
        eco   = self.game.economy
        fleet = self.game.fleet

        col1_w = min(348, w // 2 - 8)
        col2_x = x + col1_w + 16
        col2_w = w - col1_w - 16
        rx     = x + col1_w          # right edge for mono value alignment

        # ── Summary banner ───────────────────────────────────────────────────
        assigned  = sum(t.get("crew", 0) for t in fleet.trucks)
        idle_crew = max(0, fleet.workers - assigned)
        veh_daily = sum(
            (t.get("lease_weekly", 0) / 7.0 if t.get("leased")
             else t.get("running_cost", 0))
            for t in fleet.trucks
        )
        ui.text("body_s",
                f"Workforce: {fleet.workers} crew  |  Assigned: {assigned}"
                f"  Idle: {idle_crew}  |  Vehicle fleet: £{veh_daily:.0f}/day",
                c.TEXT_MUTED, x, y)
        ty = y + 26

        # ── LEFT COLUMN: Pay rates & per-worker breakdown ────────────────────
        ui.section_header(x, ty, "PAY RATES", col1_w)
        ty += 22

        ty = self._stepper(screen, x, ty,
                           "Base wage (£/hr)",
                           f"£{eco.hourly_wage_rate:.2f}",
                           lambda: self._adjust_wage(-0.50),
                           lambda: self._adjust_wage(+0.50),
                           label_w=178, val_w=70)

        # ── Worker morale & strike risk ───────────────────────────────────────
        morale      = eco.worker_morale
        morale_lbl  = eco.morale_label()
        strike_risk = eco.strike_risk_pct()

        # Colour the bar: green → amber → red as morale falls
        if morale >= 65:
            bar_col = c.STATUS_GOOD
        elif morale >= 40:
            bar_col = c.STATUS_WARN
        else:
            bar_col = c.STATUS_BAD

        # Morale label + bar
        ui.text("body_s", "Worker morale", c.TEXT_SECONDARY, x, ty)
        mtext_col = bar_col
        ui.text("body_s", f"{morale_lbl}  ({morale:.0f}%)", mtext_col, rx - 2, ty, align="right")
        ty += 18
        bar_w = col1_w - 30
        bar_h = 7
        pygame.draw.rect(screen, c.BG_CARD, (x, ty, bar_w, bar_h), border_radius=3)
        fill_w = int(bar_w * morale / 100.0)
        if fill_w > 0:
            pygame.draw.rect(screen, bar_col, (x, ty, fill_w, bar_h), border_radius=3)
        pygame.draw.rect(screen, c.BORDER_SUBTLE, (x, ty, bar_w, bar_h), 1, border_radius=3)
        ty += 14

        # Strike risk line
        if strike_risk < 3.0:
            risk_col  = c.TEXT_DIM
            risk_text = f"Strike risk: {strike_risk:.1f}%  — crew content"
        elif strike_risk < 8.0:
            risk_col  = c.STATUS_WARN
            risk_text = f"Strike risk: {strike_risk:.1f}%  ⚠ Consider a pay rise"
        else:
            risk_col  = c.STATUS_BAD
            risk_text = f"Strike risk: {strike_risk:.1f}%  ⚠⚠ Union action likely!"
        ui.text("caption", risk_text, risk_col, x, ty)
        ty += 20

        ty = self._stepper(screen, x, ty,
                           "Employer pension",
                           f"{eco.pension_rate * 100:.1f}%",
                           lambda: self._adjust_pension(-0.005),
                           lambda: self._adjust_pension(+0.005),
                           label_w=178, val_w=70)

        ty = self._stepper(screen, x, ty,
                           "PPE / uniform (£/worker/day)",
                           f"£{eco.ppe_daily:.2f}",
                           lambda: self._adjust_ppe(-0.50),
                           lambda: self._adjust_ppe(+0.50),
                           label_w=178, val_w=70)

        ui.text("caption",
                f"Employer NI: 13.8% fixed (HMRC 2025/26)  |  "
                f"Min wage floor: £11.44/hr",
                c.TEXT_DIM, x, ty)
        ty += 18

        ui.h_line(x, ty, col1_w)
        ty += 12

        # ── Per-worker cost breakdown ─────────────────────────────────────────
        ui.section_header(x, ty, "COST PER WORKER / DAY", col1_w)
        ty += 22

        bd  = eco.staff_cost_breakdown(fleet.workers)
        n   = max(1, fleet.workers)
        per_base    = bd["base"]    / n
        per_ni      = bd["ni"]      / n
        per_pension = bd["pension"] / n
        per_ppe     = bd["ppe"]     / n
        per_total   = bd["per_head"]

        # label, per-head value, colour, annotation
        bdown_rows = [
            ("Base wages",    per_base,    c.TEXT_SECONDARY,
             f"(8h × £{eco.hourly_wage_rate:.2f})"),
            ("Employer NI",   per_ni,      c.STATUS_WARN,
             f"(13.8% on earnings above £{eco.ni_secondary_daily:.2f})"),
            ("Pension",       per_pension, c.TEXT_SECONDARY,
             f"({eco.pension_rate * 100:.1f}%)"),
            ("PPE / uniform", per_ppe,     c.TEXT_SECONDARY, ""),
        ]
        for lbl, val, vcol, note in bdown_rows:
            ui.label(lbl, x, ty)
            ui.text("mono", f"£{val:6.2f}", vcol, rx - 2, ty, align="right")
            if note:
                ui.text("caption", note, c.TEXT_DIM, rx + 4, ty + 1)
            ty += 22

        # Separator + totals
        pygame.draw.line(screen, c.BORDER_SUBTLE, (x, ty), (x + col1_w - 30, ty))
        ty += 8
        ui.text("body_b", "Per worker / day", c.TEXT_PRIMARY, x, ty)
        ui.text("mono_b", f"£{per_total:.2f}",
                c.ACCENT_AMBER, rx - 2, ty, align="right")
        ty += 24

        total_col = c.STATUS_BAD if bd["total"] > 0.5 * eco.budget else c.TEXT_PRIMARY
        ui.text("body_b", f"Total ({fleet.workers} workers)", c.TEXT_PRIMARY, x, ty)
        ui.text("mono_b", f"£{bd['total']:.0f}/day",
                total_col, rx - 2, ty, align="right")
        ty += 32

        # Full staff + vehicle daily burn
        all_daily = bd["total"] + veh_daily
        ui.label("All-in daily cost (staff + fleet)", x, ty)
        burn_col = c.STATUS_BAD if all_daily > eco.budget * 0.6 else c.TEXT_SECONDARY
        ui.text("mono_b", f"£{all_daily:.0f}/day",
                burn_col, rx - 2, ty, align="right")
        ty += 30

        # Hire / fire buttons
        hire_r = pygame.Rect(x, ty, 138, 28)
        fire_r = pygame.Rect(x + 148, ty, 126, 28)
        self._pbtn(screen, hire_r, "Hire crew  £2,500", self._hire,
                   enabled=eco.budget >= 2500, fkey="body_s",
                   accent=eco.budget >= 2500)
        self._pbtn(screen, fire_r, "Release crew", self._fire,
                   enabled=fleet.workers > 0, fkey="body_s")

        # ── RIGHT COLUMN: Vehicle fleet cards (scrollable) ───────────────────
        SB_W   = 10          # scrollbar width in pixels
        list_w = col2_w - SB_W - 4  # card width, narrowed to leave room for bar
        ry     = y + 26

        ui.section_header(col2_x, ry, "VEHICLE FLEET", col2_w)
        veh_bd = eco.vehicle_cost_breakdown(fleet.trucks)
        ui.text("caption",
                f"{len(fleet.trucks)} vehicle(s)  |  £{veh_daily:.0f}/day",
                c.TEXT_MUTED, col2_x + 136, ry + 2)
        ry += 24

        CARD_H   = 112
        CARD_GAP = 6
        list_top = ry
        list_bot = y + h - 28      # reserve 28 px for the fleet total line
        list_h   = max(1, list_bot - list_top)

        # Clip rect covers the scrollable area (cards only, not header/total)
        clip_rect = pygame.Rect(col2_x, list_top, list_w + SB_W + 4, list_h)
        self._staff_fleet_clip = clip_rect

        content_h = len(veh_bd) * (CARD_H + CARD_GAP)
        self._staff_fleet_max_scroll = max(0, content_h - list_h)
        # Clamp scroll so shrinking fleet never leaves us past the end
        self._staff_fleet_scroll = max(
            0, min(self._staff_fleet_scroll, self._staff_fleet_max_scroll))
        scroll = self._staff_fleet_scroll

        # ── Draw cards inside clip ───────────────────────────────────────────
        screen.set_clip(clip_rect)
        for i, vb in enumerate(veh_bd):
            card_top = list_top + i * (CARD_H + CARD_GAP) - scroll
            if card_top + CARD_H <= list_top:
                continue   # card fully above viewport — skip but keep iterating
            if card_top >= list_bot:
                break      # card fully below viewport — nothing more to draw

            is_broken   = vb["broken"]
            is_renaming = (self._renaming_truck_id == vb["id"])
            ui.card(col2_x, card_top, list_w, CARD_H,
                    selected=is_broken or is_renaming)

            # Left accent stripe: colour by cost type
            type_stripe = {
                "owned":  c.ACCENT_TEAL,
                "lease":  c.ACCENT_AMBER,
                "rental": c.STATUS_BAD,
            }.get(vb["cost_type"], c.TEXT_DIM)
            pygame.draw.rect(screen, type_stripe,
                             pygame.Rect(col2_x, card_top, 4, CARD_H),
                             border_radius=3)

            # Truck ID badge
            id_surf = ui.fonts.render("badge", f"#{vb['id']}", c.ACCENT_AMBER)
            screen.blit(id_surf, (col2_x + 10, card_top + 10))

            # Nickname (editable) or rename input field
            nickname = vb.get("nickname", f"L{vb['id']}")
            nm_col   = c.STATUS_BAD if is_broken else c.TEXT_PRIMARY
            if is_renaming:
                inp_r = pygame.Rect(col2_x + 34, card_top + 6, list_w - 120, 22)
                ui.inset_panel(inp_r.x, inp_r.y, inp_r.w, inp_r.h)
                ui.text("mono_b", self._rename_buffer + "|",
                        c.ACCENT_AMBER, inp_r.x + 6, inp_r.y + 4)
            else:
                ui.text("body_b", nickname, nm_col, col2_x + 34, card_top + 8)

            # Model name (muted, below nickname)
            ui.text("caption", vb["name"], c.TEXT_DIM, col2_x + 34, card_top + 26)

            # Condition / age readout (right side, under the daily cost)
            truck_for_cond = fleet.get_truck(vb["id"])
            if truck_for_cond is not None:
                cpct = fleet.condition_pct(truck_for_cond)
                clabel = fleet.condition_label(truck_for_cond)
                ccol = (c.STATUS_GOOD if cpct >= 60 else
                        c.STATUS_WARN if cpct >= 35 else c.STATUS_BAD)
                yrs = truck_for_cond.get("age_days", 0) / 112.0
                ui.text("caption", f"{clabel} · {yrs:.1f}y",
                        ccol, col2_x + list_w - 10, card_top + 26, align="right")

            # Daily cost (top-right)
            ui.text("mono_b", f"£{vb['daily']:.0f}/day",
                    c.TEXT_PRIMARY, col2_x + list_w - 10, card_top + 8,
                    align="right")

            # Cost-type + broken badges
            type_text = {"owned": "OWNED", "lease": "LEASED",
                         "rental": "RENTAL"}.get(vb["cost_type"], "?")
            type_tc = {"owned":  (c.ACCENT_TEAL,  (18, 50, 54)),
                       "lease":  (c.ACCENT_AMBER, (54, 44, 16)),
                       "rental": (c.STATUS_BAD,   (56, 20, 20))}.get(
                           vb["cost_type"], (c.TEXT_MUTED, c.BG_DEEP))
            ui.badge(col2_x + 10, card_top + 40, type_text, type_tc[0], type_tc[1])
            if is_broken:
                ui.badge(col2_x + 74, card_top + 40,
                         "BROKEN", c.STATUS_BAD, (72, 18, 18))

            # ── Crew +/- controls ───────────────────────────────────────────
            btn_y = card_top + 58
            ui.label("crew", col2_x + 10, btn_y + 4)
            minus_crew = pygame.Rect(col2_x + 46, btn_y, 22, 24)
            crew_val_r = pygame.Rect(col2_x + 70, btn_y, 28, 24)
            plus_crew  = pygame.Rect(col2_x + 100, btn_y, 22, 24)
            ui.icon_button(minus_crew, "-", enabled=vb["crew"] > 0)
            ui.inset_panel(crew_val_r.x, crew_val_r.y, crew_val_r.w, crew_val_r.h)
            ui.text("mono_b", str(vb["crew"]), c.TEXT_PRIMARY,
                    crew_val_r.centerx, crew_val_r.y + 5, align="center")
            ui.icon_button(plus_crew, "+")
            # Only register click widgets for buttons inside the visible region
            if clip_rect.colliderect(minus_crew):
                self.planner_widgets.append(
                    (minus_crew,
                     lambda tid=vb["id"]: self._adjust_truck_crew(tid, -1)))
            if clip_rect.colliderect(plus_crew):
                self.planner_widgets.append(
                    (plus_crew,
                     lambda tid=vb["id"]: self._adjust_truck_crew(tid, +1)))
            ui.text("caption", f"cap {vb['capacity']:,}",
                    c.TEXT_MUTED, col2_x + 132, btn_y + 6)

            # ── Rename / OK+Cancel  and  Scrap ──────────────────────────────
            scrap_r = pygame.Rect(col2_x + list_w - 64, btn_y, 56, 24)
            if is_renaming:
                ok_r = pygame.Rect(col2_x + list_w - 128, btn_y, 56, 24)
                self._pbtn_in_clip(screen, ok_r, "OK",
                                   lambda: self._commit_rename(),
                                   clip_rect, fkey="body_s", accent=True)
                self._pbtn_in_clip(screen, scrap_r, "Cancel",
                                   lambda: self._cancel_rename(),
                                   clip_rect, fkey="body_s")
            else:
                rename_r = pygame.Rect(col2_x + list_w - 128, btn_y, 56, 24)
                self._pbtn_in_clip(screen, rename_r, "Rename",
                                   lambda tid=vb["id"], nn=nickname:
                                       self._start_rename(tid, nn),
                                   clip_rect, fkey="body_s")
                self._pbtn_in_clip(screen, scrap_r, "Scrap",
                                   lambda tid=vb["id"]: self._scrap_truck(tid),
                                   clip_rect, fkey="body_s")

            # ── Route-pinning row ────────────────────────────────────────────
            truck_obj = fleet.get_truck(vb["id"])
            pref      = truck_obj.get("preferred_area", -1) if truck_obj else -1
            if pref >= 0:
                area_obj  = self.game.city.get_area(pref)
                route_lbl = area_obj.name if area_obj else f"Round {pref}"
            else:
                route_lbl = "Auto"
            ui.label("Route", col2_x + 10, card_top + 86)
            route_btn_r = pygame.Rect(col2_x + 52, card_top + 84,
                                      list_w - 62, 22)
            self._pbtn_in_clip(screen, route_btn_r, route_lbl,
                               lambda tid=vb["id"]: self._cycle_truck_area(tid),
                               clip_rect, fkey="body_s", accent=(pref >= 0))

        screen.set_clip(None)

        if not fleet.trucks:
            ui.text("body_s", "No vehicles in fleet.",
                    c.TEXT_DIM, col2_x, list_top + 8)

        # ── Scrollbar (drawn outside clip, always visible) ───────────────────
        sb_x  = col2_x + list_w + 4
        track = pygame.Rect(sb_x, list_top, SB_W, list_h)
        pygame.draw.rect(screen, c.BG_DEEP, track, border_radius=SB_W // 2)
        pygame.draw.rect(screen, c.BORDER_SUBTLE, track, 1,
                         border_radius=SB_W // 2)
        if content_h > list_h:
            thumb_ratio = list_h / max(1, content_h)
            thumb_h     = max(24, int(list_h * thumb_ratio))
            max_s       = max(1, self._staff_fleet_max_scroll)
            thumb_y     = list_top + int(
                scroll / max_s * max(0, list_h - thumb_h))
            thumb = pygame.Rect(sb_x + 1, thumb_y, SB_W - 2, thumb_h)
            pygame.draw.rect(screen, c.ACCENT_TEAL, thumb,
                             border_radius=(SB_W - 2) // 2)

        # ── Fleet daily total: pinned below the scroll region ────────────────
        total_y = y + h - 20
        pygame.draw.line(screen, c.BORDER_SUBTLE,
                         (col2_x, total_y - 6), (col2_x + col2_w, total_y - 6))
        all_veh = sum(v["daily"] for v in veh_bd)
        ui.label("Fleet daily total", col2_x, total_y)
        ui.text("mono_b", f"£{all_veh:.0f}/day",
                c.TEXT_PRIMARY, col2_x + col2_w, total_y, align="right")

    def _tab_finance(self, screen, x, y, w, h):
        ui = self.ui
        c = ui.c
        eco = self.game.economy
        snap = eco.ledger_snapshot()
        ui.text("body_s", "Yesterday's profit & loss. Adjust council tax to balance books against satisfaction.", c.TEXT_MUTED, x, y)
        ty = y + 26
        lx = x
        rx = x + 320
        for key, label in eco.LEDGER_LABELS:
            val = snap.get(key, 0.0)
            is_rev = key in eco.REVENUE_KEYS
            ui.label(label, lx, ty)
            sign = "+" if is_rev else ""
            val_color = c.STATUS_GOOD if is_rev else c.TEXT_SECONDARY
            ui.text("mono", f"{sign}£{abs(val):,.0f}", val_color, rx, ty, align="right")
            ty += 22
        ui.h_line(lx, ty + 2, rx - lx)
        ty += 10
        net = snap.get("net", 0.0)
        ui.text("body_b", "Net / day", c.TEXT_PRIMARY, lx, ty)
        net_color = c.STATUS_GOOD if net >= 0 else c.STATUS_BAD
        ui.text("mono_b", f"{'+' if net >= 0 else ''}£{abs(net):,.0f}", net_color, rx, ty, align="right")
        ty += 32
        ty2 = self._stepper(screen, lx, ty, "Council tax (£/resident/day)", f"{eco.council_tax_rate:.2f}",
                           (lambda: self._adjust_tax(-0.10)), (lambda: self._adjust_tax(0.10)))
        tax_pressure = eco.council_tax_pressure()
        if tax_pressure > 0:
            ui.text("caption",
                    f"+{tax_pressure*100:.0f}% above baseline: satisfaction ceiling down "
                    f"{min(45.0, tax_pressure*80.0):.0f} pts. Residents notice.",
                    c.STATUS_WARN, lx, ty2)
            ty = ty2 + 40  # Account for multi-line text wrapping
        else:
            ui.text("caption", "At or below the baseline rate: no satisfaction penalty.",
                    c.TEXT_DIM, lx, ty2)
            ty = ty2 + 20
        
        ty = self._stepper(screen, lx, ty, "Business rates (£/commercial/day)", f"£{eco.business_rates:.2f}",
                      (lambda: self._adjust_business_rates(-0.10)), (lambda: self._adjust_business_rates(0.10)))
        biz_pressure = eco.business_rate_pressure()
        if biz_pressure > 0:
            lost_pct = (1.0 - eco.business_rate_elasticity()) * 100.0
            ui.text("caption",
                    f"+{biz_pressure*100:.0f}% above baseline: ~{lost_pct:.0f}% of that revenue "
                    f"lost as marginal firms close or relocate.",
                    c.STATUS_WARN, lx, ty)
            ty += 40  # Account for multi-line text wrapping
        else:
            ui.text("caption", "At or below baseline rate: the high street stays put.",
                    c.TEXT_DIM, lx, ty)
            ty += 20

        gx = x + 360
        gw = w - 360
        ui.text("h3", "Net trend (14 days)", c.TEXT_PRIMARY, gx, y + 26)
        hist = eco.history[-14:]
        if hist:
            nets = [eco._ledger_net(d) for d in hist]
            peak = max(1.0, max(abs(n) for n in nets))
            base_y = y + 160
            bw = max(8, (gw - (len(nets) - 1) * 4) // max(1, len(nets)))
            bxx = gx
            for n in nets:
                bh_px = int((abs(n) / peak) * 60)
                if n >= 0:
                    rect = pygame.Rect(bxx, base_y - bh_px, bw, bh_px)
                    pygame.draw.rect(screen, c.STATUS_GOOD, rect, border_radius=3)
                    shine = pygame.Rect(bxx, base_y - bh_px, bw, bh_px // 2)
                    s_surf = pygame.Surface((shine.w, shine.h), pygame.SRCALPHA)
                    s_surf.fill((255, 255, 255, 30))
                    screen.blit(s_surf, shine)
                else:
                    rect = pygame.Rect(bxx, base_y, bw, bh_px)
                    pygame.draw.rect(screen, c.STATUS_BAD, rect, border_radius=3)
                bxx += bw + 4
            ui.h_line(gx, base_y, gw - 20)
            ui.text("caption", "zero", c.TEXT_DIM, gx, base_y + 4)
        else:
            ui.text("body_s", "Trend builds after a few days.", c.TEXT_DIM, gx, y + 60)
        ui.label("Budget", gx, y + 200)
        ui.text("display", f"£{int(eco.budget):,}", c.TEXT_PRIMARY, gx, y + 218)

        # (Developer options have moved to the Debug Tools window, Ctrl+Shift+D)
        ry = y + 278 + 30

        # ── Diesel market readout ────────────────────────────────────────────
        ry += 4
        ui.section_header(gx, ry, "DIESEL MARKET", gw)
        ry += 22
        _idx = getattr(eco, "fuel_index", 1.0)
        _tr  = getattr(eco, "fuel_index_trend", 0.0)
        _arrow = "rising" if _tr > 0.002 else "falling" if _tr < -0.002 else "steady"
        _dcol = (c.STATUS_BAD if _idx >= 1.15 else
                 c.STATUS_GOOD if _idx <= 0.92 else c.TEXT_SECONDARY)
        ui.label("Pump price (£/litre)", gx, ry)
        ui.text("mono_b", f"£{eco.fuel_price():.2f}", _dcol, gx + gw, ry, align="right")
        ry += 20
        ui.label("Market", gx, ry)
        ui.text("body_s", f"{eco.fuel_index_label()} — {_arrow}", _dcol, gx + gw, ry, align="right")
        ry += 20
        ui.text("caption",
                "Diesel RCV running costs track this. Electric eRCVs are immune.",
                c.TEXT_DIM, gx, ry)
        ry += 30

        # ── Debt & statutory obligations ─────────────────────────────────────
        ui.section_header(gx, ry, "DEBT & STATUTORY", gw)
        ry += 22
        if not eco.loan_cleared():
            ui.label("Startup loan outstanding", gx, ry)
            ui.text("mono_b", f"£{int(eco.loan_balance()):,}", c.ACCENT_CORAL,
                    gx + gw, ry, align="right")
            ry += 20
            ui.label("Daily repayment", gx, ry)
            ui.text("mono", f"£{eco.loan_daily_payment():.0f}/day", c.TEXT_SECONDARY,
                    gx + gw, ry, align="right")
            ry += 26
            can_pay = eco.can_pay_off_loan()
            pay_label = (f"Pay off loan now (£{int(eco.loan_balance()):,})" if can_pay
                         else f"Pay off loan (need £{int(eco.loan_balance()):,})")
            pay_rect = pygame.Rect(gx, ry, gw, 28)
            self._pbtn(screen, pay_rect, pay_label, self._pay_off_loan,
                       enabled=can_pay, accent=can_pay)
            ry += 36
        else:
            ui.label("Startup loan", gx, ry)
            ui.text("body_s", "Cleared", c.STATUS_GOOD, gx + gw, ry, align="right")
            ry += 20

        ui.label("Landfill tax escalator", gx, ry)
        _lt = eco.landfill_tax_pct_increase()
        ui.text("mono", f"+{_lt:.0f}% vs yr 1",
                c.STATUS_WARN if _lt > 0 else c.TEXT_DIM, gx + gw, ry, align="right")
        ry += 20

        _div = eco.current_diversion_pct()
        _tgt = eco.diversion_target * 100.0
        ui.label("Recycling diversion (yr)", gx, ry)
        if _div is None:
            ui.text("body_s", "no data yet", c.TEXT_DIM, gx + gw, ry, align="right")
        else:
            _dcol2 = c.STATUS_GOOD if _div >= _tgt else c.STATUS_BAD
            ui.text("mono", f"{_div:.0f}% / {_tgt:.0f}%", _dcol2, gx + gw, ry, align="right")
        ry += 18
        ui.text("caption",
                f"Miss the {_tgt:.0f}% statutory target at year-end for a DEFRA fine.",
                c.TEXT_DIM, gx, ry)

        # ── Achievements ─────────────────────────────────────────────────────
        if eco.achievements:
            ry += 28
            ui.section_header(gx, ry, "ACHIEVEMENTS", gw)
            ry += 22
            for ach in eco.achievements.values():
                short_name = ach["name"].replace("Achievement Unlocked: ", "")
                ui.text("body_s", f"{short_name} — Day {ach['day']}", c.ACCENT_SAGE, gx, ry)
                ry += 18

    # ── Financial charts ──────────────────────────────────────────────────
    def _tab_charts(self, screen, x, y, w, h):
        ui = self.ui
        c = ui.c
        eco = self.game.economy

        ui.text("body_s", "Trend of the council's daily finances over time.",
                c.TEXT_MUTED, x, y)
        ty = y + 24

        ui.section_header(x, ty, "BUDGET TREND", w)
        ty += 22
        hist = list(eco.budget_history)
        if not hist or hist[-1] != eco.budget:
            hist = hist + [eco.budget]
        chart_h = 160
        self._line_chart(screen, x, ty, w, chart_h, hist, c.ACCENT_TEAL, prefix="£")
        ty += chart_h + 22

        ui.section_header(x, ty, "INCOME / EXPENDITURE — YESTERDAY", w)
        ty += 22
        snap = eco.ledger_snapshot()
        rows = [(label, snap.get(key, 0.0), key in eco.REVENUE_KEYS)
                for key, label in eco.LEDGER_LABELS
                if abs(snap.get(key, 0.0)) > 0.5]
        rows.sort(key=lambda r: -abs(r[1]))
        max_rows = max(1, (y + h - ty - 56) // 20)
        ty = self._finance_breakdown(screen, x, ty, w, rows[:max_rows])
        if len(rows) > max_rows:
            ui.text("caption", f"+{len(rows) - max_rows} smaller line item(s) not shown",
                    c.TEXT_DIM, x, ty)
            ty += 18

        ui.h_line(x, ty + 4, w)
        ty += 16
        net = snap.get("net", 0.0)
        ui.text("body_b", "Net / day", c.TEXT_PRIMARY, x, ty)
        net_color = c.STATUS_GOOD if net >= 0 else c.STATUS_BAD
        ui.text("mono_b", f"{'+' if net >= 0 else ''}£{abs(net):,.0f}",
                net_color, x + w, ty, align="right")

    def _line_chart(self, screen, x, y, w, h, values, color, prefix=""):
        """A small axis + gridline line graph for a series of daily values."""
        ui = self.ui
        c = ui.c
        ui.inset_panel(x, y, w, h)
        pad = 10
        plot = pygame.Rect(x + pad, y + pad, w - 2 * pad, h - 2 * pad - 16)

        if len(values) < 2:
            ui.text("body_s", "Need a few more days of data…", c.TEXT_DIM,
                    plot.centerx, plot.centery, align="center")
            return

        lo, hi = min(values), max(values)
        if hi == lo:
            hi = lo + 1.0
        span = hi - lo

        for i in range(5):
            gy = plot.y + plot.h * i // 4
            pygame.draw.line(screen, c.BORDER_SUBTLE, (plot.x, gy), (plot.right, gy), 1)
            v = hi - span * i / 4.0
            ui.text("caption", f"{prefix}{v:,.0f}", c.TEXT_DIM, plot.x + 2, gy - 12)

        if lo < 0 < hi:
            zy = plot.y + plot.h - (0 - lo) / span * plot.h
            pygame.draw.line(screen, c.TEXT_DIM, (plot.x, zy), (plot.right, zy), 1)

        n = len(values)
        step = plot.w / max(1, n - 1)
        pts = [(plot.x + i * step,
                plot.y + plot.h - (v - lo) / span * plot.h) for i, v in enumerate(values)]
        pygame.draw.lines(screen, color, False, pts, 2)
        for px, py in pts:
            pygame.draw.circle(screen, color, (int(px), int(py)), 3)

        ui.text("mono_b", f"{prefix}{values[-1]:,.0f}", color,
                plot.right, plot.y - 2, align="right")

        eco = self.game.economy
        first_day = max(1, eco.day - len(values))
        ui.text("caption", f"Day {first_day}", c.TEXT_DIM, plot.x, plot.bottom + 2)
        ui.text("caption", f"Day {eco.day}", c.TEXT_DIM, plot.right, plot.bottom + 2, align="right")

    def _finance_breakdown(self, screen, x, y, w, rows):
        """rows: [(label, value, is_revenue), ...]. Draws a horizontal-bar
        breakdown and returns the y position after the last row."""
        ui = self.ui
        c = ui.c
        if not rows:
            ui.text("body_s", "No transactions recorded yet.", c.TEXT_DIM, x, y)
            return y + 20
        peak = max(abs(v) for _, v, _ in rows) or 1.0
        bar_x = x + 200
        bar_w = max(20, w - 200 - 90)
        ty = y
        for label, val, is_rev in rows:
            ui.text("body_s", label, c.TEXT_SECONDARY, x, ty + 2)
            bw = int(bar_w * min(1.0, abs(val) / peak))
            color = c.STATUS_GOOD if is_rev else c.STATUS_BAD
            pygame.draw.rect(screen, c.BG_DEEP, (bar_x, ty, bar_w, 14), border_radius=4)
            if bw > 0:
                pygame.draw.rect(screen, color, (bar_x, ty, bw, 14), border_radius=4)
            sign = "+" if is_rev else "-"
            ui.text("mono", f"{sign}£{abs(val):,.0f}", color, x + w, ty, align="right")
            ty += 20
        return ty

    def _tab_data(self, screen, x, y, w, h):
        ui = self.ui
        c = ui.c
        ui.text("body_s", "Save / load the whole borough (full game state)", c.TEXT_MUTED, x, y)
        sy = y + 32
        sv = pygame.Rect(x, sy, 240, 40)
        ld = pygame.Rect(sv.right + 16, sy, 240, 40)
        self._pbtn(screen, sv, "Save game  (F5)", self._save_game, accent=True)
        self._pbtn(screen, ld, "Load game  (F9)", self._load_game)
        y = sy + 60
        ui.text("body_s", "Export the borough plan to a spreadsheet (.ods or .xml)", c.TEXT_MUTED, x, y)
        ty = y + 32
        exp = pygame.Rect(x, ty, 240, 40)
        imp = pygame.Rect(exp.right + 16, ty, 240, 40)
        self._pbtn(screen, exp, "Export plan (.ods/.xml)", self._export_xml, accent=True)
        self._pbtn(screen, imp, "Import plan (.ods/.xml)", self._import_xml)
        ty += 56
        lines = [
            "Editable sheets (round-trip on import):",
            "  - Collection Rounds  (day + weekly/fortnightly)",
            "  - Waste Streams      (on/off, frequency, gate fee, credit)",
            "  - Finance            (council tax / business rates / wage)",
            "  - Routes & Staff     (service threshold, crew target)",
            "  - Fleet              (set crew, pin round, Scrap? = Yes)",
            "  - Place Orders       (set Quantity to order from Catalogue)",
            "  - Config             (day length, event chance, win target)",
            "",
            "Catalogue and Procurement Orders are read-only reference.",
            "On import only safe levers apply: money is never edited directly,",
            "and crew/vehicles are only bought within the available budget.",
            "A summary of each import is written to the Summary sheet.",
        ]
        for ln in lines:
            color = c.TEXT_MUTED if ln.strip() else c.TEXT_DIM
            ui.text("body_s", ln, color, x, ty)
            ty += 20

    # ── Debug Tools window (Ctrl+Shift+D) ───────────────────────────────────
    def _tab_debug(self, screen, x, y, w, h):
        ui = self.ui
        c = ui.c
        sub_tabs = [("tools", "Weather & Events"), ("editor", "Edit City")]
        tx = x
        for key, label in sub_tabs:
            bw = ui.fonts.size("body_b", label)[0] + 28
            rect = pygame.Rect(tx, y, bw, 30)
            self._pbtn(screen, rect, label, (lambda k=key: self._set_debug_tab(k)),
                      accent=(self._debug_tab == key))
            tx += bw + 8
        ty = y + 42
        # "Editor" tab transitions to bottom-bar mode and closes this window,
        # so only "tools" content is ever shown here.
        self._debug_tools_tab(screen, x, ty, w, h - 42)

    def _set_debug_tab(self, key):
        if key == "editor":
            # Clicking the Editor tab closes the debug window and switches to
            # the non-obscuring bottom editor bar instead.
            self._editor_mode = True
            self.editor_tool = None
            self._debug_status = ""
            self.close_window("debug")
        else:
            self._debug_tab = key

    # ── Bottom editor bar helpers ────────────────────────────────────────────
    def _in_editor_bar(self, pos):
        """True if `pos` is inside the editor bar region."""
        if not self._editor_mode:
            return False
        w, h = self._screen_size
        return pos[0] >= HUD_W and pos[1] >= h - EDITOR_BAR_H

    def _exit_editor_mode(self):
        self._editor_mode = False
        self.editor_tool = None
        self._debug_status = ""

    def _editor_bar_resolve(self, pos):
        for rect, fn in self._editor_bar_widgets:
            if rect.collidepoint(pos):
                fn()
                return

    def _draw_editor_bar(self, screen, w, h):
        """A slim two-row toolbar fixed to the bottom of the screen.  All
        map-editor brush and build-style buttons live here so the city is
        fully visible while painting tiles."""
        ui = self.ui
        c = ui.c
        tool = self.editor_tool
        mouse = pygame.mouse.get_pos()

        bar_x = HUD_W
        bar_y = h - EDITOR_BAR_H
        bar_w = w - HUD_W

        # Background + amber top border to signal editor mode
        pygame.draw.rect(screen, c.BG_PANEL, pygame.Rect(bar_x, bar_y, bar_w, EDITOR_BAR_H))
        pygame.draw.line(screen, c.ACCENT_AMBER, (bar_x, bar_y), (w, bar_y), 2)

        self._editor_bar_widgets = []
        GAP   = 4
        BTN_H = 26

        r1_y = bar_y + 4         # row 1: action tools
        r2_y = bar_y + 34        # row 2: build-style chips

        # ── Row 1: EDITOR label + action tools + status + exit ───────────────
        bx = bar_x + 10

        lsurf = ui.fonts.render("body_s", "EDITOR", c.ACCENT_AMBER)
        screen.blit(lsurf, (bx, r1_y + (BTN_H - lsurf.get_height()) // 2))
        bx += lsurf.get_width() + 8
        pygame.draw.line(screen, c.BORDER_SUBTLE, (bx, bar_y + 6), (bx, bar_y + 32))
        bx += 10

        action_tools = [
            ("Bulldoze",
             self._set_tool_bulldoze,
             bool(tool and tool.get("mode") == "bulldoze")),
            ("Green sq.",
             self._set_tool_green,
             bool(tool and tool.get("mode") == "green")),
            ("→Res",
             lambda: self._set_tool_clear_green("residential"),
             bool(tool and tool.get("mode") == "clear_green"
                  and tool.get("kind") == "residential")),
            ("→Com",
             lambda: self._set_tool_clear_green("commercial"),
             bool(tool and tool.get("mode") == "clear_green"
                  and tool.get("kind") == "commercial")),
        ]
        for label, fn, active in action_tools:
            tw = ui.fonts.size("body_b", label)[0] + 16
            rect = pygame.Rect(bx, r1_y, tw, BTN_H)
            ui.button(rect, label, accent=active, hovered=rect.collidepoint(mouse))
            self._editor_bar_widgets.append((rect, fn))
            bx += tw + GAP

        # Status text
        bx += 6
        if tool:
            status_text = f"Tool: {self._editor_tool_label(tool)}"
            status_col  = c.ACCENT_TEAL
        else:
            status_text = "Select a brush then click the map  ·  ESC to exit"
            status_col  = c.TEXT_DIM
        ssurf = ui.fonts.render("body_s", status_text, status_col)
        screen.blit(ssurf, (bx, r1_y + (BTN_H - ssurf.get_height()) // 2))

        # Exit button (right-aligned)
        ex_label = "✕ Exit Editor"
        etw = ui.fonts.size("body_b", ex_label)[0] + 16
        exit_rect = pygame.Rect(w - etw - 8, r1_y, etw, BTN_H)
        ui.button(exit_rect, ex_label, hovered=exit_rect.collidepoint(mouse))
        self._editor_bar_widgets.append((exit_rect, self._exit_editor_mode))

        # ── Row 2: build-style chips ─────────────────────────────────────────
        SHORT = {
            "terrace":   "Terrace",  "semi":      "Semi",
            "detached":  "Detach",   "bungalow":  "Bungalow",
            "flats":     "Flats",    "tower":     "Tower",
            "shop":      "Shop",     "office":    "Office",
            "warehouse": "Whouse",   "highrise":  "Hi-rise",
        }
        bx = bar_x + 10

        rl = ui.fonts.render("body_s", "Res:", c.TEXT_MUTED)
        screen.blit(rl, (bx, r2_y + (BTN_H - rl.get_height()) // 2))
        bx += rl.get_width() + 4

        for sid in RES_STYLE_WEIGHTS.keys():
            lbl  = SHORT.get(sid, sid)
            tw   = ui.fonts.size("body_b", lbl)[0] + 14
            rect = pygame.Rect(bx, r2_y, tw, BTN_H)
            active = bool(tool and tool.get("mode") == "build"
                          and tool.get("style") == sid)
            ui.button(rect, lbl, accent=active, hovered=rect.collidepoint(mouse),
                      color=(50, 140, 70))
            self._editor_bar_widgets.append((rect, lambda s=sid: self._set_tool_build(s)))
            bx += tw + GAP

        # Divider between Res and Com
        bx += 4
        pygame.draw.line(screen, c.BORDER_SUBTLE,
                         (bx, bar_y + 35), (bx, bar_y + EDITOR_BAR_H - 5))
        bx += 8

        cl = ui.fonts.render("body_s", "Com:", c.TEXT_MUTED)
        screen.blit(cl, (bx, r2_y + (BTN_H - cl.get_height()) // 2))
        bx += cl.get_width() + 4

        for sid in COM_STYLE_WEIGHTS.keys():
            lbl  = SHORT.get(sid, sid)
            tw   = ui.fonts.size("body_b", lbl)[0] + 14
            rect = pygame.Rect(bx, r2_y, tw, BTN_H)
            active = bool(tool and tool.get("mode") == "build"
                          and tool.get("style") == sid)
            ui.button(rect, lbl, accent=active, hovered=rect.collidepoint(mouse),
                      color=(50, 110, 170))
            self._editor_bar_widgets.append((rect, lambda s=sid: self._set_tool_build(s)))
            bx += tw + GAP

    def _debug_tools_tab(self, screen, x, y, w, h):
        ui = self.ui
        c = ui.c
        economy = self.game.economy

        ui.section_header(x, y, "Force weather", w)
        ty = y + 26
        weathers = [("dry", "Dry"), ("rain", "Rain"), ("snow", "Snow"), ("overcast", "Overcast")]
        bx = x
        for wid, label in weathers:
            rect = pygame.Rect(bx, ty, 110, 32)
            self._pbtn(screen, rect, label, (lambda w_id=wid: self._force_weather(w_id)),
                      accent=(economy.weather == wid))
            bx += 120
        ty += 46
        ui.text("body_s",
                f"Current: {economy.weather}  |  Season: {economy.season_name()}  |  Day {economy.day}",
                c.TEXT_MUTED, x, ty)
        ty += 30
        ui.h_line(x, ty, w)
        ty += 16

        ui.section_header(x, ty, "Force event", w)
        ty += 26
        cols = 4
        col_w = (w - 16 * (cols - 1)) // cols
        for i, ev in enumerate(economy.events):
            col = i % cols
            row = i // cols
            rect = pygame.Rect(x + col * (col_w + 16), ty + row * 38, col_w, 32)
            self._pbtn(screen, rect, ev["name"], (lambda eid=ev["id"]: self._force_event(eid)),
                      enabled=(economy.active_event is None), fkey="body_s")
        rows_used = (len(economy.events) + cols - 1) // cols
        ty += rows_used * 38 + 12
        ui.h_line(x, ty, w)
        ty += 16

        clear_rect = pygame.Rect(x, ty, 170, 32)
        self._pbtn(screen, clear_rect, "Clear active event", self._clear_event,
                  enabled=(economy.active_event is not None))
        if economy.active_event:
            ui.text("body_s", f"Active: {economy.active_event['name']}", c.TEXT_MUTED,
                    clear_rect.right + 16, ty + 8)
        ty += 46
        ui.h_line(x, ty, w)
        ty += 16

        ui.section_header(x, ty, "Developer options", w)
        ty += 26
        ty = self._stepper(screen, x, ty, "Event chance",
                           f"{int(economy.event_chance * 100)}%",
                           lambda: self._adjust_event_chance(-0.05),
                           lambda: self._adjust_event_chance(0.05),
                           label_w=150, val_w=54)
        ty = self._stepper(screen, x, ty, "Win streak (days)",
                           str(economy.win_streak_target),
                           lambda: self._adjust_win_target(-1),
                           lambda: self._adjust_win_target(1),
                           label_w=150, val_w=54)
        ty = self._stepper(screen, x, ty, "Day length (sec)",
                           str(economy.day_duration),
                           lambda: self._adjust_day_duration(-5),
                           lambda: self._adjust_day_duration(5),
                           label_w=150, val_w=54)
        ui.text("caption", "Lower day length = faster game pace.", c.TEXT_DIM, x, ty)
        ty += 24

        if self._debug_status:
            ui.text("body_s", self._debug_status, c.ACCENT_TEAL, x, ty)

    def _force_weather(self, weather_id):
        economy = self.game.economy
        economy.weather = weather_id
        economy._weather_timer = 2 if weather_id in ("rain", "snow") else 0
        self._debug_status = f"Weather forced to {weather_id}."

    def _force_event(self, event_id):
        if self.game.economy.force_event(event_id, fleet=self.game.fleet):
            self._debug_status = f"Forced event: {event_id}"
        else:
            self._debug_status = f"Could not force event: {event_id}"

    def _clear_event(self):
        economy = self.game.economy
        if economy.active_event:
            economy._clear_event_effects(economy.active_event, self.game.city, self.game.fleet)
            economy.active_event = None
            self._debug_status = "Active event cleared."

    # ── Editor sub-tab: place/delete buildings, green squares, districts ───
    def _debug_editor_tab(self, screen, x, y, w, h):
        ui = self.ui
        c = ui.c
        city = self.game.city
        col1_w = int(w * 0.46)
        col2_x = x + col1_w + 20
        col2_w = w - col1_w - 20
        tool = self.editor_tool

        # ---- Brush tools (left column) ----
        ty = y
        ui.section_header(x, ty, "Brush", col1_w)
        ty += 24
        bull = pygame.Rect(x, ty, col1_w, 30)
        self._pbtn(screen, bull, "Bulldoze (-> green)", self._set_tool_bulldoze,
                  accent=bool(tool and tool.get("mode") == "bulldoze"))
        ty += 36
        green = pygame.Rect(x, ty, col1_w, 30)
        self._pbtn(screen, green, "Place green square", self._set_tool_green,
                  accent=bool(tool and tool.get("mode") == "green"))
        ty += 36
        half = (col1_w - 8) // 2
        cgr = pygame.Rect(x, ty, half, 30)
        cgc = pygame.Rect(x + half + 8, ty, half, 30)
        self._pbtn(screen, cgr, "Remove green -> Res",
                  (lambda: self._set_tool_clear_green("residential")), fkey="body_s",
                  accent=bool(tool and tool.get("mode") == "clear_green" and tool.get("kind") == "residential"))
        self._pbtn(screen, cgc, "Remove green -> Com",
                  (lambda: self._set_tool_clear_green("commercial")), fkey="body_s",
                  accent=bool(tool and tool.get("mode") == "clear_green" and tool.get("kind") == "commercial"))
        ty += 40
        ui.h_line(x, ty, col1_w)
        ty += 12

        ui.text("body_s", "Residential", c.TEXT_MUTED, x, ty)
        ty += 20
        ty = self._editor_style_grid(screen, x, ty, col1_w, list(RES_STYLE_WEIGHTS.keys()))
        ty += 8
        ui.text("body_s", "Commercial", c.TEXT_MUTED, x, ty)
        ty += 20
        ty = self._editor_style_grid(screen, x, ty, col1_w, list(COM_STYLE_WEIGHTS.keys()))
        ty += 12

        status = self._editor_tool_label(tool) if tool else "None"
        ui.text("body_s", f"Tool: {status}", c.ACCENT_TEAL, x, ty)
        ty += 18
        ui.text("caption", "Click a tile on the map to apply. Esc clears the tool.",
                c.TEXT_DIM, x, ty)

        # ---- District tools (right column) ----
        ty2 = y
        ui.section_header(col2_x, ty2, "Districts", col2_w)
        ty2 += 24
        ui.text("body_s", "Select a round, then apply:", c.TEXT_MUTED, col2_x, ty2)
        ty2 += 22
        cols = 2
        chip_w = (col2_w - 8) // cols
        for i, area in enumerate(city.areas):
            col = i % cols
            row = i // cols
            rect = pygame.Rect(col2_x + col * (chip_w + 8), ty2 + row * 30, chip_w, 26)
            self._pbtn(screen, rect, area.name, (lambda aid=area.id: self._select_editor_area(aid)),
                      accent=(self.editor_selected_area == area.id), fkey="body_s")
        rows = (len(city.areas) + cols - 1) // cols
        ty2 += rows * 30 + 10
        ui.h_line(col2_x, ty2, col2_w)
        ty2 += 12

        sel = self.editor_selected_area
        sel_name = next((a.name for a in city.areas if a.id == sel), None)
        ui.text("body_s", f"Selected: {sel_name or '(none)'}", c.TEXT_PRIMARY, col2_x, ty2)
        ty2 += 26

        actions = [
            ("Make residential", lambda: self._district_action("residential")),
            ("Make commercial",  lambda: self._district_action("commercial")),
            ("Clear to green",   lambda: self._district_action("green")),
            ("Regenerate round", lambda: self._district_action("regen")),
        ]
        for label, fn in actions:
            rect = pygame.Rect(col2_x, ty2, col2_w, 30)
            self._pbtn(screen, rect, label, fn, enabled=(sel is not None))
            ty2 += 36
        ty2 += 8
        if self._debug_status:
            ui.text("body_s", self._debug_status, c.ACCENT_TEAL, col2_x, ty2)

    def _editor_style_grid(self, screen, x, y, w, style_ids, cols=2):
        gap = 6
        cw = (w - gap * (cols - 1)) // cols
        ch = 28
        tool = self.editor_tool
        for i, sid in enumerate(style_ids):
            col = i % cols
            row = i // cols
            rect = pygame.Rect(x + col * (cw + gap), y + row * (ch + gap), cw, ch)
            label = STYLE_LABELS.get(sid, sid)
            active = bool(tool and tool.get("mode") == "build" and tool.get("style") == sid)
            self._pbtn(screen, rect, label, (lambda s=sid: self._set_tool_build(s)),
                      accent=active, fkey="body_s")
        rows = (len(style_ids) + cols - 1) // cols
        return y + rows * (ch + gap)

    def _set_tool_bulldoze(self):
        self.editor_tool = {"mode": "bulldoze"}

    def _set_tool_green(self):
        self.editor_tool = {"mode": "green"}

    def _set_tool_clear_green(self, kind):
        self.editor_tool = {"mode": "clear_green", "kind": kind}

    def _set_tool_build(self, style):
        self.editor_tool = {"mode": "build", "style": style}

    def _editor_tool_label(self, tool):
        mode = tool.get("mode")
        if mode == "bulldoze":
            return "Bulldoze"
        if mode == "green":
            return "Place green square"
        if mode == "clear_green":
            return f"Remove green -> {tool.get('kind')}"
        if mode == "build":
            return f"Build: {STYLE_LABELS.get(tool.get('style'), tool.get('style'))}"
        return "None"

    def _select_editor_area(self, area_id):
        self.editor_selected_area = area_id

    def _district_action(self, action):
        city = self.game.city
        aid = self.editor_selected_area
        if aid is None:
            return
        if action == "residential":
            n = city.set_area_type(aid, "residential")
            self._debug_status = f"Set {n} tiles to residential."
        elif action == "commercial":
            n = city.set_area_type(aid, "commercial")
            self._debug_status = f"Set {n} tiles to commercial."
        elif action == "green":
            n = city.set_area_green(aid)
            self._debug_status = f"Cleared {n} tiles to green."
        elif action == "regen":
            n = city.regenerate_area(aid)
            self._debug_status = f"Regenerated {n} buildings."

    # ── Per-vehicle inspect window (click a lorry on the map) ──────────────
    def _truck_window_content(self, screen, x, y, w, h, truck_id):
        ui = self.ui
        c = ui.c
        game = self.game
        fleet = game.fleet
        truck = fleet.get_truck(truck_id)
        if truck is None:
            ui.text("body_s", "This vehicle has been scrapped.", c.TEXT_DIM, x, y)
            return

        clip = pygame.Rect(x - 4, y - 4, w + 8, h + 8)
        old_clip = screen.get_clip()
        screen.set_clip(clip)

        # ── Vehicle preview ───────────────────────────────────────────────
        prev_r = pygame.Rect(x, y, w, 84)
        ui.inset_panel(prev_r.x, prev_r.y, prev_r.w, prev_r.h)
        screen.set_clip(prev_r)
        game.renderer.draw_truck(prev_r.centerx, prev_r.centery + 12, truck, 2.3)
        screen.set_clip(clip)
        ty = prev_r.bottom + 10

        # ── Nickname (editable) + model ─────────────────────────────────────
        is_renaming = (self._renaming_truck_id == truck_id)
        nickname = truck.get("nickname", f"L{truck['id']}")
        if is_renaming:
            inp_r = pygame.Rect(x, ty, w - 88, 26)
            ui.inset_panel(inp_r.x, inp_r.y, inp_r.w, inp_r.h)
            ui.text("mono_b", self._rename_buffer + "|", c.ACCENT_AMBER,
                    inp_r.x + 8, inp_r.y + 5)
            ok_r = pygame.Rect(x + w - 84, ty, 40, 26)
            cancel_r = pygame.Rect(x + w - 40, ty, 40, 26)
            self._pbtn(screen, ok_r, "OK", self._commit_rename, fkey="body_s", accent=True)
            self._pbtn(screen, cancel_r, "X", self._cancel_rename, fkey="body_s")
        else:
            ui.text("h3", nickname, c.TEXT_PRIMARY, x, ty)
            rename_r = pygame.Rect(x + w - 84, ty - 2, 84, 24)
            self._pbtn(screen, rename_r, "Rename",
                      lambda tid=truck_id, nn=nickname: self._start_rename(tid, nn),
                      fkey="body_s")
        ty += 26
        ui.text("body_s", truck.get("model_name", "?"), c.TEXT_MUTED, x, ty)
        ty += 22

        # ── Status pill + ownership ─────────────────────────────────────────
        broken = truck.get("broken", False)
        state = truck.get("state", "depot")
        if broken:
            status_text = f"Repair bay — {truck.get('repair_days', 0)}d left"
            status_type = "bad"
        else:
            status_labels = {
                "depot":     "At depot",
                "to_stop":   "En route to round",
                "servicing": "Collecting bins",
                "to_depot":  "Returning to depot",
            }
            status_text = status_labels.get(state, state.replace("_", " ").title())
            status_type = "good" if state in ("to_stop", "servicing") else "neutral"
        ui.status_pill(x, ty, status_text, status_type)
        own_lbl = ("Leased" if truck.get("leased") else
                   "Rental" if truck.get("tier_id") == "rental" else "Owned")
        ui.text("caption", own_lbl, c.TEXT_DIM, x + w, ty + 3, align="right")
        ty += 28
        ui.h_line(x, ty, w)
        ty += 12

        # ── Current job ───────────────────────────────────────────────────
        ui.section_header(x, ty, "CURRENT JOB", w)
        ty += 20
        area_id = truck.get("area_id", -1)
        pref = truck.get("preferred_area", -1)
        if area_id >= 0:
            area_obj = game.city.get_area(area_id)
            route_name = area_obj.name if area_obj else f"Round {area_id}"
        else:
            route_name = "Unassigned"
        ui.label("Route / round", x, ty)
        ui.text("body_b", route_name, c.ACCENT_TEAL, x + w, ty, align="right")
        ty += 20
        ui.label("Assignment", x, ty)
        pin_lbl = "Auto-assigned" if pref < 0 else "Pinned"
        pin_r = pygame.Rect(x + w - 110, ty - 3, 110, 22)
        self._pbtn(screen, pin_r, pin_lbl,
                  lambda tid=truck_id: self._cycle_truck_area(tid),
                  fkey="caption", accent=(pref >= 0))
        ty += 24
        queued = len(truck.get("bin_queue", [])) + len(truck.get("service_bins", []))
        ui.label("Bins on this stop", x, ty)
        ui.text("mono", str(queued), c.TEXT_SECONDARY, x + w, ty, align="right")
        ty += 24

        # ── Crew complement ───────────────────────────────────────────────
        ui.section_header(x, ty, "CREW COMPLEMENT", w)
        ty += 20
        crew = truck.get("crew", 0)
        crew_cap = truck.get("crew_cap", 0)
        out = len(truck.get("out_workers", []))
        onboard = max(0, crew - out)
        ui.label("Assigned / capacity", x, ty)
        ui.text("mono", f"{crew} / {crew_cap}", c.TEXT_SECONDARY, x + w, ty, align="right")
        ty += 18
        ui.label("On board / out collecting", x, ty)
        ui.text("mono", f"{onboard} / {out}", c.TEXT_SECONDARY, x + w, ty, align="right")
        ty += 22
        minus_r = pygame.Rect(x, ty, 32, 26)
        val_r = pygame.Rect(x + 38, ty, 36, 26)
        plus_r = pygame.Rect(x + 80, ty, 32, 26)
        idle = fleet.workers - sum(t.get("crew", 0) for t in fleet.trucks)
        ui.icon_button(minus_r, "-", enabled=crew > 0)
        ui.inset_panel(val_r.x, val_r.y, val_r.w, val_r.h)
        ui.text("mono_b", str(crew), c.TEXT_PRIMARY, val_r.centerx, val_r.y + 5, align="center")
        ui.icon_button(plus_r, "+", enabled=(crew < crew_cap and idle > 0))
        self.planner_widgets.append((minus_r, lambda tid=truck_id: self._adjust_truck_crew(tid, -1)))
        self.planner_widgets.append((plus_r, lambda tid=truck_id: self._adjust_truck_crew(tid, +1)))
        ty += 34

        # ── Load ─────────────────────────────────────────────────────────
        ui.section_header(x, ty, "LOAD", w)
        ty += 20
        load = truck.get("load", 0.0)
        cap = truck.get("capacity", 1.0) or 1.0
        bar_w = w - 52
        ui.progress_bar(x, ty, bar_w, 14, load, cap, show_text=False)
        pct = load / cap * 100.0
        ui.text("mono", f"{pct:.0f}%", c.TEXT_SECONDARY, x + w, ty - 1, align="right")
        ty += 18
        ui.text("caption", f"{load:,.0f} / {cap:,.0f} fill units", c.TEXT_DIM, x, ty)
        ty += 24

        # ── Shift & condition ──────────────────────────────────────────────
        ui.section_header(x, ty, "SHIFT & CONDITION", w)
        ty += 20
        ui.label("Working hours", x, ty)
        ui.text("body_s", "06:00 – 14:00 (8h shift)", c.TEXT_SECONDARY, x + w, ty, align="right")
        ty += 18
        cpct = fleet.condition_pct(truck)
        clabel = fleet.condition_label(truck)
        ccol = (c.STATUS_GOOD if cpct >= 60 else
                c.STATUS_WARN if cpct >= 35 else c.STATUS_BAD)
        ui.label("Condition", x, ty)
        ui.text("body_b", f"{clabel} ({cpct:.0f}%)", ccol, x + w, ty, align="right")
        ty += 18
        yrs = truck.get("age_days", 0) / 112.0
        ui.label("Age in service", x, ty)
        ui.text("mono", f"{yrs:.1f} yrs", c.TEXT_SECONDARY, x + w, ty, align="right")
        ty += 18
        daily_cost = (truck.get("lease_weekly", 0) / 7.0 if truck.get("leased")
                      else truck.get("running_cost", 0))
        ui.label("Daily cost", x, ty)
        ui.text("mono_b", f"£{daily_cost:.0f}/day", c.TEXT_PRIMARY, x + w, ty, align="right")
        ty += 30

        # ── Actions ──────────────────────────────────────────────────────
        center_r = pygame.Rect(x, ty, w // 2 - 6, 30)
        scrap_r = pygame.Rect(x + w // 2 + 6, ty, w // 2 - 6, 30)
        self._pbtn(screen, center_r, "Centre view",
                  lambda tid=truck_id: self._center_on_truck(tid), accent=True)
        self._pbtn(screen, scrap_r, "Scrap vehicle",
                  lambda tid=truck_id: self._scrap_truck(tid))

        screen.set_clip(old_clip)

    def _cycle_round_freq(self, area_id):
        self.game.city.cycle_area_frequency(area_id)

    def _adjust_threshold(self, delta):
        f = self.game.fleet
        f.service_threshold = max(5, min(80, f.service_threshold + delta))

    def _toggle_stream(self, sid):
        self.game.waste.toggle(sid)

    def _cycle_stream_freq(self, sid):
        self.game.waste.cycle_frequency(sid)

    def _buy_vehicle(self, model_id, tier_id, lease):
        eco = self.game.economy
        ok, cost, msg = self.game.fleet.order_vehicle(model_id, tier_id=tier_id, leased=lease)
        if not ok:
            self.game.set_toast(msg)
            return
        if eco.budget < cost:
            self.game.fleet.orders.pop()
            self._flash_insufficient()
            self.game.set_toast("Insufficient funds for that order.")
            return
        eco.budget -= cost
        self.game.set_toast(msg)

    def _hire(self):
        eco = self.game.economy
        if eco.budget >= 2500:
            eco.budget -= 2500
            self.game.fleet.hire_worker()
            self.game.set_toast("Hired one crew member.")
        else:
            self._flash_insufficient()

    def _fire(self):
        if self.game.fleet.fire_worker():
            self.game.set_toast("Released one crew member.")

    def _adjust_wage(self, delta):
        self.game.economy.adjust_wage(delta)

    def _adjust_pension(self, delta):
        self.game.economy.adjust_pension(delta)

    def _adjust_ppe(self, delta):
        self.game.economy.adjust_ppe(delta)

    def _scrap_truck(self, truck_id):
        if self.game.fleet.scrap_truck(truck_id):
            self.game.set_toast(f"Vehicle #{truck_id} removed from fleet.")
        else:
            self.game.set_toast("Cannot remove that vehicle.")

    def _adjust_tax(self, delta):
        eco = self.game.economy
        eco.council_tax_rate = max(0.0, round(eco.council_tax_rate + delta, 2))

    def _adjust_business_rates(self, delta):
        eco = self.game.economy
        eco.business_rates = round(max(0.0, min(20.0, eco.business_rates + delta)), 2)

    def _pay_off_loan(self):
        ok, msg = self.game.economy.pay_off_loan()
        self.game.set_toast(msg)

    def _adjust_event_chance(self, delta):
        eco = self.game.economy
        eco.event_chance = round(max(0.0, min(1.0, eco.event_chance + delta)), 2)

    def _adjust_win_target(self, delta):
        eco = self.game.economy
        eco.win_streak_target = max(1, min(30, eco.win_streak_target + delta))

    def _adjust_day_duration(self, delta):
        eco = self.game.economy
        eco.day_duration = max(10, min(300, eco.day_duration + delta))

    def _cycle_truck_area(self, truck_id):
        """Cycle a lorry's pinned round: Auto → Round 0 → … → last → Auto."""
        fleet     = self.game.fleet
        city      = self.game.city
        truck     = fleet.get_truck(truck_id)
        if not truck:
            return
        num_areas = len(city.areas)
        cur       = truck.get("preferred_area", -1)
        if cur < 0:
            nxt = 0
        elif cur >= num_areas - 1:
            nxt = -1          # wrap back to Auto
        else:
            nxt = cur + 1
        fleet.assign_truck_area(truck_id, nxt)
        if nxt < 0:
            self.game.set_toast(f"Lorry #{truck_id}: automatic round selection.")
        else:
            area = city.get_area(nxt)
            name = area.name if area else f"Round {nxt}"
            self.game.set_toast(f"Lorry #{truck_id} pinned to {name}.")

    def _adjust_truck_crew(self, truck_id, delta):
        """Move a crew member to/from a specific lorry within the existing pool."""
        fleet = self.game.fleet
        truck = fleet.get_truck(truck_id)
        if not truck:
            return
        cap  = int(truck.get("crew_cap", 4))
        cur  = int(truck.get("crew", 0))
        idle = fleet.workers - sum(t.get("crew", 0) for t in fleet.trucks)
        if delta > 0 and (cur >= cap or idle <= 0):
            return          # truck full or no idle crew
        if delta < 0 and cur <= 0:
            return          # already empty
        dist = {t["id"]: t.get("crew", 0) for t in fleet.trucks}
        dist[truck_id] = cur + delta
        fleet.set_fleet_crew(dist)

    def _export_xml(self):
        ok, msg = xmlio.prompt_export(self.game)
        self.game.set_toast(msg)

    def _import_xml(self):
        ok, msg = xmlio.prompt_import(self.game)
        self.game.set_toast(msg)

    def _save_game(self):
        ok, msg = savegame.save_game(self.game)
        self.game.set_toast(msg)

    def _load_game(self):
        ok, msg = savegame.load_game(self.game)
        self.game.set_toast(msg)

    def _draw_wrapped_text(self, screen, text, x, y, max_width, font, colour):
        words = text.split(" ")
        lines = []
        current = ""
        for word in words:
            test = current + " " + word if current else word
            if font.size(test)[0] <= max_width:
                current = test
            else:
                if current:
                    lines.append(current)
                current = word
        if current:
            lines.append(current)
        for line in lines:
            surf = font.render(line, True, colour)
            screen.blit(surf, (x, y))
            y += font.get_height() + 2

    def update(self, dt):
        if self._event_visible:
            self._event_timer_active += dt
            if self._event_timer_active >= self._event_duration:
                self._event_visible = False
                self._event_timer_active = 0
        if self._insufficient_funds_flash:
            self._flash_timer += dt
            if self._flash_timer >= self._flash_duration:
                self._insufficient_funds_flash = False
                self._flash_timer = 0
        self._tooltip_timer += dt
        mouse = pygame.mouse.get_pos()
        if self._tooltip_pos and math.hypot(mouse[0] - self._tooltip_pos[0], mouse[1] - self._tooltip_pos[1]) > 10:
            self._tooltip_text = None
            self._tooltip_timer = 0