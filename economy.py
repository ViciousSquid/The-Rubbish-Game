import random

DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
DAY_ABBRS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

# One in-game "day" is `day_duration` seconds of accumulated dt. Daily figures
# below are quoted per in-game day and metered out each frame by the fraction of
# a day that elapsed, so the live ledger always sums to the per-day totals.
HOURS_PER_DAY = 8.0          # paid hours per crew member per day


class Economy:
    # ----- profit & loss ledger schema ------------------------------------
    REVENUE_KEYS = {"council_tax", "business_rates", "recycling_credit",
                    "garden_charges", "grants"}
    EXPENSE_KEYS = {"wages", "vehicles", "gate_fees"}
    LEDGER_LABELS = [
        ("council_tax",     "Council tax receipts"),
        ("business_rates",  "Business rates"),
        ("recycling_credit", "Recycling material credit"),
        ("garden_charges",  "Garden waste subscriptions"),
        ("grants",          "Grants & one-offs"),
        ("wages",           "Crew wages"),
        ("vehicles",        "Vehicle running / lease"),
        ("gate_fees",       "Disposal gate fees"),
    ]

    def __init__(self):
        self.budget = 500000
        # Revenue levers represent the WASTE SERVICE's slice of each tax, per day.
        # A UK household's waste service costs roughly £60-£90/yr, funded from
        # council tax; trade waste is charged per commercial premises.
        self.council_tax_rate = 0.45     # GBP / resident / day (waste portion)
        self.business_rates = 2.20       # GBP / premises / day (trade waste)
        # Blended crew cost to the council: Class-2 refuse drivers ~£15-17/hr and
        # loaders ~£12.50-13.50/hr, plus ~25-30% employer on-costs (NI, pension).
        self.hourly_wage_rate = 16.50    # GBP / crew / hour (employer cost)
        self.truck_maintenance = 45.00   # legacy reference (vehicles carry own cost)

        self.day = 1
        self.day_timer = 0
        self.day_duration = 55
        self.week_index = 0

        self.budget_trend = 0
        self.last_day_budget = 500000
        self.daily_revenue = 0
        self.daily_expenses = 0

        self.ledger = self._blank_ledger()
        self.history = []                # completed daily ledgers (most recent last)

        self.satisfaction = 88.0
        self.complaints_total = 0
        self.complaints_today = 0

        self.active_event = None
        self.pending_event = None
        self._bin_rate_multiplier = 1

        # Editable difficulty levers (exposed via the Config sheet in xmlio).
        self.event_chance = 0.30           # chance of a new event each day (0-1)
        self.win_streak_target = 7         # clean days in a row needed to win

        # Win condition tracking
        self.perfect_days_streak = 0       # consecutive days with 0 complaints
        self.has_won = False
        self.win_day = None
        self.win_celebration_timer = 0.0

        self.events = [
            {"id": "bank_holiday", "name": "Bank Holiday",
             "desc": "Rubbish output doubles for the day. Mind the overflows.",
             "duration": 1, "effect": "binRate", "value": 2.0},
            {"id": "heatwave", "name": "Heatwave Warning",
             "desc": "Heat accelerates waste. Bins fill 50% faster for 2 days.",
             "duration": 2, "effect": "binRate", "value": 1.5},
            {"id": "budget_cut", "name": "Govt Budget Cut",
             "desc": "Central funding reduced. Council tax receipts down 25% for 3 days.",
             "duration": 3, "effect": "taxRate", "value": 0.75},
            {"id": "union_dispute", "name": "Union Dispute",
             "desc": "Crews demanding a 15% pay rise. Labour costs up for 4 days.",
             "duration": 4, "effect": "wageRate", "value": 1.15},
            {"id": "recycling_grant", "name": "Recycling Grant",
             "desc": "Awarded a GBP 75,000 sustainability grant from Westminster!",
             "duration": 0, "effect": "money", "value": 75000},
            {"id": "festival", "name": "Local Festival",
             "desc": "High street thriving. Business rates doubled for 2 days.",
             "duration": 2, "effect": "businessRate", "value": 2.0},
            {"id": "fleet_breakdown", "name": "Fleet Breakdown",
             "desc": "Emergency RCV maintenance bill: GBP 20,000.",
             "duration": 0, "effect": "money", "value": -20000},
            {"id": "new_residents", "name": "New Residents",
             "desc": "Housing demand surges -- business rates up 50% for 3 days.",
             "duration": 3, "effect": "businessRate", "value": 1.5},
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
        """The most recently completed day's P&L (or the live one on day 1)."""
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
            self._on_new_day()
            new_day = True

        tax_mult = wage_mult = business_mult = 1.0
        self._bin_rate_multiplier = 1
        if self.active_event:
            effect = self.active_event["effect"]
            val = self.active_event["value"]
            if effect == "binRate":
                self._bin_rate_multiplier = val
            elif effect == "taxRate":
                tax_mult = val
            elif effect == "wageRate":
                wage_mult = val
            elif effect == "businessRate":
                business_mult = val

        frac = dt / self.day_duration            # fraction of an in-game day
        sat_mult = 0.65 + 0.35 * (self.satisfaction / 100.0)

        # --- revenue (per-day rates, metered by frac) ----------------------
        council = city.population * self.council_tax_rate * tax_mult * sat_mult
        business = city.metrics["commercial"] * self.business_rates * business_mult
        self.ledger["council_tax"] += council * frac
        self.ledger["business_rates"] += business * frac

        # --- labour + vehicles (per-day, metered by frac) ------------------
        wages = fleet.workers * self.hourly_wage_rate * wage_mult * HOURS_PER_DAY
        vehicles = fleet.daily_vehicle_cost()
        self.ledger["wages"] += wages * frac
        self.ledger["vehicles"] += vehicles * frac

        # --- disposal economics (driven by actual volume tipped) -----------
        volume = fleet.take_pending_volume()
        if volume > 0:
            gate, recycle, garden = waste.disposal_economics(volume)
            self.ledger["gate_fees"] += gate
            self.ledger["recycling_credit"] += recycle
            self.ledger["garden_charges"] += garden

        revenue = (council + business) * frac + 0.0
        expenses = (wages + vehicles) * frac
        self.daily_revenue += revenue
        self.daily_expenses += expenses
        self.budget += (revenue - expenses)
        if volume > 0:
            self.budget += (recycle + garden - gate)
        if self.budget < 0:
            self.budget = 0
        return new_day

    def _on_new_day(self):
        # finalise the day that just ended
        self.ledger["day"] = self.day
        self.history.append(self.ledger)
        if len(self.history) > 30:
            self.history.pop(0)
        self.ledger = self._blank_ledger()

        self.budget_trend = self.budget - self.last_day_budget
        self.last_day_budget = self.budget
        self.daily_revenue = 0
        self.daily_expenses = 0
        self.complaints_today = 0
        self.day += 1
        self.week_index = (self.day - 1) // 7

        if self.active_event:
            self.active_event["remaining_days"] -= 1
            if self.active_event["remaining_days"] <= 0:
                self.active_event = None

        if not self.active_event and random.random() < self.event_chance:
            template = random.choice(self.events)
            self.active_event = {**template, "remaining_days": template["duration"]}
            if template["effect"] == "money":
                self.budget = max(0, self.budget + template["value"])
                self.ledger["grants"] += template["value"]
            self.pending_event = self.active_event

    # ----- service quality -------------------------------------------------
    def register_day_quality(self, overflow_count, property_count, service_ceiling=100.0):
        """Once per new day: adjust satisfaction from overflow snapshot, then
        drift toward the ceiling implied by the waste service on offer."""
        if property_count > 0:
            overflow_ratio = overflow_count / property_count
            if overflow_ratio <= 0.02:
                self.satisfaction = min(100.0, self.satisfaction + 3.0)
            else:
                drop = min(22.0, overflow_ratio * 140.0)
                self.satisfaction = max(0.0, self.satisfaction - drop)
            self.complaints_today = overflow_count
            self.complaints_total += overflow_count

        # Win condition: 7 consecutive days with 0 complaints
        if overflow_count == 0:
            self.perfect_days_streak += 1
        else:
            self.perfect_days_streak = 0

        if self.perfect_days_streak >= self.win_streak_target and not self.has_won:
            self.has_won = True
            self.win_day = self.day
            self.win_celebration_timer = 10.0

        # Pull gently toward the service ceiling (more streams -> happier baseline).
        self.satisfaction += (service_ceiling - self.satisfaction) * 0.10
        self.satisfaction = max(0.0, min(100.0, self.satisfaction))

    # ----- queries ---------------------------------------------------------
    def get_bin_rate_multiplier(self):
        return self._bin_rate_multiplier

    def get_day_progress(self):
        return self.day_timer / self.day_duration

    def is_budget_crisis(self):
        return self.budget < 50000

    def satisfaction_label(self):
        s = self.satisfaction
        if s >= 80:
            return "Excellent"
        if s >= 60:
            return "Good"
        if s >= 40:
            return "Poor"
        if s >= 20:
            return "Failing"
        return "In Crisis"

    def win_progress(self):
        """Returns progress toward win condition (0.0 to 1.0)."""
        target = max(1, getattr(self, "win_streak_target", 7))
        return min(1.0, self.perfect_days_streak / float(target))
