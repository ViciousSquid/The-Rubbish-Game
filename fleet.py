import math
import random
from collections import deque

import wastestreams
import congestion
from procurement import get_vehicle, Order, get_tier

# --- Tuning -----------------------------------------------------------------
SERVICE_FILL_THRESHOLD = 20      # default "worth emptying" %% (now a fleet lever)
# --- Vehicle ageing / reliability -------------------------------------------
# Lorries wear out. Daily running cost climbs with age, and the daily chance of
# an age-related breakdown rises sharply once a vehicle is a few years old, so
# running a lorry forever is a false economy -- you have to plan replacements.
DAYS_PER_YEAR        = 112       # one council year (matches economy season cycle)
WEAR_COST_PER_YEAR   = 0.16      # +16% running cost per year of age
WEAR_COST_CAP        = 1.20      # never more than +120% over base
BREAKDOWN_BASE       = 0.003     # daily breakdown chance for a near-new lorry
BREAKDOWN_LINEAR     = 0.007     # added per year of age
BREAKDOWN_QUAD       = 0.0035    # added per year^2 of age
BREAKDOWN_CAP        = 0.060     # hard ceiling on daily breakdown chance
REPAIR_DAYS_MIN      = 2
REPAIR_DAYS_MAX      = 5
# --- Usage-based wear weights (Phase 3) -------------------------------------
# Combine the running usage totals into one "load" figure. NORMAL_USAGE_PER_YEAR
# is what that figure reaches per council year for a typical, well-utilised
# lorry, so usage_factor() sits near 1.0 for normal use and the classic
# age-based breakdown balance is preserved; harder use pushes it up.
USAGE_MILEAGE_W  = 1.0 / 1000.0   # per tile driven
USAGE_HOURS_W    = 1.0 / 200.0    # per second in service
USAGE_CYCLE_W    = 2.0            # per tip / compaction cycle
USAGE_OVERLOAD_W = 6.0            # per overload event (extra stress)
NORMAL_USAGE_PER_YEAR = 220.0    # measured normal annual usage load (see tests)
TRUCK_SPEED = 11.0               # tiles / second (base, scaled by crew + model)
WORKER_SPEED = 9.0               # tiles / second (loaders, cosmetic)
PER_BIN_TIME = 0.10              # seconds per bin within a wave of loaders
STOP_BASE_TIME = 0.05            # fixed overhead per kerbside stop
LOAD_TIME_PER_FILL = 0.00045     # extra service seconds per fill-% presented
# Disposal (tip) service time: weigh-in, queue, tipping, manoeuvre out. A dwell
# timer at the facility so disposal trips cost real time in route planning.
TIP_BASE_TIME = 0.55             # fixed weigh-in / manoeuvre dwell (seconds)
TIP_TIME_PER_LOAD = 0.00004      # extra tip seconds per unit of load volume
# --- Electric RCV battery / range (Phase 4) ---------------------------------
# An eRCV runs a normal day on one charge and tops up overnight at the depot,
# but a long/heavy round drains it and forces a mid-shift charge — lost
# collection time is the price of the cheap running cost. Cold weather cuts
# range. Diesel lorries ignore all of this.
EV_DRAIN_PER_TILE = 1.0 / 300.0  # battery fraction drained per tile driven
EV_COLD_DRAIN_MULT = 1.5         # winter/snow drains the pack faster
EV_LOW_BATTERY = 0.12            # below this, divert to the depot to charge
EV_CHARGE_TIME = 6.0             # seconds dwell to recharge at the depot
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
        # Per-stream disposal mass tipped since the economy last read it
        # (residual, recycling, food, garden) plus the recycling mass rejected
        # as contaminated. Drives stream-accurate gate fees / diversion.
        self._pending_streams = [0.0, 0.0, 0.0, 0.0]
        self._pending_reject = 0.0
        # Per-area due-stream mask cache, rebuilt each update tick.
        self._due_cache = {}

        # Rental tracking for budget impact
        self.rental_daily_cost = 0.0  # accumulated rental costs per day

        # Event state
        self.on_strike = False       # True while a crew strike event is active

        # Ambient road congestion (slows lorries in busy areas / near road works).
        self.traffic = congestion.TrafficField()

    # ------------------------------------------------------------ initial fleet
    def setup_initial_fleet(self, lorries=None, crew=None):
        """Spawn the council's starting fleet. No direct cash hit here -- the
        vehicles are financed by the startup loan held in the Economy, which is
        paid back daily with interest (see economy.StartupLoan).

        Fleet size, crew headcount and vehicle age come from the economy's
        difficulty preset (explicit arguments override it): a comfortable
        borough starts with new lorries, a crisis borough inherits a small,
        high-mileage fleet that costs more to run and breaks down often."""
        eco = getattr(self.game, "economy", None)
        if lorries is None:
            lorries = getattr(eco, "start_lorries", 4)
        if crew is None:
            crew = getattr(eco, "start_crew", 16)
        age_years = getattr(eco, "fleet_age_years", 0.0)

        for i in range(lorries):
            truck = self.purchase_truck(DEFAULT_MODEL)
            if age_years > 0:
                # Medium hands over a half-worn fleet (every second lorry is
                # aged); hard wears the whole fleet, with per-vehicle jitter so
                # they don't all fall apart in the same week.
                whole_fleet_worn = age_years >= 4.0
                if whole_fleet_worn or i % 2 == 1:
                    jitter = random.uniform(0.80, 1.15)
                    truck["age_days"] = int(age_years * DAYS_PER_YEAR * jitter)
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
        if (x, y) in self._road_tiles:
            # Road works block this tile for vehicles
            rw = getattr(self.game.city, "road_works_tiles", None)
            if rw and (x, y) in rw:
                return False
            return True
        return False

    # -------------------------------------------------------------- purchasing
    def purchase_truck(self, model_id=DEFAULT_MODEL, leased=False, tier_id="dealer"):
        """Spawn a lorry at the depot built from a catalogue model."""
        model = get_vehicle(model_id) or get_vehicle(DEFAULT_MODEL)
        tier = get_tier(tier_id)

        # Apply tier-specific cost adjustments
        running_cost = model.running_cost
        if tier:
            running_cost = model.get_running_cost_for_tier(tier_id)

        truck = {
            "id": len(self.trucks) + 1,
            "nickname": f"L{len(self.trucks) + 1}",
            "x": float(self.depot_x),
            "y": float(self.depot_y),
            "model_id": model.id,
            "model_name": model.name,
            "capacity": float(model.capacity),
            "crew_cap": model.crew_cap,
            "speed_factor": model.speed_factor,
            "running_cost": running_cost,
            "lease_weekly": model.lease_weekly,
            "leased": leased,
            "tier_id": tier_id,
            "load": 0.0,                # truck body volume in use (vs capacity)
            "load_streams": [0.0, 0.0, 0.0, 0.0],  # mass onboard per stream
            "load_reject": 0.0,         # recycling mass flagged contaminated
            "crew": 0,
            "state": "depot",          # depot | to_stop | servicing | to_depot
            "area_id": -1,             # round this lorry is currently working
            "preferred_area": -1,      # round pinned via the Fleet sheet (-1 = auto)
            "path": [],
            "claimed": set(),
            "bin_queue": [],
            "out_workers": [],
            "service_t": 0.0,
            "service_need": 0.0,
            "service_bins": [],
            "facing": 1,
            # --- ageing / reliability ---
            "age_days": 0,            # in-service age, ticked once per day
            "broken": False,          # out of action awaiting repair
            "repair_days": 0,         # days left in the repair bay
            # --- usage-based wear (Phase 3): a hard-worked young lorry can be
            # less reliable than an old lightly-used one. Compact running totals,
            # not history. ---
            "mileage": 0.0,           # tiles driven in service
            "op_hours": 0.0,          # seconds spent in active (non-depot) states
            "load_cycles": 0,         # number of tips (compactor/hydraulic cycles)
            "overload": 0,            # times tipped while near/over capacity
            "maint_deferred": 0,      # days maintenance has been skipped (unused hook)
            # --- crew productivity & fatigue (Phase 3) ---
            "crew_experience": 0.45,  # 0..1, grows with days worked
            "fatigue": 0.0,           # 0..1, rises on heavy/overtime days
            "work_today": 0.0,        # fraction of today spent working
            # --- electric range (only meaningful for the eRCV) ---
            "battery": 1.0,           # 0..1 state of charge
        }
        self.trucks.append(truck)
        return truck

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
    def order_vehicle(self, model_id, tier_id="dealer", leased=False):
        """Place an order through a procurement tier. Returns (ok, cost, message).
        Does NOT charge budget; the caller (UI) handles affordability."""
        model = get_vehicle(model_id)
        if not model:
            return False, 0, "Unknown vehicle"

        tier = get_tier(tier_id)
        if not tier:
            return False, 0, "Unknown procurement tier"

        # Current procurement-market conditions (shortage/glut/battery) modify
        # both price and lead time; rentals are spot-hire and shrug it off.
        price_mult, lead_mult = self.game.economy.procurement_mods(model_id)

        # Calculate cost based on tier, then the market.
        if leased:
            cost = model.deposit()
        else:
            cost = model.get_price_for_tier(tier_id)
        if tier_id != "rental":
            cost = int(cost * price_mult)

        order = Order(model, self.game.economy.day, tier_id, leased=leased)
        # Stretch (or shorten) the quoted delivery by the market lead multiplier.
        if tier_id != "rental" and abs(lead_mult - 1.0) > 1e-6:
            base_days = order.arrival_day - order.order_day
            new_days = max(1, int(round(base_days * lead_mult)))
            order.arrival_day = order.order_day + new_days
            order.quoted_arrival = order.arrival_day
        self.orders.append(order)

        tier_name = tier.display_name
        arrival = order.arrival_day
        msg = f"{model.name} ordered via {tier_name}, arriving day {arrival}"
        mkt = self.game.economy.procurement_market_info()
        if self.game.economy.procurement_market != "normal" and tier_id != "rental":
            msg += f" [{mkt['label']}]"

        if order.event_name:
            msg += f" (\u26a0 {order.event_name}: +{order.event_delay_days} days)"

        if tier_id == "rental":
            msg += f" — Emergency rental at £{order.adjusted_running_cost}/day!"

        return True, cost, msg

    def process_deliveries(self, day):
        """Called on each new day -- spawn any vehicles that have arrived."""
        delivered = []
        events_triggered = []

        for o in list(self.orders):
            # Check for procurement events triggering during the wait
            if o.tier_id == "dealer" and o.pending_event and not o.event_triggered:
                event = o.trigger_event_if_due(day)
                if event:
                    events_triggered.append(event)

            if day >= o.arrival_day:
                truck = self.purchase_truck(o.vehicle.id, leased=o.leased, tier_id=o.tier_id)
                # Apply rental-specific running cost
                if o.is_rental:
                    truck["running_cost"] = o.adjusted_running_cost
                self.orders.remove(o)
                delivered.append(o.vehicle.name)

        return delivered, events_triggered

    def daily_vehicle_cost(self, fuel_index=1.0, fuel_fraction=0.54):
        """Per-day running + lease cost across the fleet (for the ledger).

        The diesel portion of each owned/rental lorry's running cost is scaled
        by the current pump-price index, so a spike at the forecourt shows up
        as a real daily hit. Electric RCVs (model id 'electric') are immune —
        that's the whole point of paying the premium for one. Leased vehicles
        bill a flat weekly charge and aren't fuel-adjusted here."""
        total = 0.0
        for t in self.trucks:
            if t.get("leased"):
                total += t["lease_weekly"] / 7.0
                continue
            running = t["running_cost"] * self.wear_factor(t)
            if t.get("model_id") == "electric":
                total += running
            else:
                fuel = running * fuel_fraction
                rest = running - fuel
                total += rest + fuel * fuel_index
        return total

    def get_rental_costs(self):
        """Return total daily rental costs for active rental trucks."""
        total = 0.0
        for t in self.trucks:
            if t.get("tier_id") == "rental":
                total += t.get("running_cost", 0)
        return total

    def get_pending_orders_summary(self):
        """Return a list of human-readable order status strings."""
        today = self.game.economy.day
        summaries = []
        for o in self.orders:
            summaries.append(o.get_status_text(today))
        return summaries

    def take_pending_volume(self):
        v = self._pending_volume
        self._pending_volume = 0.0
        return v

    def take_pending_streams(self):
        """Return and clear the per-stream disposal mass tipped since the last
        read: ``(masses[4], reject_mass, total_mass)``. ``masses`` is the mass
        of each stream sent for disposal; ``reject_mass`` is the recycling mass
        already flagged contaminated at collection (rejected at the MRF)."""
        masses = self._pending_streams
        reject = self._pending_reject
        self._pending_streams = [0.0, 0.0, 0.0, 0.0]
        self._pending_reject = 0.0
        total = masses[0] + masses[1] + masses[2] + masses[3]
        return masses, reject, total

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

    # ------------------------------------------------- spreadsheet management
    def get_truck(self, truck_id):
        for t in self.trucks:
            if t["id"] == truck_id:
                return t
        return None

    def set_fleet_crew(self, distribution):
        """Redistribute the EXISTING crew pool across lorries to match the
        desired per-lorry counts from the Fleet sheet. Never hires or fires
        (that is the Staff target's job) -- it only reassigns who rides where,
        honouring each lorry's crew_cap and the total headcount available.

        `distribution` maps truck_id -> desired crew. Trucks not mentioned keep
        their current allocation if the pool allows. Returns the number of
        lorries whose crew changed."""
        before = {t["id"]: t["crew"] for t in self.trucks}

        # Desired (clamped to cap); default to current for unmentioned lorries.
        desired = {}
        for t in self.trucks:
            want = distribution.get(t["id"], t["crew"])
            try:
                want = int(want)
            except (TypeError, ValueError):
                want = t["crew"]
            cap = int(t.get("crew_cap", MAX_CREW))
            desired[t["id"]] = max(0, min(cap, want))

        # Hand out crew greedily against the available pool.
        pool = self.workers
        for t in self.trucks:
            give = min(desired[t["id"]], pool)
            t["crew"] = give
            pool -= give
        # Any leftover crew (pool > 0) stays idle but still on the books.

        return sum(1 for t in self.trucks if t["crew"] != before[t["id"]])

    def assign_truck_area(self, truck_id, area_id):
        """Pin a lorry to a round (-1 = automatic). Returns True if applied."""
        t = self.get_truck(truck_id)
        if not t:
            return False
        t["preferred_area"] = int(area_id)
        return True

    # ----------------------------------------------------------- bin queries
    def _today(self):
        return self.game.economy.get_day_of_week()

    def _week_index(self):
        return getattr(self.game.economy, "week_index", 0)

    def _bin_serviceable(self, x, y, today, area_id=None):
        tile = self.game.city.get_tile(x, y)
        if tile is None or tile.type in ("road", "green", "landfill"):
            return False
        area = self.game.city.get_area(tile.area_id)
        if area is None or not area.due_today(today, self._week_index()):
            return False
        if area_id is not None and tile.area_id != area_id:
            return False
        # Serviceable only if a stream that is actually LIFTED this visit is over
        # threshold. A property whose only full bin is a fortnightly stream not
        # due this week is left alone (its bin_fill stays high, so it can still
        # overflow and complain — that's the missed-collection consequence).
        s = getattr(tile, "streams", None)
        if s is None:
            return tile.bin_fill > self.service_threshold
        due = self._due_mask(area)
        thr = self.service_threshold
        for i in range(wastestreams.STREAM_COUNT):
            if due[i] and s[i] > thr:
                return True
        return False

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
        """Assign this lorry to a round to work. If the player has pinned this
        lorry to a round (via the Fleet sheet) and that round still has work
        due today, honour it; otherwise pick the due round with the most
        outstanding work."""
        today = self._today()
        week = self._week_index()

        pref = truck.get("preferred_area", -1)
        if pref is not None and pref >= 0:
            area = self.game.city.get_area(pref)
            if area and area.due_today(today, week) \
                    and self._area_remaining(pref, today) > 0:
                truck["area_id"] = pref
                return pref

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
        speed = TRUCK_SPEED * truck.get("speed_factor", 1.0) * crew_factor
        # Ambient congestion at the truck's current tile slows driving.
        tx, ty = self._truck_tile(truck)
        speed *= self.traffic.speed_factor(tx, ty)
        return speed

    def crew_productivity(self, truck):
        """0-ish..~1.25 multiplier on how quickly a crew works a stop, from
        experience, borough morale, fatigue, vehicle condition and weather.
        Experienced, rested crews on a sound lorry in fair weather are faster and
        more reliable; a fatigued crew on a clapped-out lorry in the rain crawls.
        Returns a *productivity* (higher = faster); callers invert it for time."""
        exp = truck.get("crew_experience", 0.45)      # 0..1
        fatigue = truck.get("fatigue", 0.0)           # 0..1
        eco = getattr(self.game, "economy", None)
        morale = (getattr(eco, "worker_morale", 70.0) / 100.0) if eco else 0.7
        cond = self.condition_pct(truck) / 100.0      # 0..1
        prod = 0.72 + 0.40 * exp                       # inexperienced ~0.72, veteran ~1.12
        prod *= 0.85 + 0.25 * morale                   # low morale drags
        prod *= 1.0 - 0.22 * fatigue                   # tired crews slow
        prod *= 0.9 + 0.15 * cond                      # a rattly lorry hampers loading
        if eco is not None:
            w = getattr(eco, "weather", "dry")
            if w == "rain":
                prod *= 0.90
            elif w == "snow":
                prod *= 0.82
        return max(0.35, prod)

    def _follow_path(self, truck, dt):
        # Spend the whole tick's movement budget, crossing as many path nodes as
        # it reaches. Popping only one node per call (the old behaviour) capped a
        # truck at one node per frame, so at high game speed sim-time advanced
        # but collection throughput did not -- trucks fell behind. Consuming the
        # full budget here makes throughput scale with dt (and with sub-steps).
        if not truck["path"]:
            return True
        budget = self._truck_speed(truck) * dt
        moved = 0.0
        while truck["path"] and budget > 1e-9:
            tx, ty = truck["path"][0]
            if abs(tx - truck["x"]) > 1e-3:
                truck["facing"] = 1 if tx > truck["x"] else -1
            dx, dy = tx - truck["x"], ty - truck["y"]
            dist = math.hypot(dx, dy)
            if dist <= budget:
                truck["x"], truck["y"] = tx, ty
                truck["path"].pop(0)
                budget -= dist
                moved += dist
            else:
                truck["x"] += dx / dist * budget
                truck["y"] += dy / dist * budget
                moved += budget
                budget = 0.0
        # Accumulate mileage for usage-based wear.
        truck["mileage"] = truck.get("mileage", 0.0) + moved
        # Electric lorries drain their battery as they drive (faster in the cold).
        if moved and truck.get("model_id") == "electric":
            eco = getattr(self.game, "economy", None)
            cold = EV_COLD_DRAIN_MULT if (eco and getattr(eco, "weather", "dry")
                                          in ("snow",)) else 1.0
            if eco and eco.season_name() == "Winter":
                cold = max(cold, 1.3)
            truck["battery"] = max(0.0, truck.get("battery", 1.0)
                                   - moved * EV_DRAIN_PER_TILE * cold)
        return len(truck["path"]) == 0

    # ----------------------------------------------------------------- claims
    def _release_bin(self, truck, b):
        truck["claimed"].discard(b)
        self.claimed.discard(b)

    def _release_truck_claims(self, truck):
        for b in list(truck["claimed"]):
            self.claimed.discard(b)
        truck["claimed"].clear()

    # ------------------------------------------------------------- ageing
    def wear_factor(self, truck):
        """Running-cost multiplier from age (1.0 when new, up to 1+CAP)."""
        years = truck.get("age_days", 0) / DAYS_PER_YEAR
        return 1.0 + min(WEAR_COST_CAP, years * WEAR_COST_PER_YEAR)

    def usage_metric(self, truck):
        """Raw combined usage load: mileage + operating hours + compaction cycles
        + overloads. Tracked as running totals (not history), so it's cheap."""
        return (truck.get("mileage", 0.0) * USAGE_MILEAGE_W
                + truck.get("op_hours", 0.0) * USAGE_HOURS_W
                + truck.get("load_cycles", 0) * USAGE_CYCLE_W
                + truck.get("overload", 0) * USAGE_OVERLOAD_W)

    def usage_factor(self, truck):
        """How hard a lorry has been worked *relative to its age*. ~1.0 for a
        normally-used vehicle (so the classic age balance is preserved), above
        1.0 for one run into the ground, below for one that's barely turned a
        wheel. This is what lets an old, lightly-used lorry outlast a young,
        hard-driven one."""
        age = max(0.12, truck.get("age_days", 0) / DAYS_PER_YEAR)
        expected = age * NORMAL_USAGE_PER_YEAR
        if expected <= 0:
            return 1.0
        return max(0.55, min(1.8, self.usage_metric(truck) / expected))

    def breakdown_chance(self, truck):
        """Daily probability this lorry breaks down. Driven by age *and* how hard
        it's been worked (mileage/hours/load-cycles/overloads), plus a small
        fatigue contribution (tired crews cause incidents)."""
        years = truck.get("age_days", 0) / DAYS_PER_YEAR
        chance = BREAKDOWN_BASE + BREAKDOWN_LINEAR * years + BREAKDOWN_QUAD * years * years
        chance *= self.usage_factor(truck)
        chance += 0.004 * truck.get("fatigue", 0.0)   # fatigue-driven incidents
        if truck.get("model_id") == "electric":
            chance *= 0.70            # fewer moving parts, gentler wear
        return min(BREAKDOWN_CAP, chance)

    def condition_pct(self, truck):
        """Headline 0-100 'condition' for the UI. New ~100, falls with age and,
        more so, with heavy use."""
        years = truck.get("age_days", 0) / DAYS_PER_YEAR
        uf = self.usage_factor(truck)
        return max(8.0, 100.0 - years * 12.0 * (0.6 + 0.55 * uf))

    def condition_label(self, truck):
        c = self.condition_pct(truck)
        if c >= 80: return "Pristine"
        if c >= 60: return "Good"
        if c >= 40: return "Worn"
        if c >= 22: return "Tired"
        return "Clapped-out"

    def repair_bill(self, truck):
        """Cost of an age-related breakdown repair (worse on older vehicles)."""
        years = truck.get("age_days", 0) / DAYS_PER_YEAR
        base = 800 + 600 * years + truck.get("running_cost", 130) * 4
        return int(min(28000, base))

    def weighted_breakdown_target(self):
        """Pick a working lorry to break down, biased toward the least reliable
        (oldest) vehicles. Used by the event-driven breakdown so failures land
        on worn lorries, not pristine ones. Returns a truck or None."""
        cands = [t for t in self.trucks if t["crew"] >= 1 and not t.get("broken")]
        if not cands:
            return None
        weights = [self.breakdown_chance(t) + 0.001 for t in cands]
        return random.choices(cands, weights=weights, k=1)[0]

    def age_fleet(self):
        """Advance the fleet one day: age every vehicle, progress repairs, and
        roll age-related breakdowns. Repair bills are charged immediately to the
        economy. Returns a list of notice dicts (for the UI event banner)."""
        notices = []
        eco = getattr(self.game, "economy", None)
        for t in self.trucks:
            t["age_days"] = t.get("age_days", 0) + 1

            # --- Crew fatigue & experience (Phase 3) --------------------------
            # A heavy/overtime day (worked most of the shift) builds fatigue; a
            # light day lets the crew recover. Overtime buys throughput today at
            # the cost of a slower, less reliable crew tomorrow. Experience
            # accrues slowly with days actually worked.
            work = t.get("work_today", 0.0)
            fatigue = t.get("fatigue", 0.0)
            # Only a genuinely long shift (past a normal day) builds fatigue; a
            # fleet with enough capacity finishes early and the crew recovers, so
            # fatigue signals an over-stretched operation.
            if work > 0.82:
                fatigue += min(0.28, (work - 0.82) * 0.8)
            else:
                fatigue -= 0.22
            t["fatigue"] = max(0.0, min(1.0, fatigue))
            if work > 0.08 and t.get("crew", 0) >= 1:
                t["crew_experience"] = min(
                    1.0, t.get("crew_experience", 0.45) + 0.02)
            t["work_today"] = 0.0

            # eRCVs charge overnight at the depot, so most days start full; only
            # a lorry stranded mid-round (rare) misses the top-up.
            if t.get("model_id") == "electric" and t.get("state") == "depot":
                t["battery"] = 1.0

            # Vehicles in the repair bay count down to roadworthy again. Only
            # age-related breakdowns carry a repair_days countdown; event-driven
            # breakdowns (repair_days == 0) are recovered by the event system,
            # so we must leave those alone here.
            if t.get("broken"):
                if t.get("repair_days", 0) > 0:
                    t["repair_days"] -= 1
                    if t["repair_days"] <= 0:
                        t["broken"] = False
                        notices.append({
                            "name": "Repair Complete",
                            "desc": f"{t.get('nickname', 'L' + str(t['id']))} is "
                                    f"back on the road after servicing.",
                            "effect": "repairDone",
                        })
                continue

            # Healthy, crewed lorries can break down from wear.
            if t["crew"] >= 1 and random.random() < self.breakdown_chance(t):
                dur = random.randint(REPAIR_DAYS_MIN, REPAIR_DAYS_MAX)
                t["broken"] = True
                t["repair_days"] = dur
                t["path"] = []
                t["state"] = "depot"
                self._release_truck_claims(t)
                bill = self.repair_bill(t)
                if eco is not None:
                    eco.budget -= bill
                    eco.ledger["repairs"] = eco.ledger.get("repairs", 0.0) + bill
                cause = ("hard use" if self.usage_factor(t) > 1.2
                         else "age" if t.get("age_days", 0) > DAYS_PER_YEAR * 2
                         else "wear")
                notices.append({
                    "name": "Vehicle Breakdown",
                    "desc": f"{t.get('nickname', 'L' + str(t['id']))} "
                            f"({t.get('model_name', 'RCV')}) has broken down "
                            f"({cause}) -- out for {dur} day"
                            f"{'s' if dur != 1 else ''}. Repair bill £{bill:,}.",
                    "effect": "truckBreakdown",
                })
        return notices

    # ----------------------------------------------------------------- update
    def update(self, dt):
        if self.on_strike:
            return   # crews refuse to work — no trucks move
        self._ensure_road_graph()
        # Refresh the ambient congestion field (cheap; mostly cached).
        self.traffic.update(dt, self.game.city,
                            getattr(self.game, "economy", None), self)
        # Which streams are lifted this week is constant across the tick; cache
        # per area and recompute lazily (week/policy can shift between ticks).
        self._due_cache = {}
        for truck in self.trucks:
            self._update_truck(truck, dt)

    def _due_mask(self, area):
        """Cached per-area mask of streams that get lifted on this week's visit."""
        m = self._due_cache.get(area.id)
        if m is None:
            m = wastestreams.due_streams(self.game.waste, area, self._week_index())
            self._due_cache[area.id] = m
        return m

    def _update_truck(self, truck, dt):
        if truck["crew"] < 1:
            return  # no crew, no service
        if truck.get("broken"):
            return  # broken down — awaiting repair

        state = truck["state"]

        # Accumulate operating hours and the day's workload (drives fatigue and
        # usage-based wear) while the lorry is out of the depot.
        if state != "depot":
            truck["op_hours"] = truck.get("op_hours", 0.0) + dt
            dd = getattr(self.game.economy, "day_duration", 55) or 55
            truck["work_today"] = truck.get("work_today", 0.0) + dt / dd

        if state == "depot":
            # An eRCV low on charge tops up before starting a round.
            if self._ev_needs_charge(truck):
                self._begin_charge(truck)
            elif self._pick_area(truck) is not None:
                route = self._route_to_stop(truck)
                if route is not None:
                    truck["path"] = route
                    truck["state"] = "to_stop"

        elif state == "to_stop":
            if self._follow_path(truck, dt):
                self._begin_servicing(truck)

        elif state == "servicing":
            self._service(truck, dt)

        elif state == "to_landfill":
            if self._follow_path(truck, dt):
                self._arrive_landfill(truck)

        elif state == "tipping":
            self._tip(truck, dt)

        elif state == "to_charge":
            if self._follow_path(truck, dt):
                truck["charge_t"] = 0.0
                truck["state"] = "charging"

        elif state == "charging":
            truck["charge_t"] = truck.get("charge_t", 0.0) + dt
            if truck["charge_t"] >= EV_CHARGE_TIME:
                truck["battery"] = 1.0
                truck["state"] = "depot"

        elif state == "to_depot":
            if self._follow_path(truck, dt):
                truck["load"] = 0.0
                truck["load_streams"] = [0.0, 0.0, 0.0, 0.0]
                truck["load_reject"] = 0.0
                truck["state"] = "depot"

    def _stop_presented_fill(self, bins, today):
        """Sum of the due-stream fills across a stop's bins — the volume the
        crew actually has to lift, which drives service time."""
        total = 0.0
        city = self.game.city
        for (bx, by) in bins:
            tile = city.get_tile(bx, by)
            s = getattr(tile, "streams", None) if tile else None
            if s is None:
                continue
            area = city.get_area(tile.area_id)
            due = self._due_mask(area) if area else (True,) * wastestreams.STREAM_COUNT
            for i in range(wastestreams.STREAM_COUNT):
                if due[i]:
                    total += s[i]
        return total

    def _service_time_factor(self, truck):
        """Multiplier on service time from crew/vehicle/site conditions. 1.0 is
        a full, experienced, rested crew in fair weather on clear roads; a green,
        tired or short crew on a worn lorry in a congested, wet street takes
        markedly longer. Lower crew productivity => higher time factor."""
        cap = max(1, truck.get("crew_cap", MAX_CREW))
        crew = max(1, truck["crew"])
        understaffed = 1.0 + 0.12 * (1.0 - crew / float(cap))
        # Productivity (>1 fast, <1 slow) inverts into a time multiplier.
        factor = understaffed / self.crew_productivity(truck)
        # Threading a congested street costs a little extra dwell.
        tx, ty = self._truck_tile(truck)
        factor *= 1.0 + 0.22 * self.traffic.congestion_at(tx, ty)
        return factor

    def _begin_servicing(self, truck):
        today = self._today()
        # Tip first if we're nearly full -- haul to the landfill.
        if truck["load"] >= truck["capacity"] * 0.95:
            self._release_truck_claims(truck)
            self._depart_to_landfill(truck)
            return

        # Keep the bins we can still service; RELEASE any claimed bin that is no
        # longer serviceable (e.g. the day rolled over mid-round so the area is
        # no longer due today) rather than leaving its claim dangling. A leaked
        # claim makes _area_remaining think the work is taken, which idles trucks
        # while bins sit full — the classic cause of a service death-spiral.
        bins = []
        for b in list(truck["claimed"]):
            if self._bin_serviceable(b[0], b[1], today, truck["area_id"]):
                bins.append(b)
            else:
                self._release_bin(truck, b)
        truck["service_bins"] = bins
        truck["service_t"] = 0.0
        crew = max(1, truck["crew"])
        waves = math.ceil(len(bins) / crew) if bins else 0
        # Service time (item 5): fixed per-wave handling plus a loading term that
        # scales with the volume actually presented at the kerb and is shared out
        # across the crew. A fuller stop, or a fortnightly round with two weeks of
        # waste stacked up, genuinely takes longer to empty — and more loaders
        # speed it up. Productivity/accessibility factors fold in via
        # _service_time_factor (crew, vehicle, congestion — expanded in later
        # phases).
        presented = self._stop_presented_fill(bins, today)
        base = (waves * PER_BIN_TIME + STOP_BASE_TIME
                + presented * LOAD_TIME_PER_FILL / crew)
        truck["service_need"] = base * self._service_time_factor(truck)

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

        # Stop complete — empty the DUE streams into the body. Each stream
        # contributes body *volume* (bulky garden eats more space than compacted
        # residual) and disposal *mass* (for economics), tracked separately so
        # capacity becomes a real logistical constraint. Gate fees/diversion are
        # charged when the load is tipped, so they follow what reaches the tip.
        mask = wastestreams.enabled_mask(self.game.waste)
        for (bx, by) in truck["service_bins"]:
            tile = self.game.city.get_tile(bx, by)
            self._release_bin(truck, (bx, by))
            if tile is None or getattr(tile, "streams", None) is None:
                continue
            area = self.game.city.get_area(tile.area_id)
            due = self._due_mask(area) if area else mask
            sf = wastestreams.size_factor(tile)
            vol, masses = wastestreams.collect_stop(tile, due, sf)
            if vol > 0:
                truck["load"] += vol
                ls = truck["load_streams"]
                for i in range(wastestreams.STREAM_COUNT):
                    ls[i] += masses[i]
                # Contamination is emergent per round: the fraction of this
                # stop's recycling rejected at the MRF uses the area's own
                # contamination rate (cohort sorting habits, missed collections,
                # whether food/garden caddies exist), not one borough number.
                rec = masses[wastestreams.RECYCLING]
                if rec > 0:
                    cont = getattr(area, "contamination", None)
                    if cont is None:
                        cont = self._current_contamination()
                    truck["load_reject"] += rec * cont
                self.collected_count += 1
            tile.bin_fill = wastestreams.visible_fill(tile, mask)
        truck["service_bins"] = []
        truck["out_workers"] = []

        # Decide what to do next.
        if truck["load"] >= truck["capacity"] * 0.95:
            self._depart_to_landfill(truck)
            return
        # An eRCV that has run low breaks off to recharge (losing round time).
        if self._ev_needs_charge(truck):
            self._begin_charge(truck)
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
        # No work left: tip any remaining load, otherwise head home.
        if truck["load"] > 0:
            self._depart_to_landfill(truck)
        else:
            self._depart_to_depot(truck)

    def _ev_needs_charge(self, truck):
        """True when an electric lorry has run low enough to need a charge."""
        return (truck.get("model_id") == "electric"
                and truck.get("battery", 1.0) < EV_LOW_BATTERY)

    def _begin_charge(self, truck):
        """Head to the depot to recharge (an eRCV can't finish the round on the
        charge it has left). Any held load is tipped first if the truck is full;
        otherwise it carries on to the depot chargers, losing collection time."""
        self._release_truck_claims(truck)
        truck["out_workers"] = []
        truck["service_bins"] = []
        route = self._route_to_depot(truck)
        if route is None:
            # Can't reach the depot — limp on and let normal routing cope.
            truck["battery"] = max(truck.get("battery", 0.0), EV_LOW_BATTERY)
            truck["state"] = "depot"
            return
        truck["area_id"] = -1
        truck["path"] = route
        truck["state"] = "to_charge"

    def _depart_to_depot(self, truck):
        self._release_truck_claims(truck)   # never carry claims home
        truck["area_id"] = -1
        truck["out_workers"] = []
        truck["service_bins"] = []
        truck["path"] = self._route_to_depot(truck) or []
        truck["state"] = "to_depot"

    # ------------------------------------------------------------- landfill
    def _landfill_gate(self):
        """Return the tipping point trucks drive to. This must be a ROAD tile
        (the site's haul gate) so a truck can road-route back out again after
        tipping. Driving to the interior centre instead strands a truck whenever
        that centre is landlocked by landfill tiles (no adjacent road) — the
        road-only round/depot routing can't then escape the site, and the truck
        idles there forever. Fall back to the centre only if no gate is known,
        and to the depot if there's no landfill at all."""
        lf = getattr(self.game.city, "landfill", None)
        if lf:
            gate = lf.get("gate")
            if gate:
                return (gate[0], gate[1])
            return (lf["cx"], lf["cy"])
        return (self.depot_x, self.depot_y)

    def _bfs_route_landfill(self, start, goal):
        """BFS that can traverse both road and landfill tiles."""
        if start == goal:
            return []
        seen = {start}
        prev = {}
        q = deque([start])
        while q:
            cur = q.popleft()
            cx, cy = cur
            for ox, oy in ADJ:
                nb = (cx + ox, cy + oy)
                if nb in seen:
                    continue
                tile = self.game.city.get_tile(nb[0], nb[1])
                if tile is None or tile.type not in ("road", "landfill"):
                    continue
                seen.add(nb)
                prev[nb] = cur
                if nb == goal:
                    path = [nb]
                    p = cur
                    while p != start:
                        path.append(p)
                        p = prev[p]
                    path.reverse()
                    return path
                q.append(nb)
        return None

    def _route_to_landfill(self, truck):
        start = self._truck_tile(truck)
        target = self._landfill_gate()
        return self._bfs_route_landfill(start, target)

    def _depart_to_landfill(self, truck):
        """Head to the landfill to tip. Keeps area_id so the round can resume
        after tipping. If unreachable, dump at the depot as a fallback."""
        truck["out_workers"] = []
        truck["service_bins"] = []
        route = self._route_to_landfill(truck)
        if route is None:
            # Landfill unreachable — tip at the depot as a fallback so the load
            # isn't silently lost from the economy.
            self._tip_load(truck)
            self._depart_to_depot(truck)
            return
        truck["path"] = route
        truck["state"] = "to_landfill"

    def _tip_load(self, truck):
        """Meter the truck's load into the pending disposal accumulators and
        empty the body. The contaminated recycling fraction was accumulated per
        stop from each round's own contamination rate (see _service), so the
        reject reflects where the load actually came from."""
        ls = truck["load_streams"]
        if truck["load"] > 0 or ls[0] or ls[1] or ls[2] or ls[3]:
            self._pending_volume += truck["load"]
            for i in range(wastestreams.STREAM_COUNT):
                self._pending_streams[i] += ls[i]
            reject = truck.get("load_reject", 0.0)
            # Guard: reject can never exceed the recycling actually onboard.
            self._pending_reject += min(reject, ls[wastestreams.RECYCLING])
            # Usage wear: each tip is a compaction/hydraulic cycle; a tip while
            # near capacity stresses the body (an overload event).
            truck["load_cycles"] = truck.get("load_cycles", 0) + 1
            if truck["load"] >= truck["capacity"] * 0.95:
                truck["overload"] = truck.get("overload", 0) + 1
        truck["load"] = 0.0
        truck["load_streams"] = [0.0, 0.0, 0.0, 0.0]
        truck["load_reject"] = 0.0

    def _current_contamination(self, truck=None):
        """Fraction of recycling rejected as contaminated. Borough-level for
        now; a later phase makes this emergent from the areas serviced."""
        waste = getattr(self.game, "waste", None)
        if waste is None:
            return 0.0
        try:
            return waste.contamination_rate()
        except Exception:
            return 0.0

    def _arrive_landfill(self, truck):
        """Begin the tip dwell (weigh-in, queue, tipping). The load is metered
        and the round resumed when the dwell completes (_finish_tip)."""
        truck["tip_t"] = 0.0
        truck["tip_need"] = TIP_BASE_TIME + truck["load"] * TIP_TIME_PER_LOAD
        truck["state"] = "tipping"

    def _tip(self, truck, dt):
        truck["tip_t"] = truck.get("tip_t", 0.0) + dt
        if truck["tip_t"] < truck.get("tip_need", 0.0):
            return
        self._finish_tip(truck)

    def _finish_tip(self, truck):
        """Dwell complete: meter the load, then resume the round, pick a new
        one, or head home."""
        self._tip_load(truck)

        # An empty eRCV low on charge heads for the depot chargers next.
        if self._ev_needs_charge(truck):
            self._begin_charge(truck)
            return

        today = self._today()
        if truck["area_id"] != -1 and self._area_remaining(truck["area_id"], today) > 0:
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
                if self._bin_serviceable(x, y, today, area.id):
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
            if self._bin_serviceable(x, y, today, area_id):
                count += 1
        return count

    def estimated_daily_capacity(self):
        active = sum(1 for t in self.trucks if t["crew"] >= 1)
        return active * PER_LORRY_DAILY

    def active_lorries(self):
        return sum(1 for t in self.trucks if t["crew"] >= 1)
