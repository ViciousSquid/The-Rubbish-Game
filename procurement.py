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


# The catalogue. Prices reflect UK new-build RCV costs (2025/26): a 26t 6x2
# rear-loader runs ~£185k-£254k in recent council procurements, a 27t electric
# eRCV ~£420k, a 7.5t narrow compact ~£115k, and a 3.5t caged tipper ~£42k.
# Lease = indicative weekly contract-hire (operating lease, ~5yr, maintenance
# inclusive). lead_time is the build/delivery wait (new RCVs are months out;
# modelled here as 14-18 in-game days). running_cost = GBP/day fuel + upkeep when owned; RCVs are thirsty
# on stop-start rounds (~£100-£160/day diesel + maintenance), electrics far
# cheaper on energy.
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


class Order:
    """A vehicle on order, awaiting delivery."""

    def __init__(self, vehicle, order_day, leased):
        self.vehicle = vehicle
        self.order_day = order_day
        self.arrival_day = order_day + vehicle.lead_time
        self.leased = leased

    def days_remaining(self, today):
        return max(0, self.arrival_day - today)
