"""
facilities.py
=============

Disposal-facility network: the landfill stops being an infinite hole in the
ground and becomes a strategic infrastructure asset.

The borough tips residual waste (plus recycling rejected as contaminated) into a
landfill with a *finite* capacity. As it fills:

  * gate fees escalate (a nearly-full site charges far more per unit),
  * a permitted daily throughput caps how much can be tipped cheaply; excess
    spills to costly export/transfer,
  * once full, everything must be exported at a premium until the site is
    expanded.

This wires straight into the emergent economy: heavy landfill use (a thin
recycling policy, or a residual surge) fills the site faster, which raises
disposal costs, which pressures the budget — pushing the player toward recycling
(which diverts waste and extends the landfill's life) or a capital-funded
expansion.

Diverted streams (clean recycling, food, garden) go to their own processors
(MRF / anaerobic digestion / composting) which are effectively unconstrained and
priced through the waste policy — so they never consume landfill capacity. That
is what makes diversion pay off twice: cheaper disposal *and* a longer-lived tip.

The model is deliberately abstract (capacity in the same disposal "units" the
rest of the sim uses) and cheap: a handful of scalars updated per tip and per
day. The network holds a list of facilities so more physical sites can be added
later without reworking callers.
"""


# Capacity (in disposal units) per property. Sized so the landfill is a
# multi-year strategic asset, not a first-year cliff: on a thin (residual-heavy)
# policy a typical borough fills it in roughly three council years (~30% in year
# one, so early-game economics stay close to the classic balance), and recycling
# stretches that out further. By the time it bites, the player has levers —
# recycle more (diverts waste, extends life) or fund an expansion.
CAPACITY_PER_PROPERTY = 2600.0
MIN_CAPACITY = 900_000.0

# Permitted daily throughput as a fraction of one council year's worth of
# average intake; tipping beyond it in a day spills to export at a surcharge.
THROUGHPUT_HEADROOM = 1.8

EXPORT_SURCHARGE = 3.5     # residual gate multiplier when the site is full
EXPANSION_UNIT_COST = 0.09  # GBP of capital per unit of added capacity


class Facility:
    """A single disposal destination. The landfill is capacity-constrained; the
    processors (MRF/AD/compost) and the export route are effectively
    unconstrained sinks kept for completeness and future physical siting."""

    def __init__(self, fid, name, kind, capacity, accepts,
                 daily_throughput=0.0):
        self.id = fid
        self.name = name
        self.kind = kind                 # "landfill" | "transfer" | "processor"
        self.capacity = float(capacity)  # 0 == unconstrained
        self.remaining = float(capacity)
        self.consumed_total = 0.0
        self.daily_intake = 0.0
        self.daily_throughput = float(daily_throughput)   # 0 == uncapped
        self.accepts = set(accepts)
        self.expansions = 0

    def fill_fraction(self):
        if self.capacity <= 0:
            return 0.0
        return max(0.0, min(1.0, 1.0 - self.remaining / self.capacity))

    def is_full(self):
        return self.capacity > 0 and self.remaining <= 0.0

    def years_left_at(self, per_day):
        if self.capacity <= 0 or per_day <= 0:
            return None
        from economy import COUNCIL_YEAR_DAYS
        return self.remaining / per_day / COUNCIL_YEAR_DAYS


class FacilityNetwork:
    """The borough's disposal network. Currently one physical landfill plus
    unconstrained processors, but structured as a list so additional physical
    facilities (a second landfill, a transfer station) can be dropped in and the
    routing/economics extended to choose between them."""

    def __init__(self, property_count):
        cap = max(MIN_CAPACITY, property_count * CAPACITY_PER_PROPERTY)
        # Rough average daily residual intake used only to derive a sane permitted
        # daily throughput headroom (players rarely hit it unless there's a surge).
        est_daily = cap / 1.4 / 112.0
        self.landfill = Facility(
            "landfill", "Borough Landfill", "landfill", cap,
            accepts={"residual"},
            daily_throughput=est_daily * THROUGHPUT_HEADROOM)
        self.facilities = [self.landfill]
        # Running record for the UI: how much went to export (over-cap / full).
        self.exported_total = 0.0
        self.daily_exported = 0.0

    # ---------------------------------------------------------------- disposal
    def residual_gate_multiplier(self):
        """Multiplier on the residual gate fee from how full the landfill is.
        Empty ~1.0, steeply dearer as it fills, and an export premium once full.
        Applied on top of the annual landfill-tax escalator."""
        lf = self.landfill
        if lf.is_full():
            return EXPORT_SURCHARGE
        f = lf.fill_fraction()
        # Gentle at first, steeper near the top: ~1.0 empty, ~1.3 half-full,
        # ~2.2 approaching full, then the export premium once actually full.
        return 1.0 + f * f * 1.2

    def dispose(self, residual_units):
        """Account `residual_units` of residual (incl. rejected recycling) into
        the landfill, consuming capacity. Anything beyond the remaining capacity
        is 'exported' (still disposed, but tracked separately). Returns the units
        that were exported rather than landfilled."""
        if residual_units <= 0:
            return 0.0
        lf = self.landfill
        exported = 0.0
        if lf.capacity > 0:
            landfilled = min(residual_units, lf.remaining)
            exported = residual_units - landfilled
            lf.remaining = max(0.0, lf.remaining - landfilled)
            lf.consumed_total += landfilled
            lf.daily_intake += landfilled
        else:
            landfilled = residual_units
            lf.consumed_total += landfilled
            lf.daily_intake += landfilled
        if exported > 0:
            self.exported_total += exported
            self.daily_exported += exported
        return exported

    def on_new_day(self):
        """Reset the per-day intake meters (called at the day rollover)."""
        self.landfill.daily_intake = 0.0
        self.daily_exported = 0.0

    # --------------------------------------------------------------- expansion
    def expansion_cost(self, added_capacity):
        return int(added_capacity * EXPANSION_UNIT_COST)

    def default_expansion(self):
        """A sensible expansion increment: ~40% of the original capacity."""
        return max(MIN_CAPACITY * 0.4, self.landfill.capacity * 0.4)

    def expand(self, added_capacity):
        lf = self.landfill
        lf.capacity += added_capacity
        lf.remaining += added_capacity
        lf.expansions += 1

    # ------------------------------------------------------------------ status
    def status(self, per_day_estimate=0.0):
        lf = self.landfill
        return {
            "capacity": lf.capacity,
            "remaining": lf.remaining,
            "fill_pct": lf.fill_fraction() * 100.0,
            "gate_mult": self.residual_gate_multiplier(),
            "is_full": lf.is_full(),
            "daily_intake": lf.daily_intake,
            "throughput": lf.daily_throughput,
            "years_left": lf.years_left_at(per_day_estimate),
            "exported_total": self.exported_total,
            "expansions": lf.expansions,
        }
