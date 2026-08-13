import random

DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
DAY_ABBRS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

# Worker morale constants
MORALE_NLW       = 11.44   # National Living Wage floor — workers are very unhappy here
MORALE_FAIR_WAGE = 18.00   # Above this, morale is fully satisfied (100 %)
MORALE_DEFAULT   = 16.50   # Starting wage → starting morale ≈ 77 %

# ── Diesel fuel market ───────────────────────────────────────────────────────
# Running costs for diesel RCVs track a volatile pump price. The index is a
# bounded random walk around 1.0 (≈ £1.50/L baseline at index 1.0), so a bad
# spell at the pumps quietly erodes the budget — and makes the electric eRCV's
# low running cost genuinely pay off when prices spike.
FUEL_INDEX_MIN  = 0.78
FUEL_INDEX_MAX  = 1.55
FUEL_BASE_PRICE = 1.50     # £/litre forecourt diesel at index 1.0 (UK 2025/26)

# ── Seasonal waste cycle ─────────────────────────────────────────────────────
# A compressed council year of four seasons, SEASON_LENGTH in-game days each.
# Garden and food waste swell through summer and peak in autumn (leaf fall);
# a mild festive bump lands in winter. The multiplier feeds the kerbside fill
# rate so a full collection plan has to flex with the calendar.
SEASON_LENGTH    = 28
SEASON_NAMES     = ["Spring", "Summer", "Autumn", "Winter"]
SEASON_FILL_MULT = {"Spring": 1.00, "Summer": 1.12, "Autumn": 1.18, "Winter": 1.06}

# One in-game "day" is `day_duration` seconds of accumulated dt. Daily figures
# below are quoted per in-game day and metered out each frame by the fraction of
# a day that elapsed, so the live ledger always sums to the per-day totals.
HOURS_PER_DAY = 8.0          # paid hours per crew member per day

# ── Insolvency / fail condition ──────────────────────────────────────────────
# A real council can't just sit at £0 — sustained insolvency forces a Section
# 114 notice (effectively "we are bankrupt"). We model two ways to fail:
#   1. Stay at/below £0 for INSOLVENCY_GRACE_DAYS consecutive days, or
#   2. Blow straight through the hard overdraft floor in one go.
OVERDRAFT_FLOOR       = -150000   # absolute hard floor; reaching it = instant bust
INSOLVENCY_GRACE_DAYS = 5         # consecutive days at/below £0 before a Section 114

# ── Council calendar ─────────────────────────────────────────────────────────
# A council "year" is the four-season cycle (SEASON_LENGTH * 4 days). Several
# yearly systems hang off this: the landfill-tax escalator and the statutory
# recycling-diversion review.
COUNCIL_YEAR_DAYS = SEASON_LENGTH * 4     # 112 in-game days

# ── Starting position & startup loan ─────────────────────────────────────────
# The borough no longer starts with a free fleet. The starter RCVs are
# financed by a startup loan that must be repaid daily, with interest, over six
# council years. Early game is therefore a balancing act: loan repayment plus
# fixed overheads and maintenance against the revenue from good service.
# These figures are the EASY baseline; DIFFICULTY_PRESETS below overrides the
# cash, principal and APR per difficulty (and doubles as the fallback for
# saves made before difficulty existed).
STARTING_CASH            = 220000
STARTUP_LOAN_PRINCIPAL   = 620000         # ~4 financed 26t RCVs
STARTUP_LOAN_ANNUAL_RATE = 0.075          # 7.5% APR
STARTUP_LOAN_TERM_DAYS   = COUNCIL_YEAR_DAYS * 6

# ── Recurring fixed overheads ────────────────────────────────────────────────
DEPOT_RENT_DAILY     = 220.0              # depot site rent (~£80k/yr)
INSURANCE_BASE_DAILY = 55.0               # base liability cover
INSURANCE_PER_VEH    = 22.0               # added per vehicle on the fleet
# UK landfill tax rises every year. The residual gate fee escalates by this
# fraction each council year.
LANDFILL_TAX_ANNUAL_RISE = 0.06

# ── Tax / rate pressure baselines ────────────────────────────────────────────
# Realistic-pressure model for the two rate levers. Both start "at baseline"
# (matching the Economy defaults below), where there's no penalty at all.
# Rates pushed above baseline start to bite: council tax annoys residents
# directly (the satisfaction ceiling falls), and steep business rates push
# marginal firms to close or relocate, quietly eroding the commercial tax base
# the rate is levied on.
BASELINE_COUNCIL_TAX   = 0.45      # £/resident/day
BASELINE_BUSINESS_RATE = 2.20      # £/commercial property/day

# ── Win bar (tightened) ──────────────────────────────────────────────────────
# A flawless streak alone is no longer enough: satisfaction must hold above a
# floor for a perfect day to count, and the streak target is longer.
WIN_STREAK_DEFAULT = 14
WIN_SAT_FLOOR      = 75.0

# ── Statutory recycling diversion ────────────────────────────────────────────
# Each council year, diversion (recycling+food+garden as a share of all waste)
# is reviewed. Missing the statutory target levies a DEFRA fine scaled to the
# shortfall — strong pressure to run the recycling/food/garden streams.
STATUTORY_DIVERSION_TARGET = 0.50         # 50% diverted from landfill
DIVERSION_FINE_PER_PCT     = 2600         # £ per percentage point short
DIVERSION_FINE_CAP         = 150000

