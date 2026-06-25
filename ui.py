import pygame
import math
from city import AREA_COLS, AREA_ROWS
import xmlio
from procurement import VEHICLE_CATALOGUE

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
    def button(self, rect, label, enabled=True, accent=False, hovered=False, pressed=False, icon=None):
        if not enabled:
            fill = self.c.BG_PANEL
            border = self.c.BORDER_SUBTLE
            text_color = self.c.TEXT_DIM
        elif pressed:
            fill = self.c.BG_ACTIVE
            border = self.c.ACCENT_AMBER
            text_color = self.c.ACCENT_AMBER
        elif accent:
            fill = self.c.ACCENT_AMBER_DIM if hovered else (220, 165, 70)
            border = self.c.ACCENT_AMBER
            text_color = self.c.BG_DEEP
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
        self._setup_buttons()

    def _setup_buttons(self):
        x = 14
        inner = HUD_W - 28
        half = (inner - 8) // 2
        self.buttons = [
            {"rect": pygame.Rect(x,            0, half,  34), "label": "Pause",              "action": "pause",     "row_offset": 0},
            {"rect": pygame.Rect(x + half + 8, 0, half,  34), "label": "1x",                 "action": "speed",     "row_offset": 0},
            {"rect": pygame.Rect(x,            0, inner, 34), "label": "Procure Vehicle",     "action": "fleet_tab", "row_offset": 42},
            {"rect": pygame.Rect(x,            0, inner, 34), "label": "Hire Crew", "cost": 2500, "action": "worker",   "row_offset": 80},
            {"rect": pygame.Rect(x,            0, inner, 34), "label": "MANAGE (TAB)",  "action": "planner",   "row_offset": 118},
        ]

    def handle_click(self, pos):
        for btn in self.buttons:
            if btn["rect"].collidepoint(pos):
                self._do_action(btn["action"])
                return True
        return False

    def handle_planner_click(self, pos):
        if self._planner_close and self._planner_close.collidepoint(pos):
            self.game.planner_open = False
            return True
        for rect, fn in self.planner_widgets:
            if rect.collidepoint(pos):
                fn()
                return True
        for rect, area_id, day in self.planner_cells:
            if rect.collidepoint(pos):
                self.game.city.set_area_day(area_id, day)
                return True
        return True

    def _do_action(self, action):
        eco = self.game.economy
        if action == "pause":
            self.game.running = not self.game.running
        elif action == "speed":
            self.game.speed = {1: 2, 2: 5}.get(self.game.speed, 1)
        elif action == "fleet_tab":
            self.game.open_planner_tab("fleet")
        elif action == "worker":
            if eco.budget >= 2500:
                eco.budget -= 2500
                self.game.fleet.hire_worker()
            else:
                self._flash_insufficient()
        elif action == "planner":
            self.game.planner_open = not self.game.planner_open

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

    def _draw_button(self, screen, btn, ui):
        rect = btn["rect"]
        mouse = pygame.mouse.get_pos()
        hovered = rect.collidepoint(mouse)
        affordable = self.game.economy.budget >= btn["cost"] if "cost" in btn else True
        label = btn["label"]
        if "cost" in btn:
            label = f"{btn['label']}  £{btn['cost']:,}"
        if btn["action"] == "pause":
            label = "Pause" if self.game.running else "Resume"
        elif btn["action"] == "speed":
            label = f"{self.game.speed}x Speed"
        elif btn["action"] == "planner":
            label = "Close" if self.game.planner_open else "MANAGE (TAB)"
        enabled = affordable
        accent = btn["action"] in ("fleet_tab", "worker")
        ui.button(rect, label, enabled=enabled, accent=accent, hovered=hovered)

    def draw(self, screen):
        self.ui = UIPrimitives(screen, self.fonts)
        w, h = screen.get_size()
        self._draw_hud(screen, w, h)
        self._draw_crisis_banner(screen, w, h)
        self._draw_win_banner(screen, w, h)
        self._draw_inspect_panel(screen, w, h)
        if self.game.planner_open:
            self._draw_planner(screen, w, h)
        self._draw_toast(screen, w, h)
        # Procurement bar drawn before event banner so events always render on top.
        self._draw_procurement_bar(screen, w)
        self._draw_event_banner(screen, w)

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


    def _draw_procurement_bar(self, screen, w):
        """Show a notification bar at the top for pending vehicle orders."""
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

        # If a critical event banner is visible (strike / breakdown), push the
        # procurement bar below it so neither obscures the other.
        active = eco.active_event
        CRITICAL_EFFECTS = ("crewStrike", "truckBreakdown")
        critical_showing = (
            (self._event_visible and self._current_event and
             self._current_event.get("effect") in CRITICAL_EFFECTS)
            or (active and active.get("effect") in CRITICAL_EFFECTS)
        )
        by = 120 if critical_showing else 10

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
        #ui.text("display_sub", "Waste Borough", c.ACCENT_AMBER, x, y)
        y += 32
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
        if not eco.has_won:
            ui.card(x, y, HUD_W - 28, 44, selected=False)
            ui.label("PERFECT SERVICE STREAK", x + 12, y + 6)
            streak = eco.perfect_days_streak
            wp = eco.win_progress()
            ui.text("body_b", f"{streak}/7", c.STATUS_GOOD, right - 12, y + 6, align="right")
            ui.progress_bar(x + 12, y + 28, HUD_W - 52, 4, streak, 7, color=c.STATUS_GOOD, show_text=False)
            y += 52
        else:
            ui.card(x, y, HUD_W - 28, 44, selected=True)
            ui.label("STATUS", x + 12, y + 6)
            ui.text("h2", "CHAMPION", c.ACCENT_AMBER, right - 12, y + 6, align="right")
            ui.progress_bar(x + 12, y + 28, HUD_W - 52, 4, 7, 7, color=c.ACCENT_AMBER, show_text=False)
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
        ui.section_header(x, y, "CONTROLS", w=HUD_W - 28)
        y += 24
        for btn in self.buttons:
            btn["rect"].y = y + btn["row_offset"]
            self._draw_button(screen, btn, ui)
        y = self.buttons[-1]["rect"].bottom + 16
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
        sub = ui.fonts.render("h2", f"7 consecutive days with zero complaints! Day {eco.win_day}.", ui.c.TEXT_PRIMARY)
        screen.blit(sub, sub.get_rect(center=(w // 2, by + 75)))
        hint = ui.fonts.render("body_s", "Keep it up to maintain your perfect record!", ui.c.TEXT_MUTED)
        screen.blit(hint, hint.get_rect(center=(w // 2, by + 100)))

    def _draw_inspect_panel(self, screen, w, h):
        if not self.game.selected_tile or self.game.planner_open:
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
        ui.text("body_xs", "Open planner (Tab) to reschedule.", c.TEXT_DIM, rx, py + ph - 24)

    def _draw_planner(self, screen, w, h):
        ui = self.ui
        c = ui.c
        scrim = pygame.Surface((w, h), pygame.SRCALPHA)
        scrim.fill((14, 16, 22, 240))
        screen.blit(scrim, (0, 0))
        self.planner_widgets = []
        self.planner_cells = []
        tab = getattr(self.game, "planner_tab", "rounds")
        pw, ph = 800, 580
        px = (w - pw) // 2
        py = (h - ph) // 2
        pygame.draw.rect(screen, (0, 0, 0, 100), pygame.Rect(px + 4, py + 4, pw, ph), border_radius=10)
        ui.card(px, py, pw, ph, selected=False)
        ui.text("h1", "Borough Management", c.TEXT_PRIMARY, px + 24, py + 16)
        self._planner_close = pygame.Rect(px + pw - 44, py + 14, 32, 32)
        ui.icon_button(self._planner_close, "X", hovered=False)
        tab_y = py + 56
        tab_x = px + 24
        for key, label in PLANNER_TABS:
            tw = ui.fonts.size("body_b", label)[0] + 32
            rect = pygame.Rect(tab_x, tab_y, tw, 32)
            active = (key == tab)
            if active:
                pygame.draw.rect(screen, c.BG_ACTIVE, rect, border_radius=6)
                pygame.draw.rect(screen, c.ACCENT_AMBER, rect, 2, border_radius=6)
                ui.text("body_b", label, c.ACCENT_AMBER, rect.centerx, tab_y + 8, align="center")
                pygame.draw.rect(screen, c.ACCENT_AMBER, pygame.Rect(rect.x, rect.bottom - 3, rect.w, 3), border_radius=2)
            else:
                mouse = pygame.mouse.get_pos()
                hover = rect.collidepoint(mouse)
                bg = c.BG_HOVER if hover else c.BG_CARD
                pygame.draw.rect(screen, bg, rect, border_radius=6)
                pygame.draw.rect(screen, c.BORDER_SUBTLE, rect, 1, border_radius=6)
                ui.text("body_b", label, c.TEXT_MUTED if not hover else c.TEXT_SECONDARY, rect.centerx, tab_y + 8, align="center")
            self.planner_widgets.append((rect, (lambda k=key: self.game.open_planner_tab(k))))
            tab_x += tw + 8
        bx = px + 24
        by = tab_y + 44
        bw = pw - 48
        bh = (py + ph - 20) - by
        if tab == "rounds":
            self._tab_rounds(screen, bx, by, bw, bh)
        elif tab == "waste":
            self._tab_waste(screen, bx, by, bw, bh)
        elif tab == "fleet":
            self._tab_fleet(screen, bx, by, bw, bh)
        elif tab == "staff":
            self._tab_staff(screen, bx, by, bw, bh)
        elif tab == "finance":
            self._tab_finance(screen, bx, by, bw, bh)
        elif tab == "data":
            self._tab_data(screen, bx, by, bw, bh)

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

        # ── RIGHT COLUMN: Vehicle fleet cards ────────────────────────────────
        ry = y + 26
        ui.section_header(col2_x, ry, "VEHICLE FLEET", col2_w)
        ui.text("caption",
                f"{len(fleet.trucks)} vehicle(s)  |  £{veh_daily:.0f}/day",
                c.TEXT_MUTED, col2_x + 136, ry + 2)
        ry += 24

        CARD_H = 96
        veh_bd = eco.vehicle_cost_breakdown(fleet.trucks)
        shown  = 0
        for vb in veh_bd:
            if ry + CARD_H > y + h - 4:
                remaining = len(veh_bd) - shown
                ui.text("caption",
                        f"... and {remaining} more. Scrap to reveal.",
                        c.TEXT_DIM, col2_x, ry)
                break

            is_broken  = vb["broken"]
            is_renaming = (self._renaming_truck_id == vb["id"])
            ui.card(col2_x, ry, col2_w, CARD_H, selected=is_broken or is_renaming)

            # Left accent stripe: colour = cost type
            type_stripe = {
                "owned":  c.ACCENT_TEAL,
                "lease":  c.ACCENT_AMBER,
                "rental": c.STATUS_BAD,
            }.get(vb["cost_type"], c.TEXT_DIM)
            pygame.draw.rect(screen, type_stripe,
                             pygame.Rect(col2_x, ry, 4, CARD_H),
                             border_radius=3)

            # Truck ID badge
            id_surf = ui.fonts.render("badge", f"#{vb['id']}", c.ACCENT_AMBER)
            screen.blit(id_surf, (col2_x + 10, ry + 10))

            # Nickname (editable) or rename input field
            nickname = vb.get("nickname", f"L{vb['id']}")
            nm_col   = c.STATUS_BAD if is_broken else c.TEXT_PRIMARY
            if is_renaming:
                inp_r = pygame.Rect(col2_x + 34, ry + 6, col2_w - 120, 22)
                ui.inset_panel(inp_r.x, inp_r.y, inp_r.w, inp_r.h)
                ui.text("mono_b", self._rename_buffer + "|",
                        c.ACCENT_AMBER, inp_r.x + 6, inp_r.y + 4)
            else:
                ui.text("body_b", nickname, nm_col, col2_x + 34, ry + 8)

            # Model name (muted, below nickname)
            ui.text("caption", vb["name"], c.TEXT_DIM, col2_x + 34, ry + 26)

            # Daily cost (top-right)
            ui.text("mono_b", f"£{vb['daily']:.0f}/day",
                    c.TEXT_PRIMARY, col2_x + col2_w - 10, ry + 8, align="right")

            # Cost-type + broken badges
            type_text = {"owned": "OWNED", "lease": "LEASED",
                         "rental": "RENTAL"}.get(vb["cost_type"], "?")
            type_tc = {"owned":  (c.ACCENT_TEAL,  (18, 50, 54)),
                       "lease":  (c.ACCENT_AMBER, (54, 44, 16)),
                       "rental": (c.STATUS_BAD,   (56, 20, 20))}.get(
                           vb["cost_type"], (c.TEXT_MUTED, c.BG_DEEP))
            ui.badge(col2_x + 10, ry + 40, type_text, type_tc[0], type_tc[1])
            if is_broken:
                ui.badge(col2_x + 74, ry + 40, "BROKEN", c.STATUS_BAD, (72, 18, 18))

            # Crew / capacity
            ui.text("caption",
                    f"crew {vb['crew']}  |  cap {vb['capacity']:,}",
                    c.TEXT_MUTED, col2_x + 10, ry + 62)

            # Rename / OK+Cancel  and  Scrap buttons (bottom-right)
            btn_y  = ry + 64
            scrap_r  = pygame.Rect(col2_x + col2_w - 64, btn_y, 56, 24)
            if is_renaming:
                ok_r     = pygame.Rect(col2_x + col2_w - 128, btn_y, 56, 24)
                self._pbtn(screen, ok_r, "OK",
                           lambda: self._commit_rename(),
                           fkey="body_s", accent=True)
                self._pbtn(screen, scrap_r, "Cancel",
                           lambda: self._cancel_rename(),
                           fkey="body_s")
            else:
                rename_r = pygame.Rect(col2_x + col2_w - 128, btn_y, 56, 24)
                self._pbtn(screen, rename_r, "Rename",
                           lambda tid=vb["id"], nn=nickname: self._start_rename(tid, nn),
                           fkey="body_s")
                self._pbtn(screen, scrap_r, "Scrap",
                           lambda tid=vb["id"]: self._scrap_truck(tid),
                           fkey="body_s")

            ry   += CARD_H + 6
            shown += 1

        if not fleet.trucks:
            ui.text("body_s", "No vehicles in fleet.", c.TEXT_DIM, col2_x, ry)

        # Fleet cost totals at bottom of right column (if room)
        if ry < y + h - 28:
            pygame.draw.line(screen, c.BORDER_SUBTLE,
                             (col2_x, ry), (col2_x + col2_w, ry))
            ry += 8
            all_veh = sum(v["daily"] for v in veh_bd)
            ui.label("Fleet daily total", col2_x, ry)
            ui.text("mono_b", f"£{all_veh:.0f}/day",
                    c.TEXT_PRIMARY, col2_x + col2_w, ry, align="right")

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
                           (lambda: self._adjust_tax(-0.10)), (lambda: self._adjust_tax(0.10)), label_w=240)
        ui.text("caption", "Higher tax raises revenue but dents satisfaction.", c.TEXT_DIM, lx, ty2)
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

    def _tab_data(self, screen, x, y, w, h):
        ui = self.ui
        c = ui.c 
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

    def _export_xml(self):
        ok, msg = xmlio.prompt_export(self.game)
        self.game.set_toast(msg)

    def _import_xml(self):
        ok, msg = xmlio.prompt_import(self.game)
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
