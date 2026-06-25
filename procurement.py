"""
procurement.py
==============

Three-tier fleet procurement system with distinct risk/reward profiles:

Tier 1: Factory Custom Order (180+ Days Lead Time)
  - Cheap purchase price, fully customized capacity/fuel type
  - Player must wait multiple in-game months
  - Best for long-term fleet planning

Tier 2: Pre-Built Stock Dealer Purchase (14–18 Days Lead Time)
  - Dealer already has chassis and compactor body built
  - 2-week delay = MOT safety plating, registration, delivery logistics
  - Premium price but solves immediate fleet shortages

Tier 3: Instant Spot Rental (1–2 Days Lead Time)
  - Available immediately for breakdown coverage
  - Massive daily operating costs drain profits
  - Emergency use only

Procurement Events (during Tier 2 waiting window):
  - Bureaucracy Bottleneck: O-License paperwork delays by 5 days
  - PDI Flaw: Hydraulic compactor blade fault, 3-day repair bay delay
"""

import random


# ---------------------------------------------------------------------------
#  Procurement Tier Definitions
# ---------------------------------------------------------------------------

class ProcurementTier:
    """Defines a procurement method with its cost modifiers and lead time rules."""

    def __init__(self, tier_id, name, display_name, lead_time_min, lead_time_max,
                 price_multiplier, daily_cost_multiplier, description, blurb,
                 can_customize=False, event_eligible=False):
        self.tier_id = tier_id
        self.name = name
        self.display_name = display_name
        self.lead_time_min = lead_time_min
        self.lead_time_max = lead_time_max
        self.price_multiplier = price_multiplier
        self.daily_cost_multiplier = daily_cost_multiplier
        self.description = description
        self.blurb = blurb
        self.can_customize = can_customize
        self.event_eligible = event_eligible

    def random_lead_time(self):
        return random.randint(self.lead_time_min, self.lead_time_max)


PROCUREMENT_TIERS = {
    "factory": ProcurementTier(
        "factory", "factory", "Factory Custom Order",
        lead_time_min=180, lead_time_max=220,
        price_multiplier=0.65, daily_cost_multiplier=1.0,
        description="Order a bespoke RCV direct from the manufacturer. Cheapest upfront cost and full customisation, but you\'ll wait half a year.",
        blurb="Best value for money if you can plan ahead. Choose exact capacity, fuel type, and crew configuration.",
        can_customize=True,
        event_eligible=False,
    ),
    "dealer": ProcurementTier(
        "dealer", "dealer", "Dealer Stock Purchase",
        lead_time_min=14, lead_time_max=18,
        price_multiplier=1.15, daily_cost_multiplier=1.0,
        description="Buy a pre-built chassis and body from an authorised dealer. The 2-week wait covers UK MOT plating, operator licensing, and delivery logistics.",
        blurb="Premium price for near-immediate delivery. Watch out for paperwork delays and pre-delivery inspection faults during the waiting period.",
        can_customize=False,
        event_eligible=True,
    ),
    "rental": ProcurementTier(
        "rental", "rental", "Spot Rental",
        lead_time_min=1, lead_time_max=2,
        price_multiplier=0.05, daily_cost_multiplier=4.5,
        description="Emergency spot-hire to cover a breakdown or sudden demand spike. Vehicle arrives tomorrow, but running costs are crippling.",
        blurb="Use sparingly. The daily burn rate will devour your budget if kept on the books for more than a few days.",
        can_customize=False,
        event_eligible=False,
    ),
}


def get_tier(tier_id):
    return PROCUREMENT_TIERS.get(tier_id)


# ---------------------------------------------------------------------------
#  Vehicle Model
# ---------------------------------------------------------------------------

class Vehicle:
    """A purchasable RCV model in the catalogue."""

    def __init__(self, vid, name, *, capacity, crew_cap, speed_factor,
                 price, lease_weekly, running_cost, lead_time, blurb):
        self.id = vid
        self.name = name
        self.capacity = capacity          # fill units before a tip run
        self.crew_cap = crew_cap          # max loaders this body supports
        self.speed_factor = speed_factor  # multiplier on base road speed
        self.price = price                # outright purchase price (base)
        self.lease_weekly = lease_weekly  # weekly charge if leased
        self.running_cost = running_cost  # GBP/day fuel + upkeep when owned
        self.lead_time = lead_time        # base delivery lead time in in-game days
        self.blurb = blurb

    def get_price_for_tier(self, tier_id):
        """Return the adjusted price for a given procurement tier."""
        tier = get_tier(tier_id)
        if not tier:
            return self.price
        return int(self.price * tier.price_multiplier)

    def get_running_cost_for_tier(self, tier_id):
        """Return the adjusted daily running cost for a given tier."""
        tier = get_tier(tier_id)
        if not tier:
            return self.running_cost
        return int(self.running_cost * tier.daily_cost_multiplier)

    def deposit(self):
        """Up-front cost to place a lease order (roughly 4 weeks + delivery)."""
        return int(self.lease_weekly * 4)


