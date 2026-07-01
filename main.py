import pygame
import sys
from city import CityGenerator
from renderer import Renderer
from economy import Economy
from ui import UIManager
from fleet import FleetManager
from waste import WastePolicy
from ambient import AmbientState
import savegame

CITY_W = 60
CITY_H = 60


class WasteCityGame:
    def __init__(self):
        pygame.init()
        pygame.display.set_caption("The Rubbish Game")
        
        # Load and set the application icon
        try:
            icon = pygame.image.load("icon.ico")
            pygame.display.set_icon(icon)
        except pygame.error:
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

    # ---------------------------------------------------------------- actions
    def _toggle_areas(self):
        self.show_areas = not self.show_areas

    def _clear_and_regenerate(self):
        self.economy = Economy()
        self.waste = WastePolicy()
        self.fleet = FleetManager(self)
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
        self.screen.fill((22, 24, 30))
        w, h = self.screen.get_size()
        for i in range(0, h, 2):
            t = i / h
            g = int(40 + (22 - 40) * t)
            pygame.draw.line(self.screen, (g, g, int(g * 1.1)), (0, i), (w, i), 2)

        self.renderer.render(self.city, self.fleet, self.selected_tile,
                             self.economy.get_day_of_week(), self.show_areas,
                             self.hovered_tile, self.economy, self.ambient)
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