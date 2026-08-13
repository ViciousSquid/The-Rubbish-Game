"""
politics.py
===========

The council as a feedback system: borough reputation, performance-linked grants,
and a periodic election that installs an administration whose priorities reshape
the constraints the player runs under.

This is the connective tissue that turns a pile of independent modifiers into an
economy that feeds back on itself:

    good service + high diversion + sound finances
        -> rising reputation
        -> performance grants and a friendlier electorate

    poor service + complaints + red ink
        -> falling reputation
        -> political pressure, a change of administration, tighter constraints

Reputation is a slow-moving 0..100 figure derived each day from satisfaction,
recycling diversion, financial health and complaints. It gates an annual
performance grant (a positive-feedback loop: doing well funds doing better) and
decides how an election goes.

Every few council years the electorate returns an administration chosen from the
borough's own condition — Austerity when the books are a mess, Green when
recycling leads, Pro-business when the high street carries the borough, Populist
when residents are restless. Each nudges priorities (the diversion target, grant
generosity, the satisfaction the public expects) rather than bolting on a
separate strategy game.

Deliberately lightweight: a few scalars updated once per day and a branch once
every few years. No new per-frame cost.
"""

from economy import COUNCIL_YEAR_DAYS

ELECTION_PERIOD_DAYS = COUNCIL_YEAR_DAYS * 3     # a term is three council years
PERFORMANCE_GRANT_PERIOD = COUNCIL_YEAR_DAYS     # reviewed annually


# ---------------------------------------------------------------------------
#  Administrations
# ---------------------------------------------------------------------------
# Each administration applies small, legible modifiers. `diversion_delta` shifts
# the statutory diversion target; `grant_mult` scales performance grants;
# `sat_expectation` nudges the satisfaction the electorate expects (folds into
# the win floor); `business_relief` softens business-rate pressure; `blurb` is
# the mandate shown to the player.
ADMINISTRATIONS = {
    "balanced": {
        "label": "Independent",
        "diversion_delta": 0.0, "grant_mult": 1.0, "sat_expectation": 0.0,
        "business_relief": 0.0,
        "blurb": "A steady independent council. No strong mandate — keep the "
                 "borough ticking over."},
    "austerity": {
        "label": "Austerity",
        "diversion_delta": -0.04, "grant_mult": 0.6, "sat_expectation": -1.0,
        "business_relief": 0.0,
        "blurb": "Elected to balance the books. Targets eased, but grant money "
                 "is scarce — live within your means."},
    "green": {
        "label": "Green",
        "diversion_delta": +0.06, "grant_mult": 1.6, "sat_expectation": +1.5,
        "business_relief": 0.0,
        "blurb": "A green mandate: divert more from landfill. Tougher recycling "
                 "target, but generous sustainability grants."},
    "probusiness": {
        "label": "Pro-business",
        "diversion_delta": -0.02, "grant_mult": 0.9, "sat_expectation": +0.5,
        "business_relief": 0.30,
        "blurb": "Open for business. Commercial rate pressure eased to keep the "
                 "high street trading; less for recycling."},
    "populist": {
        "label": "Populist",
        "diversion_delta": 0.0, "grant_mult": 1.1, "sat_expectation": +3.0,
        "business_relief": 0.0,
        "blurb": "Swept in on promises of spotless streets. Residents now expect "
                 "a first-class service — anything less won't do."},
}


def administration(aid):
    return ADMINISTRATIONS.get(aid, ADMINISTRATIONS["balanced"])


# ---------------------------------------------------------------------------
#  Reputation
# ---------------------------------------------------------------------------

def reputation_target(economy):
    """Where reputation is heading given the borough's current standing:
    satisfaction, recycling diversion vs target, financial health and complaint
    pressure. 0..100."""
    sat = economy.satisfaction

    # Diversion score: at/above target = full marks, sliding down below it.
    div = economy.current_diversion_pct()
    tgt = economy.diversion_target * 100.0
    if div is None:
        div_score = 55.0
    else:
        div_score = max(0.0, min(100.0, 55.0 + (div - tgt) * 2.2))

    # Financial score: healthy reserves and a shrinking loan read well.
    budget = economy.budget
    fin = 50.0
    if budget <= 0:
        fin = max(0.0, 30.0 + budget / 5000.0)     # deep red reads badly
    else:
        fin = min(100.0, 45.0 + budget / 8000.0)
    fin = min(100.0, fin + economy.loan_progress() * 12.0)

    # Complaint pressure knocks reputation regardless of the average mood.
    comp = getattr(economy, "complaints_today", 0)
    comp_pressure = min(30.0, comp * 0.4)

    target = (0.50 * sat + 0.22 * div_score + 0.20 * fin + 0.08 * 60.0)
    target -= comp_pressure
    return max(0.0, min(100.0, target))


