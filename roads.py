class RoadGenerator:
    """A regular street grid. Spacing is chosen so that, combined with the
    loaders' 2-tile kerbside reach in fleet.py, *every* property is collectable
    -- no marooned blocks that can never have their bins emptied."""

    SPACING = 5

    @staticmethod
    def generate_grid(width, height):
        roads = set()
        s = RoadGenerator.SPACING
        for y in range(height):
            for x in range(width):
                if x % s == 0 or y % s == 0 or x == width - 1 or y == height - 1:
                    roads.add(f"{x},{y}")
        return roads
