import pygame
import sys
import math
from city import CityGenerator
from renderer import Renderer
from economy import Economy
from ui import UIManager
from fleet import FleetManager
from waste import WastePolicy
from ambient import AmbientState
from assets import asset_path
import savegame
import citystore

CITY_W = 60
CITY_H = 60


def _tiles_on_line(a, b):
    """Integer grid tiles from `a` to `b` inclusive (Bresenham). The start `a`
    is excluded so a continuous drag doesn't re-apply the tile painted on the
    previous motion event. Used to fill gaps when the mouse jumps several tiles
    between frames."""
    (x0, y0), (x1, y1) = a, b
    if (x0, y0) == (x1, y1):
        return [(x1, y1)]
    dx = abs(x1 - x0)
    dy = -abs(y1 - y0)
    sx = 1 if x0 < x1 else -1
    sy = 1 if y0 < y1 else -1
    err = dx + dy
    out = []
    while True:
        if (x0, y0) != a:
            out.append((x0, y0))
        if x0 == x1 and y0 == y1:
            break
        e2 = 2 * err
        if e2 >= dy:
            err += dy
            x0 += sx
        if e2 <= dx:
            err += dx
            y0 += sy
    return out


class WasteCityGame:
    def __init__(self):
        pygame.init()
        pygame.display.set_caption("The Rubbish Game")
        
        # Load and set the application icon
        try:
            icon = pygame.image.load(asset_path("icon.ico"))
            pygame.display.set_icon(icon)
        except (pygame.error, FileNotFoundError):
            # Fallback if the icon asset path isn't ready yet during development
            pass

        self.screen = pygame.display.set_mode((1280, 720), pygame.RESIZABLE)
        self.clock = pygame.time.Clock()

        self.running = True
        self.speed = 1
        self.last_time = 0

        self.camera = {"x": 0, "y": 0, "zoom": 1}
        self.dragging = False
        self.drag_moved = False
        self._ui_press = False     # True when a left-press started on the UI
        self.mouse = {"x": 0, "y": 0}

        # Editor drag-painting (SimCity-style): left-drag paints the active
        # brush; right/middle-drag pans instead.
        self._editor_painting = False
        self._editor_last_tile = None   # last painted (x, y) for line-fill
        self._editor_pan = False        # right/middle button panning the camera

        self.selected_tile = None
        self.hovered_tile = None
        self.show_areas = True

        # Transient status line (XML import/export, deliveries, etc.)
        self.toast = ""
        self.toast_timer = 0.0

        self.city = CityGenerator(CITY_W, CITY_H)
        self.city.generate()

        self.waste = WastePolicy()
        self.fleet = FleetManager(self)
        self.fleet.setup_initial_fleet()
        self.economy = Economy()
        self.ui = UIManager(self)
        self.renderer = Renderer(self.screen, self.camera)
        self.ambient = AmbientState()

        self._center_camera()

        # ── Game state / start menu ──────────────────────────────────────────
        # The city generated above becomes the living backdrop behind the menu.
        self.state = "menu"            # "menu" | "playing" | "editor"
        self._editor_source = None     # ("new", density) | ("saved", path)
        self._menu_cam_t = 0.0         # drives the slow cinematic backdrop pan
        self.settings = {
            "day_length": "normal",    # short | normal | long
            "events": "normal",        # calm | normal | chaotic
            "show_areas": True,
        }

    # ---------------------------------------------------------------- actions
    def _toggle_areas(self):
        self.show_areas = not self.show_areas

    def _clear_and_regenerate(self, city_path=None):
        self.economy = Economy()
        self.waste = WastePolicy()
        self.fleet = FleetManager(self)
        if city_path:
            try:
                self.city = citystore.load_city(city_path)
            except Exception as e:
                self.city = CityGenerator(CITY_W, CITY_H)
                self.city.generate()
                self.set_toast(f"Couldn't load city: {e}")
            # A saved map might have been left without a landfill in the editor;
            # a playable borough needs one, so auto-site it as a fallback.
            if not getattr(self.city, "landfill", None):
                self.city._place_landfill()
        else:
            self.city = CityGenerator(CITY_W, CITY_H)
            self.city.generate()
        self.fleet.setup_initial_fleet()
        self.ambient = AmbientState()
        # Reset any open floating windows for a clean fresh term.
        self.ui.windows.clear()
        self.ui._win_drag = None
        self.clear_selection()
        self._center_camera()

    def set_toast(self, message):
        self.toast = message
        self.toast_timer = 4.0

    # -------------------------------------------------------------- main menu
    def _apply_settings(self):
        """Push the menu settings onto the freshly-created game objects."""
        self.show_areas = self.settings.get("show_areas", True)
        day = {"short": 38, "normal": 55, "long": 78}
        self.economy.day_duration = day.get(self.settings.get("day_length"), 55)
        ev = {"calm": 0.16, "normal": 0.30, "chaotic": 0.48}
        self.economy.event_chance = ev.get(self.settings.get("events"), 0.30)

    def _start_new_game(self, city_path=None):
        self._clear_and_regenerate(city_path=city_path)
        self._apply_settings()
        self.ui._menu_newgame_open = False
        self.ui._menu_editor_open = False
        self.toast = ""
        self.toast_timer = 0.0
        self.state = "playing"

    def _menu_load(self):
        ok, msg = savegame.load_game(self)
        self.set_toast(msg)
        if ok:
            self.show_areas = self.settings.get("show_areas", self.show_areas)
            self.state = "playing"

    def _menu_dispatch(self, action):
        # Dynamic entries (saved cities) arrive as tuples.
        if isinstance(action, tuple):
            kind, val = action
            if kind == "new_saved":
                self._start_new_game(city_path=val)
            elif kind == "edit_saved":
                self._start_editor(("saved", val))
            return

        if action == "new":
            # Open the start-game chooser (Random + any saved cities).
            self.ui._menu_editor_open = False
            self.ui._menu_settings_open = False
            self.ui._menu_newgame_open = True
        elif action == "new_random":
            self._start_new_game()
        elif action == "editor":
            # Open the city-editor chooser (Blank/Partial/Full + saved).
            self.ui._menu_newgame_open = False
            self.ui._menu_settings_open = False
            self.ui._menu_editor_open = True
        elif action in ("edit_blank", "edit_partial", "edit_full"):
            self._start_editor(("new", action.split("_", 1)[1]))
        elif action == "load":
            self._menu_load()
        elif action == "settings":
            self.ui._menu_settings_open = True
        elif action == "quit":
            pygame.quit()
            sys.exit()
        elif action == "menu_back":
            self.ui._menu_settings_open = False
            self.ui._menu_newgame_open = False
            self.ui._menu_editor_open = False
        elif action == "set_day_length":
            order = ["short", "normal", "long"]
            cur = self.settings.get("day_length", "normal")
            self.settings["day_length"] = order[(order.index(cur) + 1) % len(order)]
        elif action == "set_events":
            order = ["calm", "normal", "chaotic"]
            cur = self.settings.get("events", "normal")
            self.settings["events"] = order[(order.index(cur) + 1) % len(order)]
        elif action == "set_areas":
            self.settings["show_areas"] = not self.settings.get("show_areas", True)

    def _handle_menu_event(self, event):
        if event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            action = self.ui.menu_resolve(event.pos)
            if action:
                self._menu_dispatch(action)
        elif event.type == pygame.KEYDOWN:
            panel_open = (self.ui._menu_settings_open or self.ui._menu_newgame_open
                          or self.ui._menu_editor_open)
            if event.key in (pygame.K_ESCAPE, pygame.K_q):
                if panel_open:
                    self.ui._menu_settings_open = False
                    self.ui._menu_newgame_open = False
                    self.ui._menu_editor_open = False
                else:
                    pygame.quit()
                    sys.exit()
            elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                if not panel_open:
                    self._start_new_game()

    # ---------------------------------------------------------- city editor
    def _start_editor(self, source):
        """Enter the standalone city editor. `source` is ("new", density) for a
        freshly-generated blank/partial/full map, or ("saved", path) to open an
        existing city for further editing."""
        self._editor_source = source
        kind, val = source
        if kind == "saved":
            try:
                self.city = citystore.load_city(val)
            except Exception as e:
                self.set_toast(f"Couldn't open city: {e}")
                return
        else:
            self.city = CityGenerator(CITY_W, CITY_H)
            self.city.generate(density=val, place_landfill=False)

        # Fresh support objects so the map renders and the fleet's road graph
        # rebinds to the new city. The editor doesn't run the simulation.
        self.economy = Economy()
        self.waste = WastePolicy()
        self.fleet = FleetManager(self)
        self.ambient = AmbientState()

        self.ui.windows.clear()
        self.ui._win_drag = None
        self.ui._menu_newgame_open = False
        self.ui._menu_editor_open = False
        self.ui.enter_editor_state()
        self.clear_selection()
        self.hovered_tile = None
        self._editor_painting = False
        self._editor_last_tile = None
        self._editor_pan = False
        self.toast = ""
        self.toast_timer = 0.0
        self.state = "editor"
        self._center_camera()

    def editor_regenerate(self):
        """Re-roll / reload the editor's current map from its source."""
        if self._editor_source:
            self._start_editor(self._editor_source)

    def editor_save_city(self, name):
        ok, msg = citystore.save_city(self.city, name)
        self.set_toast(msg)
        return ok

    def play_edited_city(self):
        """Leave the editor and start a fresh game on the edited city."""
        if not getattr(self.city, "landfill", None):
            self.set_toast("Place a landfill site first (Landfill tool).")
            return
        stranded = len(self.city.unreachable_building_tiles())
        self.economy = Economy()
        self.waste = WastePolicy()
        self.fleet = FleetManager(self)
        self.fleet.setup_initial_fleet()
        self.ambient = AmbientState()
        self._apply_settings()
        self.ui.exit_editor_state()
        self.ui.windows.clear()
        self.ui._win_drag = None
        self.clear_selection()
        self.toast = ""
        self.toast_timer = 0.0
        self.state = "playing"
        self._center_camera()
        if stranded:
            self.set_toast(
                f"Note: {stranded} building(s) sit too far from a road and "
                f"won't be collected — their bins will overflow.")

    def exit_editor_to_menu(self):
        """Abandon the editor and return to the main menu (with a fresh living
        backdrop city behind it)."""
        self.ui.exit_editor_state()
        self._clear_and_regenerate()
        self.ui._menu_settings_open = False
        self.ui._menu_newgame_open = False
        self.ui._menu_editor_open = False
        self.state = "menu"
        self._center_camera()

    def _editor_tile_at(self, pos):
        return self.renderer.screen_to_tile(pos[0], pos[1],
                                             self.screen.get_width(),
                                             self.screen.get_height())

    def _editor_map_click(self, pos):
        """A discrete click on the map (used for the landfill stamp, which is a
        single placement rather than a paint stroke)."""
        coord = self._editor_tile_at(pos)
        tool = self.ui.editor_tool or {}
        if tool.get("mode") == "landfill":
            if self.city.editor_place_landfill(coord["x"], coord["y"]):
                self.set_toast("Landfill sited.")
            else:
                self.set_toast("Can't place a landfill there.")

    def _editor_paint_at(self, pos):
        """Paint the active brush at the tile under `pos`, filling the straight
        line back to the previously-painted tile so a fast drag leaves no gaps."""
        coord = self._editor_tile_at(pos)
        cur = (coord["x"], coord["y"])
        last = self._editor_last_tile
        stops = _tiles_on_line(last, cur) if last is not None else [cur]
        for (tx, ty) in stops:
            self.ui.editor_paint(tx, ty)
        self._editor_last_tile = cur

    def _step_editor(self, dt):
        """Editor frame: keep the UI responsive and the camera clamped, but
        freeze the simulation entirely."""
        if self.toast_timer > 0:
            self.toast_timer -= dt
            if self.toast_timer <= 0:
                self.toast = ""
        self.ui.update(dt)
        self._clamp_camera()

    # Hotkeys that select a brush from the keyboard (SimCity muscle memory).
    _EDITOR_HOTKEYS = {
        pygame.K_r: ("zone", "residential"),
        pygame.K_c: ("zone", "commercial"),
        pygame.K_p: ("green", None),
        pygame.K_d: ("road", None),
        pygame.K_e: ("erase_road", None),
        pygame.K_b: ("bulldoze", None),
        pygame.K_l: ("landfill", None),
    }

    def _handle_editor_event(self, event):
        ui = self.ui
        # A save-name prompt captures all keys while open.
        if ui._city_name_active:
            if event.type == pygame.KEYDOWN:
                ui.handle_city_name_key(event)
            return

        if event.type == pygame.KEYDOWN:
            # Help overlay: H/? toggles it; while it's up it captures Esc and
            # otherwise swallows keys so shortcuts don't fire behind it.
            if event.key == pygame.K_h or event.unicode == "?":
                ui._editor_help_open = not ui._editor_help_open
                return
            if ui._editor_help_open:
                if event.key == pygame.K_ESCAPE:
                    ui._editor_help_open = False
                return
            if event.key == pygame.K_ESCAPE:
                # First Esc drops the active brush; a second Esc leaves the editor.
                if ui.editor_tool:
                    ui.editor_tool = None
                else:
                    self.exit_editor_to_menu()
            elif event.key == pygame.K_g:
                self.show_areas = not self.show_areas
            elif event.key == pygame.K_w:
                ui._editor_show_warnings = not ui._editor_show_warnings
            elif event.key in (pygame.K_LEFTBRACKET, pygame.K_MINUS):
                ui.editor_cycle_brush_size(-1)
            elif event.key in (pygame.K_RIGHTBRACKET, pygame.K_EQUALS):
                ui.editor_cycle_brush_size(1)
            elif event.key in self._EDITOR_HOTKEYS:
                mode, kind = self._EDITOR_HOTKEYS[event.key]
                ui.editor_tool = {"mode": mode}
                if kind:
                    ui.editor_tool["kind"] = kind

        elif event.type == pygame.MOUSEBUTTONDOWN:
            if event.button == 1:
                on_chrome = ui.editor_on_mouse_down(event.pos)
                self._ui_press = on_chrome
                tool = ui.editor_tool or {}
                if on_chrome:
                    # Resolve as a click on release; never paint or pan.
                    self.dragging = True
                    self.drag_moved = False
                elif tool and tool.get("mode") != "landfill":
                    # Paint tools: start a stroke and paint the first tile now.
                    self._editor_painting = True
                    self._editor_last_tile = None
                    self._update_editor_hover(event.pos)
                    self._editor_paint_at(event.pos)
                else:
                    # Landfill (single stamp) or no tool: treat as a click; a
                    # left-drag with no tool falls back to panning.
                    self.dragging = True
                    self.drag_moved = False
            elif event.button in (2, 3):
                self._editor_pan = True          # right / middle drag pans
            elif event.button == 4:
                self.camera["zoom"] = min(4, self.camera["zoom"] * 1.1)
            elif event.button == 5:
                self.camera["zoom"] = max(0.3, self.camera["zoom"] * 0.9)

        elif event.type == pygame.MOUSEBUTTONUP:
            if event.button == 1:
                if self._editor_painting:
                    self._editor_painting = False
                    self._editor_last_tile = None
                else:
                    was_click = self.dragging and not self.drag_moved
                    consumed = ui.editor_on_mouse_up(event.pos, was_click)
                    if was_click and not consumed:
                        self._editor_map_click(event.pos)
                self.dragging = False
                self._ui_press = False
            elif event.button in (2, 3):
                self._editor_pan = False

        elif event.type == pygame.MOUSEMOTION:
            self.mouse["x"] = event.pos[0]
            self.mouse["y"] = event.pos[1]
            self._update_editor_hover(event.pos)
            if self._editor_painting:
                self._editor_paint_at(event.pos)
            else:
                # Pan on right/middle drag, or on a left drag when no brush is
                # selected (so an empty hand still lets you move the map).
                no_tool = not ui.editor_tool
                if self._editor_pan or (self.dragging and not self._ui_press and no_tool):
                    self.camera["x"] += event.rel[0] / self.camera["zoom"]
                    self.camera["y"] += event.rel[1] / self.camera["zoom"]
                    if abs(event.rel[0]) > 2 or abs(event.rel[1]) > 2:
                        self.drag_moved = True

    def _update_editor_hover(self, pos):
        """Track the tile under the cursor so the brush footprint can preview."""
        if pos[1] <= self.ui.MENU_BAR_H or self.ui._in_editor_bar(pos):
            self.hovered_tile = None
        else:
            self.hovered_tile = self._editor_tile_at(pos)

    def _step_backdrop(self, dt):
        """Keep the city alive behind the menu: ambient life, driving lorries
        and bin fill, plus a slow cinematic pan. The economy, day count and
        lose condition are deliberately left frozen."""
        self._menu_cam_t += dt
        cx = self.city.width * 0.5 + math.sin(self._menu_cam_t * 0.10) * self.city.width * 0.30
        cy = self.city.height * 0.5 + math.cos(self._menu_cam_t * 0.07) * self.city.height * 0.22
        self.center_camera_on(cx, cy)

        self.city.update(dt, self.waste.fill_multiplier())
        self.fleet.update(dt)
        self.ambient.update(dt, self.city, self.fleet, self.economy)

        if self.toast_timer > 0:
            self.toast_timer -= dt
            if self.toast_timer <= 0:
                self.toast = ""
        self.ui.update(dt)

    def open_planner_tab(self, tab):
        # Back-compat shim: opens the corresponding floating window.
        self.ui.open_window(tab)

    def _center_camera(self):
        """Frame the camera on the landfill site at start (falls back to the
        depot if no landfill exists)."""
        lf = getattr(self.city, "landfill", None)
        if lf:
            self.center_camera_on(lf["cx"], lf["cy"])
        else:
            self.center_camera_on(self.fleet.depot_x, self.fleet.depot_y)

    def center_camera_on(self, wx, wy):
        """Pan/centre the camera so world tile-space point (wx, wy) sits at
        screen centre (used on startup and from the vehicle inspect window)."""
        target = self.renderer.to_iso(wx, wy)
        sw, sh = self.screen.get_size()
        zoom = self.camera["zoom"]
        # Solve render()'s mapping so the target sits at screen centre:
        #   screen_x = sw/2 + camera_x + iso_x*zoom
        #   screen_y = 120  + camera_y + iso_y*zoom
        self.camera["x"] = -target[0] * zoom
        self.camera["y"] = sh / 2 - 120 - target[1] * zoom

    def _map_iso_bounds(self):
        corners = [
            self.renderer.to_iso(0, 0),
            self.renderer.to_iso(self.city.width, 0),
            self.renderer.to_iso(0, self.city.height),
            self.renderer.to_iso(self.city.width, self.city.height),
        ]
        xs = [c[0] for c in corners]
        ys = [c[1] for c in corners]
        return min(xs), max(xs), min(ys), max(ys)

    def _clamp_camera(self):
        """Keep the map in reach: the camera may centre on any point of the map
        (including the corners, where the landfill sits) plus a small margin of
        overscroll, scaled with zoom."""
        zoom = self.camera["zoom"]
        margin = 300
        sw, sh = self.screen.get_size()
        min_ix, max_ix, min_iy, max_iy = self._map_iso_bounds()
        # camera_x that centres iso_x is -iso_x*zoom; allow the full span + margin.
        self.camera["x"] = max(-max_ix * zoom - margin,
                               min(-min_ix * zoom + margin, self.camera["x"]))
        cy_for = lambda iso_y: sh / 2 - 120 - iso_y * zoom
        self.camera["y"] = max(cy_for(max_iy) - margin,
                               min(cy_for(min_iy) + margin, self.camera["y"]))

    # ----------------------------------------------------------------- clicks
    def handle_map_click(self, screen_x, screen_y):
        """A genuine click on the map (UI windows/toolbar/HUD already had their
        chance to consume it). A click on a lorry opens its inspect window;
        otherwise select or deselect a tile."""
        if self.economy.has_lost:
            return

        truck = self.renderer.truck_at_screen_pos(self.fleet, screen_x, screen_y)
        if truck is not None:
            self.ui.open_truck_window(truck["id"])
            return

        coord = self.renderer.screen_to_tile(screen_x, screen_y,
                                               self.screen.get_width(),
                                               self.screen.get_height())

        if self.ui.editor_active():
            self.ui.apply_editor_brush(coord["x"], coord["y"])
            return

        tile = self.city.get_tile(coord["x"], coord["y"])
        if not tile:
            self.clear_selection()
            return

        if self.selected_tile and self.selected_tile["x"] == coord["x"] and self.selected_tile["y"] == coord["y"]:
            self.clear_selection()
        else:
            self.selected_tile = {"x": coord["x"], "y": coord["y"], "tile": tile}

    def clear_selection(self):
        self.selected_tile = None
        self.hovered_tile = None

    # ----------------------------------------------------------------- update
    def _update_realtime(self, dt):
        """Real-time (unscaled) pass: camera, hover, transient UI. Runs once per
        rendered frame regardless of game speed."""
        # Once the borough is insolvent the simulation halts — only the
        # game-over overlay remains, awaiting a restart.
        if self.economy.has_lost:
            self.economy.game_over_timer += dt
            self.ui.update(dt)
            return

        # Camera movement from held keys (the map stays live with windows open;
        # suppressed only while typing a truck rename).
        if self.ui._renaming_truck_id is None:
            keys = pygame.key.get_pressed()
            speed = 35 / self.camera["zoom"] * self.speed
            if keys[pygame.K_w]:
                self.camera["y"] += speed * dt
            if keys[pygame.K_s]:
                self.camera["y"] -= speed * dt
            if keys[pygame.K_a]:
                self.camera["x"] += speed * dt
            if keys[pygame.K_d]:
                self.camera["x"] -= speed * dt

        # Track hovered tile for building tinting
        coord = self.renderer.screen_to_tile(self.mouse["x"], self.mouse["y"],
                                               self.screen.get_width(),
                                               self.screen.get_height())
        tile = self.city.get_tile(coord["x"], coord["y"])
        if tile and tile.type not in ("road", "green", "landfill"):
            self.hovered_tile = {"x": coord["x"], "y": coord["y"], "tile": tile}
        else:
            self.hovered_tile = None

        if self.toast_timer > 0:
            self.toast_timer -= dt
            if self.toast_timer <= 0:
                self.toast = ""

        self.ui.update(dt)
        self._clamp_camera()

    def _step_sim(self, sim_dt):
        """One fixed-size simulation tick. The game loop calls this N times per
        frame at Nx speed, so the sim is deterministic and independent of frame
        rate; only this pass advances game time."""
        bin_mult = (self.economy.get_bin_rate_multiplier()
                    * self.waste.fill_multiplier()
                    * self.economy.seasonal_fill_mult())
        self.city.update(sim_dt, bin_mult)
        self.fleet.update(sim_dt)
        new_day = self.economy.update(sim_dt, self.city, self.fleet, self.waste)

        if new_day:
            # Deliver any vehicles that have arrived. process_deliveries returns
            # both the delivered vehicles and any procurement events (O-licence
            # delays, pre-delivery faults) that fired while we waited.
            delivered, proc_events = self.fleet.process_deliveries(self.economy.day)
            if delivered:
                self.set_toast("Delivered: " + ", ".join(str(d) for d in delivered))
            for ev in proc_events:
                self.ui.show_event({
                    "name": ev.get("name", "Procurement notice"),
                    "desc": ev.get("message", ev.get("description", "")),
                    "effect": "procurement",
                })
            # Age the fleet: ticks vehicle age, progresses repairs, and rolls
            # age-related breakdowns (charging repair bills to the economy).
            for ev in self.fleet.age_fleet():
                self.ui.show_event(ev)
            # Surface any day-rollover notices (loan cleared, statutory fines).
            for ev in self.economy.day_notices:
                self.ui.show_event(ev)
            # Once-per-day service-quality snapshot (one scan, not per frame).
            self.economy.register_day_quality(
            self.city, self.waste.satisfaction_ceiling())

        if self.economy.pending_event:
            self.ui.show_event(self.economy.pending_event)
            self.economy.pending_event = None

        self.ambient.update(sim_dt, self.city, self.fleet, self.economy)

    # ---------------------------------------------------------------- render
    def render(self):
        w, h = self.screen.get_size()
        # The backdrop gradient is static for a given window size. Build it once
        # and blit it, rather than issuing ~h/2 draw.line calls every frame.
        cache = getattr(self, "_bg_gradient_cache", None)
        if cache is None or self._bg_gradient_size != (w, h):
            grad = pygame.Surface((w, h))
            grad.fill((22, 24, 30))
            for i in range(0, h, 2):
                t = i / h
                g = int(40 + (22 - 40) * t)
                pygame.draw.line(grad, (g, g, int(g * 1.1)), (0, i), (w, i), 2)
            self._bg_gradient_cache = grad
            self._bg_gradient_size = (w, h)
            cache = grad
        self.screen.blit(cache, (0, 0))

        menu = self.state == "menu"
        editor = self.state == "editor"
        sel = None if (menu or editor) else self.selected_tile
        hov = None if (menu or editor) else self.hovered_tile
        areas = self.show_areas and not menu
        self.renderer.render(self.city, self.fleet, sel,
                             self.economy.get_day_of_week(), areas,
                             hov, self.economy, self.ambient)
        if menu:
            self.ui.draw_main_menu(self.screen)
        elif editor:
            if self.ui._editor_show_warnings:
                pulse = 0.5 + 0.5 * math.sin(pygame.time.get_ticks() * 0.004)
                self.renderer.draw_unreachable(
                    self.ui.editor_unreachable_tiles(), pulse)
            if self.ui.editor_tool and self.hovered_tile:
                self.renderer.draw_editor_cursor(
                    self.ui.editor_cursor_tiles(self.hovered_tile),
                    self.ui.editor_cursor_color())
            self.ui.draw_editor(self.screen)
        else:
            self.ui.draw(self.screen)
        pygame.display.flip()

    # ------------------------------------------------------------------- loop
    def _process_event(self, event):
        if event.type == pygame.QUIT:
            pygame.quit()
            sys.exit()

        elif event.type == pygame.VIDEORESIZE:
            self.screen = pygame.display.set_mode((event.w, event.h), pygame.RESIZABLE)
            self.ui._setup_buttons()

        elif self.state == "menu":
            self._handle_menu_event(event)

        elif self.state == "editor":
            self._handle_editor_event(event)

        elif event.type == pygame.KEYDOWN:
            mods = pygame.key.get_mods()
            # Global debug-window toggle -- works in every game state.
            if (event.key == pygame.K_d and (mods & pygame.KMOD_CTRL)
                    and (mods & pygame.KMOD_SHIFT)):
                self.ui.toggle_debug_window()
            # Game over: only restart (R) or quit (Esc/Q) are accepted.
            elif self.economy.has_lost:
                if event.key == pygame.K_r:
                    self._clear_and_regenerate()
                elif event.key in (pygame.K_ESCAPE, pygame.K_q):
                    pygame.quit()
                    sys.exit()
            # If a truck rename is in progress, all keys go to the rename field.
            elif self.ui._renaming_truck_id is not None:
                self.ui.handle_key(event)
            else:
                # Number keys toggle the floating windows directly.
                win_keys = {pygame.K_1: "rounds", pygame.K_2: "waste",
                            pygame.K_3: "fleet",   pygame.K_4: "staff",
                            pygame.K_5: "finance", pygame.K_6: "data"}
                if event.key in win_keys:
                    self.ui.toggle_window(win_keys[event.key])
                elif event.key == pygame.K_F5:
                    ok, msg = savegame.save_game(self)
                    self.set_toast(msg)
                elif event.key == pygame.K_F9:
                    ok, msg = savegame.load_game(self)
                    self.set_toast(msg)
                elif event.key == pygame.K_TAB:
                    # Tab toggles the most-used management window.
                    self.ui.toggle_window("rounds")
                elif event.key == pygame.K_g:
                    self.show_areas = not self.show_areas
                elif event.key == pygame.K_ESCAPE:
                    # Esc exits editor mode in one press (no two-step).
                    # If no editor mode, close the focused window; else clear selection.
                    if self.ui._editor_mode:
                        self.ui._exit_editor_mode()
                    elif self.ui.windows:
                        self.ui.close_window(self.ui.windows[-1])
                    else:
                        self.clear_selection()

        elif event.type == pygame.MOUSEBUTTONDOWN:
            if event.button == 1:
                # Always treat the press as a potential click; the UI gets first
                # refusal. If the UI takes it, suppress the camera pan but still
                # let the click resolve on release.
                self._ui_press = self.ui.on_mouse_down(event.pos)
                self.dragging = True
                self.drag_moved = False
            elif event.button == 4:
                if not self.ui.on_scroll(4, event.pos):
                    self.camera["zoom"] = min(4, self.camera["zoom"] * 1.1)
            elif event.button == 5:
                if not self.ui.on_scroll(5, event.pos):
                    self.camera["zoom"] = max(0.3, self.camera["zoom"] * 0.9)

        elif event.type == pygame.MOUSEBUTTONUP:
            if event.button == 1:
                was_click = self.dragging and not self.drag_moved
                consumed = self.ui.on_mouse_up(event.pos, was_click)
                if was_click and not consumed:
                    self.handle_map_click(event.pos[0], event.pos[1])
                self.dragging = False
                self._ui_press = False

        elif event.type == pygame.MOUSEMOTION:
            # A window being dragged takes priority over a camera pan.
            if self.ui.on_mouse_motion(event.rel, event.pos):
                self.drag_moved = True
            elif self.dragging and not self._ui_press:
                self.camera["x"] += event.rel[0] / self.camera["zoom"]
                self.camera["y"] += event.rel[1] / self.camera["zoom"]
                if abs(event.rel[0]) > 2 or abs(event.rel[1]) > 2:
                    self.drag_moved = True
            self.mouse["x"] = event.pos[0]
            self.mouse["y"] = event.pos[1]

    def run(self):
        # Fixed-timestep sim: the simulation always advances in FIXED_DT ticks,
        # and game speed simply runs more ticks per frame. This keeps physics /
        # collection deterministic and frame-rate independent, and lets high
        # speeds (5x/10x) scale truck throughput correctly rather than starving
        # it. Camera and UI still update once per frame on real dt.
        FIXED_DT = 1.0 / 60.0
        MAX_SUBSTEPS = 16          # hard cap so a stall can't spiral
        accumulator = 0.0
        while True:
            frame_dt = self.clock.tick(60) / 1000.0
            frame_dt = min(frame_dt, 0.1)      # clamp a hitch (avoid death spiral)
            for event in pygame.event.get():
                self._process_event(event)

            if self.state == "menu":
                self._step_backdrop(frame_dt)
                self.render()
                continue

            if self.state == "editor":
                self._step_editor(frame_dt)
                self.render()
                continue

            self._update_realtime(frame_dt)

            if self.running and not self.economy.has_lost:
                accumulator += frame_dt * self.speed
                steps = 0
                while accumulator >= FIXED_DT and steps < MAX_SUBSTEPS:
                    self._step_sim(FIXED_DT)
                    steps += 1
                    accumulator -= FIXED_DT
                    if self.economy.has_lost:
                        break
                if steps >= MAX_SUBSTEPS:
                    accumulator = 0.0          # drop the backlog we couldn't run
            else:
                accumulator = 0.0

            self.render()


if __name__ == "__main__":
    game = WasteCityGame()
    game.run()