def update_daily(economy):
    """Advance reputation, run the annual performance grant and the periodic
    election. Called from economy._on_new_day. Returns a list of notice dicts."""
    notices = []

    # --- Reputation drifts slowly toward its target.
    tgt = reputation_target(economy)
    economy.reputation += (tgt - economy.reputation) * 0.06
    economy.reputation = max(0.0, min(100.0, economy.reputation))

    # --- Annual performance grant (endogenous: good performance funds more).
    if economy.day > 1 and (economy.day % PERFORMANCE_GRANT_PERIOD) == 0:
        notices.extend(_award_performance_grant(economy))

    # --- Election every few years.
    if economy.day > 1 and (economy.day % ELECTION_PERIOD_DAYS) == 0:
        notices.extend(_run_election(economy))

    return notices


def _award_performance_grant(economy):
    """A central-government grant scaled by reputation and the ruling
    administration's generosity. Rewards a well-run borough with capital to
    reinvest — closing the good-service -> grants -> investment loop."""
    rep = economy.reputation
    if rep < 45.0:
        return [{
            "name": "Performance Review",
            "desc": (f"Annual review: reputation {rep:.0f}/100. No performance "
                     "grant this year — Whitehall wants to see improvement."),
            "effect": "reputation",
        }]
    admin = administration(economy.administration)
    base = (rep - 45.0) / 55.0                       # 0..1 above the threshold
    grant = int(base * 90000 * admin["grant_mult"] * economy.grant_mult_base)
    if grant <= 0:
        return []
    economy.budget += grant
    economy.ledger["grants"] = economy.ledger.get("grants", 0.0) + grant
    return [{
        "name": "Performance Grant",
        "desc": (f"Reputation {rep:.0f}/100 earns a £{grant:,} government "
                 f"performance grant. Reinvest it wisely."),
        "effect": "money",
    }]


def _choose_administration(economy):
    """Pick the administration the electorate returns, from the borough's own
    condition at election time. Scores each and takes the strongest pull."""
    sat = economy.satisfaction
    div = economy.current_diversion_pct()
    tgt = economy.diversion_target * 100.0
    budget = economy.budget
    complaints = getattr(economy, "complaints_today", 0)
    biz_pressure = economy.business_rate_pressure()

    scores = {
        "balanced": 0.5,
        "austerity": 0.0,
        "green": 0.0,
        "probusiness": 0.0,
        "populist": 0.0,
    }
    # Money trouble -> austerity.
    if budget < 40000:
        scores["austerity"] += 1.2
    if not economy.loan_cleared() and budget < 80000:
        scores["austerity"] += 0.4
    # Strong recycling & happy borough -> green.
    if div is not None and div >= tgt:
        scores["green"] += 0.9
    if sat >= 82:
        scores["green"] += 0.3
    # Restless residents -> populist.
    if sat < 65:
        scores["populist"] += 1.0
    if complaints > 20:
        scores["populist"] += 0.6
    # Business squeezed -> pro-business.
    if biz_pressure > 0.15:
        scores["probusiness"] += 0.9
    return max(scores.items(), key=lambda kv: kv[1])[0]


def _run_election(economy):
    """Hold an election, install the new administration and apply its modifiers
    on top of the difficulty baseline (so effects don't compound term on term)."""
    new_aid = _choose_administration(economy)
    economy.administration = new_aid
    economy.term_number = getattr(economy, "term_number", 0) + 1
    admin = administration(new_aid)

    # Re-derive modified constraints from the difficulty baseline each term.
    economy.diversion_target = max(
        0.30, min(0.60, economy.diversion_target_base + admin["diversion_delta"]))
    economy.win_sat_floor = economy.win_sat_floor_base + admin["sat_expectation"]
    economy.business_relief = admin["business_relief"]

    return [{
        "name": f"Election: {admin['label']} council",
        "desc": (f"The {admin['label']} group takes control (term "
                 f"{economy.term_number}). {admin['blurb']}"),
        "effect": "election",
    }]


def reputation_label(rep):
    if rep >= 80:
        return "Exemplary"
    if rep >= 65:
        return "Well-regarded"
    if rep >= 50:
        return "Steady"
    if rep >= 35:
        return "Under pressure"
    return "In disgrace"
