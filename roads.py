import random


class RoadGenerator:
    """Street layout generator.

    The base is still a grid -- spacing is capped so that, combined with the
    loaders' 2-tile kerbside reach in fleet.py, *every* property is collectable
    (no marooned blocks that can never have their bins emptied) -- but three
    kinds of variation stop maps looking stamped out of the same press:

      * grid lines are irregularly spaced (gaps of MIN_SPACING..SPACING tiles
        rather than a fixed 5), so block sizes vary street to street;
      * short cul-de-sac stubs poke into some blocks;
      * one stepped diagonal "high street" cuts across the borough.

    Every variation is *additive* or keeps the maximum block gap at SPACING,
    so the collectability guarantee is preserved: no interior tile is ever
    more than 2 tiles (Manhattan) from a road. The depot column/row at 5 is
    always forced in so the depot tile at (5, 5) stays on the network.
    """

    SPACING = 5          # max gap between parallel grid lines (do not raise:
                         # reach-2 loaders can only cover interiors <= 4 wide)
    MIN_SPACING = 4      # min gap (below this the map is all tarmac)
    DEPOT_LINE = 5       # a road line is always forced here on both axes

    @staticmethod
    def _line_positions(limit):
        """Irregularly spaced grid-line coordinates along one axis: always
        includes 0, DEPOT_LINE and the far edge; consecutive gaps never
        exceed SPACING."""
        s_min, s_max = RoadGenerator.MIN_SPACING, RoadGenerator.SPACING
        lines = {0, limit - 1}
        if 0 < RoadGenerator.DEPOT_LINE < limit - 1:
            lines.add(RoadGenerator.DEPOT_LINE)
        # First step lands exactly on the depot line so gaps stay regular
        # around it; after that, wander.
        x = RoadGenerator.DEPOT_LINE if RoadGenerator.DEPOT_LINE < limit - 1 else 0
        while x < limit - 1:
            x += random.randint(s_min, s_max)
            if x < limit - 1:
                lines.add(x)
        return lines

    @staticmethod
    def generate_grid(width, height):
        vxs = RoadGenerator._line_positions(width)     # vertical line x coords
        hys = RoadGenerator._line_positions(height)    # horizontal line y coords

        roads = set()
        for y in range(height):
            for x in range(width):
                if x in vxs or y in hys:
                    roads.add(f"{x},{y}")

        # --- Cul-de-sac stubs ------------------------------------------------
        # Short dead-ends poking 2 tiles into a block from a grid line. Purely
        # additive, so collectability and connectivity are untouched; BFS
        # routing handles dead ends fine (trucks just reverse out).
        n_stubs = max(2, (width * height) // 450)
        h_lines = sorted(hys - {0, height - 1})
        v_lines = sorted(vxs - {0, width - 1})
        for _ in range(n_stubs):
            if random.random() < 0.5 and h_lines:
                y0 = random.choice(h_lines)
                x0 = random.randint(1, width - 2)
                d = random.choice((-1, 1))
                for i in (1, 2):
                    yy = y0 + d * i
                    if 0 < yy < height - 1:
                        roads.add(f"{x0},{yy}")
            elif v_lines:
                x0 = random.choice(v_lines)
                y0 = random.randint(1, height - 2)
                d = random.choice((-1, 1))
                for i in (1, 2):
                    xx = x0 + d * i
                    if 0 < xx < width - 1:
                        roads.add(f"{xx},{y0}")

        # --- Stepped diagonal high street ------------------------------------
        # One staircase road drifting down-right across the borough. Each step
        # is orthogonal, so the street is a connected 4-neighbour path, and it
        # crosses grid lines constantly, so it's always joined to the network.
        # Additive: it only ever converts tiles *to* road.
        x = 0
        y = random.randint(height // 5, (2 * height) // 5)
        right_bias = random.uniform(0.45, 0.65)
        while x < width - 1 and y < height - 1:
            roads.add(f"{x},{y}")
            if random.random() < right_bias:
                x += 1
            else:
                y += 1
        roads.add(f"{x},{y}")

        return roads
