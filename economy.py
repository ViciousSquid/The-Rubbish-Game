import random

DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
DAY_ABBRS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

# Worker morale constants
MORALE_NLW       = 11.44   # National Living Wage floor — workers are very unhappy here
MORALE_FAIR_WAGE = 18.00   # Above this, morale is fully satisfied (100 %)
MORALE_DEFAULT   = 16.50   # Starting wage → starting morale ≈ 77 %

# One in-game "day" is `day_duration` seconds of accumulated dt. Daily figures
# below are quoted per in-game day and metered out each frame by the fraction of
# a day that elapsed, so the live ledger always sums to the per-day totals.
HOURS_PER_DAY = 8.0          # paid hours per crew member per day


class Economy:
    # ----- profit & loss ledger schema ------------------------------------
    REVENUE_KEYS = {"council_tax", "business_rates", "recycling_credit",
                    "garden_charges", "grants"}
    EXPENSE_KEYS = {"wages", "oncosts", "vehicles", "gate_fees", "rental_costs"}
    LEDGER_LABELS = [
        ("council_tax",      "Council tax receipts"),
        ("business_rates",   "Business rates"),
        ("recycling_credit", "Recycling material credit"),
        ("garden_charges",   "Garden waste subscriptions"),
        ("grants",           "Grants & one-offs"),
        ("wages",            "Crew base wages"),
        ("oncosts",          "Staff on-costs (NI / pension / PPE)"),
        ("vehicles",         "Vehicle running / lease"),
        ("rental_costs",     "Emergency vehicle rentals"),
        ("gate_fees",        "Disposal gate fees"),
    ]

    def __init__(self):
        self.budget = 500000
        self.council_tax_rate = 0.45
        self.business_rates = 2.20
        self.hourly_wage_rate = 16.50
        self.truck_maintenance = 45.00

        # ── Staff on-cost rates (editable via Staff tab) ─────────────────────
        # Employer secondary NI rate — HMRC 2025/26 (13.8 %)
        self.employer_ni_rate   = 0.138
        # Secondary NI threshold as daily equivalent (£4,994 / yr ÷ 365.25)
        self.ni_secondary_daily = 13.68
        # Employer auto-enrolment pension minimum (3 %, can be raised)
        self.pension_rate       = 0.030
        # Daily PPE + uniform allowance per worker
        self.ppe_daily          = 1.20

        # ── Vehicle cost display fractions (informational, not separate charges)
        self.fuel_fraction        = 0.54   # share of running_cost that is fuel
        self.maintenance_fraction = 0.31   # tyres + scheduled servicing
        self.insurance_fraction   = 0.15   # fleet insurance + VOSA plating

        self.day = 1
        self.day_timer = 0
        self.day_duration = 55
        self.week_index = 0

        self.budget_trend = 0
        self.last_day_budget = 500000
        self.daily_revenue = 0
        self.daily_expenses = 0

        self.ledger = self._blank_ledger()
        self.history = []

        self.satisfaction = 88.0
        self.complaints_total = 0
        self.complaints_today = 0

        self.active_event = None
        self.pending_event = None
        self._bin_rate_multiplier = 1
        self._recycling_multiplier = 1.0   # boosted by recycling_drive

        # Editable difficulty levers
        self.event_chance = 0.30
        self.win_streak_target = 7

        # Win condition
        self.perfect_days_streak = 0
        self.has_won = False
        self.win_day = None
        self.win_celebration_timer = 0.0

        # Procurement notifications
        self.procurement_events = []

        # Ambient weather: "dry" | "rain" | "snow"
        self.weather = "dry"
        self._weather_timer = 0           # days remaining for current weather spell

        # Road-works events — independent of active_event, up to 3 concurrent.
        # Each entry: {"tiles": set, "remaining_days": int}
        self.road_works_active = []

        # ── Worker morale (0–100) ──────────────────────────────────────────────
        # Tracks crew sentiment toward their pay.  Starts at ~72 (neutral at the
        # default £16.50/hr wage).  Falls when wages are cut, rises when raised.
        # Low morale strongly increases the chance of a crew_strike event.
        self.worker_morale = self._morale_target()
        # Extra strike-weight spike from recent wage cuts; added to immediately
        # on any cut and decays by 8 pts/day (gone in ~10–12 days).
        self._wage_anger = 0.0

        self.events = [
            # ---- bin-rate (fill speed) ----------------------------------------
            {"id": "bank_holiday", "name": "Bank Holiday",
             "desc": "Rubbish output doubles for the day. Mind the overflows.",
             "duration": 1, "effect": "binRate", "value": 2.0},
            {"id": "heatwave", "name": "Heatwave",
             "desc": "Heat spoils food faster. Bins fill 50% faster for 2 days.",
             "duration": 2, "effect": "binRate", "value": 1.5},
            {"id": "heavy_rain", "name": "Heavy Rain",
             "desc": "Torn bin bags everywhere. Fill rates up 60% today.",
             "duration": 1, "effect": "binRate", "value": 1.6},
            # ---- revenue / cost multipliers ------------------------------------
            {"id": "budget_cut", "name": "Govt Budget Cut",
             "desc": "Central funding cut. Council tax receipts down 25% for 3 days.",
             "duration": 3, "effect": "taxRate", "value": 0.75},
            {"id": "union_dispute", "name": "Union Dispute",
             "desc": "Crews demanding a 15% pay rise. Labour costs up for 4 days.",
             "duration": 4, "effect": "wageRate", "value": 1.15},
            {"id": "overtime_demand", "name": "Overtime Demand",
             "desc": "Crews insist on overtime rates. Labour costs up 50% for 2 days.",
             "duration": 2, "effect": "wageRate", "value": 1.5},
            {"id": "festival", "name": "Local Festival",
             "desc": "High street thriving. Business rates doubled for 2 days.",
             "duration": 2, "effect": "businessRate", "value": 2.0},
            {"id": "new_residents", "name": "New Residents",
             "desc": "Housing demand surges -- business rates up 50% for 3 days.",
             "duration": 3, "effect": "businessRate", "value": 1.5},
            # ---- money (instant) ----------------------------------------------
            {"id": "recycling_grant", "name": "Recycling Grant",
             "desc": "Awarded a GBP 75,000 sustainability grant from Westminster!",
             "duration": 0, "effect": "money", "value": 75000},
            {"id": "fleet_breakdown", "name": "Fleet Breakdown",
             "desc": "Emergency RCV maintenance bill: GBP 20,000.",
             "duration": 0, "effect": "money", "value": -20000},
            {"id": "fly_tipping", "name": "Fly-Tipping Complaint",
             "desc": "Illegal dumping reported. Council clean-up bill: GBP 12,000.",
             "duration": 0, "effect": "money", "value": -12000},
            # ---- recycling bonus ----------------------------------------------
            {"id": "recycling_drive", "name": "Recycling Drive",
             "desc": "Community campaign. Recycling material credits up 80% for 2 days.",
             "duration": 2, "effect": "recyclingBonus", "value": 1.8},
            # ---- crew actions -------------------------------------------------
            {"id": "crew_strike", "name": "Crew Strike",
             "desc": "Union action! Crews refuse to lift a bin today. No collections.",
             "duration": 1, "effect": "crewStrike", "value": 0},
            # ---- truck breakdown ----------------------------------------------
            {"id": "vehicle_breakdown", "name": "Vehicle Breakdown",
             "desc": "An RCV has broken down. One truck out of action. "
                     "Duration depends on parts availability.",
             "duration": 3, "effect": "truckBreakdown", "value": 1},
            # ---- council inspection (outcome depends on satisfaction) ----------
            {"id": "council_inspection", "name": "Council Inspection",
             "desc": "Performance review. High satisfaction brings a bonus; "
                     "poor service brings a fine.",
             "duration": 0, "effect": "councilInspection", "value": 0},
        ]

    # ----- ledger helpers --------------------------------------------------
    def _blank_ledger(self):
        d = {k: 0.0 for k, _ in self.LEDGER_LABELS}
        d["day"] = getattr(self, "day", 1)
        return d

    def _ledger_net(self, led):
        rev = sum(led.get(k, 0.0) for k in self.REVENUE_KEYS)
        exp = sum(led.get(k, 0.0) for k in self.EXPENSE_KEYS)
        return rev - exp

    def ledger_snapshot(self):
        led = self.history[-1] if self.history else self.ledger
        out = dict(led)
        out["net"] = self._ledger_net(led)
        return out

    # ----- days ------------------------------------------------------------
    def get_day_of_week(self):
        return (self.day - 1) % 7

    def get_day_of_week_name(self):
        return DAY_NAMES[self.get_day_of_week()]

    def get_day_of_week_abbr(self):
        return DAY_ABBRS[self.get_day_of_week()]

    def is_weekend(self):
        return self.get_day_of_week() >= 5

    # ----- update ----------------------------------------------------------
    def update(self, dt, city, fleet, waste):
        """Advance the economy. Returns True on the frame a new day begins."""
        new_day = False
        self.day_timer += dt
        if self.day_timer >= self.day_duration:
            self.day_timer -= self.day_duration
            self._on_new_day(city, fleet)
            new_day = True

        tax_mult = wage_mult = business_mult = 1.0
        self._bin_rate_multiplier = 1
        self._recycling_multiplier = 1.0
        if self.active_event:
            effect = self.active_event["effect"]
            val    = self.active_event["value"]
            if effect == "binRate":
                self._bin_rate_multiplier = val
            elif effect == "taxRate":
                tax_mult = val
            elif effect == "wageRate":
                wage_mult = val
            elif effect == "businessRate":
                business_mult = val
            elif effect == "recyclingBonus":
                self._recycling_multiplier = val

        # Weather bin-rate bump (rain makes bags tear)
        if self.weather == "rain":
            self._bin_rate_multiplier *= 1.25
        elif self.weather == "snow":
            self._bin_rate_multiplier *= 1.10

        frac     = dt / self.day_duration
        sat_mult = 0.65 + 0.35 * (self.satisfaction / 100.0)

        council  = city.population * self.council_tax_rate * tax_mult * sat_mult
        business = city.metrics["commercial"] * self.business_rates * business_mult
        self.ledger["council_tax"]    += council  * frac
        self.ledger["business_rates"] += business * frac

        base_wages   = fleet.workers * self.hourly_wage_rate * wage_mult * HOURS_PER_DAY
        # Employer NI: 13.8 % on earnings above the daily secondary threshold
        _ni_ph       = max(0.0, self.hourly_wage_rate * wage_mult * HOURS_PER_DAY
                           - self.ni_secondary_daily) * self.employer_ni_rate
        oncosts      = (fleet.workers * _ni_ph
                        + base_wages * self.pension_rate
                        + fleet.workers * self.ppe_daily)
        vehicles     = fleet.daily_vehicle_cost()
        rental_costs = fleet.get_rental_costs()
        self.ledger["wages"]        += base_wages   * frac
        self.ledger["oncosts"]      += oncosts      * frac
        self.ledger["vehicles"]     += vehicles     * frac
        self.ledger["rental_costs"] += rental_costs * frac

        volume = fleet.take_pending_volume()
        if volume > 0:
            gate, recycle, garden = waste.disposal_economics(volume)
            recycle *= self._recycling_multiplier
            self.ledger["gate_fees"]        += gate
            self.ledger["recycling_credit"] += recycle
            self.ledger["garden_charges"]   += garden

        revenue  = (council + business) * frac
        expenses = (base_wages + oncosts + vehicles + rental_costs) * frac
        self.daily_revenue  += revenue
        self.daily_expenses += expenses
        self.budget += (revenue - expenses)
        if volume > 0:
            self.budget += (recycle + garden - gate)
        if self.budget < 0:
            self.budget = 0
        return new_day

    def _on_new_day(self, city=None, fleet=None):
        # Finalise the day that just ended
        self.ledger["day"] = self.day
        self.history.append(self.ledger)
        if len(self.history) > 30:
            self.history.pop(0)
        self.ledger = self._blank_ledger()

        self.budget_trend    = self.budget - self.last_day_budget
        self.last_day_budget = self.budget
        self.daily_revenue   = 0
        self.daily_expenses  = 0
        self.complaints_today = 0
        self.day        += 1
        self.week_index  = (self.day - 1) // 7

        # ---- age / expire the active event -----------------------------------
        if self.active_event:
            self.active_event["remaining_days"] -= 1
            if self.active_event["remaining_days"] <= 0:
                self._clear_event_effects(self.active_event, city, fleet)
                self.active_event = None

        # ---- fire a new event (at most one active at a time) -----------------
        if not self.active_event and random.random() < self.event_chance:
            template = self._weighted_event_choice()
            evt = {**template, "remaining_days": template["duration"]}
            effect = template["effect"]

            if effect == "truckBreakdown" and fleet:
                days = random.randint(1, 7)
                evt["remaining_days"] = days
                evt["duration"]       = days
                bd_name = self._apply_truck_breakdown(fleet)
                if bd_name:
                    evt["desc"] = (f"{bd_name} has broken down and will be out of "
                                   f"action for {days} day{'s' if days != 1 else ''}.")
            elif effect == "money":
                self.budget = max(0, self.budget + template["value"])
                self.ledger["grants"] += max(0, template["value"])
            elif effect == "crewStrike" and fleet:
                fleet.on_strike = True
            elif effect == "councilInspection":
                if self.satisfaction >= 70:
                    bonus = 22000
                    self.budget = max(0, self.budget + bonus)
                    self.ledger["grants"] += bonus
                    evt["desc"] = (f"Inspection passed! Performance rated "
                                   f"\"{self.satisfaction_label()}\". "
                                   f"GBP {bonus:,} bonus grant awarded.")
                else:
                    fine = 18000
                    self.budget = max(0, self.budget - fine)
                    evt["desc"] = (f"Inspection failed! Service rated "
                                   f"\"{self.satisfaction_label()}\". "
                                   f"GBP {fine:,} penalty issued.")
            elif effect == "heavy_rain" or (effect == "binRate" and template["id"] == "heavy_rain"):
                self.weather = "rain"
                self._weather_timer = 1

            self.active_event = evt
            self.pending_event = evt

        # ---- advance road-works independently --------------------------------
        self._update_road_works(city, fleet)

        # ---- ambient weather transitions -------------------------------------
        self._tick_weather()

        # ---- worker morale (wage-to-strike pipeline) -------------------------
        self._update_worker_morale()

    # ----- road-works management -------------------------------------------
    def _update_road_works(self, city, fleet):
        """Age existing blockages, maybe add a new one (up to 3 concurrent)."""
        if city is None:
            return
        old_tiles = frozenset(city.road_works_tiles)

        for rw in list(self.road_works_active):
            rw["remaining_days"] -= 1
            if rw["remaining_days"] <= 0:
                self.road_works_active.remove(rw)

        # Independent daily chance (~15%) for a new set of road works
        if len(self.road_works_active) < 3 and random.random() < 0.15:
            tiles = self._road_works_segment(city)
            if tiles:
                duration = random.randint(3, 6)
                self.road_works_active.append({"tiles": tiles,
                                               "remaining_days": duration})
                # Push a UI notification via the event system
                if self.pending_event is None:
                    self.pending_event = {
                        "name": "Road Works",
                        "desc": (f"Highways are resurfacing {len(tiles)} tiles near "
                                 f"a junction for {duration} days. Trucks will divert."),
                        "effect": "roadWorks",
                    }

        new_tiles = set()
        for rw in self.road_works_active:
            new_tiles |= rw["tiles"]

        if new_tiles != old_tiles:
            city.road_works_tiles = new_tiles
            if fleet:
                fleet._roads_built_for = None
                for truck in fleet.trucks:
                    truck["path"] = []

    def _road_works_segment(self, city):
        """Pick a linear road segment (5-11 tiles) avoiding existing blockages."""
        existing = getattr(city, "road_works_tiles", set())
        length   = random.randint(5, 11)

        # Candidate road tiles away from existing road works
        candidates = [
            (x, y)
            for y in range(city.height)
            for x in range(city.width)
            if city.tiles[y][x].type == "road" and (x, y) not in existing
        ]
        if not candidates:
            return set()
        random.shuffle(candidates)

        for sx, sy in candidates[:30]:
            for dx, dy in ((1, 0), (0, 1)):
                seg = []
                cx, cy = sx, sy
                while len(seg) < length:
                    if not city.is_inside(cx, cy):
                        break
                    if city.tiles[cy][cx].type != "road":
                        break
                    if (cx, cy) in existing:
                        break
                    seg.append((cx, cy))
                    cx += dx
                    cy += dy
                if 5 <= len(seg):
                    return set(seg[:length])

        # Fallback: small cluster
        seed = candidates[0]
        blocked = {seed}
        for tx, ty in candidates[1:]:
            if len(blocked) >= 5:
                break
            if any(abs(tx - bx) + abs(ty - by) <= 1 for bx, by in blocked):
                blocked.add((tx, ty))
        return blocked

    # ----- worker morale & strike risk ------------------------------------
    def _morale_target(self):
        """Ideal morale given the current wage rate (0–100)."""
        wage = getattr(self, "hourly_wage_rate", MORALE_DEFAULT)
        span = MORALE_FAIR_WAGE - MORALE_NLW
        return max(0.0, min(100.0, (wage - MORALE_NLW) / span * 100.0))

    def _update_worker_morale(self):
        """Drift morale 12 % of the way toward the wage-based target each day.
        Workers notice pay cuts gradually — morale doesn't crater overnight.
        Wage-cut anger spike decays by 8 pts/day (clears in ~10–12 days)."""
        target = self._morale_target()
        self.worker_morale += (target - self.worker_morale) * 0.12
        self.worker_morale = max(0.0, min(100.0, self.worker_morale))
        self._wage_anger = max(0.0, getattr(self, "_wage_anger", 0.0) - 8.0)

    def _crew_strike_weight(self):
        """Event weight for crew_strike relative to every other event (1.0).

        High morale  → weight < 1  (strikes suppressed)
        Neutral (72) → weight ≈ 1  (baseline)
        Low morale   → weight up to 8  (strikes very likely when any event fires)
        Recent wage-cut anger adds up to +6 on top of the morale weight.
        """
        m = self.worker_morale / 100.0
        if m >= 0.72:
            # Morale at or above neutral — gradually suppress strike events
            # 0.72 → 1.0,  1.0 → 0.15
            t = (m - 0.72) / 0.28
            base = max(0.15, 1.0 - t * 0.85)
        else:
            # Morale below neutral — ramp up sharply
            # 0.72 → 1.0,  0.0 → 8.0
            t = (0.72 - m) / 0.72
            base = 1.0 + t * 7.0
        # Recent wage-cut anger amplifies strike risk independently of morale
        anger_boost = getattr(self, "_wage_anger", 0.0) / 100.0 * 6.0
        return base + anger_boost

    def _weighted_event_choice(self):
        """Pick a random event, biasing crew_strike by current morale."""
        weights = [
            self._crew_strike_weight() if e["id"] == "crew_strike" else 1.0
            for e in self.events
        ]
        return random.choices(self.events, weights=weights, k=1)[0]

    def strike_risk_pct(self):
        """Approximate daily probability (%) that the next event is a crew strike.
        Used by the UI to show a human-readable risk indicator."""
        if not self.events:
            return 0.0
        weights = [
            self._crew_strike_weight() if e["id"] == "crew_strike" else 1.0
            for e in self.events
        ]
        total_w = sum(weights)
        strike_w = self._crew_strike_weight()
        p_strike_given_event = strike_w / total_w
        return round(self.event_chance * p_strike_given_event * 100.0, 1)

    def morale_label(self):
        m = self.worker_morale
        if m >= 85: return "High"
        if m >= 65: return "Neutral"
        if m >= 45: return "Unhappy"
        if m >= 25: return "Hostile"
        return "Mutinous"

    # ----- event effect helpers --------------------------------------------
    def _apply_truck_breakdown(self, fleet):
        """Mark one active truck as broken. Returns the truck name or None."""
        active = [t for t in fleet.trucks
                  if t["crew"] >= 1 and not t.get("broken")]
        if not active:
            return None
        truck = random.choice(active)
        truck["broken"] = True
        truck["path"]   = []
        truck["state"]  = "depot"
        self.active_event["broken_truck_id"] = truck["id"]
        return truck.get("model_name", f"Truck #{truck['id']}")

    def _clear_event_effects(self, event, city=None, fleet=None):
        effect = event.get("effect")
        if effect == "truckBreakdown" and fleet:
            truck_id = event.get("broken_truck_id")
            if truck_id is not None:
                for t in fleet.trucks:
                    if t["id"] == truck_id:
                        t["broken"] = False
                        break
        elif effect == "crewStrike" and fleet:
            fleet.on_strike = False

    # ----- ambient weather -------------------------------------------------
    def _tick_weather(self):
        """Randomly change weather each day for ambient visuals."""
        if self._weather_timer > 0:
            self._weather_timer -= 1
            return
        r = random.random()
        if r < 0.60:
            self.weather = "dry"
        elif r < 0.85:
            self.weather = "rain"
            self._weather_timer = random.randint(1, 3)
        else:
            self.weather = "overcast"

    # ----- service quality -------------------------------------------------
    def register_day_quality(self, city, service_ceiling=100.0):
        daily_complaints = 0
        for y in range(city.height):
            for x in range(city.width):
                tile = city.tiles[y][x]
                if tile.type in ("road", "green", "landfill"):
                    continue
                if tile.bin_fill >= 100:
                    tile.days_overflowing += 1
                    if tile.days_overflowing > 1:
                        daily_complaints += 1
                else:
                    tile.days_overflowing = 0

        self.complaints_today  = daily_complaints
        self.complaints_total += daily_complaints

        if city.property_count > 0:
            overflow_ratio = daily_complaints / city.property_count
            if overflow_ratio <= 0.02:
                self.satisfaction = min(100.0, self.satisfaction + 3.0)
            else:
                drop = min(22.0, overflow_ratio * 140.0)
                self.satisfaction = max(0.0, self.satisfaction - drop)

        if daily_complaints == 0:
            self.perfect_days_streak += 1
        else:
            self.perfect_days_streak = 0

        if self.perfect_days_streak >= self.win_streak_target and not self.has_won:
            self.has_won      = True
            self.win_day      = self.day
            self.win_celebration_timer = 10.0

        self.satisfaction += (service_ceiling - self.satisfaction) * 0.10
        self.satisfaction  = max(0.0, min(100.0, self.satisfaction))

    # ----- queries ---------------------------------------------------------
    def get_bin_rate_multiplier(self):
        return self._bin_rate_multiplier

    def get_day_progress(self):
        return self.day_timer / self.day_duration

    def is_budget_crisis(self):
        return self.budget < 50000

    def satisfaction_label(self):
        s = self.satisfaction
        if s >= 80: return "Excellent"
        if s >= 60: return "Good"
        if s >= 40: return "Poor"
        if s >= 20: return "Failing"
        return "In Crisis"


    # ── Staff & vehicle cost helpers ─────────────────────────────────────────
    def staff_cost_breakdown(self, workers, wage_mult=1.0):
        """Itemised daily staff cost breakdown for the Staff management tab."""
        base    = workers * self.hourly_wage_rate * wage_mult * HOURS_PER_DAY
        ni_ph   = max(0.0, self.hourly_wage_rate * wage_mult * HOURS_PER_DAY
                     - self.ni_secondary_daily) * self.employer_ni_rate
        ni      = workers * ni_ph
        pension = base * self.pension_rate
        ppe     = workers * self.ppe_daily
        oncosts = ni + pension + ppe
        total   = base + oncosts
        return {
            "workers":  workers,
            "base":     base,
            "ni":       ni,
            "pension":  pension,
            "ppe":      ppe,
            "oncosts":  oncosts,
            "total":    total,
            "per_head": total / max(1, workers),
        }

    def vehicle_cost_breakdown(self, trucks):
        """Per-truck daily cost detail list for the Staff management tab."""
        result = []
        for t in trucks:
            if t.get("leased"):
                daily     = t.get("lease_weekly", 0) / 7.0
                cost_type = "lease"
            elif t.get("tier_id") == "rental":
                daily     = t.get("running_cost", 0)
                cost_type = "rental"
            else:
                daily     = t.get("running_cost", 130)
                cost_type = "owned"
            result.append({
                "id":        t["id"],
                "name":      t.get("model_name", "Unknown"),
                "daily":     daily,
                "cost_type": cost_type,
                "crew":      t.get("crew", 0),
                "broken":    t.get("broken", False),
                "capacity":  int(t.get("capacity", 0)),
                "fuel":      round(daily * self.fuel_fraction),
                "maint":     round(daily * self.maintenance_fraction),
                "ins":       round(daily * self.insurance_fraction),
            })
        return result

    def adjust_wage(self, delta):
        """Adjust hourly wage rate. Floor is UK 2025 National Living Wage (£11.44).

        A pay *cut* (delta < 0) triggers an immediate morale shock — 60 % of the
        gap to the new morale target is applied instantly rather than waiting for
        the daily 12 % drift — and spikes _wage_anger proportional to the cut
        size, giving a strong short-term boost to strike probability.
        """
        old = self.hourly_wage_rate
        self.hourly_wage_rate = round(
            max(11.44, min(50.0, self.hourly_wage_rate + delta)), 2)
        actual = self.hourly_wage_rate - old
        if actual < 0:
            # Immediate morale shock: snap 60 % of the way to the new target
            target = self._morale_target()
            self.worker_morale = max(
                0.0, self.worker_morale + (target - self.worker_morale) * 0.60)
            # Anger spike: each £1/hr cut adds ~8 anger (capped at 50 per cut)
            self._wage_anger = min(
                100.0, getattr(self, "_wage_anger", 0.0) + min(50.0, abs(actual) * 8.0))

    def adjust_pension(self, delta):
        """Adjust employer pension contribution. Auto-enrolment floor is 3 %."""
        self.pension_rate = round(
            max(0.03, min(0.15, self.pension_rate + delta)), 3)

    def adjust_ppe(self, delta):
        """Adjust daily PPE and uniform allowance per worker."""
        self.ppe_daily = round(max(0.0, min(15.0, self.ppe_daily + delta)), 2)

    def win_progress(self):
        target = max(1, getattr(self, "win_streak_target", 7))
        return min(1.0, self.perfect_days_streak / float(target))
