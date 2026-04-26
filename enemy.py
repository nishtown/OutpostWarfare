"""
enemy.py
--------
Prototype tower-defence enemy wave system.

This module is deliberately isolated from the rest of the game so the whole
idea is easy to remove if it does not feel right. The current game only needs
to:

* create an ``EnemyDirector``
* call ``update(dt)``
* call ``draw(surface, camera)``

Everything else lives here.

Current design
--------------
* Several spawn points are generated near the world edge.
* Each spawn point computes a tile path to the base at the map centre.
* Enemies spawn in waves from those edge points and follow the computed path.
* Natural terrain obstacles remain meaningful because pathing is built from
    traversable terrain tiles rather than straight-line movement.
"""

from __future__ import annotations

from dataclasses import dataclass
import heapq
import math
import random

import pygame
from pygame import Vector2

from entity import Entity
from settings import FONT_SMALL, GOLD, RED, TILE_SIZE, WHITE, WORLD_HEIGHT, WORLD_WIDTH


@dataclass(frozen=True)
class EnemyTier:
    """Configuration for one enemy tier.

    The sprite is currently shared across all tiers, but the data structure is
    already ready for future variation in health, speed, and tint.
    """

    key: str
    label: str
    speed: float
    max_health: float
    tint: tuple[int, int, int]


ENEMY_TIERS = {
    "scout": EnemyTier("scout", "Scout", speed=78.0, max_health=20.0, tint=(255, 190, 190)),
    "raider": EnemyTier("raider", "Raider", speed=64.0, max_health=42.0, tint=(255, 155, 155)),
    "brute": EnemyTier("brute", "Brute", speed=48.0, max_health=90.0, tint=(225, 120, 120)),
}


@dataclass(frozen=True)
class SpawnPoint:
    """One enemy spawn point on or near the edge of the world.

    Each spawn point stores a fully-resolved path to the base so enemies can
    be spawned cheaply during gameplay without recalculating their route.
    """

    key: str
    side: str
    tile: tuple[int, int]
    world_position: Vector2
    path_points: tuple[Vector2, ...]


