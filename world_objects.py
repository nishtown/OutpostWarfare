"""
world_objects.py
----------------
Shared world-object layer for Outpost Warfare.

This module owns everything the procedural terrain does not:

* placeable buildings and walls
* traps and their trigger logic
* arrow towers and their projectiles
* harvestable tree and rock nodes

Keeping these objects in one manager lets the player, enemies, and UI all talk
to the same simulation layer instead of inventing parallel one-off systems.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
import random

import pygame
from pygame import Vector2

from entity import Entity
from settings import BLACK, DARK_BROWN, FONT_SMALL, GOLD, GREEN, LIGHT_GRAY, ORANGE, RED, TILE_SIZE, WHITE


@dataclass(frozen=True)
class BuildDefinition:
    """Static data for one player-placeable structure."""

    key: str
    label: str
    cost: dict[str, int]
    max_health: float
    color: tuple[int, int, int]
    blocks_movement: bool = True
    target_priority: int = 0
    detour_radius: float = 0.0
    tower_range: float = 0.0
    projectile_damage: float = 0.0
    projectile_speed: float = 0.0
    attack_cooldown: float = 0.0
    is_trap: bool = False
    trap_damage: float = 0.0
    hidden_to_enemy: bool = False

    @property
    def menu_cost(self) -> int:
        return sum(self.cost.values())


BUILD_DEFINITIONS = {
    "farm": BuildDefinition(
        "farm", "Farm", {"wood": 28}, max_health=110.0, color=(84, 156, 58),
        target_priority=2, detour_radius=TILE_SIZE * 2.2,
    ),
    "lumberyard": BuildDefinition(
        "lumberyard", "Lumberyard", {"wood": 32, "stone": 10}, max_health=130.0, color=(97, 74, 44),
        target_priority=3, detour_radius=TILE_SIZE * 2.4,
    ),
    "arrow_tower": BuildDefinition(
        "arrow_tower", "Arrow Tower", {"wood": 40, "stone": 18}, max_health=150.0, color=(120, 94, 52),
        target_priority=4, detour_radius=TILE_SIZE * 2.8,
        tower_range=TILE_SIZE * 3.7, projectile_damage=14.0, projectile_speed=340.0, attack_cooldown=0.85,
    ),
    "wall": BuildDefinition(
        "wall", "Wall", {"wood": 10, "stone": 20}, max_health=260.0, color=(126, 118, 104),
        target_priority=1,
    ),
    "spike_trap": BuildDefinition(
        "spike_trap", "Spike Trap", {"wood": 18, "stone": 6}, max_health=40.0, color=(96, 80, 56),
        blocks_movement=False, is_trap=True, trap_damage=36.0, hidden_to_enemy=True,
    ),
    "barracks": BuildDefinition(
        "barracks", "Barracks", {"wood": 34, "stone": 14}, max_health=145.0, color=(122, 56, 50),
        target_priority=2, detour_radius=TILE_SIZE * 2.0,
    ),
    "workshop": BuildDefinition(
        "workshop", "Workshop", {"wood": 26, "stone": 24}, max_health=140.0, color=(126, 108, 54),
        target_priority=2, detour_radius=TILE_SIZE * 2.0,
    ),
    "market": BuildDefinition(
        "market", "Market", {"wood": 24, "stone": 12}, max_health=125.0, color=(172, 146, 64),
        target_priority=2, detour_radius=TILE_SIZE * 2.0,
    ),
}

BUILD_MENU_ORDER = [
    "farm",
    "lumberyard",
    "arrow_tower",
    "wall",
    "spike_trap",
    "barracks",
    "workshop",
    "market",
]


@dataclass(frozen=True)
class ResourceNodeDefinition:
    """Static data for one harvestable node type."""

    key: str
    label: str
    resource_key: str
    action_label: str
    action_duration: float
    min_yield: int
    max_yield: int


RESOURCE_DEFINITIONS = {
    "tree": ResourceNodeDefinition("tree", "Tree", "wood", "Chopping tree", 1.15, 8, 14),
    "rock": ResourceNodeDefinition("rock", "Rock", "stone", "Mining rock", 1.55, 6, 11),
}

RESOURCE_COST_ORDER = ("wood", "stone", "gold", "food")
RESOURCE_COST_ABBREVIATIONS = {
    "wood": "W",
    "stone": "S",
    "gold": "G",
    "food": "F",
}


def format_cost_text(cost: dict[str, int], compact: bool = True) -> str:
    """Return a readable resource cost label for build buttons and status UI."""
    parts: list[str] = []
    for resource_key in RESOURCE_COST_ORDER:
        amount = int(cost.get(resource_key, 0))
        if amount <= 0:
            continue

        if compact:
            parts.append(f"{amount}{RESOURCE_COST_ABBREVIATIONS[resource_key]}")
        else:
            parts.append(f"{resource_key.title()} {amount}")

    return " ".join(parts) if parts else "Free"


def _footprint_for_key(building_key: str) -> tuple[int, int]:
    if building_key == "wall":
        size = int(TILE_SIZE * 0.88)
        return size, max(22, int(TILE_SIZE * 0.36))
    if building_key == "spike_trap":
        size = int(TILE_SIZE * 0.42)
        return size, size
    size = int(TILE_SIZE * 0.68)
    return size, size


class Structure(Entity):
    """One placed structure, wall, tower, or trap."""

    def __init__(self, main, definition: BuildDefinition, position: Vector2) -> None:
        image = self._build_surface(definition)
        super().__init__(
            main,
            position.x,
            position.y,
            image.get_width(),
            image.get_height(),
            tags={"structure", definition.key},
        )

        self.definition = definition
        self.original_image = image
        self.image = image.copy()
        self.collision_size = _footprint_for_key(definition.key)

        self.max_health = definition.max_health
        self.health = definition.max_health
        self.blocks_movement = definition.blocks_movement
        self.enemy_targetable = True
        self.cooldown_remaining = 0.0
        self.armed = definition.is_trap
        self.revealed = not definition.hidden_to_enemy
        self.attack_radius = max(self.collision_size) / 2 + 8

    @property
    def is_detour_candidate(self) -> bool:
        return self.definition.detour_radius > 0.0 and self.definition.target_priority > 0

    @property
    def is_trap(self) -> bool:
        return self.definition.is_trap

    def take_damage(self, amount: float) -> None:
        self.revealed = True
        self.health -= max(0.0, float(amount))
        if self.health <= 0.0:
            self.alive = False

    def reveal(self) -> None:
        self.revealed = True

    def consume_trap(self) -> None:
        self.revealed = True
        self.armed = False
        self.alive = False

    def update(self, dt: float) -> None:
        self.cooldown_remaining = max(0.0, self.cooldown_remaining - dt)
        super().update(dt)

    def draw(self, surface: pygame.Surface, camera=None) -> None:
        draw_image = self.image
        if self.is_trap and not self.revealed and (camera is None or getattr(camera, "name", "") != "minimap"):
            draw_image = self.image.copy()
            draw_image.set_alpha(150)

        if camera is not None and hasattr(camera, "world_rect_to_screen"):
            draw_rect = camera.world_rect_to_screen(self.rect)
            if draw_rect.width <= 0 or draw_rect.height <= 0:
                return
            scaled = pygame.transform.smoothscale(draw_image, draw_rect.size)
            surface.blit(scaled, draw_rect)
        else:
            surface.blit(draw_image, self.rect)

        if getattr(camera, "name", "") != "minimap" and self.health < self.max_health:
            self._draw_health_bar(surface, camera)

        if self.main.debug_mode and camera is not None and hasattr(camera, "world_rect_to_screen"):
            pygame.draw.rect(surface, RED, camera.world_rect_to_screen(self.get_collision_rect()), 1)

    def _draw_health_bar(self, surface: pygame.Surface, camera) -> None:
        if camera is None or not hasattr(camera, "world_to_screen"):
            return
        screen_pos = camera.world_to_screen(self.pos)
        width = max(10, int(28 * camera.scale_x))
        height = max(3, int(5 * camera.scale_y))
        top_y = int(screen_pos.y) - max(12, int(self.rect.height * camera.scale_y / 2)) - 7
        rect = pygame.Rect(int(screen_pos.x) - width // 2, top_y, width, height)
        fill = pygame.Rect(rect.x, rect.y, int(width * max(0.0, self.health / self.max_health)), height)
        pygame.draw.rect(surface, (35, 20, 14), rect)
        pygame.draw.rect(surface, RED, fill)
        pygame.draw.rect(surface, WHITE, rect, 1)

    @staticmethod
    def _build_surface(definition: BuildDefinition) -> pygame.Surface:
        surface = pygame.Surface((48, 48), pygame.SRCALPHA)
        accent = definition.color

        if definition.key == "farm":
            pygame.draw.rect(surface, (97, 75, 42), (16, 22, 16, 12))
            pygame.draw.polygon(surface, (145, 120, 58), [(12, 22), (24, 13), (36, 22)])
            for row in range(3):
                y = 31 + row * 4
                pygame.draw.line(surface, (111, 160, 56), (8, y), (40, y), 2)
        elif definition.key == "lumberyard":
            for offset in range(3):
                pygame.draw.rect(surface, (120, 82, 44), (10, 15 + offset * 8, 28, 6), border_radius=2)
                pygame.draw.rect(surface, DARK_BROWN, (10, 15 + offset * 8, 28, 6), 1, border_radius=2)
            pygame.draw.rect(surface, (146, 122, 82), (32, 10, 6, 16))
        elif definition.key == "arrow_tower":
            pygame.draw.rect(surface, (116, 98, 68), (16, 12, 16, 24))
            pygame.draw.rect(surface, accent, (12, 8, 24, 8))
            for battlement_x in range(12, 36, 6):
                pygame.draw.rect(surface, accent, (battlement_x, 4, 4, 4))
            pygame.draw.line(surface, ORANGE, (24, 18), (36, 10), 2)
            pygame.draw.line(surface, WHITE, (34, 12), (40, 8), 1)
        elif definition.key == "wall":
            pygame.draw.rect(surface, accent, (6, 18, 36, 12), border_radius=3)
            for x in range(8, 38, 8):
                pygame.draw.rect(surface, accent, (x, 12, 4, 6))
        elif definition.key == "spike_trap":
            pygame.draw.rect(surface, (84, 68, 44), (10, 24, 28, 6), border_radius=3)
            for x in range(12, 36, 5):
                pygame.draw.polygon(surface, LIGHT_GRAY, [(x, 24), (x + 2, 16), (x + 4, 24)])
        elif definition.key == "market":
            pygame.draw.rect(surface, (148, 112, 58), (12, 20, 24, 12))
            pygame.draw.polygon(surface, accent, [(10, 20), (24, 12), (38, 20)])
            for x in range(13, 35, 6):
                pygame.draw.line(surface, (188, 52, 52), (x, 22), (x, 30), 2)
        elif definition.key == "workshop":
            pygame.draw.rect(surface, (112, 92, 58), (12, 18, 24, 16))
            pygame.draw.circle(surface, LIGHT_GRAY, (19, 27), 4, 2)
            pygame.draw.rect(surface, DARK_BROWN, (29, 12, 4, 10))
        else:
            pygame.draw.rect(surface, accent, (12, 18, 24, 16))
            pygame.draw.polygon(surface, (90, 46, 40), [(10, 18), (24, 10), (38, 18)])

        pygame.draw.rect(surface, BLACK, surface.get_rect(), 1)
        return surface


class ResourceNode(Entity):
    """One harvestable tree or rock node."""

    def __init__(self, main, definition: ResourceNodeDefinition, position: Vector2, total_yield: int) -> None:
        image = self._build_surface(definition)
        super().__init__(
            main,
            position.x,
            position.y,
            image.get_width(),
            image.get_height(),
            tags={"resource", "harvestable", definition.key},
        )

        self.definition = definition
        self.original_image = image
        self.image = image.copy()
        self.total_yield = int(total_yield)
        self.remaining_yield = int(total_yield)
        self.action_label = definition.action_label
        self.action_duration = definition.action_duration
        self.collision_size = (int(TILE_SIZE * 0.5), int(TILE_SIZE * 0.5))

    def harvest(self) -> dict[str, int]:
        if not self.alive or self.remaining_yield <= 0:
            return {}

        amount = min(3, self.remaining_yield)
        self.remaining_yield -= amount
        if self.remaining_yield <= 0:
            self.alive = False
        return {self.definition.resource_key: amount}

    def draw(self, surface: pygame.Surface, camera=None) -> None:
        super().draw(surface, camera)

        if self.main.debug_mode and camera is not None and hasattr(camera, "world_to_screen"):
            screen_pos = camera.world_to_screen(self.pos)
            label = FONT_SMALL.render(str(self.remaining_yield), True, WHITE)
            surface.blit(label, (int(screen_pos.x) - label.get_width() // 2, int(screen_pos.y) - 26))

    @staticmethod
    def _build_surface(definition: ResourceNodeDefinition) -> pygame.Surface:
        surface = pygame.Surface((46, 46), pygame.SRCALPHA)

        if definition.key == "tree":
            pygame.draw.rect(surface, (96, 62, 28), (20, 24, 6, 14))
            pygame.draw.circle(surface, (42, 132, 56), (17, 23), 10)
            pygame.draw.circle(surface, (34, 116, 49), (27, 19), 11)
            pygame.draw.circle(surface, (60, 150, 74), (24, 28), 8)
        else:
            pygame.draw.polygon(surface, (118, 118, 118), [(12, 33), (18, 18), (30, 13), (36, 24), (31, 35), (18, 37)])
            pygame.draw.polygon(surface, (86, 86, 86), [(12, 33), (18, 18), (30, 13), (36, 24), (31, 35), (18, 37)], 2)
            pygame.draw.circle(surface, (152, 152, 152), (23, 22), 4)

        pygame.draw.rect(surface, BLACK, surface.get_rect(), 1)
        return surface


class ArrowProjectile:
    """Simple projectile fired by an arrow tower."""

    def __init__(self, position: Vector2, target, damage: float, speed: float) -> None:
        self.pos = Vector2(position)
        self.target = target
        self.damage = float(damage)
        self.speed = float(speed)
        self.alive = True

    def update(self, dt: float) -> None:
        if not self.alive:
            return

        if self.target is None or not getattr(self.target, "alive", False):
            self.alive = False
            return

        direction = self.target.pos - self.pos
        distance = direction.length()
        if distance <= 0.001:
            self._hit_target()
            return

        heading = direction.normalize()
        step = min(distance, self.speed * dt)
        self.pos += heading * step

        if distance <= step + max(6, getattr(self.target, "attack_radius", 8)):
            self._hit_target()

    def draw(self, surface: pygame.Surface, camera) -> None:
        if getattr(camera, "name", "") == "minimap":
            return

        screen_pos = camera.world_to_screen(self.pos)
        pygame.draw.circle(surface, ORANGE, (int(screen_pos.x), int(screen_pos.y)), max(2, int(3 * camera.scale_x)))
        pygame.draw.circle(surface, WHITE, (int(screen_pos.x), int(screen_pos.y)), max(2, int(3 * camera.scale_x)), 1)

    def _hit_target(self) -> None:
        if self.target is not None and getattr(self.target, "alive", False):
            self.target.take_damage(self.damage)
        self.alive = False


class WorldObjectManager:
    """Shared simulation layer for placeables, resource nodes, and projectiles."""

    _TREE_CHANCE = 0.035
    _ROCK_CHANCE = 0.016
    _MIN_RESOURCE_TILE_SPACING = 2.0

    def __init__(self, main, world, base_position, seed: int, announce_callback=None) -> None:
        self.main = main
        self.world = world
        self.base_position = Vector2(base_position)
        self.announce_callback = announce_callback
        self.rng = random.Random(seed + 1701)

        self.structures: list[Structure] = []
        self.resource_nodes: list[ResourceNode] = []
        self.projectiles: list[ArrowProjectile] = []

        self._spawn_resource_nodes()

    def update(self, dt: float, enemies) -> None:
        for structure in self.structures:
            structure.update(dt)

        self._update_traps(enemies)
        self._update_towers(enemies)

        for projectile in self.projectiles:
            projectile.update(dt)

        surviving_structures: list[Structure] = []
        for structure in self.structures:
            if structure.alive:
                surviving_structures.append(structure)
            elif not structure.is_trap:
                self._announce(f"{structure.definition.label} destroyed", accent=RED, duration=1.8)
        self.structures = surviving_structures

        self.resource_nodes = [node for node in self.resource_nodes if node.alive]
        self.projectiles = [projectile for projectile in self.projectiles if projectile.alive]

    def draw(self, surface: pygame.Surface, camera) -> None:
        for node in self.resource_nodes:
            node.draw(surface, camera)
        for structure in self.structures:
            structure.draw(surface, camera)

    def draw_projectiles(self, surface: pygame.Surface, camera) -> None:
        for projectile in self.projectiles:
            projectile.draw(surface, camera)

    def place_structure(self, building_key: str, world_position, player) -> tuple[bool, str]:
        definition = BUILD_DEFINITIONS.get(building_key)
        if definition is None:
            return False, "Unknown build option"

        snapped = self._snap_to_tile_center(world_position)
        tile = self.world.get_tile_at_world(snapped.x, snapped.y)
        if tile is None or not tile.traversable:
            return False, "That ground cannot support a structure"

        placement_rect = self._structure_rect(snapped, definition)
        if placement_rect.collidepoint(int(self.base_position.x), int(self.base_position.y)):
            return False, "Keep the central base clear"

        if self.find_blocking_structure_for_rect(placement_rect) is not None:
            return False, "Another structure is already there"

        for node in self.resource_nodes:
            if node.rect.colliderect(placement_rect.inflate(10, 10)):
                return False, "Harvest the nearby resource first"

        if not player.consume_resources(definition.cost):
            return False, "Not enough resources"

        structure = Structure(self.main, definition, snapped)
        self.structures.append(structure)
        self._announce(f"Placed {definition.label}", accent=GOLD, duration=1.3)
        return True, definition.label

    def find_harvest_target(self, clicked_world_pos, player_pos, max_range: float, click_radius: float = 48.0):
        clicked = Vector2(clicked_world_pos)
        player = Vector2(player_pos)
        best_node = None
        best_score = float("inf")

        for node in self.resource_nodes:
            clicked_distance = node.pos.distance_to(clicked)
            player_distance = node.pos.distance_to(player)
            if clicked_distance > click_radius or player_distance > max_range:
                continue

            score = clicked_distance * 0.8 + player_distance * 0.2
            if score < best_score:
                best_score = score
                best_node = node

        return best_node

    def find_blocking_structure_for_rect(self, collision_rect: pygame.Rect, ignore=None):
        for structure in self.structures:
            if structure is ignore or not structure.alive or not structure.blocks_movement:
                continue
            if structure.get_collision_rect().colliderect(collision_rect):
                return structure
        return None

    def find_blocking_structure_at_world(self, world_position):
        point = Vector2(world_position)
        for structure in self.structures:
            if not structure.alive or not structure.blocks_movement:
                continue
            if structure.get_collision_rect().collidepoint(int(point.x), int(point.y)):
                return structure
        return None

    def find_enemy_detour_target(self, enemy_pos, radius: float):
        origin = Vector2(enemy_pos)
        best_target = None
        best_score = float("-inf")

        for structure in self.structures:
            if not structure.alive or not structure.is_detour_candidate:
                continue

            distance = structure.pos.distance_to(origin)
            if distance > min(radius, structure.definition.detour_radius):
                continue

            score = structure.definition.target_priority * 90.0 - distance
            if score > best_score:
                best_score = score
                best_target = structure

        return best_target

    def find_detectable_trap(self, enemy_pos, radius: float):
        origin = Vector2(enemy_pos)
        best_target = None
        best_distance = float("inf")

        for structure in self.structures:
            if not structure.alive or not structure.is_trap or not structure.armed:
                continue

            distance = structure.pos.distance_to(origin)
            if distance <= radius and distance < best_distance:
                best_distance = distance
                best_target = structure

        return best_target

    def _update_traps(self, enemies) -> None:
        for trap in self.structures:
            if not trap.alive or not trap.is_trap or not trap.armed:
                continue

            trigger_rect = trap.get_collision_rect().inflate(16, 16)
            for enemy in enemies:
                if not getattr(enemy, "alive", False) or getattr(enemy, "can_detect_traps", False):
                    continue
                if trigger_rect.collidepoint(int(enemy.pos.x), int(enemy.pos.y)):
                    enemy.take_damage(trap.definition.trap_damage)
                    trap.consume_trap()
                    self._announce("A trap was sprung", accent=ORANGE, duration=1.6)
                    break

    def _update_towers(self, enemies) -> None:
        living_enemies = [enemy for enemy in enemies if getattr(enemy, "alive", False)]
        if not living_enemies:
            return

        for structure in self.structures:
            definition = structure.definition
            if not structure.alive or definition.tower_range <= 0.0 or structure.cooldown_remaining > 0.0:
                continue

            candidates = [
                enemy for enemy in living_enemies
                if enemy.pos.distance_to(structure.pos) <= definition.tower_range
            ]
            if not candidates:
                continue

            target = min(candidates, key=lambda enemy: enemy.pos.distance_squared_to(structure.pos))
            self.projectiles.append(
                ArrowProjectile(structure.pos, target, definition.projectile_damage, definition.projectile_speed)
            )
            structure.cooldown_remaining = definition.attack_cooldown

    def _spawn_resource_nodes(self) -> None:
        used_tiles: list[tuple[int, int]] = []

        for grid_y in range(self.world.rows):
            for grid_x in range(self.world.columns):
                tile = self.world.get_tile(grid_x, grid_y)
                if tile is None or not tile.traversable:
                    continue

                if tile.terrain_key in {"grass", "forest"} and self.rng.random() < self._TREE_CHANCE:
                    self._try_add_resource_node("tree", (grid_x, grid_y), used_tiles)
                elif tile.terrain_key in {"sand", "grass"} and self.rng.random() < self._ROCK_CHANCE:
                    self._try_add_resource_node("rock", (grid_x, grid_y), used_tiles)

        self._seed_resources_near_base("tree", used_tiles, target_count=5)
        self._seed_resources_near_base("rock", used_tiles, target_count=3)

    def _seed_resources_near_base(self, resource_key: str, used_tiles, target_count: int) -> None:
        base_tile = self._tile_coord(self.base_position)
        seeded = 0

        for radius in range(2, 10):
            for grid_y in range(max(0, base_tile[1] - radius), min(self.world.rows, base_tile[1] + radius + 1)):
                for grid_x in range(max(0, base_tile[0] - radius), min(self.world.columns, base_tile[0] + radius + 1)):
                    if seeded >= target_count:
                        return
                    tile = self.world.get_tile(grid_x, grid_y)
                    if tile is None or not tile.traversable:
                        continue
                    if resource_key == "tree" and tile.terrain_key not in {"grass", "forest", "sand"}:
                        continue
                    if resource_key == "rock" and tile.terrain_key not in {"grass", "sand", "forest"}:
                        continue
                    if self._try_add_resource_node(resource_key, (grid_x, grid_y), used_tiles):
                        seeded += 1

    def _try_add_resource_node(self, resource_key: str, tile_coord: tuple[int, int], used_tiles) -> bool:
        if any(math.dist(tile_coord, other_tile) < self._MIN_RESOURCE_TILE_SPACING for other_tile in used_tiles):
            return False

        definition = RESOURCE_DEFINITIONS[resource_key]
        world_position = self._tile_center(tile_coord)
        total_yield = self.rng.randint(definition.min_yield, definition.max_yield)
        self.resource_nodes.append(ResourceNode(self.main, definition, world_position, total_yield))
        used_tiles.append(tile_coord)
        return True

    def _structure_rect(self, position, definition: BuildDefinition) -> pygame.Rect:
        rect = pygame.Rect(0, 0, *_footprint_for_key(definition.key))
        rect.center = (int(position.x), int(position.y))
        return rect

    def _tile_coord(self, position) -> tuple[int, int]:
        pos = Vector2(position)
        return int(pos.x // self.world.tile_size), int(pos.y // self.world.tile_size)

    def _tile_center(self, tile_coord: tuple[int, int]) -> Vector2:
        grid_x, grid_y = tile_coord
        half = self.world.tile_size / 2
        return Vector2(grid_x * self.world.tile_size + half, grid_y * self.world.tile_size + half)

    def _snap_to_tile_center(self, world_position) -> Vector2:
        tile = self._tile_coord(world_position)
        return self._tile_center(tile)

    def _announce(self, text: str, accent=GOLD, duration: float = 2.0) -> None:
        if callable(self.announce_callback):
            self.announce_callback(text, accent=accent, duration=duration)