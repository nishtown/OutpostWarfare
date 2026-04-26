"""
world_gen.py
------------
Seeded tile-based world generation and terrain rendering.

This module generates a deterministic terrain grid from a seed and keeps the
metadata needed for future autotiling. Even though the current renderer only
uses flat colours, each tile already knows enough about its neighbours to let
you pick edge, inner-corner, and outer-corner sprites later.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import math

import pygame

from settings import DARK_BROWN, TILE_SIZE, WORLD_HEIGHT, WORLD_WIDTH


# Direction bitmasks used by transition profiles. These are intentionally
# explicit so future sprite-selection code can use readable names rather than
# magic numbers.
NORTH = 1
EAST = 2
SOUTH = 4
WEST = 8
NORTH_EAST = 16
SOUTH_EAST = 32
SOUTH_WEST = 64
NORTH_WEST = 128

CARDINAL_DIRECTIONS = {
    "north": (0, -1, NORTH),
    "east": (1, 0, EAST),
    "south": (0, 1, SOUTH),
    "west": (-1, 0, WEST),
}

DIAGONAL_DIRECTIONS = {
    "north_east": (1, -1, NORTH_EAST),
    "south_east": (1, 1, SOUTH_EAST),
    "south_west": (-1, 1, SOUTH_WEST),
    "north_west": (-1, -1, NORTH_WEST),
}

CORNER_RULES = {
    "north_east": ("north", "east", NORTH_EAST),
    "south_east": ("south", "east", SOUTH_EAST),
    "south_west": ("south", "west", SOUTH_WEST),
    "north_west": ("north", "west", NORTH_WEST),
}

CARDINAL_BITS = NORTH | EAST | SOUTH | WEST


@dataclass(frozen=True)
class TerrainType:
    """Static definition for one terrain type."""

    key: str
    label: str
    color: tuple[int, int, int]
    traversable: bool
    move_cost: float = 1.0


@dataclass(frozen=True)
class TransitionProfile:
    """Neighbour information used for future sprite selection.

    A profile answers questions like:
    * Which sides touch water?
    * Is this sand tile an outer shoreline corner?
    * Is this grass tile fully surrounded by the same terrain?
    """

    target_key: str
    cardinal_mask: int
    diagonal_mask: int
    all_mask: int
    edge_mask: int
    inner_corners: tuple[str, ...]
    outer_corners: tuple[str, ...]


@dataclass
class TerrainTile:
    """One generated world tile."""

    grid_x: int
    grid_y: int
    terrain_key: str
    traversable: bool
    terrain_profile: TransitionProfile | None = None
    transition_cache: dict[str, TransitionProfile] = field(default_factory=dict)


class WorldGenerator:
    """Generate and draw a deterministic tile world from a seed."""

    def __init__(
        self,
        world_width: int,
        world_height: int,
        tile_size: int = TILE_SIZE,
        seed: int = 0,
    ) -> None:
        self.world_width = int(world_width)
        self.world_height = int(world_height)
        self.tile_size = int(tile_size)
        self.seed = int(seed)

        self.columns = math.ceil(self.world_width / self.tile_size)
        self.rows = math.ceil(self.world_height / self.tile_size)

        self.terrain_types = {
            "deep_water": TerrainType("deep_water", "Deep Water", (23, 73, 143), False),
            "water": TerrainType("water", "Water", (42, 118, 198), False),
            "sand": TerrainType("sand", "Sand", (212, 194, 129), True, 1.15),
            "grass": TerrainType("grass", "Grass", (56, 136, 64), True, 1.0),
            "forest": TerrainType("forest", "Forest", (31, 92, 43), True, 1.25),
            "rock": TerrainType("rock", "Rock", (109, 109, 109), False),
        }

        self.tiles: list[list[TerrainTile]] = []
        self._generate_world()

    # ── Public helpers ────────────────────────────────────────────────────

    def get_tile(self, grid_x: int, grid_y: int) -> TerrainTile | None:
        """Return the tile at grid coordinates, or None when out of bounds."""
        if 0 <= grid_x < self.columns and 0 <= grid_y < self.rows:
            return self.tiles[grid_y][grid_x]
        return None

    def get_tile_at_world(self, world_x: float, world_y: float) -> TerrainTile | None:
        """Return the tile containing a world-space position."""
        return self.get_tile(int(world_x // self.tile_size), int(world_y // self.tile_size))

    def is_traversable_at_world(self, world_x: float, world_y: float) -> bool:
        """Return whether the tile under a world-space position can be walked on."""
        tile = self.get_tile_at_world(world_x, world_y)
        return tile is not None and tile.traversable

    def get_transition_profile(self, grid_x: int, grid_y: int, target_terrain) -> TransitionProfile:
        """Return neighbour info relative to *target_terrain*.

        Parameters
        ----------
        grid_x, grid_y : int
            Tile coordinates.
        target_terrain : str | set[str] | tuple[str, ...]
            The terrain type(s) to test neighbours against. This is the key to
            future autotiling. Examples:

            * ``get_transition_profile(x, y, "water")``
            * ``get_transition_profile(x, y, {"water", "deep_water"})``
        """
        tile = self.get_tile(grid_x, grid_y)
        if tile is None:
            raise IndexError("Tile coordinates out of range")

        if isinstance(target_terrain, str):
            target_keys = (target_terrain,)
            cache_key = target_terrain
        else:
            target_keys = tuple(sorted(target_terrain))
            cache_key = "|".join(target_keys)

        if cache_key in tile.transition_cache:
            return tile.transition_cache[cache_key]

        profile = self._build_transition_profile(grid_x, grid_y, target_keys, cache_key)
        tile.transition_cache[cache_key] = profile
        return profile

    def draw(self, surface: pygame.Surface, camera) -> None:
        """Render the visible portion of the world to *surface* using *camera*."""
        surface.fill((18, 64, 30))

        visible = camera.view_rect
        start_col = max(0, visible.left // self.tile_size)
        end_col = min(self.columns, (visible.right // self.tile_size) + 2)
        start_row = max(0, visible.top // self.tile_size)
        end_row = min(self.rows, (visible.bottom // self.tile_size) + 2)

        for grid_y in range(start_row, end_row):
            for grid_x in range(start_col, end_col):
                tile = self.tiles[grid_y][grid_x]
                world_rect = pygame.Rect(
                    grid_x * self.tile_size,
                    grid_y * self.tile_size,
                    self.tile_size,
                    self.tile_size,
                )
                draw_rect = camera.world_rect_to_screen(world_rect)
                if draw_rect.width <= 0 or draw_rect.height <= 0:
                    continue

                terrain = self.terrain_types[tile.terrain_key]
                pygame.draw.rect(surface, terrain.color, draw_rect)

                # Only draw edge detail when the tile still has enough pixels
                # on-screen to be readable.
                if draw_rect.width >= 6 and draw_rect.height >= 6:
                    self._draw_transition_overlays(surface, draw_rect, tile)

        border_rect = camera.world_rect_to_screen(
            pygame.Rect(0, 0, self.world_width, self.world_height)
        )
        pygame.draw.rect(
            surface,
            (95, 65, 28),
            border_rect,
            max(1, int(min(camera.scale_x, camera.scale_y) * 2)),
        )

    # ── Generation ────────────────────────────────────────────────────────

    def _generate_world(self) -> None:
        """Generate terrain keys and post-process them into full tiles."""
        terrain_grid: list[list[str]] = []
        for grid_y in range(self.rows):
            row: list[str] = []
            for grid_x in range(self.columns):
                elevation = self._sample_elevation(grid_x, grid_y)
                moisture = self._sample_moisture(grid_x, grid_y)
                row.append(self._pick_terrain(elevation, moisture))
            terrain_grid.append(row)

        terrain_grid = self._cleanup_singletons(terrain_grid)

        self.tiles = []
        for grid_y, row in enumerate(terrain_grid):
            tile_row: list[TerrainTile] = []
            for grid_x, terrain_key in enumerate(row):
                terrain = self.terrain_types[terrain_key]
                tile_row.append(
                    TerrainTile(
                        grid_x=grid_x,
                        grid_y=grid_y,
                        terrain_key=terrain_key,
                        traversable=terrain.traversable,
                    )
                )
            self.tiles.append(tile_row)

        for grid_y in range(self.rows):
            for grid_x in range(self.columns):
                tile = self.tiles[grid_y][grid_x]
                tile.terrain_profile = self.get_transition_profile(grid_x, grid_y, tile.terrain_key)

    def _sample_elevation(self, grid_x: int, grid_y: int) -> float:
        """Low-frequency landmass value in the range 0..1."""
        value = (
            self._fbm(grid_x, grid_y, base_scale=20.0, octaves=3, channel=0) * 0.62
            + self._fbm(grid_x, grid_y, base_scale=9.0, octaves=2, channel=11) * 0.23
            + self._fbm(grid_x, grid_y, base_scale=4.5, octaves=2, channel=19) * 0.15
        )

        # Bias the outer edge of the world slightly downward so coastlines are
        # common around the border and the world reads more like a landmass.
        cx = (grid_x / max(1, self.columns - 1)) * 2.0 - 1.0
        cy = (grid_y / max(1, self.rows - 1)) * 2.0 - 1.0
        radial_falloff = max(0.0, math.sqrt(cx * cx + cy * cy) - 0.55)
        value -= radial_falloff * 0.30
        return max(0.0, min(1.0, value))

    def _sample_moisture(self, grid_x: int, grid_y: int) -> float:
        """Second noise field used to split land into sand/grass/forest/rock."""
        value = (
            self._fbm(grid_x, grid_y, base_scale=16.0, octaves=3, channel=101) * 0.55
            + self._fbm(grid_x, grid_y, base_scale=7.0, octaves=2, channel=113) * 0.30
            + self._fbm(grid_x, grid_y, base_scale=3.5, octaves=1, channel=127) * 0.15
        )
        return max(0.0, min(1.0, value))

    def _pick_terrain(self, elevation: float, moisture: float) -> str:
        """Map noise values to a terrain type."""
        if elevation < 0.24:
            return "deep_water"
        if elevation < 0.31:
            return "water"
        if elevation < 0.37:
            return "sand"
        if elevation > 0.82 and moisture < 0.48:
            return "rock"
        if moisture > 0.68:
            return "forest"
        return "grass"

    def _cleanup_singletons(self, terrain_grid: list[list[str]]) -> list[list[str]]:
        """Remove tiny single-tile specks so terrain shapes read more cleanly."""
        smoothed = [row[:] for row in terrain_grid]
        for grid_y in range(self.rows):
            for grid_x in range(self.columns):
                current = terrain_grid[grid_y][grid_x]
                counts: dict[str, int] = {}
                for dy in (-1, 0, 1):
                    for dx in (-1, 0, 1):
                        if dx == 0 and dy == 0:
                            continue
                        nx = grid_x + dx
                        ny = grid_y + dy
                        if 0 <= nx < self.columns and 0 <= ny < self.rows:
                            key = terrain_grid[ny][nx]
                            counts[key] = counts.get(key, 0) + 1

                dominant_key, dominant_count = current, 0
                for key, count in counts.items():
                    if count > dominant_count:
                        dominant_key, dominant_count = key, count

                if dominant_key != current and dominant_count >= 5:
                    smoothed[grid_y][grid_x] = dominant_key
        return smoothed

    # ── Noise ─────────────────────────────────────────────────────────────

    def _fbm(self, x: float, y: float, base_scale: float, octaves: int, channel: int) -> float:
        """Layered value noise using deterministic hashes."""
        total = 0.0
        amplitude = 1.0
        amplitude_sum = 0.0
        scale = base_scale

        for octave in range(octaves):
            total += self._smooth_value_noise(x, y, scale, channel + octave * 37) * amplitude
            amplitude_sum += amplitude
            amplitude *= 0.5
            scale *= 0.5

        return total / max(0.0001, amplitude_sum)

    def _smooth_value_noise(self, x: float, y: float, scale: float, channel: int) -> float:
        """Sample bilinearly-smoothed value noise at tile coordinates."""
        sample_x = x / scale
        sample_y = y / scale

        x0 = math.floor(sample_x)
        y0 = math.floor(sample_y)
        x1 = x0 + 1
        y1 = y0 + 1

        fx = self._fade(sample_x - x0)
        fy = self._fade(sample_y - y0)

        v00 = self._hash01(x0, y0, channel)
        v10 = self._hash01(x1, y0, channel)
        v01 = self._hash01(x0, y1, channel)
        v11 = self._hash01(x1, y1, channel)

        top = self._lerp(v00, v10, fx)
        bottom = self._lerp(v01, v11, fx)
        return self._lerp(top, bottom, fy)

    def _hash01(self, x: int, y: int, channel: int) -> float:
        """Return a deterministic pseudo-random float in the range 0..1."""
        value = (
            x * 374761393
            + y * 668265263
            + self.seed * 1442695040888963407
            + channel * 2654435761
        ) & 0xFFFFFFFFFFFFFFFF
        value ^= value >> 33
        value = (value * 0xFF51AFD7ED558CCD) & 0xFFFFFFFFFFFFFFFF
        value ^= value >> 33
        value = (value * 0xC4CEB9FE1A85EC53) & 0xFFFFFFFFFFFFFFFF
        value ^= value >> 33
        return (value & 0xFFFFFFFF) / 0xFFFFFFFF

    @staticmethod
    def _fade(value: float) -> float:
        """Smoothstep easing curve used for noise interpolation."""
        return value * value * (3.0 - 2.0 * value)

    @staticmethod
    def _lerp(start: float, end: float, amount: float) -> float:
        """Linear interpolation helper."""
        return start + (end - start) * amount

    # ── Transition profile construction ──────────────────────────────────

    def _build_transition_profile(
        self,
        grid_x: int,
        grid_y: int,
        target_keys: tuple[str, ...],
        cache_key: str,
    ) -> TransitionProfile:
        """Build neighbour and corner data for a tile relative to target_keys."""
        cardinal_mask = 0
        diagonal_mask = 0
        matches: dict[str, bool] = {}

        for name, (dx, dy, bit) in CARDINAL_DIRECTIONS.items():
            neighbour = self.get_tile(grid_x + dx, grid_y + dy)
            is_match = neighbour is not None and neighbour.terrain_key in target_keys
            matches[name] = is_match
            if is_match:
                cardinal_mask |= bit

        for name, (dx, dy, bit) in DIAGONAL_DIRECTIONS.items():
            neighbour = self.get_tile(grid_x + dx, grid_y + dy)
            is_match = neighbour is not None and neighbour.terrain_key in target_keys
            matches[name] = is_match
            if is_match:
                diagonal_mask |= bit

        inner_corners: list[str] = []
        outer_corners: list[str] = []
        for corner_name, (side_a, side_b, diagonal_bit) in CORNER_RULES.items():
            side_a_match = matches[side_a]
            side_b_match = matches[side_b]
            diagonal_match = bool(diagonal_mask & diagonal_bit)

            # Inner corner: both cardinal neighbours match, but the diagonal
            # does not. This is the classic "concave" autotile case.
            if side_a_match and side_b_match and not diagonal_match:
                inner_corners.append(corner_name)

            # Outer corner: neither adjacent side matches, so the current tile
            # visually protrudes into the target terrain.
            if not side_a_match and not side_b_match:
                outer_corners.append(corner_name)

        return TransitionProfile(
            target_key=cache_key,
            cardinal_mask=cardinal_mask,
            diagonal_mask=diagonal_mask,
            all_mask=cardinal_mask | diagonal_mask,
            edge_mask=(~cardinal_mask) & CARDINAL_BITS,
            inner_corners=tuple(inner_corners),
            outer_corners=tuple(outer_corners),
        )

    # ── Current colour-based transition rendering ────────────────────────

    def _draw_transition_overlays(self, surface: pygame.Surface, draw_rect: pygame.Rect, tile: TerrainTile) -> None:
        """Draw simple edge/corner hints using colours only.

        This is the temporary bridge between abstract tile metadata and future
        sprite-based autotiling. The data already knows what kind of edge a tile
        has; right now we just visualize that with bands and corner fills.
        """
        shore_profile = self.get_transition_profile(
            tile.grid_x,
            tile.grid_y,
            {"water", "deep_water"},
        )

        if tile.terrain_key in {"sand", "grass", "forest", "rock"} and shore_profile.cardinal_mask:
            shore_color = (235, 223, 176) if tile.terrain_key == "sand" else (194, 183, 142)
            self._draw_edge_bands(surface, draw_rect, shore_profile, shore_color)
            self._draw_corner_marks(surface, draw_rect, shore_profile, shore_color)

        # Slight dark outline where land becomes rock so cliffs remain legible.
        if tile.terrain_key != "rock":
            rock_profile = self.get_transition_profile(tile.grid_x, tile.grid_y, "rock")
            if rock_profile.cardinal_mask:
                self._draw_edge_bands(surface, draw_rect, rock_profile, (76, 69, 60), thickness=1)

        pygame.draw.rect(surface, DARK_BROWN, draw_rect, 1)

    def _draw_edge_bands(
        self,
        surface: pygame.Surface,
        draw_rect: pygame.Rect,
        profile: TransitionProfile,
        color: tuple[int, int, int],
        thickness: int | None = None,
    ) -> None:
        """Draw thin bands on the tile sides that touch the target terrain."""
        band = thickness if thickness is not None else max(2, min(draw_rect.width, draw_rect.height) // 6)

        if profile.cardinal_mask & NORTH:
            pygame.draw.rect(surface, color, (draw_rect.x, draw_rect.y, draw_rect.width, band))
        if profile.cardinal_mask & EAST:
            pygame.draw.rect(surface, color, (draw_rect.right - band, draw_rect.y, band, draw_rect.height))
        if profile.cardinal_mask & SOUTH:
            pygame.draw.rect(surface, color, (draw_rect.x, draw_rect.bottom - band, draw_rect.width, band))
        if profile.cardinal_mask & WEST:
            pygame.draw.rect(surface, color, (draw_rect.x, draw_rect.y, band, draw_rect.height))

    def _draw_corner_marks(
        self,
        surface: pygame.Surface,
        draw_rect: pygame.Rect,
        profile: TransitionProfile,
        color: tuple[int, int, int],
    ) -> None:
        """Draw simple square corner fills for inner and outer corners."""
        size = max(2, min(draw_rect.width, draw_rect.height) // 4)
        corners = {
            "north_east": pygame.Rect(draw_rect.right - size, draw_rect.y, size, size),
            "south_east": pygame.Rect(draw_rect.right - size, draw_rect.bottom - size, size, size),
            "south_west": pygame.Rect(draw_rect.x, draw_rect.bottom - size, size, size),
            "north_west": pygame.Rect(draw_rect.x, draw_rect.y, size, size),
        }

        # Outer corners get a solid fill to round off protruding coast shapes.
        for corner_name in profile.outer_corners:
            pygame.draw.rect(surface, color, corners[corner_name])

        # Inner corners get a smaller inset fill, which reads like a diagonal
        # bite into the tile without needing actual corner sprites yet.
        inset = max(1, size // 3)
        for corner_name in profile.inner_corners:
            inner_rect = corners[corner_name].inflate(-inset, -inset)
            pygame.draw.rect(surface, color, inner_rect)