class Enemy(Entity):
    """A basic enemy that follows a pre-generated tile path to the base."""

    _WAYPOINT_REACHED_DISTANCE = 16.0
    _COLLISION_W = 18
    _COLLISION_H = 18

    def __init__(self, main, spawn_point: SpawnPoint, tier_key: str = "scout") -> None:
        tier = ENEMY_TIERS[tier_key]

        base_image = Entity.load_image(
            "assets", "player", "player.png",
            fallback_size=(32, 32),
            fallback_color=(210, 100, 100),
        )
        base_image = base_image.copy()
        base_image.fill((*tier.tint, 255), special_flags=pygame.BLEND_RGBA_MULT)

        super().__init__(
            main,
            spawn_point.world_position.x,
            spawn_point.world_position.y,
            base_image.get_width(),
            base_image.get_height(),
            tags={"enemy", tier.key},
        )

        self.tier = tier
        self.spawn_point = spawn_point
        self.path_points = spawn_point.path_points
        self.original_image = base_image
        self.image = self.original_image.copy()
        self.collision_size = (self._COLLISION_W, self._COLLISION_H)

        self.max_health = tier.max_health
        self.health = tier.max_health
        self.speed = tier.speed

        self.route_index = 1
        self.reached_base = False

    @property
    def current_target(self) -> Vector2 | None:
        """Return the next waypoint the enemy is moving toward."""
        if self.route_index >= len(self.path_points):
            return None
        return self.path_points[self.route_index]

    def update(self, dt: float) -> None:
        """Move toward the next waypoint in the path."""
        if not self.alive:
            return

        target = self.current_target
        if target is None:
            self.reached_base = True
            self.alive = False
            return

        direction = target - self.pos
        distance = direction.length()

        if distance <= self._WAYPOINT_REACHED_DISTANCE:
            self.route_index += 1
            target = self.current_target
            if target is None:
                self.reached_base = True
                self.alive = False
                return
            direction = target - self.pos
            distance = direction.length()

        if distance > 0:
            heading = direction.normalize()
            step = min(distance, self.speed * dt)
            self.pos += heading * step
            self.facing_angle = math.degrees(math.atan2(-heading.y, heading.x))

        self.image = pygame.transform.rotate(self.original_image, self.facing_angle)
        self.rect = self.image.get_rect(center=(int(self.pos.x), int(self.pos.y)))
        super().update(dt)

    def draw(self, surface: pygame.Surface, camera=None) -> None:
        super().draw(surface, camera)
        self._draw_health_bar(surface, camera)

    def _draw_health_bar(self, surface: pygame.Surface, camera) -> None:
        if not self.alive:
            return

        if camera is not None and hasattr(camera, "world_to_screen"):
            screen_pos = camera.world_to_screen(self.pos)
            center_x = int(screen_pos.x)
            top_y = int(screen_pos.y) - max(6, self.rect.height // 2) - 8
            bar_width = max(10, int(26 * camera.scale_x))
            bar_height = max(2, int(4 * camera.scale_y))
        else:
            center_x = int(self.pos.x)
            top_y = int(self.pos.y) - self.rect.height // 2 - 8
            bar_width = 26
            bar_height = 4

        ratio = max(0.0, min(1.0, self.health / self.max_health))
        bar_rect = pygame.Rect(center_x - bar_width // 2, top_y, bar_width, bar_height)
        fill_rect = pygame.Rect(bar_rect.x, bar_rect.y, int(bar_width * ratio), bar_height)
        pygame.draw.rect(surface, (48, 20, 20), bar_rect)
        pygame.draw.rect(surface, RED, fill_rect)
        pygame.draw.rect(surface, WHITE, bar_rect, 1)


class EnemyDirector:
    """Owns the experimental wave-spawn system.

    This wrapper keeps the whole idea easy to remove: delete this module and
    the few call sites in ``game.py`` and the rest of the project stays intact.
    """

    _SPAWN_POINT_COUNT = 6
    _MAX_EDGE_SEARCH_MARGINS = 4
    _MIN_SPAWN_TILE_SPACING = 10
    _SPAWN_INTERVAL = 0.9
    _WAVE_COOLDOWN = 4.0
    _BASE_MARKER_RADIUS = TILE_SIZE * 0.35

    def __init__(self, main, world, base_position, seed: int) -> None:
        self.main = main
        self.world = world
        base_candidate = Vector2(base_position)
        self.base_position = (
            self.world.find_nearest_traversable(base_candidate.x, base_candidate.y, max_radius_tiles=10)
            or base_candidate
        )
        self.base_tile = self._world_to_tile(self.base_position)
        self.rng = random.Random(seed + 701)

        self.spawn_points = self._generate_spawn_points(self._SPAWN_POINT_COUNT)
        self.enemies: list[Enemy] = []
        self.base_hits = 0
        self.wave_number = 0
        self.pending_spawns: list[str] = []
        self.spawn_timer = 0.0
        self.time_until_next_wave = 0.75

    @property
    def active_enemy_count(self) -> int:
        return len(self.enemies)

    def spawn_enemy(self, tier_key: str = "scout", spawn_point: SpawnPoint | None = None) -> Enemy | None:
        if not self.spawn_points:
            return None

        if spawn_point is None:
            spawn_point = self.rng.choice(self.spawn_points)

        enemy = Enemy(self.main, spawn_point, tier_key=tier_key)
        self.enemies.append(enemy)
        return enemy

    def start_next_wave(self) -> None:
        """Queue the next wave of enemies.

        Enemy tier composition gradually gets more dangerous as the wave number
        rises, but the rules are contained here so they are easy to change.
        """
        self.wave_number += 1
        self.pending_spawns = self._build_wave_queue(self.wave_number)
        self.spawn_timer = 0.0

    def update(self, dt: float) -> None:
        for enemy in self.enemies:
            enemy.update(dt)

        survivors: list[Enemy] = []
        for enemy in self.enemies:
            if enemy.reached_base:
                self.base_hits += 1
            elif enemy.alive:
                survivors.append(enemy)
        self.enemies = survivors

        if self.pending_spawns and self.spawn_points:
            self.spawn_timer -= dt
            while self.pending_spawns and self.spawn_timer <= 0.0:
                tier_key = self.pending_spawns.pop(0)
                self.spawn_enemy(tier_key)
                self.spawn_timer += self._SPAWN_INTERVAL
        elif not self.enemies:
            self.time_until_next_wave -= dt
            if self.time_until_next_wave <= 0.0:
                self.start_next_wave()
                self.time_until_next_wave = self._WAVE_COOLDOWN

    def draw(self, surface: pygame.Surface, camera) -> None:
        self._draw_spawn_points(surface, camera)
        self._draw_base(surface, camera)
        if self.main.debug_mode:
            self._draw_paths(surface, camera)
        for enemy in self.enemies:
            enemy.draw(surface, camera)

    def _build_wave_queue(self, wave_number: int) -> list[str]:
        """Return the enemy tiers for a wave.

        This is intentionally simple and easy to edit. Waves gradually trend
        from scouts to raiders to brutes.
        """
        scouts = max(2, 4 + wave_number)
        raiders = max(0, wave_number - 2)
        brutes = max(0, wave_number - 5)
        queue = (["scout"] * scouts) + (["raider"] * raiders) + (["brute"] * brutes)
        self.rng.shuffle(queue)
        return queue

    def _generate_spawn_points(self, count: int) -> list[SpawnPoint]:
        candidates = self._collect_edge_candidates()
        selected: list[SpawnPoint] = []
        selected_tiles: list[tuple[int, int]] = []

        self.rng.shuffle(candidates)

        for side, tile_coord, world_position in candidates:
            if any(self._tile_distance(tile_coord, other_tile) < self._MIN_SPAWN_TILE_SPACING for other_tile in selected_tiles):
                continue

            tile_path = self._find_tile_path(tile_coord, self.base_tile)
            if tile_path is None or len(tile_path) < 2:
                continue

            path_points = tuple(self._tile_to_world(tile) for tile in tile_path)
            spawn_point = SpawnPoint(
                key=f"{side}_{len(selected)}",
                side=side,
                tile=tile_coord,
                world_position=world_position,
                path_points=path_points,
            )
            selected.append(spawn_point)
            selected_tiles.append(tile_coord)

            if len(selected) >= count:
                break

        return selected

    def _collect_edge_candidates(self) -> list[tuple[str, tuple[int, int], Vector2]]:
        candidates: list[tuple[str, tuple[int, int], Vector2]] = []
        seen_tiles: set[tuple[int, int]] = set()
        tile_size = self.world.tile_size

        for margin_tiles in range(self._MAX_EDGE_SEARCH_MARGINS + 1):
            top_y = margin_tiles * tile_size + tile_size / 2
            bottom_y = WORLD_HEIGHT - margin_tiles * tile_size - tile_size / 2
            left_x = margin_tiles * tile_size + tile_size / 2
            right_x = WORLD_WIDTH - margin_tiles * tile_size - tile_size / 2

            for world_x in range(tile_size // 2, WORLD_WIDTH, tile_size):
                self._append_edge_candidate(candidates, seen_tiles, "north", world_x, top_y)
                self._append_edge_candidate(candidates, seen_tiles, "south", world_x, bottom_y)

            for world_y in range(tile_size // 2, WORLD_HEIGHT, tile_size):
                self._append_edge_candidate(candidates, seen_tiles, "west", left_x, world_y)
                self._append_edge_candidate(candidates, seen_tiles, "east", right_x, world_y)

        candidates.sort(
            key=lambda item: Vector2(item[2]).distance_squared_to(self.base_position),
            reverse=True,
        )
        return candidates

    def _append_edge_candidate(self, candidates, seen_tiles, side: str, world_x: float, world_y: float) -> None:
        snapped = self.world.find_nearest_traversable(world_x, world_y, max_radius_tiles=3)
        if snapped is None:
            return

        tile_coord = self._world_to_tile(snapped)
        if tile_coord == self.base_tile or tile_coord in seen_tiles:
            return

        seen_tiles.add(tile_coord)
        candidates.append((side, tile_coord, snapped))

    def _find_tile_path(self, start_tile: tuple[int, int], goal_tile: tuple[int, int]) -> list[tuple[int, int]] | None:
        """Compute a simple A* path across traversable world tiles."""
        if start_tile == goal_tile:
            return [start_tile]

        open_heap: list[tuple[float, int, tuple[int, int]]] = []
        heapq.heappush(open_heap, (0.0, 0, start_tile))
        came_from: dict[tuple[int, int], tuple[int, int]] = {}
        g_score = {start_tile: 0.0}
        counter = 1

        while open_heap:
            _, _, current = heapq.heappop(open_heap)

            if current == goal_tile:
                return self._reconstruct_path(came_from, current)

            for neighbor in self._iter_neighbor_tiles(current):
                tile = self.world.get_tile(*neighbor)
                if tile is None or not tile.traversable:
                    continue

                terrain_type = self.world.terrain_types[tile.terrain_key]
                tentative_g = g_score[current] + terrain_type.move_cost

                if tentative_g >= g_score.get(neighbor, float("inf")):
                    continue

                came_from[neighbor] = current
                g_score[neighbor] = tentative_g
                priority = tentative_g + self._heuristic_cost(neighbor, goal_tile)
                heapq.heappush(open_heap, (priority, counter, neighbor))
                counter += 1

        return None

    def _iter_neighbor_tiles(self, tile_coord: tuple[int, int]):
        grid_x, grid_y = tile_coord
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nx = grid_x + dx
            ny = grid_y + dy
            if 0 <= nx < self.world.columns and 0 <= ny < self.world.rows:
                yield (nx, ny)

    def _reconstruct_path(
        self,
        came_from: dict[tuple[int, int], tuple[int, int]],
        current: tuple[int, int],
    ) -> list[tuple[int, int]]:
        path = [current]
        while current in came_from:
            current = came_from[current]
            path.append(current)
        path.reverse()
        return path

    def _heuristic_cost(self, start: tuple[int, int], end: tuple[int, int]) -> float:
        return abs(start[0] - end[0]) + abs(start[1] - end[1])

    def _world_to_tile(self, position) -> tuple[int, int]:
        pos = Vector2(position)
        return int(pos.x // self.world.tile_size), int(pos.y // self.world.tile_size)

    def _tile_to_world(self, tile_coord: tuple[int, int]) -> Vector2:
        grid_x, grid_y = tile_coord
        half = self.world.tile_size / 2
        return Vector2(grid_x * self.world.tile_size + half, grid_y * self.world.tile_size + half)

    def _tile_distance(self, a: tuple[int, int], b: tuple[int, int]) -> float:
        return math.dist(a, b)

    def _draw_spawn_points(self, surface: pygame.Surface, camera) -> None:
        for spawn_point in self.spawn_points:
            screen_pos = camera.world_to_screen(spawn_point.world_position)
            center = (int(screen_pos.x), int(screen_pos.y))
            radius = max(5, int(6 * min(camera.scale_x, camera.scale_y)))
            pygame.draw.circle(surface, (160, 45, 45), center, radius)
            pygame.draw.circle(surface, WHITE, center, radius, 1)

            if camera.scale_x >= 0.75 and camera.scale_y >= 0.75:
                label = FONT_SMALL.render(spawn_point.side[0].upper(), True, WHITE)
                surface.blit(label, (center[0] + radius + 3, center[1] - label.get_height() // 2))

    def _draw_paths(self, surface: pygame.Surface, camera) -> None:
        for spawn_point in self.spawn_points:
            if len(spawn_point.path_points) < 2:
                continue

            screen_points = []
            for point in spawn_point.path_points:
                screen = camera.world_to_screen(point)
                screen_points.append((int(screen.x), int(screen.y)))

            pygame.draw.lines(surface, (245, 210, 115), False, screen_points, 1)

    def _draw_base(self, surface: pygame.Surface, camera) -> None:
        base_screen = camera.world_to_screen(self.base_position)
        radius = max(8, int(self._BASE_MARKER_RADIUS * min(camera.scale_x, camera.scale_y)))
        center = (int(base_screen.x), int(base_screen.y))

        pygame.draw.circle(surface, (120, 82, 38), center, radius)
        pygame.draw.circle(surface, GOLD, center, radius, 2)

        if camera.scale_x >= 0.75 and camera.scale_y >= 0.75:
            label = FONT_SMALL.render("Base", True, WHITE)
            surface.blit(label, (center[0] + radius + 4, center[1] - label.get_height() // 2))