# ── Difficulty presets ───────────────────────────────────────────────────────
# Three starting positions for the borough, chosen on the New Game screen.
# Every number stays inside the same realistic council-finance model — harder
# settings don't cheat, they just hand you the kind of borough that actually
# ends up on the news: thinner reserves, dearer legacy debt, a clapped-out
# fleet, a less patient bank and a stricter DEFRA settlement.
#
#   easy   "Comfortable" — the current, forgiving baseline. Healthy reserves,
#          a brand-new financed fleet, and residents inclined to like you.
#   medium "Stretched"   — reserves half spent, part-worn lorries, a worse
#          credit rating and stiffer DEFRA fines. You must actually manage.
#   hard   "Crisis"      — a borough one bad month from a Section 114: tiny
#          reserves, three high-mileage lorries, 9.9% APR legacy debt, a 52%
#          diversion quota and a bank that pulls the plug at -£60k. Winning
#          means rebuilding service quality AND the balance sheet at once.
DIFFICULTY_PRESETS = {
    "easy": {
        "label": "Comfortable",
        "blurb": "Healthy reserves, a new fleet and forgiving lenders. "
                 "Learn the ropes; the win comes to those who keep it tidy.",
        "starting_cash": 220000,
        "loan_principal": 620000,
        "loan_apr": 0.075,
        "overdraft_floor": -150000,
        "insolvency_grace": 5,
        "start_lorries": 4,
        "start_crew": 16,
        "fleet_age_years": 0.0,
        "win_streak": 14,
        "win_sat_floor": 75.0,
        "start_satisfaction": 88.0,
        "sat_recovery": 1.25,
        "karen_mult": 1.0,
        "diversion_target": 0.50,
        "diversion_fine_per_pct": 2600,
        "diversion_fine_cap": 150000,
        "landfill_rise": 0.06,
        "inspection_bonus": 22000,
        "inspection_fine": 18000,
        "grant_mult": 1.0,
        "penalty_mult": 1.0,
    },
    "medium": {
        "label": "Stretched",
        "blurb": "Reserves half spent, two part-worn lorries, a weaker credit "
                 "rating and stiffer DEFRA fines. The books need watching.",
        "starting_cash": 150000,
        "loan_principal": 660000,
        "loan_apr": 0.084,
        "overdraft_floor": -100000,
        "insolvency_grace": 4,
        "start_lorries": 4,
        "start_crew": 14,
        "fleet_age_years": 2.5,       # two of the four arrive part-worn
        "win_streak": 17,
        # The floor sits strictly above the bare-bones service ceiling (78 —
        # clean-day recovery can never push past the ceiling), and the term
        # starts below it: a winning streak only becomes possible once the
        # service is broadened (food/garden caddies lift the ceiling).
        "win_sat_floor": 79.0,
        "start_satisfaction": 76.0,
        "sat_recovery": 1.15,
        "karen_mult": 1.2,
        "diversion_target": 0.50,
        "diversion_fine_per_pct": 3200,
        "diversion_fine_cap": 180000,
        "landfill_rise": 0.07,
        "inspection_bonus": 16000,
        "inspection_fine": 24000,
        "grant_mult": 0.85,
        "penalty_mult": 1.1,
    },
    # Note on diversion targets: with every kerbside stream enabled and clean
    # loads, the policy model tops out at ~52.6% diversion — so 52% on hard is
    # the ceiling of what a flawless borough can deliver, not an impossible
    # quota. Anything less than a full, well-run service eats a DEFRA fine.
    "hard": {
        "label": "Crisis",
        "blurb": "Tiny reserves, three clapped-out lorries, 9.9% APR legacy "
                 "debt, a 52% diversion quota and a bank that bolts at "
                 "-£60k. One bad month from a Section 114.",
        "starting_cash": 70000,
        "loan_principal": 680000,
        "loan_apr": 0.099,
        "overdraft_floor": -60000,
        "insolvency_grace": 3,
        "start_lorries": 3,
        "start_crew": 10,
        "fleet_age_years": 4.5,       # the whole fleet is on its last legs
        "win_streak": 21,
        "win_sat_floor": 80.0,
        "start_satisfaction": 72.0,
        "sat_recovery": 1.0,
        "karen_mult": 1.5,
        "diversion_target": 0.52,
        "diversion_fine_per_pct": 4000,
        "diversion_fine_cap": 220000,
        "landfill_rise": 0.08,
        "inspection_bonus": 12000,
        "inspection_fine": 30000,
        "grant_mult": 0.6,
        "penalty_mult": 1.25,
    },
}
DIFFICULTY_ORDER = ["easy", "medium", "hard"]


def get_difficulty(diff_id):
    """Preset dict for a difficulty id, falling back to easy."""
    return DIFFICULTY_PRESETS.get(diff_id, DIFFICULTY_PRESETS["easy"])


class StartupLoan:
    """A fixed-term amortising loan financing the starter fleet. A constant
    daily payment is charged; interest accrues daily on the outstanding
    balance, and the remainder pays down principal until the loan clears."""

    def __init__(self, principal, annual_rate, term_days):
        self.principal   = float(principal)
        self.balance     = float(principal)
        self.annual_rate = annual_rate
        self.daily_rate  = annual_rate / 365.0
        self.term_days   = term_days
        self.cleared     = principal <= 0
        self.total_paid  = 0.0
        r, n = self.daily_rate, term_days
        if r <= 0 or n <= 0:
            self.daily_payment = principal / max(1, n)
        else:
            self.daily_payment = principal * r / (1.0 - (1.0 + r) ** (-n))

    def current_payment(self):
        """The cash leaving the budget today (smaller on the final payment)."""
        if self.cleared or self.balance <= 0:
            return 0.0
        interest = self.balance * self.daily_rate
        return min(self.daily_payment, self.balance + interest)

    def accrue_day(self):
        """Apply one day of interest and principal reduction. Returns True on
        the day the loan is finally cleared."""
        if self.cleared:
            return False
        interest = self.balance * self.daily_rate
        pay = min(self.daily_payment, self.balance + interest)
        self.balance = max(0.0, self.balance + interest - pay)
        self.total_paid += pay
        if self.balance <= 0.005:
            self.balance = 0.0
            self.cleared = True
            return True
        return False

    def progress(self):
        if self.principal <= 0:
            return 1.0
        return max(0.0, min(1.0, 1.0 - self.balance / self.principal))


