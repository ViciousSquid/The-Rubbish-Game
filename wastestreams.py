"""
wastestreams.py
===============

Per-property multi-stream waste model.

The classic game modelled a property's waste as a single ``bin_fill`` value
(0-100 %) with the borough-wide :class:`waste.WastePolicy` splitting *collected*
volume between streams after the fact. That made policy an economic lever but
gave it no *physical* consequence: a missed recycling collection just meant a
slightly higher generic ``bin_fill``.

This module gives every building four independent kerbside receptacles:

    0  residual   black bin      weekly    reference-sized, compacts well
    1  recycling  dry recycling  fortnightly  big bin, bulky, can contaminate
    2  food        caddy         weekly    tiny, dense, fills FAST
    3  garden      brown bin      fortnightly  bulky, strongly seasonal

Each accumulates on its own, so a food caddy can be overflowing while the black
bin is half-empty, and a fortnightly stream that gets skipped keeps filling
until it tips over. The visible ``tile.bin_fill`` the renderer/HUD already read
is kept in sync as the *fullest enabled bin* — the one that actually overflows —
so nothing downstream has to change.

Design goals:

  * Cheap. Four floats per building tile (~2000 buildings on a 60x60 map) and a
    tight per-tick loop over *building tiles only* (fewer iterations than the old
    whole-grid scan).
  * Physically meaningful frequency: each stream is calibrated to reach ~90 %
    over its own collection interval, so weekly vs fortnightly genuinely changes
    accumulation and overflow risk.
  * Composition matters for logistics: collecting a stream yields both a
    *mass* (for disposal economics / diversion, same scale as before) and a
    *volume* (bulk that eats truck capacity). Bulky garden waste fills a body
    faster per tonne than compacted residual — see :data:`STREAM_VOLUME`.
  * Redirection: a stream the borough doesn't collect doesn't vanish — its
    material lands in the black bin instead (recyclables and food scraps in the
    residual waste), so dropping a service makes residual fill faster. That is
    the physical cost of a thin collection policy.
"""

import random

# Canonical stream order. Everything in this module (tile.streams lists,
# composition tuples, multiplier tuples) uses exactly this ordering.
STREAM_IDS = ("residual", "recycling", "food", "garden")
STREAM_COUNT = len(STREAM_IDS)
STREAM_INDEX = {sid: i for i, sid in enumerate(STREAM_IDS)}
RESIDUAL, RECYCLING, FOOD, GARDEN = 0, 1, 2, 3

# ---------------------------------------------------------------------------
#  Per-stream physical characteristics
# ---------------------------------------------------------------------------
# Base fill speed, expressed as "% of this bin per in-game day" for a *typical*
# building (intensity 1.0, TYPICAL_COMPOSITION mix). Each stream is tuned to
# reach roughly 88-92 % over its own collection interval, so a punctually-
# serviced bin never overflows but a skipped or stretched-out collection does.
# Food is deliberately tight — the caddy is the pressure point.
# These are calibrated at intensity 1.0; a building's own fill_rate scales them,
# so the worst case (a tower, ~1.75x) still peaks below overflow when serviced on
# schedule. Emergent overflow then comes from *stress* — a missed round, a
# stretched frequency, a seasonal surge — not from the default service.
STREAM_BASE_DAILY = (
    5.0,    # residual   weekly; carries redirected food/garden by default
    3.2,    # recycling  fortnightly; a tower peaks ~78% just before the visit
    5.0,    # food       weekly caddy; the tight one when enabled
    2.0,    # garden     fortnightly; light normally, surges hard in autumn
)

# Fortnightly streams are offset so recycling and garden fall on OPPOSITE weeks
# (as real councils schedule them), spreading the fortnightly load evenly rather
# than stacking a heavy recycling+garden week against a light one. Weekly streams
# ignore this. Aligned to STREAM_IDS: residual, recycling, food, garden.
STREAM_PHASE = (0, 0, 0, 1)

# Reference composition mix used to normalise the per-building bias: a building
# whose composition matches this fills each stream at exactly STREAM_BASE_DAILY.
# A leafy detached house (garden share ~0.21) therefore fills its garden bin
# ~1.9x faster; a flat (~0.02) barely at all.
TYPICAL_COMPOSITION = (0.44, 0.30, 0.15, 0.11)

