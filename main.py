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
        pygame.display.set_caption("Waste Borough - UK Refuse Management Sim")
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
        self.planner_open = False
        self.planner_tab = "rounds"      # rounds | waste | fleet | finance | data
        self.show_areas = False

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

        # Menu bar state
        self.menu_bar_height = 28
        self.menu_items = []
        self.menu_open = False
        self.menu_item_rects = []
        self._setup_menu()

        self._center_camera()

    def _setup_menu(self):
        self.menu_font = pygame.font.SysFont("segoeui", 12)
        self.menu_hover_font = pygame.font.SysFont("segoeui", 12, bold=True)
        self.menu_items = [
            {"label": "Open Collection Planner", "action": self._toggle_planner},
            {"label": "Toggle Round Overlay (G)", "action": self._toggle_areas},
            {"label": "Clear and Regenerate", "action": self._clear_and_regenerate},
        ]

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
        # Focus camera on the depot location
        depot_iso = self.renderer.to_iso(self.fleet.depot_x, self.fleet.depot_y)
        sw, sh = self.screen.get_size()
        # Center the depot in the screen (accounting for the renderer's cy offset of 120)
        self.camera["x"] = -depot_iso[0] + (sw / 2) / self.camera["zoom"]
        self.camera["y"] = -depot_iso[1] + (sh / 2) / self.camera["zoom"] - 120

    def _clamp_camera(self):
        margin = 400
        max_iso_x = (self.city.width - self.city.height) * (self.renderer.tile_w / 2)
        max_iso_y = (self.city.width + self.city.height) * (self.renderer.tile_h / 2)
        self.camera["x"] = max(-max_iso_x - margin, min(margin, self.camera["x"]))
        self.camera["y"] = max(-max_iso_y - margin, min(margin, self.camera["y"]))

    # ----------------------------------------------------------------- clicks
    def handle_click(self, screen_x, screen_y):
        # Planner is modal — it takes all clicks until closed.
        if self.planner_open:
            self.ui.handle_planner_click((screen_x, screen_y))
            return

        if screen_y < self.menu_bar_height:
            self._handle_menu_click(screen_x, screen_y)
            return

        if self.menu_open:
            self.menu_open = False
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

    def _handle_menu_click(self, screen_x, screen_y):
        debug_btn_rect = pygame.Rect(4, 2, 60, self.menu_bar_height - 4)
        if not self.menu_open and debug_btn_rect.collidepoint(screen_x, screen_y):
            self.menu_open = True
            return
        if self.menu_open:
            for i, item_rect in enumerate(self.menu_item_rects):
                if item_rect.collidepoint(screen_x, screen_y):
                    self.menu_items[i]["action"]()
                    self.menu_open = False
                    return
            self.menu_open = False

    def clear_selection(self):
        self.selected_tile = None

    # ----------------------------------------------------------------- update
    def update(self, dt):
        bin_mult = self.economy.get_bin_rate_multiplier() * self.waste.fill_multiplier()
        self.city.update(dt, bin_mult)
        self.fleet.update(dt)
        new_day = self.economy.update(dt, self.city, self.fleet, self.waste)

        if new_day:
            # Deliver any vehicles that have arrived.
            delivered = self.fleet.process_deliveries(self.economy.day)
            if delivered:
                self.set_toast("Delivered: " + ", ".join(delivered))
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
                             self.economy.get_day_of_week(), self.show_areas)
        self.ui.draw(self.screen)
        self._draw_menu_bar()
        pygame.display.flip()

    def _draw_menu_bar(self):
        w = self.screen.get_width()
        pygame.draw.rect(self.screen, (24, 24, 24), pygame.Rect(0, 0, w, self.menu_bar_height))
        pygame.draw.line(self.screen, (96, 96, 96), (0, self.menu_bar_height), (w, self.menu_bar_height), 1)

        mouse_pos = pygame.mouse.get_pos()
        debug_btn_rect = pygame.Rect(4, 2, 60, self.menu_bar_height - 4)
        is_hovered = debug_btn_rect.collidepoint(mouse_pos) or self.menu_open
        if is_hovered:
            pygame.draw.rect(self.screen, (54, 54, 54), debug_btn_rect)
        text = self.menu_hover_font.render("Menu", True, (240, 240, 240)) if is_hovered \
            else self.menu_font.render("Menu", True, (180, 180, 180))
        self.screen.blit(text, text.get_rect(center=debug_btn_rect.center))

        # Status hint on the right of the bar
        hint = self.menu_font.render(
            f"Round overlay: {'ON' if self.show_areas else 'off'}   |   Tab = planner",
            True, (140, 140, 140))
        self.screen.blit(hint, (w - hint.get_width() - 10, 8))

        if self.menu_open:
            self._draw_menu_dropdown()

    def _draw_menu_dropdown(self):
        menu_x = 4
        menu_y = self.menu_bar_height
        menu_w = 220
        item_h = 26
        menu_h = len(self.menu_items) * item_h + 8

        pygame.draw.rect(self.screen, (32, 32, 32), pygame.Rect(menu_x, menu_y, menu_w, menu_h))
        pygame.draw.rect(self.screen, (96, 96, 96), pygame.Rect(menu_x, menu_y, menu_w, menu_h), 1)

        mouse_pos = pygame.mouse.get_pos()
        self.menu_item_rects = []
        for i, item in enumerate(self.menu_items):
            item_rect = pygame.Rect(menu_x + 4, menu_y + 4 + i * item_h, menu_w - 8, item_h)
            self.menu_item_rects.append(item_rect)
            is_hovered = item_rect.collidepoint(mouse_pos)
            if is_hovered:
                pygame.draw.rect(self.screen, (66, 66, 66), item_rect)
            text = self.menu_hover_font.render(item["label"], True, (245, 245, 245)) if is_hovered \
                else self.menu_font.render(item["label"], True, (200, 200, 200))
            self.screen.blit(text, (item_rect.x + 8, item_rect.y + 4))

    # ------------------------------------------------------------------- loop
    def run(self):
        while True:
            dt = self.clock.tick(60) / 1000.0 * self.speed

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    pygame.quit()
                    sys.exit()

                elif event.type == pygame.VIDEORESIZE:
                    self.screen = pygame.display.set_mode((event.w, event.h), pygame.RESIZABLE)
                    self.ui._setup_buttons()

                elif event.type == pygame.KEYDOWN:
                    speed = 35 / self.camera["zoom"]
                    tab_keys = {pygame.K_1: "rounds", pygame.K_2: "waste",
                                pygame.K_3: "fleet", pygame.K_4: "finance",
                                pygame.K_5: "data"}
                    if self.planner_open and event.key in tab_keys:
                        self.planner_tab = tab_keys[event.key]
                    elif event.key == pygame.K_w:
                        self.camera["y"] += speed
                    elif event.key == pygame.K_s:
                        self.camera["y"] -= speed
                    elif event.key == pygame.K_a:
                        self.camera["x"] += speed
                    elif event.key == pygame.K_d:
                        self.camera["x"] -= speed
                    elif event.key == pygame.K_TAB:
                        self.planner_open = not self.planner_open
                    elif event.key == pygame.K_g:
                        self.show_areas = not self.show_areas
                    elif event.key == pygame.K_ESCAPE:
                        if self.planner_open:
                            self.planner_open = False
                        elif self.menu_open:
                            self.menu_open = False
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
