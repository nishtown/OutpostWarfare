"""
enemy.py
--------
Prototype tower-defence enemy and route system.

This module is deliberately isolated from the rest of the game so it is easy
to remove if the checkpoint / maze idea does not feel right. The current game
only needs to:

* create an ``EnemyDirector``
* call ``update(dt)``
* call ``draw(surface, camera)``

Everything else lives here.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
import random

import pygame
from pygame import Vector2

from entity import Entity
from settings import FONT_SMALL, GOLD, RED, TILE_SIZE, VIEWPORT_HEIGHT, VIEWPORT_WIDTH, WHITE, WORLD_HEIGHT, WORLD_WIDTH


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
class RoutePlan:
    """A generated enemy route from world edge to base."""

    spawn_position: Vector2
    checkpoints: tuple[Vector2, ...]
    base_position: Vector2

    @property
    def points(self) -> tuple[Vector2, ...]:
        return (self.spawn_position, *self.checkpoints, self.base_position)


class Enemy(Entity):
    """A basic enemy that follows a pre-generated route to the base."""

    _WAYPOINT_REACHED_DISTANCE = 16.0
    _COLLISION_W = 18
    _COLLISION_H = 18

    def __init__(self, main, route: RoutePlan, tier_key: str = "scout") -> None:
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
            route.spawn_position.x,
            route.spawn_position.y,
            base_image.get_width(),
            base_image.get_height(),
            tags={"enemy", tier.key},
        )

        self.tier = tier
        self.route = route
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
        points = self.route.points
        if self.route_index >= len(points):
            return None
        return points[self.route_index]

    def update(self, dt: float) -> None:
        """Move toward the next waypoint in the route."""
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
    """Owns the experimental route and the enemies following it.

    This wrapper keeps the whole idea easy to remove: delete this module and
    the few call sites in ``game.py`` and the rest of the project stays intact.
    """

    _MIN_CHECKPOINTS = 5
    _MAX_CHECKPOINTS = 10
    _CHECKPOINT_MIN_RADIUS = TILE_SIZE * 4
    _CHECKPOINT_MAX_RADIUS = TILE_SIZE * 10
    _CHECKPOINT_MIN_SPACING = TILE_SIZE * 2.5

    def __init__(self, main, world, base_position, seed: int) -> None:
        self.main = main
        self.world = world
        self.base_position = Vector2(base_position)
        self.rng = random.Random(seed + 701)

        self.route = self._generate_route()
        self.enemies: list[Enemy] = []
        self.base_hits = 0

        # Spawn a single prototype enemy so the new behaviour is visible.
        self.spawn_enemy("scout")

    def spawn_enemy(self, tier_key: str = "scout") -> Enemy:
        enemy = Enemy(self.main, self.route, tier_key=tier_key)
        self.enemies.append(enemy)
        return enemy

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

    def draw(self, surface: pygame.Surface, camera) -> None:
        self._draw_route(surface, camera)
        self._draw_base(surface, camera)
        for enemy in self.enemies:
            enemy.draw(surface, camera)

    def _generate_route(self) -> RoutePlan:
        checkpoint_count = self.rng.randint(self._MIN_CHECKPOINTS, self._MAX_CHECKPOINTS)
        checkpoints = self._generate_checkpoints(checkpoint_count)
        spawn_position = self._pick_spawn_position()
        ordered_checkpoints = self._order_checkpoints(spawn_position, checkpoints)
        return RoutePlan(
            spawn_position=spawn_position,
            checkpoints=tuple(ordered_checkpoints),
            base_position=self.base_position,
        )

    def _generate_checkpoints(self, count: int) -> list[Vector2]:
        checkpoints: list[Vector2] = []
        attempts = 0
        max_attempts = count * 50

        while len(checkpoints) < count and attempts < max_attempts:
            attempts += 1
            angle = self.rng.uniform(0.0, math.tau)
            radius = self.rng.uniform(self._CHECKPOINT_MIN_RADIUS, self._CHECKPOINT_MAX_RADIUS)
            candidate = self.base_position + Vector2(math.cos(angle), math.sin(angle)) * radius
            snapped = self.world.find_nearest_traversable(candidate.x, candidate.y, max_radius_tiles=8)
            if snapped is None:
                continue

            if snapped.distance_to(self.base_position) < self._CHECKPOINT_MIN_RADIUS * 0.85:
                continue

            if any(snapped.distance_to(existing) < self._CHECKPOINT_MIN_SPACING for existing in checkpoints):
                continue

            checkpoints.append(snapped)

        if len(checkpoints) < count:
            for index in range(count - len(checkpoints)):
                angle = (math.tau / max(1, count)) * index
                fallback = self.base_position + Vector2(math.cos(angle), math.sin(angle)) * self._CHECKPOINT_MAX_RADIUS
                snapped = self.world.find_nearest_traversable(fallback.x, fallback.y, max_radius_tiles=12)
                if snapped is not None and all(
                    snapped.distance_to(existing) >= self._CHECKPOINT_MIN_SPACING * 0.7
                    for existing in checkpoints
                ):
                    checkpoints.append(snapped)

        return checkpoints

    def _pick_spawn_position(self) -> Vector2:
        candidates: list[Vector2] = []
        tile = self.world.tile_size

        for margin_tiles in range(0, 5):
            margin = margin_tiles * tile + tile / 2

            for x in range(tile // 2, WORLD_WIDTH, tile):
                candidates.extend(self._append_if_traversable(x, margin))
                candidates.extend(self._append_if_traversable(x, WORLD_HEIGHT - margin))

            for y in range(tile // 2, WORLD_HEIGHT, tile):
                candidates.extend(self._append_if_traversable(margin, y))
                candidates.extend(self._append_if_traversable(WORLD_WIDTH - margin, y))

            if candidates:
                break

        if not candidates:
            return self.base_position

        candidates.sort(key=lambda pos: pos.distance_squared_to(self.base_position), reverse=True)
        top_slice = candidates[: max(1, min(10, len(candidates)))]
        return self.rng.choice(top_slice)

    def _append_if_traversable(self, world_x: float, world_y: float) -> list[Vector2]:
        snapped = self.world.find_nearest_traversable(world_x, world_y, max_radius_tiles=2)
        if snapped is None:
            return []
        return [snapped]

    def _order_checkpoints(self, spawn_position: Vector2, checkpoints: list[Vector2]) -> list[Vector2]:
        remaining = [Vector2(point) for point in checkpoints]
        ordered: list[Vector2] = []
        current = Vector2(spawn_position)

        while remaining:
            next_index = min(
                range(len(remaining)),
                key=lambda index: self._route_score(current, remaining[index]),
            )
            next_checkpoint = remaining.pop(next_index)
            ordered.append(next_checkpoint)
            current = next_checkpoint

        return ordered

    def _route_score(self, start: Vector2, end: Vector2) -> float:
        """Score a checkpoint segment.

        Distance still matters, but segments that cross a lot of blocked terrain
        are penalised so the generated prototype route tends to stay on land.
        """
        distance = start.distance_to(end)
        blocked_fraction = self._estimate_blocked_fraction(start, end)
        return distance * (1.0 + blocked_fraction * 2.5)

    def _estimate_blocked_fraction(self, start: Vector2, end: Vector2) -> float:
        distance = max(1.0, start.distance_to(end))
        sample_count = max(3, int(distance // (TILE_SIZE / 2)))
        blocked = 0

        for step in range(sample_count + 1):
            t = step / sample_count
            sample = start.lerp(end, t)
            if not self.world.is_traversable_at_world(sample.x, sample.y):
                blocked += 1

        return blocked / (sample_count + 1)

    def _draw_route(self, surface: pygame.Surface, camera) -> None:
        points = self.route.points
        if len(points) < 2:
            return

        screen_points: list[tuple[int, int]] = []
        for point in points:
            screen_point = camera.world_to_screen(point)
            screen_points.append((int(screen_point.x), int(screen_point.y)))

        if len(screen_points) >= 2:
            pygame.draw.lines(surface, (250, 215, 120), False, screen_points, 2)

        for index, point in enumerate(points[:-1]):
            sx, sy = screen_points[index]
            pygame.draw.circle(surface, (235, 208, 92), (sx, sy), 6)
            pygame.draw.circle(surface, WHITE, (sx, sy), 6, 1)

            if camera.scale_x >= 0.75 and camera.scale_y >= 0.75:
                label = FONT_SMALL.render(str(index), True, WHITE)
                surface.blit(label, (sx + 8, sy - 6))

    def _draw_base(self, surface: pygame.Surface, camera) -> None:
        base_screen = camera.world_to_screen(self.base_position)
        radius = max(8, int(TILE_SIZE * 0.35 * min(camera.scale_x, camera.scale_y)))
        center = (int(base_screen.x), int(base_screen.y))

        pygame.draw.circle(surface, (120, 82, 38), center, radius)
        pygame.draw.circle(surface, GOLD, center, radius, 2)

        if camera.scale_x >= 0.75 and camera.scale_y >= 0.75:
            label = FONT_SMALL.render("Base", True, WHITE)
            surface.blit(label, (center[0] + radius + 4, center[1] - label.get_height() // 2))