# Volume factor: how much *truck body space* one mass-unit of a stream eats once
# loaded. Residual compacts hard (1.0 reference); garden is springy, bulky and
# barely compactable; loose recycling takes room; food is dense and small.
# This is what makes "18,000 units of garden" behave nothing like "18,000 units
# of compacted residual" — the garden fills the hopper long before the mass adds
# up.
STREAM_VOLUME = (
    1.00,   # residual  (compacted)
    1.18,   # recycling (loose card/plastic)
    0.60,   # food      (dense)
    1.40,   # garden    (bulky, incompactable — the capacity pressure point)
)

# How much mass a full bin of each stream represents relative to residual. A
# food caddy is tiny (little mass even when overflowing); a garden bin holds a
# lot. Used to convert a collected fill-% into disposal mass so the economy
# stays on roughly the same scale as the old single-bin model.
STREAM_MASS = (
    1.00,   # residual
    0.85,   # recycling
    0.22,   # food (small caddy)
    0.95,   # garden
)

# Legacy reference fill_rate (the "semi" building). A building's own fill_rate
# scales all its streams: a tower fills every bin ~1.75x faster, a bungalow
# ~0.70x. This preserves the existing per-building intensity tuning.
REF_FILL = 0.097

# When a stream is not collected, residents put that material in the black bin
# instead — but a caddy-full of food is only a modest addition to a much bigger
# black bin, so the redirect is scaled down accordingly (the rest is hoarded,
# home-composted, or bagged loosely). This is the physical cost of a thin policy:
# dropping food/garden separation measurably speeds up how fast residual fills.
REDIRECT_TO_RESIDUAL = {
    RECYCLING: 0.32,   # recyclables bulk out the black bin
    FOOD:      0.20,   # food scraps, dense but small
    GARDEN:    0.16,   # some garden waste bagged into residual
}

# ---------------------------------------------------------------------------
#  Per-building-style waste composition
# ---------------------------------------------------------------------------
# Fraction of a building's total waste going to each stream when the full
# service is offered. Gardens track property type (bungalows/detached have big
# gardens; flats and towers have none). Commercial premises are card/paper-heavy
# with little food or garden. Tuples are (residual, recycling, food, garden) and
# each roughly sums to 1.0. These bias the *base* fill speeds per building so a
# leafy street of detached houses generates a very different stream mix from a
# tower-block estate or a parade of shops.
STYLE_COMPOSITION = {
    "bungalow":  (0.32, 0.27, 0.12, 0.29),   # retirees: big gardens, tidy sorters
    "terrace":   (0.44, 0.30, 0.18, 0.08),   # families, small yards
    "semi":      (0.40, 0.29, 0.16, 0.15),
    "detached":  (0.35, 0.29, 0.15, 0.21),   # large gardens
    "flats":     (0.53, 0.29, 0.16, 0.02),   # no gardens, transient sorting
    "tower":     (0.57, 0.27, 0.15, 0.01),   # no gardens, high churn
    "shop":      (0.38, 0.45, 0.15, 0.02),   # packaging + some food
    "office":    (0.44, 0.49, 0.05, 0.02),   # paper-heavy
    "warehouse": (0.56, 0.39, 0.03, 0.02),   # card + residual
    "highrise":  (0.47, 0.43, 0.08, 0.02),
}
_DEFAULT_COMPOSITION = (0.45, 0.30, 0.15, 0.10)


def composition_for(style):
    return STYLE_COMPOSITION.get(style, _DEFAULT_COMPOSITION)


# ---------------------------------------------------------------------------
#  Seasonal & weather per-stream multipliers
# ---------------------------------------------------------------------------
# (residual, recycling, food, garden). Garden waste swells through the growing
# season and peaks in the autumn leaf-fall, then goes dormant in winter; food
# rises with summer heat and the festive period; packaging (recycling/residual)
# climbs over winter. This replaces the old single seasonal fill multiplier with
# a stream-resolved one, so autumn hits garden collections specifically.
SEASON_STREAM_MULT = {
    "Spring": (1.00, 1.00, 1.00, 1.15),
    "Summer": (1.02, 1.04, 1.22, 1.45),
    "Autumn": (1.06, 1.06, 1.05, 1.85),
    "Winter": (1.12, 1.22, 1.06, 0.50),
}

WEATHER_STREAM_MULT = {
    "dry":      (1.00, 1.00, 1.00, 1.00),
    "overcast": (1.00, 1.00, 1.00, 1.00),
    "rain":     (1.16, 1.05, 1.00, 1.20),   # soggy waste, torn bags, wet garden
    "snow":     (1.08, 1.02, 1.00, 0.60),   # frozen ground, little garden
}
_NEUTRAL = (1.0, 1.0, 1.0, 1.0)


