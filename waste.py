"""
waste.py
========

Borough-wide *waste stream* policy -- the "what waste is collected" lever.

A real council runs several parallel collections (residual/black bin, dry
recycling, food caddy, garden brown bin). Rather than splitting every tile into
four separate bins (which would mean rewriting the whole fleet/collection loop),
the streams are modelled as a single borough policy that modulates three things:

    * how fast the kerbside bin fills      (more streams = more to present/move)
    * the economics of disposal            (landfill gate fees vs recycling
                                            credits vs chargeable garden waste)
    * baseline public satisfaction         (residents like a full service)

That keeps the existing per-tile `bin_fill` and the fleet untouched while giving
the player a meaningful set of policy choices.
"""


def _num(value, default=None):
    """Parse a spreadsheet cell to float, tolerating GBP/commas/blanks."""
    if value is None:
        return default
    s = str(value).replace(",", "").replace("GBP", "").strip()
    if s == "":
        return default
    try:
        return float(s)
    except (ValueError, TypeError):
        return default


class WasteStream:
    def __init__(self, sid, name, color, *, fill_share, gate_fee, credit,
                 satisfaction, frequency=1, can_disable=True, enabled=True,
                 blurb=""):
        self.id = sid
        self.name = name
        self.color = color
        # Relative contribution to how fast the kerbside bin fills when on.
        self.fill_share = fill_share
        # GBP per "unit" of this stream sent for disposal (a cost).
        self.gate_fee = gate_fee
        # GBP per unit recovered/charged (income: recycling credit, garden sub).
        self.credit = credit
        # Contribution to the satisfaction ceiling when offered.
        self.satisfaction = satisfaction
        # 1 = weekly, 2 = fortnightly.
        self.frequency = frequency
        self.can_disable = can_disable
        self.enabled = enabled if can_disable else True
        self.blurb = blurb

    @property
    def freq_label(self):
        return "Weekly" if self.frequency <= 1 else "Fortnightly"


def _default_streams():
    # Disposal economics reflect the real UK picture: residual waste to
    # landfill/energy-from-waste is dominated by landfill tax (£126.15/tonne
    # standard rate, 2025/26), so its gate fee dwarfs everything else.
    # Recycling and garden earn a modest material credit / subscription income.
    return [
        WasteStream(
            "residual", "General (black bin)", "#4b4f57",
            fill_share=0.60, gate_fee=0.11, credit=0.0, satisfaction=0,
            frequency=1, can_disable=False, enabled=True,
            blurb="Residual waste to landfill / energy-from-waste. Always "
                  "collected; dominated by landfill tax."),
        WasteStream(
            "recycling", "Dry recycling", "#3d6f8e",
            fill_share=0.35, gate_fee=0.012, credit=0.005, satisfaction=8,
            frequency=2, enabled=True,
            blurb="Mixed paper, card, cans, plastics. Roughly break-even on "
                  "material value -- recycled mainly to dodge landfill tax."),
        WasteStream(
            "food", "Food waste caddy", "#6f8e4a",
            fill_share=0.16, gate_fee=0.020, credit=0.018, satisfaction=6,
            frequency=1, enabled=False,
            blurb="Weekly food caddies. Fills fast, modest AD credit, big "
                  "satisfaction lift."),
        WasteStream(
            "garden", "Garden waste", "#8a6f3a",
            fill_share=0.20, gate_fee=0.010, credit=0.045, satisfaction=4,
            frequency=2, enabled=False,
            blurb="Chargeable brown-bin subscription. Net income, but more "
                  "tonnage to shift."),
    ]