# The catalogue. Prices reflect UK new-build RCV costs (2025/26).
VEHICLE_CATALOGUE = [
    Vehicle(
        "narrow", "Narrow-Track 7.5t",
        capacity=9000, crew_cap=2, speed_factor=1.15,
        price=115000, lease_weekly=780, running_cost=75, lead_time=14,
        blurb="Compact cab for terraced streets and alleys. Nips about, but a "
              "small hopper means frequent tips."),
    Vehicle(
        "standard", "Borough Standard 26t",
        capacity=18000, crew_cap=3, speed_factor=1.0,
        price=200000, lease_weekly=1300, running_cost=130, lead_time=15,
        blurb="The dependable 26t 6x2 workhorse. Balanced capacity and crew -- "
              "a safe first choice for most rounds."),
    Vehicle(
        "large", "Heavy Hopper 32t",
        capacity=30000, crew_cap=4, speed_factor=0.82,
        price=235000, lease_weekly=1560, running_cost=160, lead_time=17,
        blurb="Huge body for tower-block rounds. Slower and needs a full crew, "
              "but clears flats without endless tip runs."),
    Vehicle(
        "electric", "eRCV ZeroEmission",
        capacity=17000, crew_cap=3, speed_factor=0.95,
        price=425000, lease_weekly=2400, running_cost=50, lead_time=18,
        blurb="27t electric drivetrain. Steep to buy and a long lead time, but "
              "very cheap to run and quiet on early rounds."),
    Vehicle(
        "tipper", "Caged Tipper 3.5t",
        capacity=6000, crew_cap=2, speed_factor=1.25,
        price=42000, lease_weekly=300, running_cost=35, lead_time=14,
        blurb="Budget bulky/garden runabout. Tiny capacity, but quick to "
              "arrive and dirt cheap to keep on the books."),
]


def get_vehicle(vid):
    for v in VEHICLE_CATALOGUE:
        if v.id == vid:
            return v
    return None


# ---------------------------------------------------------------------------
#  Procurement Events
# ---------------------------------------------------------------------------

class ProcurementEvent:
    """A random event that can occur during the dealer waiting window."""

    EVENTS = [
        {
            "id": "bureaucracy_bottleneck",
            "name": "Bureaucracy Bottleneck",
            "description": "UK operator licensing (O-License) paperwork has been delayed. The Vehicle and Operator Services Agency (VOSA) needs another 5 days to process your application.",
            "delay_days": 5,
            "message": "O-License paperwork delayed by 5 days. Consider a spot rental to cover the gap.",
        },
        {
            "id": "pdi_flaw",
            "name": "PDI Flaw",
            "description": "The truck arrived on schedule, but the pre-delivery inspection found a faulty hydraulic compactor blade. It\'s been sent to the repair bay for 3 days.",
            "delay_days": 3,
            "message": "Hydraulic compactor blade fault detected. Vehicle in repair bay for 3 days.",
        },
    ]

    @classmethod
    def roll_event(cls):
        """Roll for a random procurement event. Returns event dict or None."""
        if random.random() < 0.35:  # 35% chance of an event
            return random.choice(cls.EVENTS)
        return None


# ---------------------------------------------------------------------------
#  Order System
# ---------------------------------------------------------------------------

class Order:
    """A vehicle on order, awaiting delivery, with procurement tier info."""

    def __init__(self, vehicle, order_day, tier_id, leased=False, custom_specs=None):
        self.vehicle = vehicle
        self.order_day = order_day
        self.tier_id = tier_id
        self.leased = leased
        self.custom_specs = custom_specs or {}  # For factory custom orders

        tier = get_tier(tier_id)
        self.base_lead_time = tier.random_lead_time() if tier else vehicle.lead_time
        self.arrival_day = order_day + self.base_lead_time

        # Procurement event tracking (dealer tier only)
        self.pending_event = None
        self.event_delay_days = 0
        self.event_name = None
        self.event_description = None
        self.event_triggered = False

        # For dealer tier, roll for a potential event at order time
        if tier and tier.event_eligible:
            event = ProcurementEvent.roll_event()
            if event:
                self.pending_event = event
                self.event_delay_days = event["delay_days"]
                self.event_name = event["name"]
                self.event_description = event["description"]
                self.arrival_day += self.event_delay_days

    @property
    def display_tier_name(self):
        tier = get_tier(self.tier_id)
        return tier.display_name if tier else self.tier_id

    @property
    def adjusted_price(self):
        return self.vehicle.get_price_for_tier(self.tier_id)

    @property
    def adjusted_running_cost(self):
        return self.vehicle.get_running_cost_for_tier(self.tier_id)

    @property
    def is_rental(self):
        return self.tier_id == "rental"

    def days_remaining(self, today):
        return max(0, self.arrival_day - today)

    def get_status_text(self, today):
        """Return a human-readable status string for the order."""
        remaining = self.days_remaining(today)
        if remaining <= 0:
            return "Ready for delivery"

        tier = get_tier(self.tier_id)
        lines = [
            f"{self.vehicle.name} — {self.display_tier_name}",
            f"Arriving: Day {self.arrival_day} ({remaining} day{'s' if remaining != 1 else ''} left)",
        ]

        if self.event_name and not self.event_triggered:
            lines.append(f"⚠ {self.event_name}: +{self.event_delay_days} days")
            lines.append(f"   {self.event_description}")
        elif self.event_triggered and self.event_name:
            lines.append(f"⚠ {self.event_name} resolved")

        if self.is_rental:
            lines.append(f"Daily cost: £{self.adjusted_running_cost}/day")
        else:
            lines.append(f"Price: £{self.adjusted_price:,}")
            if self.leased:
                lines.append(f"Lease: £{self.vehicle.lease_weekly}/week")
            else:
                lines.append(f"Running cost: £{self.adjusted_running_cost}/day")

        return "\n".join(lines)

    def trigger_event_if_due(self, today):
        """Check if the procurement event should trigger now."""
        if self.pending_event and not self.event_triggered:
            # Event triggers when we're within the delay period of arrival
            if today >= self.arrival_day - self.event_delay_days:
                self.event_triggered = True
                return self.pending_event
        return None