# ---------------------------------------------------------------------------
#  Tile stream bookkeeping
# ---------------------------------------------------------------------------

def new_streams(seed_fill=0.0):
    """Fresh per-stream fill list for a building, lightly pre-filled so a new
    borough doesn't start with every bin bone-empty."""
    if seed_fill <= 0:
        return [random.random() * 20.0, random.random() * 18.0,
                random.random() * 22.0, random.random() * 16.0]
    # Seed from an existing aggregate bin_fill (migrating an old save): spread
    # it across the streams with a little jitter.
    return [seed_fill * random.uniform(0.7, 1.0) for _ in range(STREAM_COUNT)]


def ensure_streams(tile):
    """Guarantee a building tile has a ``streams`` list. Idempotent and cheap;
    used to migrate tiles from old saves / editor JSON that predate streams."""
    s = getattr(tile, "streams", None)
    if s is None or len(s) != STREAM_COUNT:
        tile.streams = new_streams(getattr(tile, "bin_fill", 0.0))
    return tile.streams


def visible_fill(tile, enabled_mask):
    """The fullest *enabled* bin — the one the resident sees overflow. This is
    what feeds ``tile.bin_fill`` so the renderer/HUD keep working unchanged."""
    s = tile.streams
    m = 0.0
    for i in range(STREAM_COUNT):
        if enabled_mask[i] and s[i] > m:
            m = s[i]
    return m if m <= 100.0 else 100.0


# ---------------------------------------------------------------------------
#  Generation context & accumulation
# ---------------------------------------------------------------------------

class GenContext:
    """Cheap per-tick bundle of the multipliers that shape waste generation.

    Built once per generation step in the game loop and reused across every
    building, so the per-tile inner loop stays a handful of float mults. The
    per-stream ``rate`` folds base speed, season, weather and the typical-mix
    normalisation together so the hot loop only multiplies by the building's own
    composition and intensity."""

    __slots__ = ("enabled_mask", "rate", "redirect", "event_mult")

    def __init__(self, policy, season_name, weather, event_mult=1.0):
        enabled = {s.id: s.enabled for s in policy.streams}
        self.enabled_mask = tuple(
            enabled.get(sid, True) or sid == "residual" for sid in STREAM_IDS)
        season = SEASON_STREAM_MULT.get(season_name, _NEUTRAL)
        weath = WEATHER_STREAM_MULT.get(weather, _NEUTRAL)
        base = STREAM_BASE_DAILY
        typ = TYPICAL_COMPOSITION
        # rate[i] = base * season * weather / typical_composition, so multiplying
        # by the building's own comp[i] yields the calibrated per-day fill.
        self.rate = tuple(base[i] * season[i] * weath[i] / typ[i]
                          for i in range(STREAM_COUNT))
        self.redirect = (0.0,
                         REDIRECT_TO_RESIDUAL[RECYCLING],
                         REDIRECT_TO_RESIDUAL[FOOD],
                         REDIRECT_TO_RESIDUAL[GARDEN])
        self.event_mult = event_mult


def accumulate(city, dt_seconds, ctx, day_duration):
    """Grow every building's bins by ``dt_seconds`` of waste generation.

    One in-game day is ``day_duration`` seconds; the fill speeds in
    :data:`STREAM_BASE_DAILY` are per in-game day. Generation is linear in dt, so
    the game loop may batch several ticks into one call for efficiency without
    changing the result.

    Streams the borough doesn't collect are redirected into the black bin, so a
    thin policy physically loads residual faster. ``tile.bin_fill`` is refreshed
    to the fullest enabled bin. The hot loop is unrolled over the four streams
    to stay cheap on a 60x60 borough."""
    if day_duration <= 0:
        return
    m0, m1, m2, m3 = ctx.enabled_mask
    r0, r1, r2, r3 = ctx.rate
    _, d1, d2, d3 = ctx.redirect
    # Per-building scalar: dt in days * intensity(=fill_rate/REF_FILL) * event.
    k = (dt_seconds / day_duration) * ctx.event_mult / REF_FILL
    comp_table = STYLE_COMPOSITION
    tiles = city.tiles

    for area in city.areas:
        for (x, y) in area.building_tiles:
            tile = tiles[y][x]
            s = tile.streams
            if s is None:
                s = ensure_streams(tile)
            comp = comp_table.get(tile.building_style, _DEFAULT_COMPOSITION)
            step = tile.fill_rate * k
            g0 = r0 * comp[0] * step
            g1 = r1 * comp[1] * step
            g2 = r2 * comp[2] * step
            g3 = r3 * comp[3] * step

            redirect = 0.0
            if m1:
                v = s[1] + g1
                s[1] = v if v < 100.0 else 100.0
                b1 = s[1]
            else:
                redirect += g1 * d1
                b1 = -1.0
            if m2:
                v = s[2] + g2
                s[2] = v if v < 100.0 else 100.0
                b2 = s[2]
            else:
                redirect += g2 * d2
                b2 = -1.0
            if m3:
                v = s[3] + g3
                s[3] = v if v < 100.0 else 100.0
                b3 = s[3]
            else:
                redirect += g3 * d3
                b3 = -1.0

            v0 = s[0] + g0 + redirect
            if v0 > 100.0:
                v0 = 100.0
            s[0] = v0

            # Fullest enabled bin -> the visible bin_fill (inlined visible_fill).
            mx = v0
            if b1 > mx:
                mx = b1
            if b2 > mx:
                mx = b2
            if b3 > mx:
                mx = b3
            tile.bin_fill = mx