class WastePolicy:
    def __init__(self):
        self.streams = _default_streams()

    # ---------------------------------------------------------------- access
    def get(self, sid):
        for s in self.streams:
            if s.id == sid:
                return s
        return None

    def enabled_streams(self):
        return [s for s in self.streams if s.enabled]

    def toggle(self, sid):
        s = self.get(sid)
        if s and s.can_disable:
            s.enabled = not s.enabled
        return s

    def cycle_frequency(self, sid):
        s = self.get(sid)
        if s:
            s.frequency = 1 if s.frequency >= 2 else 2
        return s

    # ------------------------------------------------------------- modelling
    def fill_multiplier(self):
        """How fast the single kerbside bin fills given the streams on offer.
        More separate collections = more material presented at the kerb."""
        total = sum(s.fill_share for s in self.enabled_streams())
        # Normalise so 'residual only' ~= 1.0 (the legacy baseline).
        return max(0.4, total / 0.60)

    def satisfaction_ceiling(self):
        """Baseline satisfaction residents settle toward for the service on
        offer (40 floor up to ~100 with the full set)."""
        return min(100.0, 70.0 + sum(s.satisfaction for s in self.enabled_streams()))

    def contamination_rate(self):
        """Fraction of the dry-recycling stream that arrives too contaminated to
        process and is rejected at the MRF -- it's redirected to landfill,
        earns no credit, and counts against the diversion target.

        It's *derived* from policy rather than a raw knob: dry recycling fouls
        badly when residents have nowhere else to put food scraps or garden
        waste, so offering those caddies is what keeps loads clean. This gives
        the food/garden toggles a hard economic payoff beyond satisfaction."""
        rec = self.get("recycling")
        if not rec or not rec.enabled:
            return 0.0
        rate = 0.06                                   # irreducible baseline
        food = self.get("food")
        if not (food and food.enabled):
            rate += 0.10                              # food scraps in the dry bin
        garden = self.get("garden")
        if not (garden and garden.enabled):
            rate += 0.03                              # grass/soil fouling paper
        return max(0.0, min(0.30, rate))

    def contamination_label(self):
        r = self.contamination_rate()
        if r <= 0:
            return "n/a"
        band = "low" if r < 0.10 else "high" if r >= 0.16 else "moderate"
        return f"{r * 100:.0f}% ({band})"

    def split_volume(self, volume):
        """Apportion a chunk of collected volume across the enabled streams by
        fill share, returning {stream_id: units}."""
        streams = self.enabled_streams()
        total = sum(s.fill_share for s in streams) or 1.0
        return {s.id: volume * s.fill_share / total for s in streams}

    def disposal_economics(self, volume, landfill_tax_mult=1.0):
        """Return ledger lines for disposing `volume` units of mixed kerbside
        collection under the current policy.

        `landfill_tax_mult` escalates the residual gate fee to model the annual
        rise in UK landfill tax (the residual stream's gate fee *is* landfill
        tax); recycling/garden gate fees are unaffected.

        Returns (gate_fees, recycling_credit, garden_charges) in GBP.
        gate_fees is a positive cost; the other two are positive income."""
        gate = 0.0
        recycle = 0.0
        garden = 0.0
        cont = self.contamination_rate()
        residual_stream = self.get("residual")
        residual_gate = (residual_stream.gate_fee * landfill_tax_mult
                         if residual_stream else 0.0)
        for sid, units in self.split_volume(volume).items():
            s = self.get(sid)
            unit_gate = s.gate_fee
            if sid == "residual":
                unit_gate *= landfill_tax_mult
            if sid == "recycling" and cont > 0.0:
                # Rejected fraction is landfilled at the residual gate fee and
                # earns nothing; only the clean remainder is credited.
                rejected = units * cont
                clean = units - rejected
                gate += clean * unit_gate + rejected * residual_gate
                recycle += clean * s.credit
            elif sid == "garden":
                gate += units * unit_gate
                garden += units * s.credit
            else:
                gate += units * unit_gate
                recycle += units * s.credit
        return gate, recycle, garden

    def diversion_split(self, volume):
        """Apportion `volume` into (residual_units, diverted_units), where
        diverted = recycling + food + garden. Drives the statutory recycling
        diversion target / fine system in the economy."""
        residual = 0.0
        diverted = 0.0
        cont = self.contamination_rate()
        for sid, units in self.split_volume(volume).items():
            if sid == "residual":
                residual += units
            elif sid == "recycling" and cont > 0.0:
                # Rejected loads are landfilled, so they don't count as diverted.
                residual += units * cont
                diverted += units * (1.0 - cont)
            else:
                diverted += units
        return residual, diverted

    # ----------------------------------------------------------------- XML io
    def to_rows(self):
        rows = []
        for s in self.streams:
            rows.append({
                "Stream": s.name,
                "Id": s.id,
                "Collected": "Yes" if s.enabled else "No",
                "Frequency": s.freq_label,
                "Gate fee (GBP/unit)": round(s.gate_fee, 4),
                "Credit (GBP/unit)": round(s.credit, 4),
                "Satisfaction": s.satisfaction,
                "Note": s.blurb,
            })
        return rows

    def apply_rows(self, rows):
        """Apply imported stream settings. Returns a count of streams changed."""
        changed = 0
        for row in rows:
            sid = (row.get("Id") or "").strip()
            s = self.get(sid)
            if not s:
                continue
            collected = (row.get("Collected") or "").strip().lower()
            if collected in ("yes", "y", "true", "1"):
                want = True
            elif collected in ("no", "n", "false", "0"):
                want = False
            else:
                want = s.enabled
            if s.can_disable and want != s.enabled:
                s.enabled = want
                changed += 1
            freq = (row.get("Frequency") or "").strip().lower()
            if freq.startswith("fort"):
                if s.frequency != 2:
                    s.frequency = 2
                    changed += 1
            elif freq.startswith("week"):
                if s.frequency != 1:
                    s.frequency = 1
                    changed += 1

            # Economic levers -- editable so players can tune disposal costs and
            # recycling income from the spreadsheet. Clamped to sane ranges.
            gate = _num(row.get("Gate fee (GBP/unit)"))
            if gate is not None:
                gate = max(0.0, min(1.0, round(gate, 4)))
                if abs(gate - s.gate_fee) > 1e-9:
                    s.gate_fee = gate
                    changed += 1
            credit = _num(row.get("Credit (GBP/unit)"))
            if credit is not None:
                credit = max(0.0, min(1.0, round(credit, 4)))
                if abs(credit - s.credit) > 1e-9:
                    s.credit = credit
                    changed += 1
            sat = _num(row.get("Satisfaction"))
            if sat is not None:
                sat = int(max(0, min(40, round(sat))))
                if sat != s.satisfaction:
                    s.satisfaction = sat
                    changed += 1
        return changed
