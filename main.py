import pygame
import sys
from city import CityGenerator
from renderer import Renderer
from economy import Economy
from ui import UIManager
from fleet import FleetManager
from waste import WastePolicy

CITY_W = 60
CITY_H = 60


class WasteCityGame:
    def __init__(self):
        pygame.init()
        pygame.display.set_caption("The Rubbish Game")
        self.screen = pygame.display.set_mode((1280, 720), pygame.RESIZABLE)
        self.clock = pygame.time.Clock()

        self.running = True
        self.speed = 1
        self.last_time = 0

        self.camera = {"x": 0, "y": 0, "zoom": 1}
        self.dragging = False
        self.drag_moved = False
        self.mouse = {"x": 0, "y": 0}

        self.selected_tile = None
        self.hovered_tile = None
        self.planner_open = False
        self.planner_tab = "rounds"      # rounds | waste | fleet | finance | data
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

        self._center_camera()

    # ---------------------------------------------------------------- actions
    def _toggle_planner(self):
        self.planner_open = not self.planner_open

    def _toggle_areas(self):
        self.show_areas = not self.show_areas

    def _clear_and_regenerate(self):
        self.economy = Economy()
        self.waste = WastePolicy()
        self.fleet = FleetManager(self)
        self.city = CityGenerator(CITY_W, CITY_H)
        self.city.generate()
        self.fleet.setup_initial_fleet()
        self.clear_selection()
        self._center_camera()

    def set_toast(self, message):
        self.toast = message
        self.toast_timer = 4.0

    def open_planner_tab(self, tab):
        self.planner_tab = tab
        self.planner_open = True

    def _center_camera(self):
        """Frame the camera on the landfill site at start (falls back to the
        depot if no landfill exists)."""
        lf = getattr(self.city, "landfill", None)
        if lf:
            target = self.renderer.to_iso(lf["cx"], lf["cy"])
        else:
            target = self.renderer.to_iso(self.fleet.depot_x, self.fleet.depot_y)
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
    def handle_click(self, screen_x, screen_y):
        # Planner is modal — it takes all clicks until closed.
        if self.planner_open:
            self.ui.handle_planner_click((screen_x, screen_y))
            return

        if screen_x < 252:
            self.ui.handle_click((screen_x, screen_y))
            return

        coord = self.renderer.screen_to_tile(screen_x, screen_y,
                                               self.screen.get_width(),
                                               self.screen.get_height())
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
    def update(self, dt):
        # Simulation dt is scaled by game speed; UI/camera use real dt
        sim_dt = dt * self.speed

        # Camera movement from held keys
        if not self.planner_open:
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

        bin_mult = self.economy.get_bin_rate_multiplier() * self.waste.fill_multiplier()
        self.city.update(sim_dt, bin_mult)
        self.fleet.update(sim_dt)
        new_day = self.economy.update(sim_dt, self.city, self.fleet, self.waste)

        if new_day:
            # Deliver any vehicles that have arrived.
            delivered = self.fleet.process_deliveries(self.economy.day)
            if delivered:
                self.set_toast("Delivered: " + ", ".join(str(d) for d in delivered))
            # Once-per-day service-quality snapshot (one scan, not per frame).
            overflows = self.fleet.get_unscheduled_overflows()
            self.economy.register_day_quality(
                overflows, self.city.property_count,
                self.waste.satisfaction_ceiling())

        if self.economy.pending_event:
            self.ui.show_event(self.economy.pending_event)
            self.economy.pending_event = None

        if self.toast_timer > 0:
            self.toast_timer -= dt
            if self.toast_timer <= 0:
                self.toast = ""

        self.ui.update(dt)
        self._clamp_camera()

    # ----------------------------------------------------------------- render
    def render(self):
        self.screen.fill((22, 24, 30))
        w, h = self.screen.get_size()
        for i in range(0, h, 2):
            t = i / h
            g = int(40 + (22 - 40) * t)
            pygame.draw.line(self.screen, (g, g, int(g * 1.1)), (0, i), (w, i), 2)

        self.renderer.render(self.city, self.fleet, self.selected_tile,
                             self.economy.get_day_of_week(), self.show_areas,
                             self.hovered_tile)
        self.ui.draw(self.screen)
        pygame.display.flip()

    # ------------------------------------------------------------------- loop
    def run(self):
        while True:
            dt = self.clock.tick(60) / 1000.0

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    pygame.quit()
                    sys.exit()

                elif event.type == pygame.VIDEORESIZE:
                    self.screen = pygame.display.set_mode((event.w, event.h), pygame.RESIZABLE)
                    self.ui._setup_buttons()

                elif event.type == pygame.KEYDOWN:
                    tab_keys = {pygame.K_1: "rounds", pygame.K_2: "waste",
                                pygame.K_3: "fleet", pygame.K_4: "finance",
                                pygame.K_5: "data"}
                    if self.planner_open and event.key in tab_keys:
                        self.planner_tab = tab_keys[event.key]
                    elif event.key == pygame.K_TAB:
                        self.planner_open = not self.planner_open
                    elif event.key == pygame.K_g:
                        self.show_areas = not self.show_areas
                    elif event.key == pygame.K_ESCAPE:
                        if self.planner_open:
                            self.planner_open = False
                        else:
                            self.clear_selection()

                elif event.type == pygame.MOUSEBUTTONDOWN:
                    if event.button == 1:
                        self.dragging = True
                        self.drag_moved = False
                    elif event.button == 4:
                        self.camera["zoom"] = min(4, self.camera["zoom"] * 1.1)
                    elif event.button == 5:
                        self.camera["zoom"] = max(0.3, self.camera["zoom"] * 0.9)

                elif event.type == pygame.MOUSEBUTTONUP:
                    if event.button == 1 and self.dragging and not self.drag_moved:
                        self.handle_click(event.pos[0], event.pos[1])
                    self.dragging = False

                elif event.type == pygame.MOUSEMOTION:
                    if self.dragging and not self.planner_open:
                        self.camera["x"] += event.rel[0] / self.camera["zoom"]
                        self.camera["y"] += event.rel[1] / self.camera["zoom"]
                        if abs(event.rel[0]) > 2 or abs(event.rel[1]) > 2:
                            self.drag_moved = True
                    self.mouse["x"] = event.pos[0]
                    self.mouse["y"] = event.pos[1]

            if self.running:
                self.update(dt)
            self.render()


if __name__ == "__main__":
    game = WasteCityGame()
    game.run()