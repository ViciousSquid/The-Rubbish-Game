"""
boroughsim.py
=============

Area-level social simulation: spatial satisfaction, spatial complaints,
resident cohorts and emergent recycling contamination.

The classic game tracked one borough-wide satisfaction score and one complaint
count. That made the map a picture rather than a management tool — you couldn't
see that Lower-Damp was drowning in bins while Northgate was fine. This module
replaces the single number with per-round (per-area) state derived from what is
actually happening on the ground, and rebuilds the borough figure as a
population-weighted average of the areas.

Lightweight by construction:

  * No per-resident agents. Each collection round carries a small *cohort mix*
    (families / retirees / students / affluent / low-income / business) inferred
    once from its building make-up. Cohorts set the round's sensitivities — how
    badly a missed collection stings, how diligently residents sort recycling,
    how high their service expectations sit.
  * All the daily work is one pass over building tiles, grouped by area — the
    same scan the economy already did, now bucketed by round. Runs once per
    in-game day.
  * Satisfaction dynamics deliberately mirror the old borough model's feel
    (slow recovery, sharp decay, drift toward a service ceiling) so the tuned
    balance carries over — it's just resolved per area now.

Emergent contamination replaces the old deterministic borough formula: each
round's recycling contamination grows from its cohort sorting habits, density,
whether food/garden caddies exist to divert scraps, recent missed collections,
weather and any education campaign. Cleaner rounds earn more recycling credit;
grubby ones get rejected at the MRF and landfilled.
"""

# ---------------------------------------------------------------------------
#  Cohorts
# ---------------------------------------------------------------------------
COHORT_IDS = ("family", "retiree", "student", "affluent", "lowincome", "business")
COHORT_LABELS = {
    "family": "Families", "retiree": "Retirees", "student": "Students",
    "affluent": "Affluent", "lowincome": "Low-income", "business": "Business",
}

# How each building style's residents split across cohorts. Weighted by the
# number of that style in a round, then normalised, to get the round's mix.
STYLE_COHORTS = {
    "bungalow":  {"retiree": 0.60, "family": 0.20, "affluent": 0.20},
    "terrace":   {"family": 0.45, "lowincome": 0.30, "student": 0.15, "retiree": 0.10},
    "semi":      {"family": 0.55, "retiree": 0.20, "affluent": 0.25},
    "detached":  {"affluent": 0.62, "family": 0.33, "retiree": 0.05},
    "flats":     {"student": 0.35, "lowincome": 0.35, "family": 0.20, "retiree": 0.10},
    "tower":     {"lowincome": 0.45, "student": 0.35, "family": 0.20},
    "shop":      {"business": 1.0},
    "office":    {"business": 1.0},
    "warehouse": {"business": 1.0},
    "highrise":  {"business": 1.0},
}

# Per-cohort behavioural profile:
#   missed    how strongly a missed / late collection hurts satisfaction
#   tax       sensitivity to council-tax / business-rate pressure
#   sort      recycling diligence (higher = cleaner loads, less contamination)
#   expect    service-quality expectation (higher = harder to please)
#   caddies   how much they value food/garden services (satisfaction)
#   base_cont irreducible contamination tendency for this cohort
COHORT_PROFILES = {
    "family":    {"missed": 1.20, "tax": 1.00, "sort": 0.70, "expect": 1.00, "caddies": 1.10, "base_cont": 0.08},
    "retiree":   {"missed": 1.30, "tax": 1.30, "sort": 0.92, "expect": 1.06, "caddies": 1.20, "base_cont": 0.05},
    "student":   {"missed": 0.62, "tax": 0.55, "sort": 0.34, "expect": 0.82, "caddies": 0.70, "base_cont": 0.19},
    "affluent":  {"missed": 1.12, "tax": 0.80, "sort": 0.86, "expect": 1.16, "caddies": 1.15, "base_cont": 0.06},
    "lowincome": {"missed": 0.92, "tax": 1.42, "sort": 0.52, "expect": 0.90, "caddies": 0.85, "base_cont": 0.12},
    "business":  {"missed": 1.02, "tax": 1.24, "sort": 0.60, "expect": 1.00, "caddies": 0.60, "base_cont": 0.11},
}


def _blank_cohorts():
    return {c: 0.0 for c in COHORT_IDS}


def compute_cohorts(city, area):
    """Infer a round's cohort mix from its buildings (weighted by count). Cheap;
    run once per area when a game starts or the map is edited."""
    mix = _blank_cohorts()
    total = 0.0
    for (x, y) in area.building_tiles:
        style = city.tiles[y][x].building_style
        split = STYLE_COHORTS.get(style)
        if not split:
            continue
        for coh, w in split.items():
            mix[coh] += w
        total += 1.0
    if total <= 0:
        # No buildings — treat as neutral family-ish so nothing divides by zero.
        return {"family": 1.0, **{c: 0.0 for c in COHORT_IDS if c != "family"}}
    for c in mix:
        mix[c] /= total
    return mix


