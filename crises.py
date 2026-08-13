"""
crises.py
=========

Emergent situation detector — the payoff of the whole simulation.

Nothing in here *causes* a crisis. Every problem the borough faces is already
produced by the interacting systems built in the earlier phases: an autumn
garden surge fills bins faster, bulky loads mean more tip trips, longer rounds
finish late, missed collections pile up, complaints rise, satisfaction and
reputation fall. This module simply *watches* that state each day, recognises
when a genuine situation is developing, and tells the story — so the player can
look at a problem and understand its causal chain instead of being handed a
scripted "Autumn Crisis" card.

Each detector reads a handful of live signals and, when thresholds are crossed,
emits a situation with a short narrative naming the cause → effect chain and the
lever that addresses it. Situations are tracked across days so a report fires
once as it emerges (and quietly clears when it resolves) rather than nagging.

Cheap: one pass over the (few) collection rounds plus some scalars, once per day.
"""


def _trend(history, n=4):
    """Simple recent trend of a value list (positive = rising)."""
    if len(history) < 2:
        return 0.0
    recent = history[-n:]
    return recent[-1] - recent[0]


class CrisisMonitor:
    """Tracks emergent situations across days. Lives on the economy so it
    persists in saves. Call assess() once per day."""

    def __init__(self):
        self.active = {}        # id -> {"name","severity","narrative","lever","since"}
        self._miss_history = []  # borough missed-round count per day
        self._complaint_history = []

    # ------------------------------------------------------------------ assess
    def assess(self, game):
        """Examine the borough and return a list of NEWLY-emerged situation
        notices (for the event banner). Updates self.active in place."""
        eco = game.economy
        city = game.city
        fleet = game.fleet
        waste = game.waste

        # --- Gather cheap signals ------------------------------------------
        missed = 0
        backlog_rounds = 0
        worst_area = None
        for a in city.areas:
            if a.property_count <= 0:
                continue
            interval = 7 * max(1, a.frequency)
            last = getattr(a, "last_collected", -1)
            overdue = (last >= 0 and (eco.day - last) > interval + 1)
            if overdue:
                missed += 1
            if getattr(a, "complaints_today", 0) > 0:
                backlog_rounds += 1
            sat = getattr(a, "satisfaction", 100.0)
            if a.population > 0 and (worst_area is None or sat < worst_area[1]):
                worst_area = (a.name, sat)

        self._miss_history.append(missed)
        self._complaint_history.append(eco.complaints_today)
        if len(self._miss_history) > 12:
            self._miss_history.pop(0)
        if len(self._complaint_history) > 12:
            self._complaint_history.pop(0)

        season = eco.season_name()
        garden = waste.get("garden")
        food = waste.get("food")
        active_lorries = fleet.active_lorries()
        broken = sum(1 for t in fleet.trucks if t.get("broken"))
        fatigued = sum(1 for t in fleet.trucks
                       if t.get("fatigue", 0.0) > 0.55 and t.get("crew", 0) >= 1)
        lf = eco.landfill_status()
        complaint_trend = _trend(self._complaint_history)

        detected = {}

        # --- Seasonal surge overwhelming capacity --------------------------
        # The canonical emergent story: a season that swells garden/food waste,
        # colliding with a fleet that can't quite keep up, so rounds slip.
        surge_season = season in ("Autumn", "Summer")
        if surge_season and (missed >= 2 or (backlog_rounds >= 3 and complaint_trend > 0)):
            stream = "garden" if season == "Autumn" else "food and garden"
            on = (garden and garden.enabled) or (food and food.enabled)
            tail = (f"so {missed} rounds are now running late." if missed > 0
                    else "and rounds are struggling to keep pace as complaints "
                    "climb.")
            detected["seasonal_surge"] = {
                "name": f"{season} waste surge",
                "severity": "high" if missed >= 4 else "medium",
                "narrative": (
                    f"{season} is swelling {stream} waste. Bins are filling "
                    f"faster than the fleet can clear them, " + tail),
                "lever": ("Add collection capacity, or the surge will keep "
                          "outpacing the fleet"
                          if on else
                          "Seasonal waste is going to the black bin; a caddy "
                          "service would spread the load"),
            }

        # --- Fleet overstretched (independent of season) -------------------
        elif missed >= 3 or (fatigued >= max(1, active_lorries // 2) and fatigued > 0):
            detected["fleet_stretched"] = {
                "name": "Fleet overstretched",
                "severity": "high" if missed >= 5 else "medium",
                "narrative": (
                    f"{active_lorries} working lor{'ries' if active_lorries != 1 else 'ry'} "
                    f"can't cover the rounds on time — "
                    f"{missed} overdue, crews fatigued. Late rounds mean full "
                    f"bins and rising complaints."),
                "lever": "Buy or hire another RCV, or hire crew to run overtime",
            }

        # --- Breakdown cluster ---------------------------------------------
        if broken >= 2:
            detected["breakdowns"] = {
                "name": "Breakdowns hitting service",
                "severity": "high" if broken >= 3 else "medium",
                "narrative": (
                    f"{broken} lorries are off the road. A worked-hard fleet "
                    f"breaks down more; each one out stretches the rest and "
                    f"pushes rounds late."),
                "lever": "Cover with a spot rental; plan replacements before the "
                         "fleet ages further",
            }

        # --- Landfill crunch ------------------------------------------------
        if lf and (lf["fill_pct"] >= 80 or lf["is_full"] or lf["gate_mult"] >= 1.6):
            if lf["is_full"]:
                nar = ("The landfill is FULL — residual waste is being exported "
                       "at a premium, and every tonne to landfill now costs far "
                       "more.")
            else:
                nar = (f"The landfill is {lf['fill_pct']:.0f}% full and disposal "
                       f"costs have climbed to x{lf['gate_mult']:.1f}. Residual "
                       f"waste is quietly draining the budget.")
            detected["landfill_crunch"] = {
                "name": "Landfill nearing capacity",
                "severity": "high" if (lf["is_full"] or lf["fill_pct"] >= 92) else "medium",
                "narrative": nar,
                "lever": "Recycle more to divert waste from the tip, or fund an "
                         "expansion",
            }

        # --- Contamination undermining recycling ---------------------------
        cont = getattr(eco, "borough_contamination", 0.0)
        if cont >= 0.17 and (garden is None or True):
            rec = waste.get("recycling")
            if rec and rec.enabled:
                detected["contamination"] = {
                    "name": "Recycling contamination high",
                    "severity": "medium",
                    "narrative": (
                        f"About {cont*100:.0f}% of dry recycling is being "
                        f"rejected at the MRF and landfilled instead — it earns "
                        f"nothing, costs gate fees, and drags diversion down."),
                    "lever": ("Offer food/garden caddies so scraps stay out of "
                              "the dry bin; consider an education campaign"),
                }

        # --- Financial squeeze ---------------------------------------------
        if eco.budget < 40000 and eco.budget_trend < -2000:
            detected["financial"] = {
                "name": "Finances under pressure",
                "severity": "high" if eco.budget < 15000 else "medium",
                "narrative": (
                    f"Reserves are down to £{int(eco.budget):,} and falling "
                    f"£{abs(int(eco.budget_trend)):,}/day. Squeezed budgets defer "
                    f"fleet investment — an older fleet breaks down more and "
                    f"service slips further."),
                "lever": "Raise council tax, lift diversion for grants, or trim "
                         "costs before the bank steps in",
            }

        # --- Political pressure --------------------------------------------
        rep = getattr(eco, "reputation", 60.0)
        if rep < 42 and eco.satisfaction < 60:
            detected["political"] = {
                "name": "Political pressure building",
                "severity": "medium",
                "narrative": (
                    f"Reputation has slid to {rep:.0f}/100 on the back of poor "
                    f"service. No performance grants at this level, and the next "
                    f"election won't be kind."),
                "lever": "Restore service quality in the worst rounds to rebuild "
                         "reputation",
            }

        # --- Diff against last day, with hysteresis so a situation on the edge
        # of its threshold doesn't flicker and re-announce itself. A situation
        # fires its narrative once when it first emerges, then stays active while
        # it keeps re-detecting within CLEAR_DAYS, and only clears after that many
        # quiet days.
        CLEAR_DAYS = 6
        new_notices = []
        for sid, sit in detected.items():
            if sid in self.active:
                # Refresh narrative/severity/lever; keep the original start day.
                prev = self.active[sid]
                sit["since"] = prev["since"]
                sit["last_seen"] = eco.day
                self.active[sid] = sit
            else:
                sit["since"] = eco.day
                sit["last_seen"] = eco.day
                self.active[sid] = sit
                new_notices.append({
                    "name": sit["name"],
                    "desc": sit["narrative"] + "  → " + sit["lever"] + ".",
                    "effect": "situation",
                })
        for sid in list(self.active.keys()):
            if sid not in detected:
                if eco.day - self.active[sid].get("last_seen", eco.day) >= CLEAR_DAYS:
                    del self.active[sid]

        if worst_area:
            self.worst_area = worst_area
        return new_notices

    def active_situations(self):
        """Ordered list of current situations (worst first) for the UI."""
        order = {"high": 0, "medium": 1, "low": 2}
        return sorted(self.active.values(),
                      key=lambda s: order.get(s.get("severity"), 3))