# ---------------------------------------------------------------------------
#  Collection
# ---------------------------------------------------------------------------
# A "collection profile" tells the fleet which streams to lift at a stop and how
# full they are. The fleet consumes truck *volume* and reports disposal *mass*.

def due_streams(policy, area, week_index):
    """Which enabled streams should be lifted when this round is serviced this
    week. Residual/food are weekly; recycling/garden default to fortnightly and
    alternate, staggered by area id so not every round's recycling lands the
    same week. Returns a mask tuple aligned to STREAM_IDS.

    The stream's own frequency (from waste policy) wins: a player who sets
    recycling to weekly gets it every visit."""
    out = [False] * STREAM_COUNT
    for i, sid in enumerate(STREAM_IDS):
        s = policy.get(sid)
        if not s or not s.enabled:
            continue
        if s.frequency <= 1:
            out[i] = True
        else:
            # Fortnightly: due on alternate service weeks, staggered by area id
            # and by the stream's phase (so recycling and garden fall on opposite
            # weeks and never stack into one heavy round).
            out[i] = ((week_index + STREAM_PHASE[i]) % s.frequency) \
                == (area.id % s.frequency)
    return tuple(out)


def collect_stop(tile, due_mask, sf):
    """Empty the due streams at a property. Returns ``(volume, masses)``:

      volume   truck body space consumed (respects STREAM_VOLUME bulk)
      masses   list[4] of disposal mass lifted per stream (for economics)

    The emptied streams are reset to a small carry-over (bins are never quite
    spotless). ``tile.bin_fill`` is NOT refreshed here — the caller does it once
    after all the stop's streams are handled."""
    s = tile.streams
    volume = 0.0
    masses = [0.0, 0.0, 0.0, 0.0]
    for i in range(STREAM_COUNT):
        if not due_mask[i]:
            continue
        fill = s[i]
        if fill <= 0.5:
            continue
        m = fill * STREAM_MASS[i] * sf
        masses[i] = m
        volume += m * STREAM_VOLUME[i]
        s[i] = random.uniform(0.0, 2.5)   # small carry-over
    return volume, masses


def size_factor(tile):
    """Bin/premise size multiplier from building intensity — a tower presents a
    lot more waste per stop than a bungalow, so it eats truck capacity faster."""
    return tile.fill_rate / REF_FILL


def enabled_mask(policy):
    """Boolean mask tuple of currently-collected streams (residual forced on)."""
    en = {s.id: s.enabled for s in policy.streams}
    return tuple(en.get(sid, True) or sid == "residual" for sid in STREAM_IDS)


def redistribute_on_policy_change(city, policy):
    """When the player toggles a stream off, its accumulated material is folded
    into the black bin (residents switch to bagging it); toggling one back on
    starts it near-empty. Keeps ``bin_fill`` honest immediately after a policy
    change rather than waiting for it to drift. Cheap: one pass over buildings."""
    mask = enabled_mask(policy)
    for area in city.areas:
        for (x, y) in area.building_tiles:
            tile = city.tiles[y][x]
            s = getattr(tile, "streams", None)
            if s is None:
                s = ensure_streams(tile)
            for i in range(STREAM_COUNT):
                if not mask[i] and s[i] > 3.0:
                    moved = s[i] * REDIRECT_TO_RESIDUAL.get(i, 0.0)
                    s[RESIDUAL] = min(100.0, s[RESIDUAL] + moved * 0.5)
                    s[i] = 2.0
            tile.bin_fill = visible_fill(tile, mask)