def _weighted_profile(mix):
    """Population-mix-weighted average of the cohort profile parameters."""
    out = {"missed": 0.0, "tax": 0.0, "sort": 0.0, "expect": 0.0,
           "caddies": 0.0, "base_cont": 0.0}
    tot = sum(mix.values()) or 1.0
    for coh, w in mix.items():
        p = COHORT_PROFILES.get(coh)
        if not p:
            continue
        for k in out:
            out[k] += p[k] * w
    for k in out:
        out[k] /= tot
    return out


# ---------------------------------------------------------------------------
#  Per-area social state (stored on the Area object; lazily migrated)
# ---------------------------------------------------------------------------

def ensure_area(area, city, start_satisfaction):
    """Guarantee a round has its social fields (cohorts, satisfaction,
    complaints, contamination, education, miss tracking). Idempotent, so it also
    migrates rounds loaded from pre-Phase-2 saves."""
    if getattr(area, "cohorts", None) is None:
        area.cohorts = compute_cohorts(city, area)
        area.profile = _weighted_profile(area.cohorts)
    if not hasattr(area, "satisfaction") or area.satisfaction is None:
        area.satisfaction = float(start_satisfaction)
    if not hasattr(area, "complaints_today"):
        area.complaints_today = 0
    if not hasattr(area, "complaints_total"):
        area.complaints_total = 0
    if not hasattr(area, "contamination"):
        area.contamination = area.profile["base_cont"] if getattr(area, "profile", None) else 0.08
    if not hasattr(area, "education"):
        area.education = 0.0            # 0..1 recycling-education campaign level
    if not hasattr(area, "days_since_service"):
        area.days_since_service = 0
    if not hasattr(area, "missed_recent"):
        area.missed_recent = 0.0        # decaying tally of recent missed rounds


def init_borough(city, start_satisfaction=85.0):
    """(Re)compute cohorts and seed social state for every round. Called when a
    new game / edited city starts."""
    for area in city.areas:
        area.cohorts = compute_cohorts(city, area)
        area.profile = _weighted_profile(area.cohorts)
        area.satisfaction = float(start_satisfaction)
        area.complaints_today = 0
        area.complaints_total = 0
        area.contamination = area.profile["base_cont"]
        area.education = 0.0
        area.days_since_service = 0
        area.missed_recent = 0.0


def area_weight(area):
    """Weight a round contributes to the borough average — population, with a
    floor for commercial-only rounds (business residents count too)."""
    return max(1.0, area.population + area.property_count * 0.5)


def dominant_cohort(area):
    mix = getattr(area, "cohorts", None)
    if not mix:
        return None
    return max(mix.items(), key=lambda kv: kv[1])[0]


# ---------------------------------------------------------------------------
#  Emergent contamination
# ---------------------------------------------------------------------------

def _area_contamination_target(area, city, economy, waste):
    """Where a round's recycling contamination settles given local conditions.

    Emergent, not a single borough knob: cohort sorting habits set the baseline,
    then density, the absence of food/garden caddies (scraps foul the dry bin),
    recent missed collections (overflow contamination), wet weather and any
    education campaign push it up or down."""
    prof = area.profile
    # Cohort baseline (students/low-income foul more; retirees/affluent less).
    rate = prof["base_cont"]
    # Poor sorters push it up a touch beyond their base tendency.
    rate += (1.0 - prof["sort"]) * 0.05

    # Density: tightly-packed flats/towers contaminate more (communal bins,
    # transient residents). Approximate density by residents per property.
    if area.property_count > 0:
        dens = area.population / area.property_count
        rate += min(0.05, max(0.0, (dens - 3.0)) * 0.012)

    # No food caddy → scraps in the dry bin; no garden bin → soil/grass fouling.
    food = waste.get("food")
    if not (food and food.enabled):
        rate += 0.06
    garden = waste.get("garden")
    if not (garden and garden.enabled):
        rate += 0.02

    # Recent missed rounds: overflowing bins get cross-contaminated / rained on.
    rate += min(0.06, area.missed_recent * 0.02)

    # Weather: rain pulps card/paper.
    if getattr(economy, "weather", "dry") == "rain":
        rate += 0.02

    # Education campaign cleans loads up.
    rate -= area.education * 0.06

    return max(0.0, min(0.35, rate))


# ---------------------------------------------------------------------------
#  Daily update
# ---------------------------------------------------------------------------

