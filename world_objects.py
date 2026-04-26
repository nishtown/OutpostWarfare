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
from settings import DARK_BROWN, FONT_SMALL, GOLD, GREEN, LIGHT_GRAY, ORANGE, RED, TILE_SIZE, WHITE


BUILDING_SPRITE_PATHS = {
    "farm": ("assets", "buildings", "lumberyard", "4.png"),
    "lumberyard": ("assets", "buildings", "lumberyard", "4.png"),
}
WORKER_SPRITE_PATHS = [
    ("assets", "workers", f"characterBlue ({index}).png")
    for index in range(1, 6)
]
ARCHER_TOWER_STAGE_1_SHEET = ("assets", "buildings", "archertower", "2.png")
ARCHER_TOWER_STAGE_1_FRAME_INDEX = 1
ARCHER_TOWER_STAGE_FRAME_COUNT = 4
ARROW_TOWER_LEVEL_SHEETS = [
    ("assets", "buildings", "archertower", "2.png"),
    ("assets", "buildings", "archertower", "3.png"),
    ("assets", "buildings", "archertower", "4.png"),
]
RESOURCE_TERRAIN_RULES = {
    "tree": {"grass", "forest", "sand"},
    "rock": {"grass", "forest", "sand"},
    "gold": {"grass", "forest", "sand"},
}
STRUCTURE_RENDER_OFFSETS = {
    "arrow_tower": 24,
}
TOWER_UPGRADE_LEVELS = {
    "arrow_tower": (
        {
            "max_health": 150.0,
            "tower_range": TILE_SIZE * 3.7,
            "projectile_damage": 14.0,
            "projectile_speed": 340.0,
            "attack_cooldown": 0.85,
            "upgrade_cost": None,
        },
        {
            "max_health": 185.0,
            "tower_range": TILE_SIZE * 4.15,
            "projectile_damage": 20.0,
            "projectile_speed": 370.0,
            "attack_cooldown": 0.74,
            "upgrade_cost": {"wood": 55, "stone": 24},
        },
        {
            "max_health": 225.0,
            "tower_range": TILE_SIZE * 4.65,
            "projectile_damage": 27.0,
            "projectile_speed": 405.0,
            "attack_cooldown": 0.64,
            "upgrade_cost": {"wood": 72, "stone": 32, "gold": 20},
        },
    ),
}


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
    food_upkeep: int = 0
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
        target_priority=3, detour_radius=TILE_SIZE * 2.4, food_upkeep=1,
    ),
    "arrow_tower": BuildDefinition(
        "arrow_tower", "Arrow Tower", {"wood": 40, "stone": 18}, max_health=150.0, color=(120, 94, 52),
        target_priority=4, detour_radius=TILE_SIZE * 2.8,
        tower_range=TILE_SIZE * 3.7, projectile_damage=14.0, projectile_speed=340.0, attack_cooldown=0.85,
        food_upkeep=2,
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
        target_priority=2, detour_radius=TILE_SIZE * 2.0, food_upkeep=1,
    ),
    "workshop": BuildDefinition(
        "workshop", "Workshop", {"wood": 26, "stone": 24}, max_health=140.0, color=(126, 108, 54),
        target_priority=2, detour_radius=TILE_SIZE * 2.0, food_upkeep=1,
    ),
    "market": BuildDefinition(
        "market", "Market", {"wood": 24, "stone": 12}, max_health=125.0, color=(172, 146, 64),
        target_priority=2, detour_radius=TILE_SIZE * 2.0, food_upkeep=1,
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
    growth_duration: float = 0.0


RESOURCE_DEFINITIONS = {
    "tree": ResourceNodeDefinition("tree", "Tree", "wood", "Chopping tree", 2.2, 8, 14, growth_duration=18.0),
    "rock": ResourceNodeDefinition("rock", "Rock", "stone", "Mining rock", 2.9, 6, 11),
    "gold": ResourceNodeDefinition("gold", "Gold Vein", "gold", "Mining gold", 3.4, 12, 20),
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
    if building_key in {"farm", "lumberyard"}:
        return int(TILE_SIZE * 1.14), int(TILE_SIZE * 0.42)
    if building_key == "arrow_tower":
        return int(TILE_SIZE * 0.54), int(TILE_SIZE * 0.34)
    size = int(TILE_SIZE * 0.68)
    return size, size


class Structure(Entity):
    """One placed structure, wall, tower, or trap."""

    _BUILDING_SPRITE_CACHE: dict[str, pygame.Surface] = {}
    _WORKER_SPRITE_CACHE: list[pygame.Surface] = []
    _WORKER_RENDER_SIZE = (12, 18)
    _LUMBERYARD_WORKER_COUNT = 2
    _LUMBERYARD_HARVEST_RADIUS = TILE_SIZE * 4.0
    _LUMBERYARD_REPLANT_RADIUS = TILE_SIZE * 3.8
    _LUMBERYARD_TREE_TARGET = 6
    _LUMBERYARD_WORKER_SPEED = 58.0
    _LUMBERYARD_CHOP_TIME = 2.6
    _LUMBERYARD_DROP_TIME = 0.45
    _LUMBERYARD_PLANT_TIME = 1.2
    _FOOD_UPKEEP_INTERVAL = 12.0
    _FOOD_UPKEEP_RETRY_DELAY = 1.0
    _FARM_GROW_TIME = 24.0
    _FARM_READY_TIME = 3.0
    _FARM_FOOD_PER_PLOT = 2
    _FARM_PLOT_OFFSETS = (
        Vector2(-70, 22),
        Vector2(-35, 34),
        Vector2(0, 40),
        Vector2(35, 34),
        Vector2(70, 22),
    )

    def __init__(self, main, definition: BuildDefinition, position: Vector2) -> None:
        image = self._build_surface(definition, level=1)
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
        self.sprite_offset_y = STRUCTURE_RENDER_OFFSETS.get(definition.key, 0)

        self.max_health = definition.max_health
        self.health = definition.max_health
        self.blocks_movement = definition.blocks_movement
        self.enemy_targetable = True
        self.cooldown_remaining = 0.0
        self.armed = definition.is_trap
        self.revealed = not definition.hidden_to_enemy
        self.attack_radius = max(self.collision_size) / 2 + 8
        self.level = 1
        self.max_level = max(1, len(TOWER_UPGRADE_LEVELS.get(definition.key, ())))
        self.tower_range = definition.tower_range
        self.projectile_damage = definition.projectile_damage
        self.projectile_speed = definition.projectile_speed
        self.attack_cooldown = definition.attack_cooldown
        self.workers = self._create_workers() if definition.key == "lumberyard" else []
        self.farm_plots = self._create_farm_plots() if definition.key == "farm" else []
        self.is_operational = True
        self.food_upkeep_timer = self._FOOD_UPKEEP_INTERVAL
        self.food_consumed = 0
        self.food_produced = 0
        self.wood_delivered = 0
        self.trees_planted = 0
        self._apply_level_stats(reset_health=True)

    @property
    def is_detour_candidate(self) -> bool:
        return self.definition.detour_radius > 0.0 and self.definition.target_priority > 0

    @property
    def is_trap(self) -> bool:
        return self.definition.is_trap

    @property
    def is_upgradeable(self) -> bool:
        return self.definition.key in TOWER_UPGRADE_LEVELS and self.level < self.max_level

    def get_upgrade_cost(self) -> dict[str, int] | None:
        stages = TOWER_UPGRADE_LEVELS.get(self.definition.key)
        if not stages or self.level >= len(stages):
            return None
        return stages[self.level].get("upgrade_cost")

    def take_damage(self, amount: float) -> None:
        self.revealed = True
        self.health -= max(0.0, float(amount))
        if self.health <= 0.0:
            self.alive = False

    def upgrade(self) -> bool:
        if not self.is_upgradeable:
            return False

        current_ratio = 1.0 if self.max_health <= 0 else max(0.0, self.health / self.max_health)
        self.level += 1
        self._apply_level_stats(reset_health=False, current_ratio=current_ratio)
        return True

    def reveal(self) -> None:
        self.revealed = True

    def consume_trap(self) -> None:
        self.revealed = True
        self.armed = False
        self.alive = False

    def update(self, dt: float) -> None:
        if not self.alive:
            super().update(dt)
            return

        self.cooldown_remaining = max(0.0, self.cooldown_remaining - dt)

        self._update_food_upkeep(dt)

        if self.definition.key == "farm" and self.farm_plots:
            self._update_farm(dt)

        if self.definition.key == "lumberyard" and self.workers and self.is_operational:
            self._update_lumberyard(dt)

        super().update(dt)

    def draw(self, surface: pygame.Surface, camera=None, selected: bool = False) -> None:
        draw_image = self.image
        if self.is_trap and not self.revealed and (camera is None or getattr(camera, "name", "") != "minimap"):
            draw_image = self.image.copy()
            draw_image.set_alpha(150)

        if self.definition.key == "farm" and getattr(camera, "name", "") != "minimap":
            self._draw_farm_growth(surface, camera)

        if self.definition.key in {"farm", "lumberyard", "arrow_tower"}:
            draw_rect = self._sprite_draw_rect(camera)
            if draw_rect.width <= 0 or draw_rect.height <= 0:
                return
            if draw_rect.size != draw_image.get_size():
                draw_image = pygame.transform.smoothscale(draw_image, draw_rect.size)
            surface.blit(draw_image, draw_rect)
        elif camera is not None and hasattr(camera, "world_rect_to_screen"):
            draw_rect = camera.world_rect_to_screen(self.rect)
            if draw_rect.width <= 0 or draw_rect.height <= 0:
                return
            scaled = pygame.transform.smoothscale(draw_image, draw_rect.size)
            surface.blit(scaled, draw_rect)
        else:
            surface.blit(draw_image, self.rect)

        if self.definition.key == "lumberyard" and getattr(camera, "name", "") != "minimap":
            self._draw_workers(surface, camera)

        if getattr(camera, "name", "") != "minimap" and self.health < self.max_health:
            self._draw_health_bar(surface, camera)

        if selected and getattr(camera, "name", "") != "minimap":
            self._draw_selection_outline(surface, camera)

        if self.main.debug_mode and camera is not None and hasattr(camera, "world_rect_to_screen"):
            pygame.draw.rect(surface, RED, camera.world_rect_to_screen(self.get_collision_rect()), 1)

    def get_sprite_world_rect(self) -> pygame.Rect:
        draw_rect = self.image.get_rect()
        draw_rect.midbottom = (int(self.pos.x), int(self.pos.y + self.sprite_offset_y))
        return draw_rect

    def contains_world_point(self, world_position) -> bool:
        point = (int(world_position.x), int(world_position.y))
        if self.get_collision_rect().collidepoint(point):
            return True
        return self.get_sprite_world_rect().collidepoint(point)

    def should_draw_over(self, entity) -> bool:
        if entity is None or self.image.get_height() <= TILE_SIZE:
            return False

        entity_rect = entity.get_collision_rect()
        if not self.get_sprite_world_rect().colliderect(entity_rect):
            return False

        return entity_rect.bottom <= self.get_collision_rect().bottom

    def _world_objects(self):
        game = getattr(self.main, "game", None)
        if game is None:
            return None
        return getattr(game, "world_objects", None)

    def _player(self):
        game = getattr(self.main, "game", None)
        if game is None:
            return None
        return getattr(game, "player", None)

    @classmethod
    def _load_worker_surfaces(cls) -> list[pygame.Surface]:
        if cls._WORKER_SPRITE_CACHE:
            return cls._WORKER_SPRITE_CACHE

        for path_parts in WORKER_SPRITE_PATHS:
            image = Entity.load_image(
                *path_parts,
                fallback_size=cls._WORKER_RENDER_SIZE,
                fallback_color=(80, 150, 210),
            )
            image = pygame.transform.smoothscale(image, cls._WORKER_RENDER_SIZE)
            cls._WORKER_SPRITE_CACHE.append(image)

        return cls._WORKER_SPRITE_CACHE

    def _create_workers(self) -> list[dict]:
        worker_sprites = self._load_worker_surfaces()
        sprite_indices = list(range(len(worker_sprites)))
        random.shuffle(sprite_indices)

        workers: list[dict] = []
        for worker_index in range(self._LUMBERYARD_WORKER_COUNT):
            sprite = worker_sprites[sprite_indices[worker_index % len(sprite_indices)]].copy()
            workers.append(
                {
                    "pos": Vector2(self.pos),
                    "state": "idle",
                    "target": None,
                    "target_pos": None,
                    "timer": 0.0,
                    "base_sprite": sprite,
                    "flip_x": False,
                    "rotation_angle": 0.0,
                    "carrying_wood": 0,
                    "carrying_sapling": False,
                }
            )

        return workers

    def _update_lumberyard(self, dt: float) -> None:
        manager = self._world_objects()
        if manager is None:
            return

        for worker in self.workers:
            state = worker["state"]
            target = worker.get("target")

            if state == "idle":
                if worker["carrying_wood"] > 0:
                    worker["state"] = "returning"
                    continue

                tree_target = self._find_tree_target(manager)
                if tree_target is not None:
                    worker["target"] = tree_target
                    worker["state"] = "moving_to_tree"
                    continue

                plant_target = self._find_plant_target(manager)
                if plant_target is not None:
                    worker["target_pos"] = plant_target
                    worker["carrying_sapling"] = True
                    worker["state"] = "moving_to_plant_site"
                continue

            if state == "moving_to_tree":
                if target is None or not getattr(target, "alive", False):
                    worker["target"] = None
                    worker["state"] = "idle"
                    continue

                if self._move_worker_toward(worker, target.pos, dt):
                    worker["state"] = "chopping"
                    worker["timer"] = max(self._LUMBERYARD_CHOP_TIME, getattr(target, "action_duration", self._LUMBERYARD_CHOP_TIME))
                continue

            if state == "chopping":
                if target is None or not getattr(target, "alive", False):
                    worker["target"] = None
                    worker["state"] = "idle"
                    continue

                worker["timer"] -= dt
                if worker["timer"] <= 0.0:
                    harvest = target.harvest()
                    worker["carrying_wood"] = harvest.get("wood", 0)
                    worker["target"] = None
                    worker["state"] = "returning" if worker["carrying_wood"] > 0 else "idle"
                continue

            if state == "moving_to_plant_site":
                plant_target = worker.get("target_pos")
                if plant_target is None:
                    worker["carrying_sapling"] = False
                    worker["state"] = "idle"
                    continue

                if self._move_worker_toward(worker, plant_target, dt):
                    worker["state"] = "planting"
                    worker["timer"] = self._LUMBERYARD_PLANT_TIME
                continue

            if state == "planting":
                worker["timer"] -= dt
                if worker["timer"] <= 0.0:
                    planted = manager.spawn_resource_node(
                        "tree",
                        worker["target_pos"],
                        total_yield=manager.rng.randint(6, 10),
                        planted_by=self,
                    )
                    if planted is not None:
                        self.trees_planted += 1
                    worker["target_pos"] = None
                    worker["carrying_sapling"] = False
                    worker["state"] = "returning"
                continue

            if state == "returning":
                if self._move_worker_toward(worker, self.pos, dt):
                    worker["state"] = "dropping_off"
                    worker["timer"] = self._LUMBERYARD_DROP_TIME
                continue

            if state == "dropping_off":
                worker["timer"] -= dt
                if worker["timer"] <= 0.0:
                    self._deposit_worker_resources(worker)
                    worker["target"] = None
                    worker["target_pos"] = None
                    worker["carrying_sapling"] = False
                    worker["state"] = "idle"

    def _find_tree_target(self, manager):
        nearby_trees = manager.get_resource_nodes_in_radius(
            self.pos,
            self._LUMBERYARD_HARVEST_RADIUS,
            resource_key="tree",
        )
        reserved_targets = {
            worker["target"]
            for worker in self.workers
            if worker["state"] in {"moving_to_tree", "chopping"} and worker.get("target") is not None
        }

        available_trees = [tree for tree in nearby_trees if tree not in reserved_targets]
        available_trees = [tree for tree in available_trees if getattr(tree, "is_harvestable", True)]
        if not available_trees:
            return None

        return min(available_trees, key=lambda tree: tree.pos.distance_squared_to(self.pos))

    def _find_plant_target(self, manager) -> Vector2 | None:
        current_trees = manager.get_resource_nodes_in_radius(
            self.pos,
            self._LUMBERYARD_REPLANT_RADIUS,
            resource_key="tree",
        )
        pending_plants = [
            worker["target_pos"]
            for worker in self.workers
            if worker["state"] in {"moving_to_plant_site", "planting"} and worker.get("target_pos") is not None
        ]
        if len(current_trees) + len(pending_plants) >= self._LUMBERYARD_TREE_TARGET:
            return None

        for _ in range(18):
            angle = random.uniform(0.0, math.tau)
            radius = random.uniform(TILE_SIZE * 1.45, self._LUMBERYARD_REPLANT_RADIUS)
            candidate = self.pos + Vector2(math.cos(angle), math.sin(angle)) * radius
            snapped = manager._snap_to_tile_center(candidate)

            if any(Vector2(target_pos).distance_to(snapped) < TILE_SIZE for target_pos in pending_plants):
                continue
            if manager.can_spawn_resource_node("tree", snapped):
                return snapped

        return None

    def _move_worker_toward(self, worker: dict, destination, dt: float) -> bool:
        target_position = Vector2(destination)
        direction = target_position - worker["pos"]
        distance = direction.length()
        if distance <= 1.0:
            worker["pos"] = target_position
            return True

        if abs(direction.y) > abs(direction.x):
            worker["rotation_angle"] = -90 if direction.y < 0 else 90
            worker["flip_x"] = False
        else:
            worker["rotation_angle"] = 0.0
            worker["flip_x"] = direction.x < -0.5

        step = min(distance, self._LUMBERYARD_WORKER_SPEED * dt)
        worker["pos"] += direction.normalize() * step
        return step >= distance - 0.001

    def _deposit_worker_resources(self, worker: dict) -> None:
        player = self._player()
        carried_wood = int(worker.get("carrying_wood", 0))
        if player is not None and carried_wood > 0:
            player.add_resource("wood", carried_wood)
            self.wood_delivered += carried_wood
        worker["carrying_wood"] = 0

    def _draw_workers(self, surface: pygame.Surface, camera) -> None:
        for worker in self.workers:
            if worker["state"] == "idle" and worker["pos"].distance_squared_to(self.pos) < 4.0:
                continue

            draw_image = worker["base_sprite"]
            if worker.get("rotation_angle"):
                draw_image = pygame.transform.rotate(draw_image, worker["rotation_angle"])
            if worker.get("flip_x"):
                draw_image = pygame.transform.flip(draw_image, True, False)

            if camera is not None and hasattr(camera, "world_to_screen"):
                screen_pos = camera.world_to_screen(worker["pos"])
                draw_size = (
                    max(1, int(draw_image.get_width() * camera.scale_x)),
                    max(1, int(draw_image.get_height() * camera.scale_y)),
                )
                if draw_size != draw_image.get_size():
                    draw_image = pygame.transform.smoothscale(draw_image, draw_size)
                draw_rect = draw_image.get_rect(midbottom=(int(screen_pos.x), int(screen_pos.y)))
            else:
                draw_rect = draw_image.get_rect(midbottom=(int(worker["pos"].x), int(worker["pos"].y)))

            surface.blit(draw_image, draw_rect)

            if worker.get("carrying_wood", 0) > 0:
                pygame.draw.circle(surface, (130, 88, 46), (draw_rect.right - 4, draw_rect.top + 8), 4)
            elif worker.get("carrying_sapling"):
                pygame.draw.circle(surface, (62, 156, 70), (draw_rect.right - 4, draw_rect.top + 8), 4)

    def _sprite_draw_rect(self, camera=None) -> pygame.Rect:
        draw_anchor = Vector2(self.pos.x, self.pos.y + self.sprite_offset_y)
        if camera is not None and hasattr(camera, "world_to_screen"):
            screen_pos = camera.world_to_screen(draw_anchor)
            draw_size = (
                max(1, int(self.image.get_width() * camera.scale_x)),
                max(1, int(self.image.get_height() * camera.scale_y)),
            )
            draw_rect = pygame.Rect(0, 0, *draw_size)
            draw_rect.midbottom = (int(screen_pos.x), int(screen_pos.y))
            return draw_rect

        draw_rect = self.image.get_rect()
        draw_rect.midbottom = (int(draw_anchor.x), int(draw_anchor.y))
        return draw_rect

    def _update_food_upkeep(self, dt: float) -> None:
        if self.definition.food_upkeep <= 0:
            self.is_operational = True
            return

        self.food_upkeep_timer -= dt
        if self.food_upkeep_timer > 0.0:
            return

        player = self._player()
        upkeep_cost = {"food": self.definition.food_upkeep}
        if player is not None and player.consume_resources(upkeep_cost):
            self.food_upkeep_timer = self._FOOD_UPKEEP_INTERVAL
            self.food_consumed += self.definition.food_upkeep
            self.is_operational = True
            return

        self.food_upkeep_timer = self._FOOD_UPKEEP_RETRY_DELAY
        self.is_operational = False

    def _create_farm_plots(self) -> list[dict]:
        return [
            {
                "offset": Vector2(offset),
                "growth": random.uniform(0.15, 0.85),
                "ready_timer": 0.0,
            }
            for offset in self._FARM_PLOT_OFFSETS
        ]

    def _update_farm(self, dt: float) -> None:
        player = self._player()
        if player is None:
            return

        for plot in self.farm_plots:
            if plot["ready_timer"] > 0.0:
                plot["ready_timer"] = max(0.0, plot["ready_timer"] - dt)
                if plot["ready_timer"] <= 0.0:
                    player.add_resource("food", self._FARM_FOOD_PER_PLOT)
                    self.food_produced += self._FARM_FOOD_PER_PLOT
                    plot["growth"] = 0.0
                continue

            plot["growth"] = min(1.0, plot["growth"] + dt / self._FARM_GROW_TIME)
            if plot["growth"] >= 1.0:
                plot["ready_timer"] = self._FARM_READY_TIME

    def _draw_farm_growth(self, surface: pygame.Surface, camera) -> None:
        for plot in self.farm_plots:
            growth = max(0.0, min(1.0, float(plot.get("growth", 0.0))))
            ready = plot.get("ready_timer", 0.0) > 0.0
            world_pos = self.pos + plot["offset"]

            if camera is not None and hasattr(camera, "world_to_screen"):
                screen_pos = camera.world_to_screen(world_pos)
                scale_x = camera.scale_x
                scale_y = camera.scale_y
            else:
                screen_pos = world_pos
                scale_x = 1.0
                scale_y = 1.0

            patch_width = max(10, int(20 * scale_x))
            patch_height = max(5, int(10 * scale_y))
            soil_rect = pygame.Rect(0, 0, patch_width, patch_height)
            soil_rect.midbottom = (int(screen_pos.x), int(screen_pos.y))
            pygame.draw.ellipse(surface, (101, 69, 36), soil_rect)
            pygame.draw.ellipse(surface, (66, 44, 22), soil_rect, 1)

            stalk_count = max(1, 2 + int(growth * 4))
            stem_height = max(4, int((4 + growth * 11) * scale_y))
            stem_color = (86, 164, 72) if not ready else (176, 164, 70)
            grain_color = (128, 196, 84) if not ready else (224, 199, 92)

            for stalk_index in range(stalk_count):
                spread = 0 if stalk_count == 1 else stalk_index / (stalk_count - 1)
                stem_x = soil_rect.left + int(3 + spread * max(1, soil_rect.width - 6))
                top_y = soil_rect.top - stem_height
                pygame.draw.line(surface, stem_color, (stem_x, soil_rect.top + 1), (stem_x, top_y), 2)
                pygame.draw.circle(surface, grain_color, (stem_x, top_y), max(1, int(2 * scale_x)))

    def _draw_selection_outline(self, surface: pygame.Surface, camera) -> None:
        if camera is None or not hasattr(camera, "world_rect_to_screen"):
            return

        collision_rect = camera.world_rect_to_screen(self.get_collision_rect())
        outline_rect = collision_rect.inflate(10, 10)
        pygame.draw.ellipse(surface, GOLD, outline_rect, 2)

    def _apply_level_stats(self, reset_health: bool = False, current_ratio: float = 1.0) -> None:
        stage_data = self._get_level_data()
        if stage_data is None:
            self.max_health = self.definition.max_health
            self.tower_range = self.definition.tower_range
            self.projectile_damage = self.definition.projectile_damage
            self.projectile_speed = self.definition.projectile_speed
            self.attack_cooldown = self.definition.attack_cooldown
            if reset_health:
                self.health = self.max_health
            return

        self.max_health = float(stage_data["max_health"])
        self.tower_range = float(stage_data["tower_range"])
        self.projectile_damage = float(stage_data["projectile_damage"])
        self.projectile_speed = float(stage_data["projectile_speed"])
        self.attack_cooldown = float(stage_data["attack_cooldown"])
        if reset_health:
            self.health = self.max_health
        else:
            self.health = max(1.0, self.max_health * current_ratio)

        self.image = self._build_surface(self.definition, level=self.level)
        self.original_image = self.image.copy()
        self.rect = self.image.get_rect(center=(int(self.pos.x), int(self.pos.y)))

    def _get_level_data(self):
        stages = TOWER_UPGRADE_LEVELS.get(self.definition.key)
        if not stages:
            return None
        return stages[self.level - 1]

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
    def _build_surface(definition: BuildDefinition, level: int = 1) -> pygame.Surface:
        sprite_surface = Structure._load_building_sprite(definition, level=level)
        if sprite_surface is not None:
            return sprite_surface

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

        return surface

    @classmethod
    def _load_building_sprite(cls, definition: BuildDefinition, level: int = 1) -> pygame.Surface | None:
        cache_key = f"{definition.key}:{level}"
        if cache_key in cls._BUILDING_SPRITE_CACHE:
            return cls._BUILDING_SPRITE_CACHE[cache_key].copy()

        image = None
        if definition.key in BUILDING_SPRITE_PATHS:
            image = Entity.load_image(
                *BUILDING_SPRITE_PATHS[definition.key],
                fallback_size=(96, 96),
                fallback_color=definition.color,
            )
        elif definition.key == "arrow_tower":
            sheet = Entity.load_image(
                *ARROW_TOWER_LEVEL_SHEETS[max(0, min(level - 1, len(ARROW_TOWER_LEVEL_SHEETS) - 1))],
                fallback_size=(70 * ARCHER_TOWER_STAGE_FRAME_COUNT, 130),
                fallback_color=definition.color,
            )
            frame_width = max(1, sheet.get_width() // ARCHER_TOWER_STAGE_FRAME_COUNT)
            frame_rect = pygame.Rect(
                frame_width * ARCHER_TOWER_STAGE_1_FRAME_INDEX,
                0,
                frame_width,
                sheet.get_height(),
            )
            image = sheet.subsurface(frame_rect).copy()

        if image is None:
            return None

        cls._BUILDING_SPRITE_CACHE[cache_key] = image
        return image.copy()


class ResourceNode(Entity):
    """One harvestable tree or rock node."""

    def __init__(self, main, definition: ResourceNodeDefinition, position: Vector2, total_yield: int, planted_by=None) -> None:
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
        self.planted_by = planted_by
        self.is_planted = planted_by is not None
        self.growth_duration = float(definition.growth_duration) if self.is_planted else 0.0
        self.growth_elapsed = 0.0 if self.growth_duration > 0.0 else self.growth_duration

    @property
    def growth_ratio(self) -> float:
        if self.growth_duration <= 0.0:
            return 1.0
        return max(0.0, min(1.0, self.growth_elapsed / self.growth_duration))

    @property
    def is_harvestable(self) -> bool:
        return self.growth_ratio >= 0.999

    def update(self, dt: float) -> None:
        if self.growth_duration > 0.0 and self.growth_elapsed < self.growth_duration:
            self.growth_elapsed = min(self.growth_duration, self.growth_elapsed + dt)
        super().update(dt)

    def harvest(self) -> dict[str, int]:
        if not self.alive or self.remaining_yield <= 0 or not self.is_harvestable:
            return {}

        amount = min(2, self.remaining_yield)
        self.remaining_yield -= amount
        if self.remaining_yield <= 0:
            self.alive = False
        return {self.definition.resource_key: amount}

    def draw(self, surface: pygame.Surface, camera=None) -> None:
        if self.definition.key == "tree" and self.growth_ratio < 1.0:
            growth_scale = 0.35 + self.growth_ratio * 0.65
            draw_image = self.original_image.copy()
            draw_image.set_alpha(int(110 + self.growth_ratio * 145))

            if camera is not None and hasattr(camera, "world_to_screen"):
                screen_pos = camera.world_to_screen(self.pos)
                draw_size = (
                    max(1, int(draw_image.get_width() * camera.scale_x * growth_scale)),
                    max(1, int(draw_image.get_height() * camera.scale_y * growth_scale)),
                )
                draw_image = pygame.transform.smoothscale(draw_image, draw_size)
                draw_rect = draw_image.get_rect(midbottom=(int(screen_pos.x), int(screen_pos.y)))
            else:
                draw_size = (
                    max(1, int(draw_image.get_width() * growth_scale)),
                    max(1, int(draw_image.get_height() * growth_scale)),
                )
                draw_image = pygame.transform.smoothscale(draw_image, draw_size)
                draw_rect = draw_image.get_rect(midbottom=(int(self.pos.x), int(self.pos.y)))

            surface.blit(draw_image, draw_rect)
        else:
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
        elif definition.key == "gold":
            pygame.draw.polygon(surface, (126, 102, 34), [(12, 33), (18, 18), (30, 13), (36, 24), (31, 35), (18, 37)])
            pygame.draw.polygon(surface, (89, 71, 18), [(12, 33), (18, 18), (30, 13), (36, 24), (31, 35), (18, 37)], 2)
            pygame.draw.circle(surface, (230, 198, 82), (23, 22), 5)
            pygame.draw.circle(surface, (255, 232, 118), (26, 20), 3)
        else:
            pygame.draw.polygon(surface, (118, 118, 118), [(12, 33), (18, 18), (30, 13), (36, 24), (31, 35), (18, 37)])
            pygame.draw.polygon(surface, (86, 86, 86), [(12, 33), (18, 18), (30, 13), (36, 24), (31, 35), (18, 37)], 2)
            pygame.draw.circle(surface, (152, 152, 152), (23, 22), 4)

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
    _GOLD_CHANCE = 0.007
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
        for node in self.resource_nodes:
            node.update(dt)

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

    def draw(self, surface: pygame.Surface, camera, occlusion_target=None, selected_structure=None, overlay_pass: bool = False) -> None:
        if overlay_pass and occlusion_target is None:
            return

        if not overlay_pass:
            for node in self.resource_nodes:
                node.draw(surface, camera)

        for structure in self.structures:
            draw_over_target = occlusion_target is not None and structure.should_draw_over(occlusion_target)
            if overlay_pass != draw_over_target:
                continue

            structure.draw(surface, camera, selected=structure is selected_structure)

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

    def find_structure_at_world(self, world_position):
        point = Vector2(world_position)
        for structure in reversed(self.structures):
            if not structure.alive:
                continue
            if structure.contains_world_point(point):
                return structure
        return None

    def upgrade_structure(self, structure, player) -> tuple[bool, str]:
        if structure is None or not getattr(structure, "alive", False):
            return False, "Nothing selected"
        if not getattr(structure, "is_upgradeable", False):
            return False, "That tower is already maxed"

        upgrade_cost = structure.get_upgrade_cost() or {}
        if not player.consume_resources(upgrade_cost):
            return False, "Not enough resources"
        if not structure.upgrade():
            player.refund_resources(upgrade_cost)
            return False, "Upgrade failed"

        self._announce(f"{structure.definition.label} upgraded", accent=GREEN, duration=1.5)
        return True, structure.definition.label

    def find_harvest_target(self, clicked_world_pos, player_pos, max_range: float, click_radius: float = 48.0):
        clicked = Vector2(clicked_world_pos)
        player = Vector2(player_pos)
        best_node = None
        best_score = float("inf")

        for node in self.resource_nodes:
            if not getattr(node, "is_harvestable", True):
                continue
            clicked_distance = node.pos.distance_to(clicked)
            player_distance = node.pos.distance_to(player)
            if clicked_distance > click_radius or player_distance > max_range:
                continue

            score = clicked_distance * 0.8 + player_distance * 0.2
            if score < best_score:
                best_score = score
                best_node = node

        return best_node

    def get_resource_nodes_in_radius(self, world_position, radius: float, resource_key: str | None = None) -> list[ResourceNode]:
        origin = Vector2(world_position)
        nodes: list[ResourceNode] = []
        for node in self.resource_nodes:
            if not node.alive:
                continue
            if resource_key is not None and node.definition.key != resource_key:
                continue
            if node.pos.distance_to(origin) <= radius:
                nodes.append(node)
        return nodes

    def can_spawn_resource_node(self, resource_key: str, world_position, ignore_structure=None) -> bool:
        snapped = self._snap_to_tile_center(world_position)
        tile = self.world.get_tile_at_world(snapped.x, snapped.y)
        if tile is None or not tile.traversable:
            return False

        allowed_terrain = RESOURCE_TERRAIN_RULES.get(resource_key)
        if allowed_terrain is not None and tile.terrain_key not in allowed_terrain:
            return False

        target_tile = self._tile_coord(snapped)
        if any(
            math.dist(target_tile, self._tile_coord(node.pos)) < self._MIN_RESOURCE_TILE_SPACING
            for node in self.resource_nodes
            if node.alive
        ):
            return False

        for structure in self.structures:
            if not structure.alive or structure is ignore_structure:
                continue
            if structure.get_collision_rect().collidepoint(int(snapped.x), int(snapped.y)):
                return False

        return True

    def spawn_resource_node(self, resource_key: str, world_position, total_yield: int | None = None, planted_by=None, ignore_structure=None):
        if resource_key not in RESOURCE_DEFINITIONS:
            return None

        snapped = self._snap_to_tile_center(world_position)
        if not self.can_spawn_resource_node(resource_key, snapped, ignore_structure=ignore_structure):
            return None

        definition = RESOURCE_DEFINITIONS[resource_key]
        yield_amount = (
            int(total_yield)
            if total_yield is not None
            else self.rng.randint(definition.min_yield, definition.max_yield)
        )
        node = ResourceNode(self.main, definition, snapped, yield_amount, planted_by=planted_by)
        self.resource_nodes.append(node)
        return node

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
            if (
                not structure.alive
                or not getattr(structure, "is_operational", True)
                or structure.tower_range <= 0.0
                or structure.cooldown_remaining > 0.0
            ):
                continue

            candidates = [
                enemy for enemy in living_enemies
                if enemy.pos.distance_to(structure.pos) <= structure.tower_range
            ]
            if not candidates:
                continue

            target = min(candidates, key=lambda enemy: enemy.pos.distance_squared_to(structure.pos))
            self.projectiles.append(
                ArrowProjectile(structure.pos, target, structure.projectile_damage, structure.projectile_speed)
            )
            structure.cooldown_remaining = structure.attack_cooldown

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
                elif tile.terrain_key in {"sand", "grass", "forest"} and self.rng.random() < self._GOLD_CHANCE:
                    self._try_add_resource_node("gold", (grid_x, grid_y), used_tiles)

        self._seed_resources_near_base("tree", used_tiles, target_count=5)
        self._seed_resources_near_base("rock", used_tiles, target_count=3)
        self._seed_resources_near_base("gold", used_tiles, target_count=2)

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
                    if resource_key == "gold" and tile.terrain_key not in {"grass", "sand", "forest"}:
                        continue
                    if self._try_add_resource_node(resource_key, (grid_x, grid_y), used_tiles):
                        seeded += 1

    def _try_add_resource_node(self, resource_key: str, tile_coord: tuple[int, int], used_tiles) -> bool:
        if any(math.dist(tile_coord, other_tile) < self._MIN_RESOURCE_TILE_SPACING for other_tile in used_tiles):
            return False
        world_position = self._tile_center(tile_coord)
        node = self.spawn_resource_node(resource_key, world_position)
        if node is None:
            return False
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