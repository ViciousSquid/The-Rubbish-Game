import pygame
from city import AREA_COLS, AREA_ROWS
import xmlio
from procurement import VEHICLE_CATALOGUE

DAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
HUD_W = 252

PLANNER_TABS = [
    ("rounds",  "Rounds"),
    ("waste",   "Waste"),
    ("fleet",   "Fleet"),
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
    "residential": (150, 220, 150),
    "commercial": (150, 190, 220),
    "mixed": (220, 210, 150),
}


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

        self.fonts = {
            "title": pygame.font.SysFont("segoeui", 17, bold=True),
            "header": pygame.font.SysFont("segoeui", 12, bold=True),
            "body": pygame.font.SysFont("segoeui", 13),
            "body_b": pygame.font.SysFont("segoeui", 13, bold=True),
            "small": pygame.font.SysFont("segoeui", 12),
            "tiny": pygame.font.SysFont("segoeui", 11),
            "big": pygame.font.SysFont("segoeui", 22, bold=True),
            "mono": pygame.font.SysFont("consolas", 12),
            "mono_b": pygame.font.SysFont("consolas", 12, bold=True),
            "win": pygame.font.SysFont("segoeui", 28, bold=True),
            "win_sub": pygame.font.SysFont("segoeui", 16, bold=True),
        }

        # Monochrome palette only. No hues, no transparency.
        self.c = {
            "bg": (18, 18, 18),
            "panel": (32, 32, 32),
            "panel_hi": (48, 48, 48),
            "panel_lo": (24, 24, 24),
            "border": (96, 96, 96),
            "border_lo": (64, 64, 64),
            "text": (240, 240, 240),
            "muted": (170, 170, 170),
            "dim": (120, 120, 120),
            "white": (245, 245, 245),
            "black": (16, 16, 16),
            "gold": (255, 215, 0),
            "green": (100, 220, 100),
        }

        self.buttons = []
        self.planner_cells = []      # clickable (rect, area_id, day) in planner
        self.planner_widgets = []    # clickable (rect, callback) in planner tabs
        self._planner_close = None
        self._setup_buttons()

    # ----------------------------------------------------------- button setup
    def _setup_buttons(self):
        x = 14
        inner = HUD_W - 28
        half = (inner - 8) // 2
        y = 326
        self.buttons = [
            {"rect": pygame.Rect(x, y, half, 30), "label": "Pause", "action": "pause"},
            {"rect": pygame.Rect(x + half + 8, y, half, 30), "label": "1x", "action": "speed"},
            {"rect": pygame.Rect(x, y + 38, inner, 30), "label": "Procure Vehicle", "action": "fleet_tab"},
            {"rect": pygame.Rect(x, y + 74, inner, 30), "label": "Hire Crew", "cost": 2500, "action": "worker"},
            {"rect": pygame.Rect(x, y + 110, inner, 30), "label": "Collection Planner", "action": "planner"},
        ]

    # --------------------------------------------------------------- clicking
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
        # Tab buttons and in-tab controls register here.
        for rect, fn in self.planner_widgets:
            if rect.collidepoint(pos):
                fn()
                return True
        # Day-grid cells (Rounds tab) reschedule a round.
        for rect, area_id, day in self.planner_cells:
            if rect.collidepoint(pos):
                self.game.city.set_area_day(area_id, day)
                return True
        return True   # swallow all clicks while planner is open

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

    def _flash_insufficient(self):
        self._insufficient_funds_flash = True
        self._flash_timer = 0

    # ----------------------------------------------------------- draw helpers
    def _panel(self, screen, x, y, w, h, fill=None, border=True):
        pygame.draw.rect(screen, fill or self.c["panel"], pygame.Rect(x, y, w, h))
        if border:
            pygame.draw.rect(screen, self.c["border"], pygame.Rect(x, y, w, h), 1)

    def _text(self, screen, key, s, color, x, y):
        screen.blit(self.fonts[key].render(s, True, color), (x, y))

    def _text_right(self, screen, key, s, color, right_x, y):
        surf = self.fonts[key].render(s, True, color)
        screen.blit(surf, (right_x - surf.get_width(), y))

    def _text_center(self, screen, key, s, color, cx, y):
        surf = self.fonts[key].render(s, True, color)
        screen.blit(surf, (cx - surf.get_width() // 2, y))

    # ----------------------------------------------------------------- draw
    def draw(self, screen):
        w, h = screen.get_size()
        self._draw_hud(screen, w, h)
        self._draw_event_banner(screen, w)
        self._draw_crisis_banner(screen, w, h)
        self._draw_win_banner(screen, w, h)
        self._draw_inspect_panel(screen, w, h)
        if self.game.planner_open:
            self._draw_planner(screen, w, h)
        self._draw_toast(screen, w, h)

    def _draw_toast(self, screen, w, h):
        if not getattr(self.game, "toast", "") or self.game.toast_timer <= 0:
            return
        msg = self.game.toast
        pad = 16
        surf = self.fonts["body_b"].render(msg, True, self.c["white"])
        bw = surf.get_width() + pad * 2
        bh = 34
        bx = HUD_W + (w - HUD_W - bw) // 2
        by = h - 70
        pygame.draw.rect(screen, self.c["panel_hi"], pygame.Rect(bx, by, bw, bh))
        pygame.draw.rect(screen, self.c["white"], pygame.Rect(bx, by, bw, bh), 1)
        pygame.draw.rect(screen, self.c["white"], pygame.Rect(bx, by, 4, bh))
        screen.blit(surf, (bx + pad, by + (bh - surf.get_height()) // 2))

    def _draw_hud(self, screen, w, h):
        eco = self.game.economy
        fleet = self.game.fleet
        city = self.game.city
        x = 14
        right = HUD_W - 14

        pygame.draw.rect(screen, (14, 14, 14), pygame.Rect(0, 0, HUD_W, h))
        pygame.draw.line(screen, self.c["border"], (HUD_W, 0), (HUD_W, h), 1)

        y = 12
        #self._text(screen, "title", "Waste Borough", self.c["text"], x, y)
        y += 28

        self._text(screen, "body_b", f"Day {eco.day}", self.c["text"], x, y)
        self._text(screen, "body", eco.get_day_of_week_name(), self.c["muted"], x + 64, y)
        trend = eco.budget_trend
        if trend != 0:
            sign = "+" if trend >= 0 else "-"
            self._text_right(screen, "small", f"{sign}GBP{abs(int(trend)):,}",
                             self.c["text"] if trend >= 0 else self.c["muted"], right, y + 1)
        y += 22

        bar_w = HUD_W - 28
        pygame.draw.rect(screen, (50, 50, 50), pygame.Rect(x, y, bar_w, 4))
        p = eco.get_day_progress()
        pygame.draw.rect(screen, self.c["white"], pygame.Rect(x, y, int(bar_w * p), 4))
        y += 14

        # Budget card
        crisis = eco.is_budget_crisis()
        self._panel(screen, x, y, HUD_W - 28, 44,
                    fill=self.c["panel_lo"] if crisis else self.c["panel_hi"])
        self._text(screen, "tiny", "BUDGET", self.c["muted"], x + 10, y + 6)
        self._text(screen, "big", f"GBP {int(eco.budget):,}",
                   self.c["white"] if not crisis else self.c["muted"], x + 10, y + 18)
        y += 52

        # Satisfaction card
        self._panel(screen, x, y, HUD_W - 28, 38, fill=self.c["panel"])
        self._text(screen, "tiny", "PUBLIC SATISFACTION", self.c["muted"], x + 10, y + 5)
        self._text_right(screen, "small",
                         f"{int(eco.satisfaction)}%  {eco.satisfaction_label()}",
                         self.c["text"], right - 2, y + 4)
        sb_w = HUD_W - 48
        pygame.draw.rect(screen, (50, 50, 50), pygame.Rect(x + 10, y + 24, sb_w, 6))
        pygame.draw.rect(screen, self.c["white"],
                         pygame.Rect(x + 10, y + 24, int(sb_w * eco.satisfaction / 100), 6))
        y += 48

        # Win progress (if not yet won)
        if not eco.has_won:
            self._panel(screen, x, y, HUD_W - 28, 32, fill=self.c["panel_lo"])
            self._text(screen, "tiny", "PERFECT SERVICE STREAK", self.c["muted"], x + 10, y + 4)
            streak = eco.perfect_days_streak
            wp = eco.win_progress()
            self._text_right(screen, "small", f"{streak}/7 days", self.c["green"], right - 2, y + 4)
            pygame.draw.rect(screen, (50, 50, 50), pygame.Rect(x + 10, y + 20, sb_w, 4))
            pygame.draw.rect(screen, self.c["green"],
                             pygame.Rect(x + 10, y + 20, int(sb_w * wp), 4))
            y += 38
        else:
            # Show "CHAMPION" badge
            self._panel(screen, x, y, HUD_W - 28, 32, fill=self.c["panel_lo"])
            self._text(screen, "tiny", "STATUS", self.c["muted"], x + 10, y + 4)
            self._text_right(screen, "small", "CHAMPION", self.c["gold"], right - 2, y + 4)
            pygame.draw.rect(screen, self.c["gold"], pygame.Rect(x + 10, y + 20, sb_w, 4))
            y += 38

        stats = [
            ("Population", f"{city.population:,}"),
            ("Properties", f"{city.property_count:,}"),
            ("Lorries", str(len(fleet.trucks))),
            ("Crew", str(fleet.workers)),
        ]
        for label, value in stats:
            self._text(screen, "body", label, self.c["muted"], x, y)
            self._text_right(screen, "body_b", value, self.c["text"], right, y)
            y += 20

        # Active event pill
        if eco.active_event and eco.active_event.get("duration", 0) > 0:
            self._panel(screen, x, y, HUD_W - 28, 24, fill=self.c["panel_hi"])
            txt = f"{eco.active_event['name']} - {eco.active_event['remaining_days']}d"
            self._text(screen, "small", txt, self.c["text"], x + 8, y + 4)
        y += 30

        # Buttons
        self._section_header(screen, x, 312, "SIMULATION")
        for btn in self.buttons:
            self._draw_button(screen, btn)

        # Collections summary
        cy = 326 + 110 + 40
        self._section_header(screen, x, cy, "COLLECTIONS")
        cy += 20
        due = fleet.get_total_full_bins()
        unscheduled = fleet.get_unscheduled_overflows()

        self._text(screen, "body", "Bins due today", self.c["muted"], x, cy)
        self._text_right(screen, "body_b", str(due), self.c["text"], right, cy)
        cy += 20
        self._text(screen, "body", "Overflowing", self.c["muted"], x, cy)
        self._text_right(screen, "body_b", str(unscheduled),
                         self.c["white"] if unscheduled else self.c["text"], right, cy)
        cy += 20
        self._text(screen, "body", "Complaints (today)", self.c["muted"], x, cy)
        self._text_right(screen, "body_b", str(eco.complaints_today), self.c["text"], right, cy)
        cy += 26

        help_y = h - 78
        self._section_header(screen, x, help_y, "CONTROLS")
        help_y += 20
        for line in ["WASD / drag - pan,  scroll - zoom",
                     "Tab - planner,  G - round overlay",
                     "Click a building - inspect"]:
            self._text(screen, "small", line, self.c["dim"], x, help_y)
            help_y += 16

    def _section_header(self, screen, x, y, label):
        self._text(screen, "header", label, self.c["dim"], x, y)
        pygame.draw.line(screen, self.c["border_lo"],
                         (x + self.fonts["header"].size(label)[0] + 8, y + 7),
                         (HUD_W - 14, y + 7), 1)

    def _draw_button(self, screen, btn):
        rect = btn["rect"]
        mouse = pygame.mouse.get_pos()
        hovered = rect.collidepoint(mouse)
        affordable = self.game.economy.budget >= btn["cost"] if "cost" in btn else True

        if "cost" in btn and not affordable:
            fill, border, text_col = self.c["panel_lo"], self.c["border_lo"], self.c["dim"]
        elif hovered:
            fill, border, text_col = (66, 66, 66), self.c["white"], self.c["white"]
        else:
            fill, border, text_col = self.c["panel_hi"], self.c["border"], self.c["text"]

        pygame.draw.rect(screen, fill, rect)
        pygame.draw.rect(screen, border, rect, 1)

        label = btn["label"]
        if "cost" in btn:
            label = f"{btn['label']}  GBP{btn['cost']:,}"
        if btn["action"] == "pause":
            label = "Pause" if self.game.running else "Resume"
        elif btn["action"] == "speed":
            label = f"{self.game.speed}x Speed"
        elif btn["action"] == "planner":
            label = "Close Planner" if self.game.planner_open else "Collection Planner"

        surf = self.fonts["body_b"].render(label, True, text_col)
        screen.blit(surf, surf.get_rect(center=rect.center))

    # ----------------------------------------------------------- top banners
    def _draw_event_banner(self, screen, w):
        if not self._event_visible or not self._current_event:
            return
        bw = min(520, max(360, w // 2))
        bh = 74
        bx = (w - bw) // 2
        progress = min(1.0, self._event_timer_active / 0.45)
        if self._event_timer_active > self._event_duration - 0.45:
            progress = 1.0 - min(1.0, (self._event_timer_active - (self._event_duration - 0.45)) / 0.45)
        by = int(-90 + (118 * progress))

        pygame.draw.rect(screen, self.c["panel"], pygame.Rect(bx, by, bw, bh))
        pygame.draw.rect(screen, self.c["white"], pygame.Rect(bx, by, bw, bh), 2)
        pygame.draw.rect(screen, self.c["white"], pygame.Rect(bx, by, 5, bh))

        e = self._current_event
        self._text(screen, "title", e["name"], self.c["white"], bx + 18, by + 12)
        self._text(screen, "body", e["desc"], self.c["text"], bx + 18, by + 42)

    def _draw_crisis_banner(self, screen, w, h):
        if not self._insufficient_funds_flash and not self.game.economy.is_budget_crisis():
            return
        text = "Insufficient funds" if self._insufficient_funds_flash else "Budget crisis - you are overspending"
        bw, bh = 460, 38
        bx = (w - bw) // 2
        pygame.draw.rect(screen, (60, 60, 60), pygame.Rect(bx, h - 54, bw, bh))
        pygame.draw.rect(screen, self.c["white"], pygame.Rect(bx, h - 54, bw, bh), 2)
        surf = self.fonts["body_b"].render(text, True, self.c["white"])
        screen.blit(surf, surf.get_rect(center=(w // 2, h - 35)))

    def _draw_win_banner(self, screen, w, h):
        """Draw win celebration banner when player achieves 7 perfect days."""
        eco = self.game.economy
        if not eco.has_won:
            return

        # Fade out over time
        eco.win_celebration_timer -= 0.016  # approx 60fps
        if eco.win_celebration_timer <= 0:
            return

        alpha = min(1.0, eco.win_celebration_timer / 3.0)
        if alpha <= 0:
            return

        bw = min(600, w - 100)
        bh = 120
        bx = (w - bw) // 2
        by = (h - bh) // 2 - 50

        # Gold background with fade
        bg_color = (40, 35, 20)
        pygame.draw.rect(screen, bg_color, pygame.Rect(bx, by, bw, bh))
        pygame.draw.rect(screen, self.c["gold"], pygame.Rect(bx, by, bw, bh), 3)

        # Trophy text
        title = self.fonts["win"].render("★ BOROUGH CHAMPION ★", True, self.c["gold"])
        screen.blit(title, title.get_rect(center=(w // 2, by + 35)))

        sub = self.fonts["win_sub"].render(
            f"7 consecutive days with zero complaints! Achieved on Day {eco.win_day}.",
            True, self.c["white"]
        )
        screen.blit(sub, sub.get_rect(center=(w // 2, by + 70)))

        hint = self.fonts["small"].render(
            "Keep it up to maintain your perfect record!",
            True, self.c["muted"]
        )
        screen.blit(hint, hint.get_rect(center=(w // 2, by + 95)))

    # ----------------------------------------------------------- inspect panel
    def _draw_inspect_panel(self, screen, w, h):
        if not self.game.selected_tile or self.game.planner_open:
            return
        pw, ph = 256, 240
        px = w - pw - 16
        py = h - ph - 16
        self._panel(screen, px, py, pw, ph, fill=self.c["panel"])

        tile = self.game.selected_tile["tile"]
        tx, ty = self.game.selected_tile["x"], self.game.selected_tile["y"]
        rx = px + 14
        rr = px + pw - 14

        if tile.type == "road":
            self._text(screen, "header", "Road", self.c["text"], rx, py + 12)
            self._text(screen, "small", "Part of the collection network.",
                       self.c["muted"], rx, py + 40)
            return

        if tile.type == "green":
            self._text(screen, "header", "Green Space", self.c["text"], rx, py + 12)
            self._text(screen, "small", "Park or garden area.",
                       self.c["muted"], rx, py + 40)
            return

        if tile.type == "landfill":
            self._text(screen, "header", "Landfill Site", self.c["text"], rx, py + 12)
            self._text(screen, "small", "Where full lorries tip their loads.",
                       self.c["muted"], rx, py + 40)
            self._text(screen, "small", "Disposal gate fees are charged here,",
                       self.c["muted"], rx, py + 62)
            self._text(screen, "small", "driven by landfill tax on residual waste.",
                       self.c["muted"], rx, py + 80)
            return

        label = STYLE_LABELS.get(tile.building_style, tile.type.title())
        self._text(screen, "header", label, self.c["text"], rx, py + 12)
        self._text_right(screen, "tiny", f"({tx}, {ty})", self.c["dim"], rr, py + 14)

        area = self.game.city.get_area(tile.area_id)
        row = py + 38
        lh = 22

        if area:
            self._text(screen, "body", "Round", self.c["muted"], rx, row)
            self._text_right(screen, "body_b", area.name, self.c["text"], rr, row)
            row += lh
            self._text(screen, "body", "Collection day", self.c["muted"], rx, row)
            self._text_right(screen, "body_b", DAY_NAMES[area.collection_day], self.c["text"], rr, row)
            row += lh
            # Route type with color
            rt = area.route_type
            rt_label = ROUTE_TYPE_LABELS.get(rt, rt)
            rt_color = ROUTE_TYPE_COLORS.get(rt, self.c["text"])
            self._text(screen, "body", "Route type", self.c["muted"], rx, row)
            self._text_right(screen, "body_b", rt_label, rt_color, rr, row)
            row += lh + 4

        pct = int(tile.bin_fill)
        if pct < 50:
            status = "Low"
        elif pct < 75:
            status = "Filling up"
        elif pct < 90:
            status = "Nearly full"
        else:
            status = "Overflowing"
        self._text(screen, "body", "Bin fill", self.c["muted"], rx, row)
        self._text_right(screen, "body_b", f"{pct}%  {status}", self.c["text"], rr, row)
        row += lh
        pygame.draw.rect(screen, (50, 50, 50), pygame.Rect(rx, row, pw - 28, 6))
        pygame.draw.rect(screen, self.c["white"], pygame.Rect(rx, row, int((pw - 28) * pct / 100), 6))
        row += 16

        if tile.population:
            self._text(screen, "body", "Residents", self.c["muted"], rx, row)
            self._text_right(screen, "body", str(tile.population), self.c["text"], rr, row)
            row += lh

        self._text(screen, "small", "Open the planner (Tab) to reschedule rounds.",
                   self.c["dim"], rx, py + ph - 24)

    # ----------------------------------------------------------- planner
    def _draw_planner(self, screen, w, h):
        """Tabbed management console. Dispatches to the active tab body."""
        # Solid scrim over the world (no alpha, stays readable).
        pygame.draw.rect(screen, (10, 10, 10), pygame.Rect(0, 0, w, h))

        # Reset per-frame clickable registries; tab bodies repopulate them.
        self.planner_widgets = []
        self.planner_cells = []

        tab = getattr(self.game, "planner_tab", "rounds")

        # ------- panel geometry (fixed, generous; tabs lay out inside) -------
        pw, ph = 760, 540
        px = (w - pw) // 2
        py = (h - ph) // 2
        self._panel(screen, px, py, pw, ph, fill=self.c["panel"])

        # ------- title + close -------
        self._text(screen, "title", "Borough Management", self.c["text"], px + 20, py + 14)
        self._planner_close = pygame.Rect(px + pw - 36, py + 12, 24, 24)
        pygame.draw.rect(screen, self.c["panel_hi"], self._planner_close)
        pygame.draw.rect(screen, self.c["border"], self._planner_close, 1)
        self._text_center(screen, "body_b", "x", self.c["text"],
                          self._planner_close.centerx, self._planner_close.y + 3)

        # ------- tab bar -------
        tab_y = py + 44
        tab_x = px + 20
        for key, label in PLANNER_TABS:
            tw = self.fonts["body_b"].size(label)[0] + 28
            rect = pygame.Rect(tab_x, tab_y, tw, 28)
            active = (key == tab)
            fill = self.c["panel_hi"] if active else self.c["panel_lo"]
            pygame.draw.rect(screen, fill, rect)
            pygame.draw.rect(screen, self.c["white"] if active else self.c["border_lo"], rect, 1)
            self._text_center(screen, "body_b", label,
                              self.c["white"] if active else self.c["muted"],
                              rect.centerx, tab_y + 6)
            if active:
                pygame.draw.rect(screen, self.c["white"],
                                 pygame.Rect(rect.x, rect.bottom - 2, rect.w, 2))
            self.planner_widgets.append(
                (rect, (lambda k=key: self.game.open_planner_tab(k))))
            tab_x += tw + 6
        pygame.draw.line(screen, self.c["border_lo"],
                         (px + 20, tab_y + 30), (px + pw - 20, tab_y + 30), 1)

        # ------- body region -------
        bx = px + 20
        by = tab_y + 42
        bw = pw - 40
        bh = (py + ph - 16) - by

        if tab == "rounds":
            self._tab_rounds(screen, bx, by, bw, bh)
        elif tab == "waste":
            self._tab_waste(screen, bx, by, bw, bh)
        elif tab == "fleet":
            self._tab_fleet(screen, bx, by, bw, bh)
        elif tab == "finance":
            self._tab_finance(screen, bx, by, bw, bh)
        elif tab == "data":
            self._tab_data(screen, bx, by, bw, bh)

    # ----------------------------------------------------------- planner: util
    def _pbtn(self, screen, rect, label, fn, enabled=True, fkey="body_b",
              fill=None, accent=False):
        """Draw a clickable button and register it (if enabled)."""
        mouse = pygame.mouse.get_pos()
        hovered = rect.collidepoint(mouse) and enabled
        if not enabled:
            bg, bd, tc = self.c["panel_lo"], self.c["border_lo"], self.c["dim"]
        elif hovered:
            bg, bd, tc = (66, 66, 66), self.c["white"], self.c["white"]
        elif accent:
            bg, bd, tc = self.c["panel_hi"], self.c["white"], self.c["white"]
        else:
            bg, bd, tc = (fill or self.c["panel_hi"]), self.c["border"], self.c["text"]
        pygame.draw.rect(screen, bg, rect)
        pygame.draw.rect(screen, bd, rect, 1)
        surf = self.fonts[fkey].render(label, True, tc)
        screen.blit(surf, surf.get_rect(center=rect.center))
        if enabled:
            self.planner_widgets.append((rect, fn))

    def _stepper(self, screen, x, y, label, value_str, dec_fn, inc_fn,
                 label_w=190, val_w=92):
        """A '- value +' control with a label. Returns next y."""
        self._text(screen, "body", label, self.c["muted"], x, y + 4)
        minus = pygame.Rect(x + label_w, y, 26, 24)
        valr = pygame.Rect(minus.right + 4, y, val_w, 24)
        plus = pygame.Rect(valr.right + 4, y, 26, 24)
        self._pbtn(screen, minus, "-", dec_fn, fkey="body_b")
        pygame.draw.rect(screen, self.c["panel_lo"], valr)
        pygame.draw.rect(screen, self.c["border_lo"], valr, 1)
        self._text_center(screen, "mono_b", value_str, self.c["text"],
                          valr.centerx, y + 5)
        self._pbtn(screen, plus, "+", inc_fn, fkey="body_b")
        return y + 32

    # ----------------------------------------------------------- planner: ROUNDS
    def _tab_rounds(self, screen, x, y, w, h):
        eco = self.game.economy
        city = self.game.city
        fleet = self.game.fleet
        today = eco.get_day_of_week()
        week = eco.week_index

        self._text(screen, "small",
                   "Click a weekday to move a round. FREQ toggles weekly / fortnightly.",
                   self.c["muted"], x, y)
        ty = y + 22

        name_w = 150
        day_w = 34
        freq_w = 84
        type_w = 70
        left_cols = name_w + 7 * day_w + freq_w + type_w
        rest = {"props": 54, "due": 56, "status": 96}

        # header
        self._text(screen, "tiny", "ROUND", self.c["dim"], x, ty)
        cxp = x + name_w
        for i, d in enumerate(DAY_NAMES):
            cell = pygame.Rect(cxp + i * day_w, ty - 2, day_w, 16)
            if i == today:
                pygame.draw.rect(screen, self.c["panel_hi"], cell)
            self._text_center(screen, "tiny", d,
                              self.c["white"] if i == today else self.c["dim"],
                              cell.centerx, ty)
        fx = cxp + 7 * day_w
        self._text_center(screen, "tiny", "FREQ", self.c["dim"], fx + freq_w // 2, ty)
        tx = fx + freq_w
        self._text_center(screen, "tiny", "TYPE", self.c["dim"], tx + type_w // 2, ty)
        sx = tx + type_w
        for label, key in (("PROPS", "props"), ("LEFT", "due"), ("STATUS", "status")):
            self._text_center(screen, "tiny", label, self.c["dim"], sx + rest[key] // 2, ty)
            sx += rest[key]
        ty += 18
        pygame.draw.line(screen, self.c["border_lo"],
                         (x, ty), (x + left_cols + sum(rest.values()), ty), 1)
        ty += 4

        per_day_rounds = [0] * 7
        for area in city.areas:
            st = city.area_stats(area.id, today, fleet.service_threshold, week)
            if not st:
                continue
            per_day_rounds[area.collection_day] += 1
            rowrect = pygame.Rect(x, ty - 2, left_cols + sum(rest.values()), 22)
            if st["is_today"]:
                pygame.draw.rect(screen, self.c["panel_lo"], rowrect)
            self._text(screen, "small", area.name, self.c["text"], x, ty)

            for i in range(7):
                cell = pygame.Rect(cxp + i * day_w + 3, ty - 1, day_w - 6, 18)
                if i == area.collection_day:
                    pygame.draw.rect(screen, self.c["white"], cell)
                    self._text_center(screen, "mono_b", "o", self.c["black"], cell.centerx, ty)
                else:
                    pygame.draw.rect(screen, self.c["panel_hi"], cell, 1)
                self.planner_cells.append((cell, area.id, i))

            # FREQ toggle
            frect = pygame.Rect(fx + 6, ty - 1, freq_w - 12, 18)
            self._pbtn(screen, frect, st["freq_label"],
                       (lambda a=area.id: self._cycle_round_freq(a)),
                       fkey="tiny")

            # Route type indicator
            rt = area.route_type
            rt_color = ROUTE_TYPE_COLORS.get(rt, self.c["text"])
            rt_label = ROUTE_TYPE_LABELS.get(rt, rt)
            trect = pygame.Rect(tx + 6, ty - 1, type_w - 12, 18)
            pygame.draw.rect(screen, self.c["panel_lo"], trect)
            pygame.draw.rect(screen, rt_color, trect, 1)
            self._text_center(screen, "tiny", rt_label, rt_color, trect.centerx, ty + 1)

            sx = tx + type_w
            self._text_center(screen, "mono", str(st["props"]), self.c["text"],
                              sx + rest["props"] // 2, ty)
            sx += rest["props"]
            left = fleet.area_due_count(area.id)
            self._text_center(screen, "mono", str(left),
                              self.c["white"] if left else self.c["muted"],
                              sx + rest["due"] // 2, ty)
            sx += rest["due"]
            stcol = self.c["white"] if st["status"] in ("OVERFLOW", "DUE TODAY") else \
                self.c["muted"] if st["status"] in ("WATCH", "NEXT WEEK") else self.c["dim"]
            stkey = "mono_b" if st["status"] in ("OVERFLOW", "DUE TODAY") else "mono"
            self._text_center(screen, stkey, st["status"], stcol,
                              sx + rest["status"] // 2, ty)
            ty += 22

        ty += 6
        pygame.draw.line(screen, self.c["border_lo"],
                         (x, ty), (x + left_cols + sum(rest.values()), ty), 1)
        ty += 10
        self._text(screen, "small", "Rounds / day", self.c["muted"], x, ty)
        for i in range(7):
            self._text_center(screen, "mono_b", str(per_day_rounds[i]),
                              self.c["white"] if i == today else self.c["text"],
                              cxp + i * day_w + day_w // 2, ty)
        ty += 26

        # service threshold lever + capacity verdict
        ty = self._stepper(
            screen, x, ty, "Service threshold (% full)",
            f"{int(fleet.service_threshold)}%",
            (lambda: self._adjust_threshold(-5)),
            (lambda: self._adjust_threshold(5)))
        demand = fleet.get_today_demand()
        capacity = fleet.estimated_daily_capacity()
        verdict = "within capacity" if demand <= capacity else "OVER CAPACITY"
        self._text(screen, "small",
                   f"Today: {fleet.active_lorries()} lorries  |  est. capacity {capacity}"
                   f"  |  demand {demand}  ->  {verdict}",
                   self.c["text"] if demand <= capacity else self.c["white"], x, ty + 2)

    # ----------------------------------------------------------- planner: WASTE
    def _tab_waste(self, screen, x, y, w, h):
        waste = self.game.waste
        self._text(screen, "small",
                   "Choose which streams the borough collects. More streams lift "
                   "satisfaction but fill bins faster and add disposal cost.",
                   self.c["muted"], x, y)
        ty = y + 26

        for s in waste.streams:
            card = pygame.Rect(x, ty, w, 70)
            self._panel(screen, card.x, card.y, card.w, card.h, fill=self.c["panel_lo"])
            on = s.enabled
            # on/off toggle
            tgl = pygame.Rect(x + 12, ty + 12, 60, 24)
            if s.can_disable:
                self._pbtn(screen, tgl, "ON" if on else "OFF",
                           (lambda sid=s.id: self._toggle_stream(sid)),
                           accent=on, fkey="body_b")
            else:
                pygame.draw.rect(screen, self.c["panel_hi"], tgl)
                pygame.draw.rect(screen, self.c["border_lo"], tgl, 1)
                self._text_center(screen, "body_b", "ON", self.c["dim"], tgl.centerx, ty + 17)

            name_col = self.c["text"] if on else self.c["dim"]
            self._text(screen, "body_b", s.name, name_col, x + 84, ty + 8)
            self._text(screen, "tiny", s.blurb, self.c["muted"] if on else self.c["dim"],
                       x + 84, ty + 28)

            # economics line
            econ = (f"gate GBP{s.gate_fee:.3f}/u  |  "
                    f"{'credit' if s.id != 'garden' else 'charge'} GBP{s.credit:.3f}/u  |  "
                    f"+{s.satisfaction} satis")
            self._text(screen, "tiny", econ, self.c["dim"], x + 84, ty + 48)

            # frequency toggle (right)
            frect = pygame.Rect(x + w - 116, ty + 12, 104, 24)
            if on:
                self._pbtn(screen, frect, s.freq_label,
                           (lambda sid=s.id: self._cycle_stream_freq(sid)), fkey="small")
            else:
                pygame.draw.rect(screen, self.c["panel_hi"], frect, 1)
                self._text_center(screen, "small", s.freq_label, self.c["dim"],
                                  frect.centerx, ty + 17)
            ty += 78

        ty += 4
        pygame.draw.line(screen, self.c["border_lo"], (x, ty), (x + w, ty), 1)
        ty += 10
        self._text(screen, "body", "Bin fill rate", self.c["muted"], x, ty)
        self._text(screen, "body_b", f"x{waste.fill_multiplier():.2f}", self.c["text"], x + 150, ty)
        self._text(screen, "body", "Satisfaction ceiling", self.c["muted"], x + 300, ty)
        self._text(screen, "body_b", f"{int(waste.satisfaction_ceiling())}%",
                   self.c["text"], x + 470, ty)

    # ----------------------------------------------------------- planner: FLEET
    def _tab_fleet(self, screen, x, y, w, h):
        eco = self.game.economy
        fleet = self.game.fleet

        self._text(screen, "small",
                   "Choose a procurement method, then select a vehicle model and place your order.",
                   self.c["muted"], x, y)
        ty = y + 20

        # --- PROCUREMENT TIER SELECTION ---
        tier_w = (w - 24) // 3
        tier_h = 56
        tier_data = [
            ("factory", "Factory Custom", "180-220 days", "-35% price", (100, 180, 120),
             "Bespoke build. Cheapest but plan 6+ months ahead."),
            ("dealer", "Dealer Stock", "14-18 days", "+15% premium", (120, 160, 220),
             "Pre-built. MOT, O-License & delivery. Watch for delays."),
            ("rental", "Spot Rental", "1-2 days", "4.5x daily cost", (220, 140, 100),
             "Emergency hire. Arrives fast, burns budget fast."),
        ]

        # Store selected tier on the game object if not present
        if not hasattr(self.game, '_selected_procurement_tier'):
            self.game._selected_procurement_tier = "dealer"
        selected_tier = self.game._selected_procurement_tier

        for i, (tid, tname, ttime, tprice, tcolour, tblurb) in enumerate(tier_data):
            tx = x + 8 + i * (tier_w + 8)
            rect = pygame.Rect(tx, ty, tier_w, tier_h)
            is_sel = selected_tier == tid

            # Background
            bg = tuple(min(255, c + 30) for c in tcolour) if is_sel else self.c["panel_lo"]
            pygame.draw.rect(screen, bg, rect, border_radius=3)
            border_col = tcolour if is_sel else self.c["border_lo"]
            pygame.draw.rect(screen, border_col, rect, 2 if is_sel else 1, border_radius=3)

            # Title
            name_col = self.c["white"] if is_sel else self.c["text"]
            self._text(screen, "body_b", tname, name_col, tx + 8, ty + 6)
            self._text(screen, "tiny", ttime, self.c["muted"], tx + 8, ty + 24)
            self._text(screen, "tiny", tprice, tcolour, tx + 8, ty + 38)

            # Clickable
            self.planner_widgets.append((rect, (lambda t=tid: setattr(self.game, '_selected_procurement_tier', t))))

        ty += tier_h + 10

        # --- TIER DETAIL BLURB ---
        tier_blurbs = {
            "factory": (
                "Factory Custom Order: Order a bespoke RCV direct from the manufacturer. "
                "You choose the exact capacity, fuel type, and crew configuration. "
                "Cheapest upfront cost (-35%), but you will wait 180-220 days before it hits the road. "
                "Best for long-term fleet expansion when you can see demand coming."
            ),
            "dealer": (
                "Dealer Stock Purchase: Buy a pre-built chassis and compactor body from an authorised dealer. "
                "The 2-week wait covers UK MOT safety plating, operator licensing (O-License), "
                "vehicle registration, and delivery logistics. Premium price (+15%) for near-immediate delivery. "
                "WARNING: Bureaucracy Bottleneck (O-License delay +5 days) or PDI Flaw (hydraulic fault +3 days) "
                "can occur during the waiting period."
            ),
            "rental": (
                "Spot Rental: Emergency spot-hire to cover a sudden breakdown or demand spike. "
                "Vehicle arrives in 1-2 days, but the daily operating cost is 4.5 times normal. "
                "This will devour your budget if kept on the books for more than a few days. "
                "Use sparingly -- rent only while a factory or dealer order is in transit."
            ),
        }
        blurb = tier_blurbs.get(selected_tier, "")
        self._draw_wrapped_text(screen, blurb, x + 8, ty, w - 16, self.fonts["tiny"], self.c["muted"])
        ty += 50

        # --- VEHICLE CATALOGUE ---
        col_w = (w - 12) // 2
        col2_x = x + col_w + 12
        cat_y = ty

        for idx, v in enumerate(VEHICLE_CATALOGUE):
            cx = x if idx % 2 == 0 else col2_x
            if idx % 2 == 0:
                row_y = cat_y

            # Get tier-adjusted price
            from procurement import get_tier
            tier = get_tier(selected_tier)
            adj_price = v.get_price_for_tier(selected_tier) if hasattr(v, 'get_price_for_tier') else v.price
            adj_run = v.get_running_cost_for_tier(selected_tier) if hasattr(v, 'get_running_cost_for_tier') else v.running_cost
            lead = tier.random_lead_time() if tier else v.lead_time

            card = pygame.Rect(cx, row_y, col_w, 110)
            self._panel(screen, card.x, card.y, card.w, card.h, fill=self.c["panel_lo"])
            self._text(screen, "body_b", v.name, self.c["text"], cx + 10, row_y + 8)
            self._text(screen, "tiny",
                       f"cap {v.capacity:,}  crew {v.crew_cap}  spd x{v.speed_factor:.2f}",
                       self.c["muted"], cx + 10, row_y + 28)
            self._text(screen, "tiny", f"run GBP{adj_run}/day  |  lead {lead}d",
                       self.c["dim"], cx + 10, row_y + 44)

            # Price display varies by tier
            if selected_tier == "rental":
                price_label = f"Rent GBP{adj_price//1000 or 1}k deposit"
                can_afford = eco.budget >= adj_price
                btn = pygame.Rect(cx + 10, row_y + 64, col_w - 20, 28)
                self._pbtn(screen, btn, price_label,
                           (lambda vid=v.id: self._buy_vehicle(vid, selected_tier, False)),
                           enabled=can_afford, fkey="small", accent=True)
            else:
                # Buy / Lease buttons
                buy = pygame.Rect(cx + 10, row_y + 64, (col_w - 30) // 2, 28)
                lease = pygame.Rect(buy.right + 10, row_y + 64, (col_w - 30) // 2, 28)
                can_buy = eco.budget >= adj_price
                can_lease = eco.budget >= v.deposit()
                self._pbtn(screen, buy, f"Buy GBP{adj_price//1000}k",
                           (lambda vid=v.id: self._buy_vehicle(vid, selected_tier, False)),
                           enabled=can_buy, fkey="small")
                self._pbtn(screen, lease, f"Lease GBP{v.deposit()//1000 or 1}k",
                           (lambda vid=v.id: self._buy_vehicle(vid, selected_tier, True)),
                           enabled=can_lease, fkey="small")

            if idx % 2 == 1:
                cat_y += 118

        if len(VEHICLE_CATALOGUE) % 2 == 1:
            cat_y += 118
        ty = cat_y + 4
        pygame.draw.line(screen, self.c["border_lo"], (x, ty), (x + w, ty), 1)
        ty += 10

        # --- CURRENT FLEET + ORDERS ---
        owned = len(fleet.trucks)
        leased_n = sum(1 for t in fleet.trucks if t.get("leased"))
        rental_n = sum(1 for t in fleet.trucks if t.get("tier_id") == "rental")
        self._text(screen, "body_b", "Current fleet", self.c["text"], x, ty)
        fleet_info = f"{owned} lorries"
        if leased_n:
            fleet_info += f" ({leased_n} leased)"
        if rental_n:
            fleet_info += f"  [Rental: {rental_n}]"
        fleet_info += f"  |  {fleet.workers} crew  |  running GBP{int(fleet.daily_vehicle_cost())}/day"
        self._text(screen, "small", fleet_info, self.c["muted"], x, ty + 20)

        # Crew hire/fire
        hire = pygame.Rect(x, ty + 46, 120, 26)
        fire = pygame.Rect(hire.right + 10, ty + 46, 120, 26)
        self._pbtn(screen, hire, "Hire crew GBP2.5k",
                   self._hire, enabled=eco.budget >= 2500, fkey="small")
        self._pbtn(screen, fire, "Release crew",
                   self._fire, enabled=fleet.workers > 0, fkey="small")

        # --- PENDING ORDERS (right column) ---
        ox = x + w - 300
        self._text(screen, "body_b", "On order", self.c["text"], ox, ty)
        oy = ty + 20
        if not fleet.orders:
            self._text(screen, "small", "Nothing on order.", self.c["dim"], ox, oy)
        else:
            for o in fleet.orders[:5]:
                rem = o.days_remaining(eco.day)
                tier_name = getattr(o, 'display_tier_name', 'Buy') if hasattr(o, 'display_tier_name') else 'Buy'
                tag = f"{tier_name}"
                if o.leased:
                    tag += " lease"
                line = f"{o.vehicle.name} ({tag}) - {rem}d"
                # Check for pending procurement events
                if hasattr(o, 'event_name') and o.event_name and not o.event_triggered:
                    line += f"  !{o.event_name}"
                    col = self.c["white"]
                elif hasattr(o, 'event_triggered') and o.event_triggered:
                    line += "  (delayed)"
                    col = self.c["muted"]
                else:
                    col = self.c["muted"]
                self._text(screen, "small", line, col, ox, oy)
                oy += 18
    def _tab_finance(self, screen, x, y, w, h):
            eco = self.game.economy
            snap = eco.ledger_snapshot()

            self._text(screen, "small",
                       "Yesterday's profit & loss. Adjust the council tax lever to "
                       "balance the books against public satisfaction.",
                       self.c["muted"], x, y)
            ty = y + 24

            # ledger table (left)
            lx = x
            rx = x + 300
            for key, label in eco.LEDGER_LABELS:
                val = snap.get(key, 0.0)
                is_rev = key in eco.REVENUE_KEYS
                self._text(screen, "body", label, self.c["muted"], lx, ty)
                sign = "+" if is_rev else "-"
                self._text_right(screen, "mono", f"{sign}GBP{abs(val):,.0f}",
                                 self.c["text"], rx, ty)
                ty += 20
            pygame.draw.line(screen, self.c["border_lo"], (lx, ty + 2), (rx, ty + 2), 1)
            ty += 8
            net = snap.get("net", 0.0)
            self._text(screen, "body_b", "Net / day", self.c["text"], lx, ty)
            self._text_right(screen, "mono_b",
                             f"{'+' if net >= 0 else '-'}GBP{abs(net):,.0f}",
                             self.c["white"], rx, ty)
            ty += 28

            # council tax lever
            ty2 = self._stepper(
                screen, lx, ty, "Council tax (GBP/resident/day)",
                f"{eco.council_tax_rate:.2f}",
                (lambda: self._adjust_tax(-0.10)),
                (lambda: self._adjust_tax(0.10)),
                label_w=220)
            self._text(screen, "tiny",
                       "Higher tax raises revenue but dents satisfaction over time.",
                       self.c["dim"], lx, ty2)

            # 14-day net trend (right column)
            gx = x + 360
            gw = w - 360
            self._text(screen, "body_b", "Net trend (last 14 days)", self.c["text"], gx, y + 24)
            hist = eco.history[-14:]
            if hist:
                nets = [eco._ledger_net(d) for d in hist]
                peak = max(1.0, max(abs(n) for n in nets))
                base_y = y + 150
                bw = max(6, (gw - (len(nets) - 1) * 4) // max(1, len(nets)))
                bxx = gx
                for n in nets:
                    bh_px = int((abs(n) / peak) * 56)
                    if n >= 0:
                        rect = pygame.Rect(bxx, base_y - bh_px, bw, bh_px)
                        pygame.draw.rect(screen, self.c["white"], rect)
                    else:
                        rect = pygame.Rect(bxx, base_y, bw, bh_px)
                        pygame.draw.rect(screen, self.c["dim"], rect)
                    bxx += bw + 4
                pygame.draw.line(screen, self.c["border_lo"],
                                 (gx, base_y), (gx + gw - 20, base_y), 1)
                self._text(screen, "tiny", "zero", self.c["dim"], gx, base_y + 4)
            else:
                self._text(screen, "small", "Trend builds after a few days.",
                           self.c["dim"], gx, y + 50)

            self._text(screen, "body", "Budget", self.c["muted"], gx, y + 180)
            self._text(screen, "big", f"GBP {int(eco.budget):,}", self.c["white"], gx, y + 196)

        # ----------------------------------------------------------- planner: DATA
    def _tab_data(self, screen, x, y, w, h):
        self._text(screen, "small",
                   "Export the borough plan to a spreadsheet (.ods or .xml) you can open "
                   "in Excel or LibreOffice, edit, and import back in.",
                   self.c["muted"], x, y)
        ty = y + 30

        exp = pygame.Rect(x, ty, 220, 36)
        imp = pygame.Rect(exp.right + 16, ty, 220, 36)
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
            "Catalogue and Procurement Orders are read-only reference. On",
            "import only safe levers apply: money is never edited directly,",
            "and crew/vehicles are only bought within the available budget.",
            "A summary of each import is written to the Summary sheet.",
        ]
        for ln in lines:
            self._text(screen, "small", ln, self.c["muted"] if ln.strip() else self.c["dim"],
                       x, ty)
            ty += 19

    # ----------------------------------------------------- planner: callbacks
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
            # roll the order back; can't afford the up-front cost
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

    def _adjust_tax(self, delta):
        eco = self.game.economy
        eco.council_tax_rate = max(0.0, round(eco.council_tax_rate + delta, 2))

    def _export_xml(self):
        ok, msg = xmlio.prompt_export(self.game)
        self.game.set_toast(msg)

    def _import_xml(self):
        ok, msg = xmlio.prompt_import(self.game)
        self.game.set_toast(msg)

    # ----------------------------------------------------------------- update
    
    def _draw_wrapped_text(self, screen, text, x, y, max_width, font, colour):
        """Simple word-wrap for multi-line descriptions."""
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