def update_day(city, economy, waste, service_ceiling):
    """Advance every round's social state one day and return the borough
    aggregates. Replaces the borough-only satisfaction/complaints scan.

    Returns a dict with:
        satisfaction        pop-weighted borough satisfaction (0..100)
        complaints_today    total genuine overflow complaints borough-wide
        area_complaints     {area_id: complaints} for the map/heatmap
        worst_area          (name, satisfaction) of the unhappiest populated round
    """
    start_sat = getattr(economy, "satisfaction", 85.0)
    tax_penalty = economy.tax_satisfaction_penalty()
    recovery = getattr(economy, "sat_recovery", 1.25)
    karen_mult = getattr(economy, "karen_mult", 1.0)
    today = economy.get_day_of_week()
    week = getattr(economy, "week_index", 0)

    total_complaints = 0
    total_karen = 0
    area_complaints = {}
    wsum = 0.0
    wtot = 0.0
    worst = None

    for area in city.areas:
        ensure_area(area, city, start_sat)
        n = area.property_count
        if n <= 0:
            continue

        # --- Count this round's overflow complaints (bins overflowing 3+ days).
        # Increment per-tile overflow age here (moved out of the economy scan).
        a_complaints = 0
        for (x, y) in area.building_tiles:
            tile = city.tiles[y][x]
            if tile.bin_fill >= 100:
                tile.days_overflowing += 1
                if tile.days_overflowing > 2:
                    a_complaints += 1
            else:
                tile.days_overflowing = 0

        # --- Missed-collection tracking: is this round overdue for its slot?
        # A weekly round should be serviced ~every 7 days, fortnightly ~14.
        interval = 7 * max(1, area.frequency)
        last = area.last_collected
        overdue = (last >= 0 and (economy.day - last) > interval + 1) or \
                  (last < 0 and economy.day > interval + 2)
        if overdue:
            area.missed_recent = min(6.0, area.missed_recent + 1.0)
        else:
            area.missed_recent = max(0.0, area.missed_recent - 0.5)

        prof = area.profile

        # --- Local service ceiling: the borough service quality (which already
        # bakes in the flat value of each caddy on offer), minus tax drag, minus
        # this cohort's extra fussiness (affluent/retiree expect more so settle
        # lower for the same service), plus a small caddy MODULATION — retirees
        # value a garden bin more than students do. The modulation is centred on
        # zero so it doesn't double-count the caddy value already in the ceiling.
        caddy_mod = 0.0
        for sid in ("food", "garden"):
            s = waste.get(sid)
            if s and s.enabled:
                caddy_mod += (2.0 if sid == "food" else 1.2) * (prof["caddies"] - 1.0)
        expect_penalty = (prof["expect"] - 1.0) * 22.0
        ceiling = max(18.0, service_ceiling - tax_penalty - expect_penalty + caddy_mod)

        # --- Recovery vs decay, mirroring the borough model but per-area and
        # cohort-scaled. Overflow ratio drives sharp decay; clean days recover
        # slowly. Missed rounds add a direct sting scaled by cohort sensitivity.
        overflow_ratio = a_complaints / n
        sat = area.satisfaction
        if overflow_ratio <= 0.02:
            if sat < ceiling:
                sat = min(ceiling, sat + recovery)
        else:
            # Local overflow ratios are far spikier than the old borough-wide
            # figure, so the curve is gentler here: a neglected round degrades
            # sharply and visibly, but not instantly to zero, leaving room to
            # recover it before it drags the borough down.
            drop = min(30.0, overflow_ratio * 140.0) * prof["missed"]
            sat = max(0.0, sat - drop)
        if overdue:
            sat = max(0.0, sat - 2.5 * prof["missed"])

        # --- Baseline "you can't please everyone" gripes, cohort-weighted, plus
        # a gentle drag so satisfaction never pins at a flawless ceiling.
        dissat = (100.0 - sat) / 100.0
        karen_rate = 0.0011 * (0.45 + dissat) * karen_mult * (0.7 + 0.3 * prof["tax"])
        a_karen = int(n * karen_rate + 0.4)
        if a_karen > 0:
            sat = max(0.0, sat - min(1.0, a_karen / n * 26.0))

        # --- Drift toward the local ceiling (slow pull).
        sat += (ceiling - sat) * 0.04
        area.satisfaction = max(0.0, min(100.0, sat))

        # --- Emergent contamination drifts toward its local target.
        target = _area_contamination_target(area, city, economy, waste)
        area.contamination += (target - area.contamination) * 0.25
        area.contamination = max(0.0, min(0.35, area.contamination))
        # Education campaigns decay slowly once run.
        area.education = max(0.0, area.education - 0.02)

        area.complaints_today = a_complaints
        area.complaints_total += a_complaints + a_karen
        area_complaints[area.id] = a_complaints
        total_complaints += a_complaints
        total_karen += a_karen

        w = area_weight(area)
        wsum += area.satisfaction * w
        wtot += w
        if area.population > 0 and (worst is None or area.satisfaction < worst[1]):
            worst = (area.name, area.satisfaction)

    borough_sat = (wsum / wtot) if wtot > 0 else start_sat
    return {
        "satisfaction": borough_sat,
        "complaints_today": total_complaints,
        "karen_today": total_karen,
        "area_complaints": area_complaints,
        "worst_area": worst,
    }


def borough_contamination(city, waste):
    """Population-weighted borough contamination rate, for headline display and
    as a fallback when a load's servicing areas aren't tracked."""
    rec = waste.get("recycling")
    if not rec or not rec.enabled:
        return 0.0
    wsum = wtot = 0.0
    for area in city.areas:
        c = getattr(area, "contamination", None)
        if c is None:
            continue
        w = area_weight(area)
        wsum += c * w
        wtot += w
    if wtot <= 0:
        return 0.06
    return wsum / wtot
