import math
from collections import deque

from procurement import get_vehicle, Order

# --- Tuning -----------------------------------------------------------------
SERVICE_FILL_THRESHOLD = 20      # default "worth emptying" %% (now a fleet lever)
TRUCK_SPEED = 11.0               # tiles / second (base, scaled by crew + model)
WORKER_SPEED = 9.0               # tiles / second (loaders, cosmetic)
PER_BIN_TIME = 0.10              # seconds per bin within a wave of loaders
STOP_BASE_TIME = 0.05            # fixed overhead per kerbside stop
TRUCK_CAPACITY = 18000           # default load before a trip to tip (fill units)
MAX_CREW = 4                     # absolute loader cap per RCV body
PER_LORRY_DAILY = 300            # rough bins one RCV clears per day (planner est.)
DEFAULT_MODEL = "standard"       # catalogue id used for the free starter fleet
ADJ = [(0, 1), (0, -1), (1, 0), (-1, 0)]
# Loaders walk up to 2 tiles from where the lorry stops (driveways / alleys).
REACH = [(dx, dy) for dx in range(-2, 3) for dy in range(-2, 3)
         if 0 < abs(dx) + abs(dy) <= 2]


class FleetManager:
    """Manages refuse collection vehicles (RCVs / bin lorries) that drive the
    road network round-by-round, and the loaders who empty the kerbside bins."""

    def __init__(self, game):
        self.game = game
        self.trucks = []             # "trucks" key kept; these are the lorries
        self.workers = 0             # total crew (loaders)
        self.depot_x = 5
        self.depot_y = 5

        self._road_tiles = set()
        self._roads_built_for = None

        self.claimed = set()         # bins reserved across the whole fleet
        self.collected_count = 0     # lifetime bins emptied (debug / stats)

        # Management levers / procurement.
        self.service_threshold = SERVICE_FILL_THRESHOLD  # editable routing lever
        self.orders = []             # vehicles on order awaiting delivery
        self._pending_volume = 0.0   # fill units tipped since economy last read

    # ------------------------------------------------------------ initial fleet
    def setup_initial_fleet(self, lorries=3, crew=6):
        """Give the council a starting fleet for free (no budget hit)."""
        for _ in range(lorries):
            self.purchase_truck(DEFAULT_MODEL)
        for _ in range(crew):
            self.hire_worker()

    # ------------------------------------------------------------------ roads
    def _ensure_road_graph(self):
        if self._roads_built_for is self.game.city:
            return
        roads = set()
        city = self.game.city
        for y in range(city.height):
            for x in range(city.width):
                if city.tiles[y][x].type == "road":
                    roads.add((x, y))
        self._road_tiles = roads
        self._roads_built_for = self.game.city

    def _is_road(self, x, y):
        return (x, y) in self._road_tiles

    # -------------------------------------------------------------- purchasing
    def purchase_truck(self, model_id=DEFAULT_MODEL, leased=False):
        """Spawn a lorry at the depot built from a catalogue model."""
        model = get_vehicle(model_id) or get_vehicle(DEFAULT_MODEL)
        self.trucks.append({
            "id": len(self.trucks) + 1,
            "x": float(self.depot_x),
            "y": float(self.depot_y),
            "model_id": model.id,
            "model_name": model.name,
            "capacity": float(model.capacity),
            "crew_cap": model.crew_cap,
            "speed_factor": model.speed_factor,
            "running_cost": model.running_cost,
            "lease_weekly": model.lease_weekly,
            "leased": leased,
            "load": 0.0,
            "crew": 0,
            "state": "depot",          # depot | to_stop | servicing | to_depot
            "area_id": -1,             # round this lorry is currently working
            "path": [],
            "claimed": set(),
            "bin_queue": [],
            "out_workers": [],
            "service_t": 0.0,
            "service_need": 0.0,
            "service_bins": [],
            "facing": 1,
        })
        return self.trucks[-1]

    def scrap_truck(self, truck_id):
        """Remove a lorry from the fleet (release any held bins first)."""
        for t in list(self.trucks):
            if t["id"] == truck_id:
                self._release_truck_claims(t)
                self.workers = max(0, self.workers - t["crew"])
                self.trucks.remove(t)
                return True
        return False

    # ------------------------------------------------------------ procurement
    def order_vehicle(self, model_id, leased=False):
        """Place an order. Returns (ok, cost, message). Does NOT charge budget;
        the caller (UI) handles affordability and deducts the up-front cost."""
        model = get_vehicle(model_id)
        if not model:
            return False, 0, "Unknown vehicle"
        cost = model.deposit() if leased else model.price
        order = Order(model, self.game.economy.day, leased)
        self.orders.append(order)
        tenure = "lease" if leased else "purchase"
        return True, cost, (f"{model.name} on {tenure}, arriving day "
                            f"{order.arrival_day}")

    def process_deliveries(self, day):
        """Called on each new day -- spawn any vehicles that have arrived."""
        delivered = []
        for o in list(self.orders):
            if day >= o.arrival_day:
                self.purchase_truck(o.vehicle.id, leased=o.leased)
                self.orders.remove(o)
                delivered.append(o.vehicle.name)
        return delivered

    def daily_vehicle_cost(self):
        """Per-day running + lease cost across the fleet (for the ledger)."""
        total = 0.0
        for t in self.trucks:
            if t.get("leased"):
                total += t["lease_weekly"] / 7.0
            else:
                total += t["running_cost"]
        return total

    def take_pending_volume(self):
        v = self._pending_volume
        self._pending_volume = 0.0
        return v

    def hire_worker(self):
        self.workers += 1
        for truck in self.trucks:
            if truck["crew"] < truck.get("crew_cap", MAX_CREW):
                truck["crew"] += 1
                break

    def fire_worker(self):
        """Release one crew member (taken from the most-crewed lorry first)."""
        if self.workers <= 0:
            return False
        self.workers -= 1
        best = None
        for truck in self.trucks:
            if truck["crew"] > 0 and (best is None or truck["crew"] > best["crew"]):
                best = truck
        if best:
            best["crew"] -= 1
        return True

    # ----------------------------------------------------------- bin queries
    def _today(self):
        return self.game.economy.get_day_of_week()

    def _week_index(self):
        return getattr(self.game.economy, "week_index", 0)

    def _bin_serviceable(self, x, y, today, area_id=None):
        tile = self.game.city.get_tile(x, y)
        if tile is None or tile.type in ("road", "green"):
            return False
        if tile.bin_fill <= self.service_threshold:
            return False
        area = self.game.city.get_area(tile.area_id)
        if area is None or not area.due_today(today, self._week_index()):
            return False
        if area_id is not None and tile.area_id != area_id:
            return False
        return True

    def _adjacent_serviceable_bins(self, rx, ry, today, area_id, skip_claimed=True):
        out = []
        for ox, oy in REACH:
            bx, by = rx + ox, ry + oy
            if self._bin_serviceable(bx, by, today, area_id):
                if skip_claimed and (bx, by) in self.claimed:
                    continue
                out.append((bx, by))
        return out

    # --------------------------------------------------------- round picking
    def _area_remaining(self, area_id, today):
        """Unclaimed, serviceable bins left in a round today."""
        city = self.game.city
        area = city.get_area(area_id)
        if not area:
            return 0
        count = 0
        for (x, y) in area.building_tiles:
            if (x, y) in self.claimed:
                continue
            if self._bin_serviceable(x, y, today, area_id):
                count += 1
        return count

    def _pick_area(self, truck):
        """Assign this lorry to the due round with the most outstanding work."""
        today = self._today()
        week = self._week_index()
        best, best_remaining = -1, 0
        for area in self.game.city.areas:
            if not area.due_today(today, week):
                continue
            remaining = self._area_remaining(area.id, today)
            if remaining > best_remaining:
                best, best_remaining = area.id, remaining
        truck["area_id"] = best
        return best if best != -1 else None

    def _maybe_mark_area_collected(self, area_id):
        """Stamp a round as serviced once nothing is left due today."""
        today = self._today()
        area = self.game.city.get_area(area_id)
        if area and self._area_remaining(area_id, today) == 0:
            # Only mark when genuinely cleared (no bins still over threshold).
            cleared = True
            for (x, y) in area.building_tiles:
                if self._bin_serviceable(x, y, today, area_id):
                    cleared = False
                    break
            if cleared:
                area.last_collected = self.game.economy.day

    # ------------------------------------------------------------- pathfinding
    def _bfs_route(self, start, goal_fn):
        if goal_fn(start):
            return []
        seen = {start}
        prev = {}
        q = deque([start])
        while q:
            cur = q.popleft()
            cx, cy = cur
            for ox, oy in ADJ:
                nb = (cx + ox, cy + oy)
                if nb in seen or not self._is_road(nb[0], nb[1]):
                    continue
                seen.add(nb)
                prev[nb] = cur
                if goal_fn(nb):
                    path = [nb]
                    p = cur
                    while p != start:
                        path.append(p)
                        p = prev[p]
                    path.reverse()
                    return path
                q.append(nb)
        return None

    def _truck_tile(self, truck):
        return (int(round(truck["x"])), int(round(truck["y"])))

    def _route_to_stop(self, truck):
        """Nearest road tile beside an unclaimed serviceable bin in this lorry's
        round. Reserves those bins and returns the path, or None if no work."""
        today = self._today()
        area_id = truck["area_id"]
        start = self._truck_tile(truck)

        def is_stop(t):
            return len(self._adjacent_serviceable_bins(t[0], t[1], today, area_id)) > 0

        path = self._bfs_route(start, is_stop)
        if path is None:
            return None
        stop = path[-1] if path else start
        bins = self._adjacent_serviceable_bins(stop[0], stop[1], today, area_id)
        if not bins:
            return None
        for b in bins:
            truck["claimed"].add(b)
            self.claimed.add(b)
        return path

    def _route_to_depot(self, truck):
        start = self._truck_tile(truck)
        depot = (self.depot_x, self.depot_y)
        return self._bfs_route(start, lambda t: t == depot)

    # --------------------------------------------------------------- movement
    @staticmethod
    def _move_towards(ent, tx, ty, speed, dt):
        dx, dy = tx - ent["x"], ty - ent["y"]
        dist = math.hypot(dx, dy)
        if dist < 1e-4:
            ent["x"], ent["y"] = tx, ty
            return True
        step = speed * dt
        if step >= dist:
            ent["x"], ent["y"] = tx, ty
            return True
        ent["x"] += dx / dist * step
        ent["y"] += dy / dist * step
        return False

    def _truck_speed(self, truck):
        cap = max(1, truck.get("crew_cap", MAX_CREW))
        crew_factor = 0.7 + 0.3 * (truck["crew"] / float(cap))
        return TRUCK_SPEED * truck.get("speed_factor", 1.0) * crew_factor

    def _follow_path(self, truck, dt):
        if not truck["path"]:
            return True
        tx, ty = truck["path"][0]
        if abs(tx - truck["x"]) > 1e-3:
            truck["facing"] = 1 if tx > truck["x"] else -1
        if self._move_towards(truck, tx, ty, self._truck_speed(truck), dt):
            truck["path"].pop(0)
        return len(truck["path"]) == 0

    # ----------------------------------------------------------------- claims
    def _release_bin(self, truck, b):
        truck["claimed"].discard(b)
        self.claimed.discard(b)

    def _release_truck_claims(self, truck):
        for b in list(truck["claimed"]):
            self.claimed.discard(b)
        truck["claimed"].clear()

    # ----------------------------------------------------------------- update
    def update(self, dt):
        self._ensure_road_graph()
        for truck in self.trucks:
            self._update_truck(truck, dt)

    def _update_truck(self, truck, dt):
        if truck["crew"] < 1:
            return  # no crew, no service

        state = truck["state"]

        if state == "depot":
            if self._pick_area(truck) is not None:
                route = self._route_to_stop(truck)
                if route is not None:
                    truck["path"] = route
                    truck["state"] = "to_stop"

        elif state == "to_stop":
            if self._follow_path(truck, dt):
                self._begin_servicing(truck)

        elif state == "servicing":
            self._service(truck, dt)

        elif state == "to_depot":
            if self._follow_path(truck, dt):
                truck["load"] = 0.0
                truck["state"] = "depot"

    def _begin_servicing(self, truck):
        today = self._today()
        # Tip first if we're nearly full.
        if truck["load"] >= truck["capacity"] * 0.95:
            self._release_truck_claims(truck)
            self._depart_to_depot(truck)
            return

        bins = [b for b in truck["claimed"]
                if self._bin_serviceable(b[0], b[1], today, truck["area_id"])]
        truck["service_bins"] = bins
        truck["service_t"] = 0.0
        crew = max(1, truck["crew"])
        waves = math.ceil(len(bins) / crew) if bins else 0
        truck["service_need"] = waves * PER_BIN_TIME + STOP_BASE_TIME

        # Spawn cosmetic loaders (visual only — throughput is driven by the timer).
        truck["out_workers"] = []
        for i in range(min(crew, len(bins))):
            bx, by = bins[i]
            truck["out_workers"].append({
                "x": truck["x"], "y": truck["y"],
                "bx": float(bx), "by": float(by),
                "state": "out", "carry": 0.0,
            })
        truck["state"] = "servicing"

    def _service(self, truck, dt):
        truck["service_t"] += dt
        frac = 1.0 if truck["service_need"] <= 0 else truck["service_t"] / truck["service_need"]

        # Animate the cosmetic loaders out to the kerb and back.
        for w in truck["out_workers"]:
            if frac < 0.5:
                w["state"] = "out"
                self._move_towards(w, w["bx"], w["by"], WORKER_SPEED, dt)
            else:
                w["state"] = "back"
                w["carry"] = 1.0
                self._move_towards(w, truck["x"], truck["y"], WORKER_SPEED, dt)

        if truck["service_t"] < truck["service_need"]:
            return

        # Stop complete — empty the bins (respecting capacity).
        for (bx, by) in truck["service_bins"]:
            tile = self.game.city.get_tile(bx, by)
            self._release_bin(truck, (bx, by))
            if tile is None:
                continue
            space = max(0.0, truck["capacity"] - truck["load"])
            if space <= 0:
                continue
            amt = min(tile.bin_fill, space)
            tile.bin_fill -= amt
            truck["load"] += amt
            if amt > 0:
                self.collected_count += 1
                self._pending_volume += amt
        truck["service_bins"] = []
        truck["out_workers"] = []

        # Decide what to do next.
        if truck["load"] >= truck["capacity"] * 0.95:
            self._depart_to_depot(truck)
            return
        route = self._route_to_stop(truck)
        if route is not None:
            truck["path"] = route
            truck["state"] = "to_stop"
            return
        if truck["area_id"] != -1:
            self._maybe_mark_area_collected(truck["area_id"])
        if self._pick_area(truck) is not None:
            route = self._route_to_stop(truck)
            if route is not None:
                truck["path"] = route
                truck["state"] = "to_stop"
                return
        self._depart_to_depot(truck)

    def _depart_to_depot(self, truck):
        truck["area_id"] = -1
        truck["out_workers"] = []
        truck["service_bins"] = []
        truck["path"] = self._route_to_depot(truck) or []
        truck["state"] = "to_depot"

    # ------------------------------------------------------------ UI metrics
    def get_total_full_bins(self):
        """Bins over 50% full AND due for collection today."""
        full_count = 0
        today = self._today()
        week = self._week_index()
        city = self.game.city
        for y in range(city.height):
            for x in range(city.width):
                tile = city.tiles[y][x]
                if tile.type in ("road", "green") or tile.bin_fill <= 50:
                    continue
                area = city.get_area(tile.area_id)
                if area and area.due_today(today, week):
                    full_count += 1
        return full_count

    def get_unscheduled_overflows(self):
        """Bins >85% full but NOT due today -- the player must act."""
        today = self._today()
        week = self._week_index()
        count = 0
        city = self.game.city
        for y in range(city.height):
            for x in range(city.width):
                tile = city.tiles[y][x]
                if tile.type in ("road", "green") or tile.bin_fill <= 85:
                    continue
                area = city.get_area(tile.area_id)
                if area and not area.due_today(today, week):
                    count += 1
        return count

    def get_today_demand(self):
        """Total serviceable bins due today (planner capacity check)."""
        today = self._today()
        week = self._week_index()
        count = 0
        city = self.game.city
        for area in city.areas:
            if not area.due_today(today, week):
                continue
            for (x, y) in area.building_tiles:
                t = city.tiles[y][x]
                if t.bin_fill > self.service_threshold:
                    count += 1
        return count

    def area_due_count(self, area_id):
        """Serviceable bins outstanding in a round right now (collections left)."""
        today = self._today()
        week = self._week_index()
        city = self.game.city
        area = city.get_area(area_id)
        if not area or not area.due_today(today, week):
            return 0
        count = 0
        for (x, y) in area.building_tiles:
            t = city.tiles[y][x]
            if t.bin_fill > self.service_threshold:
                count += 1
        return count

    def estimated_daily_capacity(self):
        active = sum(1 for t in self.trucks if t["crew"] >= 1)
        return active * PER_LORRY_DAILY

    def active_lorries(self):
        return sum(1 for t in self.trucks if t["crew"] >= 1)