class Economy:
    # ----- profit & loss ledger schema ------------------------------------
    REVENUE_KEYS = {"council_tax", "business_rates", "recycling_credit",
                    "garden_charges", "grants"}
    EXPENSE_KEYS = {"wages", "oncosts", "vehicles", "gate_fees", "rental_costs",
                    "loan_repayment", "depot_rent", "insurance", "repairs",
                    "diversion_fines"}
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
        ("repairs",          "Vehicle repairs"),
        ("gate_fees",        "Disposal gate fees"),
        ("loan_repayment",   "Startup loan repayment"),
        ("depot_rent",       "Depot rent"),
        ("insurance",        "Fleet & liability insurance"),
        ("diversion_fines",  "Recycling diversion fines"),
    ]

    # ── Difficulty-tuned fields ──────────────────────────────────────────────
    # Class-level defaults double as fallbacks for economies unpickled from
    # saves made before difficulty existed (their instance __dict__ lacks these
    # attributes, so lookups fall through to the class — i.e. old saves behave
    # as "easy", which is exactly what they were).
    difficulty        = "easy"
    difficulty_label  = DIFFICULTY_PRESETS["easy"]["label"]
    overdraft_floor   = OVERDRAFT_FLOOR
    insolvency_grace  = INSOLVENCY_GRACE_DAYS
    landfill_rise     = LANDFILL_TAX_ANNUAL_RISE
    diversion_fine_per_pct = DIVERSION_FINE_PER_PCT
    diversion_fine_cap     = DIVERSION_FINE_CAP
    sat_recovery      = 1.25
    karen_mult        = 1.0
    inspection_bonus  = 22000
    inspection_fine   = 18000
    start_lorries     = 4
    start_crew        = 16
    fleet_age_years   = 0.0

    def __init__(self, difficulty="easy"):
        preset = get_difficulty(difficulty)
        self.difficulty       = difficulty if difficulty in DIFFICULTY_PRESETS else "easy"
        self.difficulty_label = preset["label"]

        self.budget = preset["starting_cash"]
        self.council_tax_rate = 0.45
        self.business_rates = 2.20
        self.hourly_wage_rate = 16.50
        self.truck_maintenance = 45.00

        # ── Startup loan financing the initial fleet ─────────────────────────
        self.loan = StartupLoan(preset["loan_principal"],
                                preset["loan_apr"],
                                STARTUP_LOAN_TERM_DAYS)

        # ── Fail-condition tolerances (bank patience shrinks with difficulty)
        self.overdraft_floor  = preset["overdraft_floor"]
        self.insolvency_grace = preset["insolvency_grace"]

        # ── Statutory / escalator severity ───────────────────────────────────
        self.landfill_rise          = preset["landfill_rise"]
        self.diversion_fine_per_pct = preset["diversion_fine_per_pct"]
        self.diversion_fine_cap     = preset["diversion_fine_cap"]

        # ── Public-mood tuning ───────────────────────────────────────────────
        self.sat_recovery = preset["sat_recovery"]
        self.karen_mult   = preset["karen_mult"]

        # ── Event severity ───────────────────────────────────────────────────
        self.inspection_bonus = preset["inspection_bonus"]
        self.inspection_fine  = preset["inspection_fine"]

        # ── Starting fleet shape (read by FleetManager.setup_initial_fleet) ──
        self.start_lorries   = preset["start_lorries"]
        self.start_crew      = preset["start_crew"]
        self.fleet_age_years = preset["fleet_age_years"]

        # ── Recurring fixed overheads ────────────────────────────────────────
        self.depot_rent_daily = DEPOT_RENT_DAILY
        self.insurance_base   = INSURANCE_BASE_DAILY
        self.insurance_per_veh = INSURANCE_PER_VEH

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
        self.last_day_budget = self.budget
        self.daily_revenue = 0
        self.daily_expenses = 0

        self.ledger = self._blank_ledger()
        self.history = []
        self.budget_history = []   # daily closing budget snapshots (charts window)

        self.satisfaction = preset["start_satisfaction"]
        self.complaints_total = 0
        self.complaints_today = 0
        # Borough-wide recycling contamination, derived from the areas' emergent
        # rates each day (see boroughsim); cached here for the HUD/Waste window.
        self.borough_contamination = 0.06
        # (name, satisfaction) of the unhappiest populated round, for the HUD.
        self.worst_area = None

        # Disposal-facility network (finite landfill + processors). Created once
        # the city exists via init_facilities(); until then disposal is
        # unconstrained (menu backdrop / very early startup).
        self.facilities = None
        self._residual_day_accum = 0.0   # residual disposed so far today
        self.residual_per_day_est = 0.0  # smoothed estimate for "years left"
        # Baseline "you can't please everyone" gripes — a trickle of complaints
        # that never fully stops and rises as satisfaction falls. Tallied and
        # displayed separately from genuine overflow complaints so they never
        # break the perfect-service streak.
        self.karen_complaints_today = 0

        self.active_event = None
        self.pending_event = None
        self._bin_rate_multiplier = 1
        self._event_bin_mult = 1           # event-only (no weather); see update()
        self._recycling_multiplier = 1.0   # boosted by recycling_drive

        # Editable difficulty levers
        self.event_chance = 0.30
        self.win_streak_target = preset["win_streak"]
        self.win_sat_floor = preset["win_sat_floor"]
        self.win_sat_floor_base = preset["win_sat_floor"]   # elections re-derive

        # ── Politics: reputation, administration & election cycle (Phase 4) ──
        # The council as a feedback system (see politics.py). Reputation is a
        # slow-moving performance score; the administration installs priorities
        # at each election; the *_base fields are the difficulty baselines the
        # administration modifiers are applied on top of (so they don't compound).
        self.reputation = 60.0
        self.administration = "balanced"
        self.term_number = 0
        self.business_relief = 0.0
        self.grant_mult_base = preset.get("grant_mult", 1.0)

        # Notices raised during a day-rollover (loan cleared, diversion fines),
        # drained by the game loop and shown in the event banner.
        self.day_notices = []

        # ── Achievements ──────────────────────────────────────────────────────
        # Minimal, idempotent unlock tracking: id -> {"name", "desc", "day"}.
        # Unlocking pushes a one-off banner via day_notices or pending_event
        # (see _unlock_achievement) -- there's no separate achievements UI tab,
        # this just records that it happened and shows the player once.
        self.achievements = {}

        # ── Statutory recycling diversion tracking ───────────────────────────
        self.diversion_target       = preset["diversion_target"]
        self.diversion_target_base  = preset["diversion_target"]   # election baseline
        self.residual_volume_year   = 0.0
        self.diverted_volume_year   = 0.0
        self._diversion_year_index  = 0
        self.last_diversion_pct     = None   # previous year's reviewed result

        # Win condition
        self.perfect_days_streak = 0
        self.has_won = False
        self.win_day = None
        self.win_celebration_timer = 0.0

        # Lose condition (Section 114 / insolvency) — mirrors the win block.
        self.has_lost = False
        self.lost_day = None
        self.lost_reason = ""
        self.insolvent_days = 0          # consecutive days spent at/below £0
        self.game_over_timer = 0.0       # counts up for the overlay fade-in

        # Procurement notifications
        self.procurement_events = []

        # ── Dynamic procurement market (Phase 4) ─────────────────────────────
        # External conditions move new-vehicle prices and lead times: a
        # manufacturer shortage stretches deliveries and lifts prices, a battery
        # shortage specifically hammers electric orders, a supplier glut is a
        # buying opportunity. Shifts every few weeks; applied when an order is
        # placed (see fleet.order_vehicle).
        self.procurement_market = "normal"
        self._market_timer = random.randint(20, 45)

        # ── Emergent crisis monitor (Phase 5) ────────────────────────────────
        # Watches the simulation and narrates crises that emerge from the systems
        # themselves (see crises.py) — it never causes them.
        import crises
        self.crisis_monitor = crises.CrisisMonitor()

        # Ambient weather: "dry" | "rain" | "snow" | "overcast"
        self.weather = "dry"
        self._weather_timer = 0           # days remaining for current weather spell

        # ── Diesel fuel market (bounded random walk around 1.0) ──────────────
        self.fuel_index = 1.0
        self.fuel_index_trend = 0.0       # yesterday→today delta, for the UI arrow

        # Road-works events — independent of active_event, up to 3 concurrent.
        # Each entry: {"tiles": set, "remaining_days": int}
        self.road_works_active = []

        # ── Worker morale (0–100) ──────────────────────────────────────────────
        # Tracks crew sentiment toward their pay.  Starts at ~72 (neutral at the
        # default £16.50/hr wage).  Falls when wages are cut, rises when raised.
        # Low morale strongly increases the chance of a crew_strike event.
        self.worker_morale = self._morale_target()

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
            # Windfalls shrink and one-off bills grow with difficulty — a
            # struggling borough gets leaner grants and nastier surprises.
            {"id": "recycling_grant", "name": "Recycling Grant",
             "desc": (f"Awarded a GBP {int(75000 * preset['grant_mult']):,} "
                      "sustainability grant from Westminster!"),
             "duration": 0, "effect": "money",
             "value": int(75000 * preset["grant_mult"])},
            {"id": "fleet_breakdown", "name": "Fleet Breakdown",
             "desc": (f"Emergency RCV maintenance bill: "
                      f"GBP {int(20000 * preset['penalty_mult']):,}."),
             "duration": 0, "effect": "money",
             "value": -int(20000 * preset["penalty_mult"])},
            {"id": "fly_tipping", "name": "Fly-Tipping Complaint",
             "desc": (f"Illegal dumping reported. Council clean-up bill: "
                      f"GBP {int(12000 * preset['penalty_mult']):,}."),
             "duration": 0, "effect": "money",
             "value": -int(12000 * preset["penalty_mult"])},
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

        # The event-only portion (bank holiday, heatwave, ...), captured before
        # weather is folded in. The per-stream waste model applies weather with
        # stream resolution (rain hits residual/garden, not food), so it reads
        # this event-only value to avoid double-counting weather.
        self._event_bin_mult = self._bin_rate_multiplier

        # Weather bin-rate bump (rain makes bags tear) — kept for the legacy
        # aggregate path (menu backdrop / old readers of get_bin_rate_multiplier).
        if self.weather == "rain":
            self._bin_rate_multiplier *= 1.25
        elif self.weather == "snow":
            self._bin_rate_multiplier *= 1.10

        frac     = dt / self.day_duration
        sat_mult = 0.65 + 0.35 * (self.satisfaction / 100.0)

        council  = city.population * self.council_tax_rate * tax_mult * sat_mult
        business = (city.metrics["commercial"] * self.business_rates * business_mult
                    * self.business_rate_elasticity())
        self.ledger["council_tax"]    += council  * frac
        self.ledger["business_rates"] += business * frac

        base_wages   = fleet.workers * self.hourly_wage_rate * wage_mult * HOURS_PER_DAY
        # Employer NI: 13.8 % on earnings above the daily secondary threshold
        _ni_ph       = max(0.0, self.hourly_wage_rate * wage_mult * HOURS_PER_DAY
                           - self.ni_secondary_daily) * self.employer_ni_rate
        oncosts      = (fleet.workers * _ni_ph
                        + base_wages * self.pension_rate
                        + fleet.workers * self.ppe_daily)
        vehicles     = fleet.daily_vehicle_cost(self.fuel_index, self.fuel_fraction)
        rental_costs = fleet.get_rental_costs()
        self.ledger["wages"]        += base_wages   * frac
        self.ledger["oncosts"]      += oncosts      * frac
        self.ledger["vehicles"]     += vehicles     * frac
        self.ledger["rental_costs"] += rental_costs * frac

        # ── Recurring fixed overheads (per in-game day, metered per frame) ────
        depot_rent = self.depot_rent_daily
        insurance  = self.insurance_estimate(len(fleet.trucks))
        loan_pay   = self.loan.current_payment()
        self.ledger["depot_rent"]     += depot_rent * frac
        self.ledger["insurance"]      += insurance  * frac
        self.ledger["loan_repayment"] += loan_pay   * frac

        # Stream-accurate disposal: the fleet reports the actual per-stream mass
        # tipped (and the recycling rejected as contaminated), so gate fees and
        # diversion follow the real composition of what was collected rather than
        # re-splitting a mixed volume by policy share.
        masses, reject, total = fleet.take_pending_streams()
        gate = recycle = garden = 0.0
        if total > 0:
            # Residual gate fee escalates both with the annual landfill-tax rise
            # AND with how full the landfill is (a nearly-full site charges far
            # more; a full one forces costly export). Diverted streams go to their
            # own processors and are unaffected.
            fac_mult = (self.facilities.residual_gate_multiplier()
                        if self.facilities else 1.0)
            gate, recycle, garden, res_u, div_u = waste.disposal_economics_streams(
                masses, self.landfill_tax_multiplier() * fac_mult, reject_mass=reject)
            recycle *= self._recycling_multiplier
            self.ledger["gate_fees"]        += gate
            self.ledger["recycling_credit"] += recycle
            self.ledger["garden_charges"]   += garden
            # Track residual vs diverted mass for the statutory annual review.
            self.residual_volume_year += res_u
            self.diverted_volume_year += div_u
            # Consume landfill capacity with the residual (incl. rejected
            # recycling) actually landfilled, and accumulate today's intake for
            # the "years left" estimate.
            if self.facilities is not None:
                self.facilities.dispose(res_u)
                self._residual_day_accum += res_u

        revenue  = (council + business) * frac
        expenses = (base_wages + oncosts + vehicles + rental_costs
                    + depot_rent + insurance + loan_pay) * frac
        self.daily_revenue  += revenue
        self.daily_expenses += expenses
        self.budget += (revenue - expenses)
        if total > 0:
            self.budget += (recycle + garden - gate)
        # The budget is allowed to dip into the red (emergency borrowing), but a
        # hard overdraft floor exists. Reaching it is instant insolvency.
        if self.budget <= self.overdraft_floor:
            self.budget = self.overdraft_floor
            self._trigger_bankruptcy(
                "Overdraft limit breached — the bank has called in the "
                "borough's debts.")
        return new_day

    def _on_new_day(self, city=None, fleet=None):
        # Finalise the day that just ended
        self.ledger["day"] = self.day
        self.history.append(self.ledger)
        if len(self.history) > 30:
            self.history.pop(0)
        self.ledger = self._blank_ledger()
        self.day_notices = []

        self.budget_trend    = self.budget - self.last_day_budget
        self.last_day_budget = self.budget
        self.daily_revenue   = 0
        self.daily_expenses  = 0
        self.complaints_today = 0
        self.day        += 1
        self.week_index  = (self.day - 1) // 7

        # ---- startup loan: accrue a day of interest / repayment --------------
        if self.loan.accrue_day():
            notice = self._unlock_achievement(
                "debt_free", "Achievement Unlocked: Debt Free",
                "The startup fleet loan is fully repaid. That daily "
                "repayment is gone for good — the books just got easier.")
            if notice:
                self.day_notices.append(notice)

        # ---- statutory recycling-diversion annual review --------------------
        year = (self.day - 1) // COUNCIL_YEAR_DAYS
        if year != self._diversion_year_index:
            self._review_diversion()
            self._diversion_year_index = year

        # ---- insolvency watch (Section 114 fail condition) -------------------
        # Count consecutive days finishing at/below £0. Sustained insolvency
        # forces a Section 114 notice once the grace period is exhausted.
        if self.budget <= 0:
            self.insolvent_days += 1
            if self.insolvent_days >= self.insolvency_grace:
                self._trigger_bankruptcy(
                    f"Insolvent for {self.insolvent_days} consecutive days — "
                    "the borough has issued a Section 114 notice.")
        else:
            self.insolvent_days = 0

        # ---- age / expire the active event -----------------------------------
        if self.active_event:
            self.active_event["remaining_days"] -= 1
            if self.active_event["remaining_days"] <= 0:
                self._clear_event_effects(self.active_event, city, fleet)
                self.active_event = None

        # ---- advance road-works independently --------------------------------
        self._update_road_works(city, fleet)

        # ---- disposal facilities: roll the day's intake, refresh estimate ----
        if self.facilities is not None:
            # Smoothed residual-per-day estimate drives the landfill "years left".
            if self._residual_day_accum > 0:
                if self.residual_per_day_est <= 0:
                    self.residual_per_day_est = self._residual_day_accum
                else:
                    self.residual_per_day_est += (
                        self._residual_day_accum - self.residual_per_day_est) * 0.25
            self._residual_day_accum = 0.0
            self.facilities.on_new_day()

        # ---- ambient weather transitions -------------------------------------
        self._tick_weather()

        # ---- diesel pump price drifts each day -------------------------------
        self._tick_fuel_index()

        # ---- procurement market drifts (shortages / gluts) -------------------
        _mkt_notice = self._tick_procurement_market()
        if _mkt_notice:
            self.day_notices.append(_mkt_notice)

        # ---- worker morale (wage-to-strike pipeline) -------------------------
        # Update morale BEFORE the event check so fresh morale affects today.
        self._update_worker_morale()

        # ---- politics: reputation, performance grants, elections -------------
        import politics
        for notice in politics.update_daily(self):
            self.day_notices.append(notice)

        # ---- fire a new event (at most one active at a time) -----------------
        if not self.active_event:
            # Guaranteed crew strike when wages are at statutory minimum and
            # morale has cratered — workers will not tolerate minimum-wage pay.
            _at_min = self.hourly_wage_rate <= MORALE_NLW + 0.01
            if _at_min and self.worker_morale < 25.0:
                template = next(
                    (e for e in self.events if e["id"] == "crew_strike"), None)
                if template:
                    evt = dict(template)
                    evt["remaining_days"] = template["duration"]
                    evt["desc"] = ("Outrage! Wages cut to statutory minimum. "
                                   "Crews have walked out — no collections today.")
                    if fleet:
                        fleet.on_strike = True
                    self.active_event = evt
                    self.pending_event = evt

            elif random.random() < self.event_chance:
                template = self._weighted_event_choice()
                evt = {**template, "remaining_days": template["duration"]}
                effect = template["effect"]

                if effect == "truckBreakdown" and fleet:
                    days = random.randint(1, 7)
                    evt["remaining_days"] = days
                    evt["duration"]       = days
                    bd_name = self._apply_truck_breakdown(fleet, evt)
                    if bd_name:
                        evt["desc"] = (f"{bd_name} has broken down and will be out of "
                                       f"action for {days} day{'s' if days != 1 else ''}.")
                elif effect == "money":
                    self.budget += template["value"]
                    if template["value"] > 0:
                        self.ledger["grants"] += template["value"]
                elif effect == "crewStrike" and fleet:
                    fleet.on_strike = True
                elif effect == "councilInspection":
                    if self.satisfaction >= 70:
                        bonus = self.inspection_bonus
                        self.budget += bonus
                        self.ledger["grants"] += bonus
                        evt["desc"] = (f"Inspection passed! Performance rated "
                                       f"\"{self.satisfaction_label()}\". "
                                       f"GBP {bonus:,} bonus grant awarded.")
                    else:
                        fine = self.inspection_fine
                        self.budget -= fine
                        evt["desc"] = (f"Inspection failed! Service rated "
                                       f"\"{self.satisfaction_label()}\". "
                                       f"GBP {fine:,} penalty issued.")
                elif effect == "heavy_rain" or (effect == "binRate" and template["id"] == "heavy_rain"):
                    self.weather = "rain"
                    self._weather_timer = 1

                self.active_event = evt
                self.pending_event = evt

        # ---- snapshot the closing budget for the trend graph ------------------
        self.budget_history.append(self.budget)
        if len(self.budget_history) > 30:
            self.budget_history.pop(0)

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
        """Drift morale 20 % of the way toward the wage-based target each day.
        Workers notice pay cuts — morale craters within ~3 days of a wage slash."""
        target = self._morale_target()
        self.worker_morale += (target - self.worker_morale) * 0.20
        self.worker_morale = max(0.0, min(100.0, self.worker_morale))

    def _crew_strike_weight(self):
        """Event weight for crew_strike relative to every other event (1.0).

        High morale  → weight < 1  (strikes suppressed)
        Neutral (72) → weight ≈ 1  (baseline)
        Low morale   → weight up to 8  (strikes very likely when any event fires)
        """
        m = self.worker_morale / 100.0
        if m >= 0.72:
            # Morale at or above neutral — gradually suppress strike events
            # 0.72 → 1.0,  1.0 → 0.15
            t = (m - 0.72) / 0.28
            return max(0.15, 1.0 - t * 0.85)
        else:
            # Morale below neutral — ramp up sharply
            # 0.72 → 1.0,  0.0 → 8.0
            t = (0.72 - m) / 0.72
            return 1.0 + t * 7.0

    # Random-event weights. Events whose consequences the simulation now
    # produces on its own (breakdowns from usage wear, grants from reputation,
    # inspections from the reputation system) are dialled right down, so the
    # drama increasingly *emerges* from the systems rather than being scripted
    # (Phase 5). They're kept, not removed, for occasional variety.
    EVENT_BASE_WEIGHTS = {
        "vehicle_breakdown": 0.35,   # now emerges from usage-based wear
        "fleet_breakdown":   0.4,    # ditto (maintenance bills come from wear)
        "council_inspection": 0.5,   # reputation system covers performance review
        "recycling_grant":   0.55,   # endogenous performance grants cover this
    }

    def _event_base_weight(self, e):
        return self.EVENT_BASE_WEIGHTS.get(e["id"], 1.0)

    def _weighted_event_choice(self):
        """Pick a random event, biasing crew_strike by current morale and
        down-weighting events the simulation now generates emergently."""
        weights = [
            (self._crew_strike_weight() if e["id"] == "crew_strike"
             else self._event_base_weight(e))
            for e in self.events
        ]
        return random.choices(self.events, weights=weights, k=1)[0]

    def strike_risk_pct(self):
        """Approximate daily probability (%) that the next event is a crew strike.
        Used by the UI to show a human-readable risk indicator."""
        if not self.events:
            return 0.0
        weights = [
            (self._crew_strike_weight() if e["id"] == "crew_strike"
             else self._event_base_weight(e))
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
    def _apply_truck_breakdown(self, fleet, event=None):
        """Mark one active truck as broken. Records the broken truck id on the
        supplied event dict (the about-to-be-activated event, which is not yet
        stored in self.active_event). Returns the truck name or None.

        The victim is chosen biased toward the least-reliable (oldest) lorries,
        so wear shows up as failures on the vehicles you've run into the ground."""
        truck = fleet.weighted_breakdown_target()
        if truck is None:
            return None
        truck["broken"] = True
        truck["path"]   = []
        truck["state"]  = "depot"
        target = event if event is not None else self.active_event
        if target is not None:
            target["broken_truck_id"] = truck["id"]
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

    # ----- debug helper ------------------------------------------------------
    def force_event(self, event_id, fleet=None):
        """Debug tool: immediately fire a specific event template by id,
        bypassing the normal random weighted selection. Mirrors the firing
        logic in update(). Returns True if the event was found and fired."""
        template = next((e for e in self.events if e["id"] == event_id), None)
        if template is None:
            return False
        evt = {**template, "remaining_days": template["duration"]}
        effect = template["effect"]

        if effect == "truckBreakdown" and fleet:
            days = random.randint(1, 7)
            evt["remaining_days"] = days
            evt["duration"]       = days
            bd_name = self._apply_truck_breakdown(fleet, evt)
            if bd_name:
                evt["desc"] = (f"{bd_name} has broken down and will be out of "
                               f"action for {days} day{'s' if days != 1 else ''}.")
        elif effect == "money":
            self.budget += template["value"]
            if template["value"] > 0:
                self.ledger["grants"] += template["value"]
        elif effect == "crewStrike" and fleet:
            fleet.on_strike = True
        elif effect == "councilInspection":
            if self.satisfaction >= 70:
                bonus = self.inspection_bonus
                self.budget += bonus
                self.ledger["grants"] += bonus
                evt["desc"] = (f"Inspection passed! Performance rated "
                               f"\"{self.satisfaction_label()}\". "
                               f"GBP {bonus:,} bonus grant awarded.")
            else:
                fine = self.inspection_fine
                self.budget -= fine
                evt["desc"] = (f"Inspection failed! Service rated "
                               f"\"{self.satisfaction_label()}\". "
                               f"GBP {fine:,} penalty issued.")
        elif effect == "heavy_rain" or (effect == "binRate" and template["id"] == "heavy_rain"):
            self.weather = "rain"
            self._weather_timer = 1

        self.active_event = evt
        self.pending_event = evt
        return True

    # ----- ambient weather -------------------------------------------------
    def _tick_weather(self):
        """Randomly change weather each day for ambient visuals. Winter swaps
        wet spells for snow, so the seasons read on the map as well as the HUD."""
        if self._weather_timer > 0:
            self._weather_timer -= 1
            return
        winter = self.season_name() == "Winter"
        r = random.random()
        if r < 0.60:
            self.weather = "dry"
        elif r < 0.85:
            # Wet weather — falls as snow in winter, rain otherwise.
            self.weather = "snow" if winter else "rain"
            self._weather_timer = random.randint(1, 3)
        else:
            self.weather = "overcast"

    # ----- dynamic procurement market --------------------------------------
    # Each state carries multipliers on new-vehicle price and lead time, with an
    # optional electric-specific overlay (a battery shortage hits eRCVs hardest).
    PROCUREMENT_MARKETS = {
        "normal": {"label": "Steady", "price": 1.0, "lead": 1.0,
                   "ev_price": 1.0, "ev_lead": 1.0,
                   "blurb": "The RCV market is steady."},
        "shortage": {"label": "Manufacturer shortage", "price": 1.16, "lead": 1.45,
                     "ev_price": 1.16, "ev_lead": 1.45,
                     "blurb": "Chassis shortages: new lorries are dearer and "
                              "slower to arrive."},
        "battery": {"label": "Battery shortage", "price": 1.02, "lead": 1.05,
                    "ev_price": 1.30, "ev_lead": 1.7,
                    "blurb": "A cell-supply crunch: electric RCVs are much dearer "
                             "and delivery times have blown out."},
        "surge": {"label": "Demand surge", "price": 1.12, "lead": 1.3,
                  "ev_price": 1.12, "ev_lead": 1.3,
                  "blurb": "Councils nationwide are re-fleeting: order books are "
                           "full, pushing up prices and lead times."},
        "glut": {"label": "Supplier glut", "price": 0.88, "lead": 0.8,
                 "ev_price": 0.9, "ev_lead": 0.85,
                 "blurb": "Overcapacity at the factories — a good moment to buy."},
    }
    _MARKET_WEIGHTS = {"normal": 0.50, "shortage": 0.16, "battery": 0.12,
                       "surge": 0.12, "glut": 0.10}

    def _tick_procurement_market(self):
        """Drift the procurement market. Returns a notice dict on a change."""
        self._market_timer -= 1
        if self._market_timer > 0:
            return None
        prev = self.procurement_market
        states = list(self._MARKET_WEIGHTS.keys())
        weights = list(self._MARKET_WEIGHTS.values())
        self.procurement_market = random.choices(states, weights=weights, k=1)[0]
        self._market_timer = random.randint(18, 40)
        if self.procurement_market == prev or self.procurement_market == "normal":
            return None
        m = self.PROCUREMENT_MARKETS[self.procurement_market]
        return {"name": f"Procurement: {m['label']}", "desc": m["blurb"],
                "effect": "procurement"}

    def procurement_market_info(self):
        return self.PROCUREMENT_MARKETS.get(
            getattr(self, "procurement_market", "normal"),
            self.PROCUREMENT_MARKETS["normal"])

    def procurement_mods(self, model_id):
        """(price_multiplier, lead_multiplier) for ordering `model_id` now."""
        m = self.procurement_market_info()
        if model_id == "electric":
            return m["ev_price"], m["ev_lead"]
        return m["price"], m["lead"]

    # ----- diesel fuel market ----------------------------------------------
    def _tick_fuel_index(self):
        """Drift the diesel price index as a bounded random walk. Most days
        move a little; the occasional shock jolts it (refinery outage, duty
        change, sterling wobble)."""
        prev = self.fuel_index
        step = random.gauss(0.0, 0.03)
        if random.random() < 0.08:               # rare price shock
            step += random.choice((-1, 1)) * random.uniform(0.06, 0.12)
        # Gentle pull back toward 1.0 so it never runs away for long.
        step += (1.0 - prev) * 0.05
        self.fuel_index = max(FUEL_INDEX_MIN,
                              min(FUEL_INDEX_MAX, round(prev + step, 4)))
        self.fuel_index_trend = self.fuel_index - prev

    def fuel_price(self):
        """Pump price in £/litre implied by the current index."""
        return FUEL_BASE_PRICE * self.fuel_index

    def fuel_index_label(self):
        idx = self.fuel_index
        if idx >= 1.30:   return "High"
        if idx >= 1.10:   return "Dear"
        if idx >= 0.92:   return "Steady"
        if idx >= 0.82:   return "Cheap"
        return "Low"

    # ----- seasonal calendar -----------------------------------------------
    def season_index(self):
        """0=Spring, 1=Summer, 2=Autumn, 3=Winter for the current day."""
        return ((self.day - 1) // SEASON_LENGTH) % 4

    def season_name(self):
        return SEASON_NAMES[self.season_index()]

    def season_day(self):
        """Which day (1-based) of the current season we're on."""
        return ((self.day - 1) % SEASON_LENGTH) + 1

    def seasonal_fill_mult(self):
        """How much faster bins fill this season (garden/food swing)."""
        return SEASON_FILL_MULT.get(self.season_name(), 1.0)

    # ----- fixed overheads & escalators ------------------------------------
    def insurance_estimate(self, n_vehicles):
        """Daily fleet & liability insurance for a given fleet size."""
        return self.insurance_base + self.insurance_per_veh * max(0, n_vehicles)

    def landfill_tax_multiplier(self):
        """Escalator applied to the residual gate fee. Landfill tax rises each
        council year; year 0 = 1.0, compounding by the difficulty's annual
        rise (6-8%)."""
        year = (self.day - 1) // COUNCIL_YEAR_DAYS
        return (1.0 + self.landfill_rise) ** year

    # ----- disposal facilities ---------------------------------------------
    def init_facilities(self, city):
        """Create the disposal-facility network sized to the borough. Called when
        a game (or edited city) starts."""
        import facilities
        self.facilities = facilities.FacilityNetwork(
            getattr(city, "property_count", 1500))

    def ensure_facilities(self, city):
        if self.facilities is None:
            self.init_facilities(city)
        return self.facilities

    def landfill_status(self):
        """Landfill/disposal status dict for the UI, or None before init."""
        if self.facilities is None:
            return None
        return self.facilities.status(self.residual_per_day_est)

    def can_expand_landfill(self):
        if self.facilities is None:
            return False
        cost = self.facilities.expansion_cost(self.facilities.default_expansion())
        return self.budget >= cost

    def expand_landfill(self):
        """Buy a landfill expansion (capital cost). Returns (ok, message)."""
        if self.facilities is None:
            return False, "No landfill to expand."
        added = self.facilities.default_expansion()
        cost = self.facilities.expansion_cost(added)
        if self.budget < cost:
            return False, (f"Not enough in the bank — a "
                           f"£{cost:,.0f} expansion is needed.")
        self.budget -= cost
        self.facilities.expand(added)
        return True, (f"Landfill expanded by {added:,.0f} units for "
                      f"£{cost:,.0f}. Capacity now "
                      f"{self.facilities.landfill.capacity:,.0f}.")

    def landfill_tax_pct_increase(self):
        """How much dearer landfill is now vs year one, as a percentage."""
        return (self.landfill_tax_multiplier() - 1.0) * 100.0

    # ----- statutory recycling diversion -----------------------------------
    def current_diversion_pct(self):
        """Running diversion rate (%) for the council year so far, or None."""
        tot = self.residual_volume_year + self.diverted_volume_year
        if tot <= 0:
            return None
        return self.diverted_volume_year / tot * 100.0

    def _review_diversion(self):
        """End-of-year statutory review: fine the borough if it diverted less
        than the target share of waste from landfill. Resets the accumulators."""
        tot = self.residual_volume_year + self.diverted_volume_year
        if tot > 0:
            rate = self.diverted_volume_year / tot
            self.last_diversion_pct = rate * 100.0
            if rate < self.diversion_target:
                short_pp = (self.diversion_target - rate) * 100.0
                fine = int(min(self.diversion_fine_cap,
                               short_pp * self.diversion_fine_per_pct))
                if fine > 0:
                    self.budget -= fine
                    self.ledger["diversion_fines"] += fine
                    self.day_notices.append({
                        "name": "Statutory Recycling Fine",
                        "desc": (f"Last year diverted only {rate * 100:.0f}% from "
                                 f"landfill against a {self.diversion_target * 100:.0f}% "
                                 f"statutory target. DEFRA penalty: £{fine:,}. "
                                 f"Enable more recycling streams to comply."),
                        "effect": "money",
                    })
        self.residual_volume_year = 0.0
        self.diverted_volume_year = 0.0

    # ----- startup loan queries --------------------------------------------
    def loan_balance(self):
        return self.loan.balance if self.loan else 0.0

    def loan_daily_payment(self):
        return self.loan.current_payment() if self.loan else 0.0

    def loan_progress(self):
        return self.loan.progress() if self.loan else 1.0

    def loan_cleared(self):
        return (not self.loan) or self.loan.cleared

    def can_pay_off_loan(self):
        """Whether there's enough in the bank to settle the loan in full
        right now."""
        return (not self.loan_cleared()) and self.budget >= self.loan_balance()

    def pay_off_loan(self):
        """Settle the entire outstanding startup loan balance today, in one
        lump sum. No early-repayment penalty is modelled (this is a council
        loan, not an FCA-regulated personal one) -- you simply stop accruing
        interest from this point on. Returns (ok, message) for the caller to
        relay to the player."""
        if self.loan_cleared():
            return False, "The startup loan is already cleared."
        amount = self.loan_balance()
        if self.budget < amount:
            short = amount - self.budget
            return False, f"Not enough in the bank — £{short:,.0f} short of the £{amount:,.0f} owed."
        self.budget -= amount
        self.loan.balance = 0.0
        self.loan.cleared = True
        notice = self._unlock_achievement(
            "debt_free", "Achievement Unlocked: Debt Free",
            f"Paid off the remaining £{amount:,.0f} on the startup loan in "
            f"one go. No more daily repayments eating into the budget.")
        if notice:
            # Fires immediately rather than waiting for the next day-rollover
            # (pending_event is drained every frame; see main.py update()).
            self.pending_event = notice
        return True, f"Loan paid off in full — £{amount:,.0f} cleared."

    # ----- achievements ------------------------------------------------------
    def _unlock_achievement(self, aid, name, desc):
        """Record an achievement once, idempotently. Returns a banner-ready
        notice dict on first unlock, or None if already unlocked."""
        if aid in self.achievements:
            return None
        self.achievements[aid] = {"name": name, "desc": desc, "day": self.day}
        return {"name": name, "desc": desc, "effect": "achievement"}

    # ----- tax & business-rate pressure --------------------------------------
    # Both council tax and business rates start "free" at their baseline
    # value (the Economy defaults) and only start costing the borough once
    # pushed above it -- a player who never touches the sliders sees none of
    # this.
    def council_tax_pressure(self):
        """How far council tax sits above baseline, as a ratio (0 = at or
        below baseline, 1.0 = double baseline)."""
        if BASELINE_COUNCIL_TAX <= 0:
            return 0.0
        return max(0.0, self.council_tax_rate / BASELINE_COUNCIL_TAX - 1.0)

    def business_rate_pressure(self):
        if BASELINE_BUSINESS_RATE <= 0:
            return 0.0
        return max(0.0, self.business_rates / BASELINE_BUSINESS_RATE - 1.0)

    def business_rate_elasticity(self):
        """Steep business rates push marginal firms to close their doors or
        relocate, eroding the commercial tax base the rate is levied on.
        Modelled as a softening multiplier on business-rate revenue -- about
        35% lost at double the baseline rate, floored so the line never
        collapses to nothing. A pro-business administration eases this."""
        relief = getattr(self, "business_relief", 0.0)
        return max(0.55, 1.0 - self.business_rate_pressure() * 0.35 * (1.0 - relief))

    def tax_satisfaction_penalty(self):
        """Combined drag on the satisfaction ceiling from rate pressure:
        residents grumble directly about a high council tax bill, and a
        visibly thinning high street (empty units from rate-driven closures)
        costs a bit more on top. Each capped well short of wiping the
        ceiling out entirely."""
        council_hit  = min(45.0, self.council_tax_pressure() * 80.0)
        business_hit = min(20.0, self.business_rate_pressure() * 22.0)
        return council_hit + business_hit

    # ----- service quality -------------------------------------------------
    def register_day_quality(self, city, waste, service_ceiling=100.0):
        """Once-per-day service-quality review. The heavy lifting now lives in
        the spatial model (boroughsim): each collection round tracks its own
        satisfaction, complaints and recycling contamination, driven by its
        resident cohorts and the service it actually receives. The borough-wide
        satisfaction and complaint totals the HUD/win-condition read are derived
        from those areas, so the map itself becomes the management tool — a
        missed collection primarily hurts the affected round, not the whole
        borough at once."""
        import boroughsim
        result = boroughsim.update_day(city, self, waste, service_ceiling)

        # Borough satisfaction is now a population-weighted average of the rounds.
        self.satisfaction = max(0.0, min(100.0, result["satisfaction"]))

        daily_complaints = result["complaints_today"]
        self.complaints_today  = daily_complaints
        self.complaints_total += daily_complaints
        # Baseline "you can't please everyone" gripes, summed from the rounds and
        # tallied separately so they never break the perfect-service streak.
        self.karen_complaints_today = result["karen_today"]
        self.complaints_total += result["karen_today"]
        # Cached for the HUD/heatmap and as a fallback contamination figure.
        self.borough_contamination = boroughsim.borough_contamination(city, waste)
        self.worst_area = result.get("worst_area")

        # A perfect day only counts toward the win if satisfaction is also
        # holding above the statutory floor — residents won't reward a borough
        # that's merely scraping by, even on a complaint-free day.
        perfect_day = (daily_complaints == 0
                       and self.satisfaction >= self.win_sat_floor)
        if perfect_day:
            self.perfect_days_streak += 1
        else:
            self.perfect_days_streak = 0

        if self.perfect_days_streak >= self.win_streak_target and not self.has_won \
                and not self.has_lost:
            self.has_won      = True
            self.win_day      = self.day
            self.win_celebration_timer = 10.0
            # Quiet, per-difficulty record (the win banner does the fanfare);
            # shows up in the Finance window's achievements list.
            self._unlock_achievement(
                f"champion_{self.difficulty}",
                f"Achievement Unlocked: Borough Champion ({self.difficulty_label})",
                f"Held a {self.win_streak_target}-day perfect service streak "
                f"on {self.difficulty_label} difficulty.")

    # ----- queries ---------------------------------------------------------
    def get_bin_rate_multiplier(self):
        return self._bin_rate_multiplier

    def get_event_bin_multiplier(self):
        """Event-only bin-rate multiplier (excludes weather, which the
        per-stream waste model applies itself)."""
        return getattr(self, "_event_bin_mult", self._bin_rate_multiplier)

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
                "nickname":  t.get("nickname", f"L{t['id']}"),
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
        """Adjust hourly wage rate. Floor is UK 2025 National Living Wage (£11.44)."""
        old_wage = self.hourly_wage_rate
        self.hourly_wage_rate = round(
            max(11.44, min(50.0, self.hourly_wage_rate + delta)), 2)
        # Immediate morale shock when wages are slashed to statutory minimum.
        # Workers don't adjust gradually to this — it causes instant outrage.
        if self.hourly_wage_rate <= MORALE_NLW + 0.01 and old_wage > MORALE_NLW + 0.01:
            self.worker_morale = max(0.0, self.worker_morale - 55.0)

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

    # ----- fail condition --------------------------------------------------
    def _trigger_bankruptcy(self, reason):
        """Flag the borough as insolvent. Idempotent — the first reason wins."""
        if self.has_lost:
            return
        self.has_lost = True
        self.lost_day = self.day
        self.lost_reason = reason
        self.game_over_timer = 0.0

    def is_insolvent(self):
        """True while the budget is in the red (warning state, not yet a fail)."""
        return self.budget <= 0

    def days_until_insolvency_fail(self):
        """Days of grace left before a sustained-insolvency Section 114. Returns
        None when solvent."""
        if self.budget > 0:
            return None
        return max(0, self.insolvency_grace - self.insolvent_days)
