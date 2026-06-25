"""
procurement.py
==============

Realistic fleet procurement. Instead of one "Buy Lorry" button that instantly
spawns an identical truck, the council picks from a catalogue of refuse
collection vehicles (RCVs), each with its own capacity, crew requirement,
speed, running cost and *lead time* -- you place an order and the vehicle is
delivered to the depot a few in-game days later.

Two ways to pay:
    * Outright   -- full price up front, no ongoing finance cost.
    * Lease      -- a small delivery deposit now, then a weekly lease charge
                    for as long as you keep the vehicle (cheaper to get moving,
                    dearer to run).

Vehicle stats feed straight into the simulation: capacity sets how much a lorry
carries before tipping, crew_cap sets how many loaders it takes, speed_factor
scales its road speed, and running_cost / lease_weekly hit the daily ledger.
"""


class Vehicle:
    """A purchasable RCV model in the catalogue."""

    def __init__(self, vid, name, *, capacity, crew_cap, speed_factor,
                 price, lease_weekly, running_cost, lead_time, blurb):
        self.id = vid
        self.name = name
        self.capacity = capacity          # fill units before a tip run
        self.crew_cap = crew_cap          # max loaders this body supports
        self.speed_factor = speed_factor  # multiplier on base road speed
        self.price = price                # outright purchase price
        self.lease_weekly = lease_weekly  # weekly charge if leased
        self.running_cost = running_cost  # GBP/day fuel + upkeep when owned
        self.lead_time = lead_time        # delivery lead time in in-game days
        self.blurb = blurb

    def deposit(self):
        """Up-front cost to place a lease order (roughly 4 weeks + delivery)."""
        return int(self.lease_weekly * 4)


# The catalogue. Tuned so there's a genuine trade-off: cheap-but-small narrow
# cab for tight terraces, balanced workhorse, big-hopper for tower rounds, a
# pricey-but-cheap-to-run electric, and a budget garden/bulky tipper.
VEHICLE_CATALOGUE = [
    Vehicle(
        "narrow", "Narrow-Track 7.5t",
        capacity=9000, crew_cap=2, speed_factor=1.15,
        price=78000, lease_weekly=620, running_cost=34, lead_time=2,
        blurb="Compact cab for terraced streets and alleys. Nips about, but a "
              "small hopper means frequent tips."),
    Vehicle(
        "standard", "Borough Standard 26t",
        capacity=18000, crew_cap=3, speed_factor=1.0,
        price=120000, lease_weekly=940, running_cost=45, lead_time=3,
        blurb="The dependable workhorse. Balanced capacity and crew -- a safe "
              "first choice for most rounds."),
    Vehicle(
        "large", "Heavy Hopper 32t",
        capacity=30000, crew_cap=4, speed_factor=0.82,
        price=168000, lease_weekly=1280, running_cost=62, lead_time=5,
        blurb="Huge body for tower-block rounds. Slower and needs a full crew, "
              "but clears flats without endless tip runs."),
    Vehicle(
        "electric", "eRCV ZeroEmission",
        capacity=17000, crew_cap=3, speed_factor=0.95,
        price=240000, lease_weekly=1650, running_cost=18, lead_time=8,
        blurb="Electric drivetrain. Steep to buy and a long lead time, but very "
              "cheap to run and quiet on early rounds."),
    Vehicle(
        "tipper", "Caged Tipper 3.5t",
        capacity=6000, crew_cap=2, speed_factor=1.25,
        price=46000, lease_weekly=410, running_cost=26, lead_time=1,
        blurb="Budget bulky/garden runabout. Tiny capacity, but quick to "
              "arrive and dirt cheap to keep on the books."),
]


def get_vehicle(vid):
    for v in VEHICLE_CATALOGUE:
        if v.id == vid:
            return v
    return None


class Order:
    """A vehicle on order, awaiting delivery."""

    def __init__(self, vehicle, order_day, leased):
        self.vehicle = vehicle
        self.order_day = order_day
        self.arrival_day = order_day + vehicle.lead_time
        self.leased = leased

    def days_remaining(self, today):
        return max(0, self.arrival_day - today)
