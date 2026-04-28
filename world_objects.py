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
    "farm": ("assets", "buildings", "farm", "1.png"),
    "lumberyard": ("assets", "buildings", "lumberyard", "3.png"),
    "stone_quarry": ("assets", "buildings", "quarry", "2.png"),
    "gold_quarry": ("assets", "buildings", "goldmine", "4.png"),
    "main_base": ("assets", "buildings", "towncentre", "1.png"),
}
WORKER_VARIANTS = ("1", "3", "4")
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
    "farm": 24,
    "lumberyard": 24,
    "stone_quarry": 24,
    "gold_quarry": 24,
    "arrow_tower": 24,
    "bomb_tower": 24,
    "main_base": 24,
}
RESOURCE_CLUSTER_MAX = 5
TOWER_UPGRADE_LEVELS = {
    "arrow_tower": (
        {
            "max_health": 150.0,
            "tower_range": TILE_SIZE * 3.7,
            "projectile_damage": 18.0,
            "projectile_speed": 360.0,
            "attack_cooldown": 1.1,
            "upgrade_cost": None,
        },
        {
            "max_health": 185.0,
            "tower_range": TILE_SIZE * 4.15,
            "projectile_damage": 24.0,
            "projectile_speed": 390.0,
            "attack_cooldown": 0.96,
            "upgrade_cost": {"wood": 55, "stone": 24},
        },
        {
            "max_health": 225.0,
            "tower_range": TILE_SIZE * 4.65,
            "projectile_damage": 30.0,
            "projectile_speed": 420.0,
            "attack_cooldown": 0.84,
            "upgrade_cost": {"wood": 72, "stone": 32, "gold": 20},
        },
    ),
    "bomb_tower": (
        {
            "max_health": 170.0,
            "tower_range": TILE_SIZE * 4.5,
            "projectile_damage": 34.0,
            "projectile_speed": 220.0,
            "attack_cooldown": 2.8,
            "splash_radius": TILE_SIZE * 0.95,
            "upgrade_cost": None,
        },
        {
            "max_health": 205.0,
            "tower_range": TILE_SIZE * 5.0,
            "projectile_damage": 46.0,
            "projectile_speed": 235.0,
            "attack_cooldown": 2.45,
            "splash_radius": TILE_SIZE * 1.15,
            "upgrade_cost": {"wood": 62, "stone": 36, "gold": 16},
        },
        {
            "max_health": 248.0,
            "tower_range": TILE_SIZE * 5.55,
            "projectile_damage": 60.0,
            "projectile_speed": 250.0,
            "attack_cooldown": 2.1,
            "splash_radius": TILE_SIZE * 1.35,
            "upgrade_cost": {"wood": 84, "stone": 48, "gold": 28},
        },
    ),
}
STRUCTURE_UPGRADE_LEVELS = {
    **TOWER_UPGRADE_LEVELS,
    "farm": (
        {"max_health": 110.0, "worker_count": 1, "food_upkeep": 0, "upgrade_cost": None},
        {"max_health": 142.0, "worker_count": 2, "food_upkeep": 1, "upgrade_cost": {"wood": 36, "stone": 12}},
        {"max_health": 178.0, "worker_count": 3, "food_upkeep": 2, "upgrade_cost": {"wood": 50, "stone": 20, "gold": 8}},
    ),
    "lumberyard": (
        {"max_health": 130.0, "worker_count": 1, "food_upkeep": 1, "upgrade_cost": None},
        {"max_health": 165.0, "worker_count": 2, "food_upkeep": 2, "upgrade_cost": {"wood": 42, "stone": 18}},
        {"max_health": 205.0, "worker_count": 3, "food_upkeep": 3, "upgrade_cost": {"wood": 58, "stone": 26, "gold": 12}},
    ),
    "stone_quarry": (
        {"max_health": 140.0, "worker_count": 1, "food_upkeep": 1, "upgrade_cost": None},
        {"max_health": 180.0, "worker_count": 2, "food_upkeep": 2, "upgrade_cost": {"wood": 44, "stone": 22}},
        {"max_health": 224.0, "worker_count": 3, "food_upkeep": 3, "upgrade_cost": {"wood": 62, "stone": 30, "gold": 14}},
    ),
    "gold_quarry": (
        {"max_health": 145.0, "worker_count": 1, "food_upkeep": 1, "upgrade_cost": None},
        {"max_health": 188.0, "worker_count": 2, "food_upkeep": 2, "upgrade_cost": {"wood": 50, "stone": 24, "gold": 16}},
        {"max_health": 236.0, "worker_count": 3, "food_upkeep": 3, "upgrade_cost": {"wood": 68, "stone": 32, "gold": 28}},
    ),
    "main_base": (
        {"max_health": 560.0, "food_upkeep": 0, "upgrade_cost": None},
        {"max_health": 700.0, "food_upkeep": 1, "upgrade_cost": {"wood": 80, "stone": 50, "gold": 30}},
        {"max_health": 880.0, "food_upkeep": 2, "upgrade_cost": {"wood": 120, "stone": 76, "gold": 52}},
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
    build_time: float = 2.5
    blocks_movement: bool = True
    target_priority: int = 0
    detour_radius: float = 0.0
    tower_range: float = 0.0
    projectile_damage: float = 0.0
    projectile_speed: float = 0.0
    attack_cooldown: float = 0.0
    projectile_kind: str = "arrow"
    splash_radius: float = 0.0
    food_upkeep: int = 0
    worker_resource_key: str | None = None
    supports_regrowth: bool = False
    is_trap: bool = False
    trap_damage: float = 0.0
    hidden_to_enemy: bool = False

    @property
    def menu_cost(self) -> int:
        return sum(self.cost.values())


BUILD_DEFINITIONS = {
    "farm": BuildDefinition(
        "farm", "Farm", {"wood": 28}, max_health=110.0, color=(84, 156, 58), build_time=3.0,
        target_priority=2, detour_radius=TILE_SIZE * 2.2,
    ),
    "lumberyard": BuildDefinition(
        "lumberyard", "Lumber Mill", {"wood": 32, "stone": 10}, max_health=130.0, color=(97, 74, 44), build_time=4.2,
        target_priority=3, detour_radius=TILE_SIZE * 2.4, food_upkeep=1,
        worker_resource_key="tree", supports_regrowth=True,
    ),
    "stone_quarry": BuildDefinition(
        "stone_quarry", "Quarry", {"wood": 34, "stone": 14}, max_health=140.0, color=(118, 112, 104), build_time=4.6,
        target_priority=3, detour_radius=TILE_SIZE * 2.4, food_upkeep=1,
        worker_resource_key="rock",
    ),
    "gold_quarry": BuildDefinition(
        "gold_quarry", "Gold Mine", {"wood": 36, "stone": 18, "gold": 12}, max_health=145.0, color=(160, 138, 64), build_time=5.0,
        target_priority=3, detour_radius=TILE_SIZE * 2.4, food_upkeep=1,
        worker_resource_key="gold",
    ),
    "arrow_tower": BuildDefinition(
        "arrow_tower", "Arrow Tower", {"wood": 40, "stone": 18}, max_health=150.0, color=(120, 94, 52), build_time=4.0,
        target_priority=4, detour_radius=TILE_SIZE * 2.8,
        tower_range=TILE_SIZE * 3.7, projectile_damage=18.0, projectile_speed=360.0, attack_cooldown=1.1,
        food_upkeep=2,
    ),
    "bomb_tower": BuildDefinition(
        "bomb_tower", "Bomb Tower", {"wood": 52, "stone": 30, "gold": 12}, max_health=170.0, color=(134, 88, 48), build_time=5.0,
        target_priority=5, detour_radius=TILE_SIZE * 3.0,
        tower_range=TILE_SIZE * 4.5, projectile_damage=34.0, projectile_speed=220.0, attack_cooldown=2.8,
        projectile_kind="bomb", splash_radius=TILE_SIZE * 0.95, food_upkeep=3,
    ),
    "main_base": BuildDefinition(
        "main_base", "Town Centre", {}, max_health=560.0, color=(150, 126, 86), build_time=0.0,
        target_priority=8, detour_radius=TILE_SIZE * 3.2,
    ),
    "wall": BuildDefinition(
        "wall", "Wall", {"wood": 10, "stone": 20}, max_health=260.0, color=(126, 118, 104),
        target_priority=1,
    ),
    "spike_trap": BuildDefinition(
        "spike_trap", "Spike Trap", {"wood": 18, "stone": 6}, max_health=40.0, color=(96, 80, 56),
        blocks_movement=False, is_trap=True, trap_damage=36.0, hidden_to_enemy=True,
    ),
}

BUILD_MENU_ORDER = [
    "farm",
    "lumberyard",
    "stone_quarry",
    "gold_quarry",
    "arrow_tower",
    "bomb_tower",
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
    if building_key in {"farm", "lumberyard", "stone_quarry", "gold_quarry", "main_base"}:
        return int(TILE_SIZE * 1.14), int(TILE_SIZE * 0.42)
    if building_key in {"arrow_tower", "bomb_tower"}:
        return int(TILE_SIZE * 0.54), int(TILE_SIZE * 0.34)
    size = int(TILE_SIZE * 0.68)
    return size, size


class Structure(Entity):
    """One placed structure, wall, tower, or trap."""

    _BUILDING_SPRITE_CACHE: dict[str, pygame.Surface] = {}
    _BUILDING_COLLISION_CACHE: dict[str, pygame.Rect] = {}
    _BUILDING_SPRITE_SCALE = 0.75
    _WORKER_ANIMATION_CACHE: dict[tuple[str, str, str], tuple[pygame.Surface, ...]] = {}
    _WORKER_RENDER_SIZE = (48, 48)
    _WORKER_ANIMATION_DIRECTION_CODES = {
        "down": "D",
        "side": "S",
        "up": "U",
    }
    _WORKER_ANIMATION_ACTION_NAMES = {
        "idle": "Idle",
        "walk": "Walk",
        "special": "Special",
    }
    _WORKER_ANIMATION_FRAME_DURATIONS = {
        "idle": 0.18,
        "walk": 0.12,
        "special": 0.12,
    }
    _LUMBERYARD_WORKER_COUNT = 1
    _FARM_WORKER_COUNT = 1
    _LUMBERYARD_HARVEST_RADIUS = TILE_SIZE * 4.0
    _LUMBERYARD_REPLANT_RADIUS = TILE_SIZE * 3.8
    _LUMBERYARD_TREE_TARGET = 6
    _LUMBERYARD_WORKER_SPEED = 58.0
    _LUMBERYARD_CHOP_TIME = 2.6
    _LUMBERYARD_DROP_TIME = 0.45
    _LUMBERYARD_PLANT_TIME = 1.2
    _QUARRY_DIG_TIME = 8.0
    _FOOD_UPKEEP_INTERVAL = 12.0
    _FOOD_UPKEEP_RETRY_DELAY = 1.0
    _FARM_GROW_TIME = 24.0
    _FARM_READY_TIME = 3.0
    _FARM_FOOD_PER_PLOT = 2
    _FARM_PLOT_OFFSETS = (
        Vector2(-22, TILE_SIZE * 0.78),
        Vector2(0, TILE_SIZE * 0.74),
        Vector2(22, TILE_SIZE * 0.8),
        Vector2(-12, TILE_SIZE * 0.98),
        Vector2(12, TILE_SIZE * 1.02),
    )
    _QUARRY_PIT_OFFSETS = (
        Vector2(-18, TILE_SIZE * 0.76),
        Vector2(0, TILE_SIZE * 0.9),
        Vector2(18, TILE_SIZE * 1.04),
    )
    _WORKER_DOOR_OFFSET_Y = 24.0
    _WORKER_EXIT_OFFSET_Y = 54.0
    _WORKER_CARRY_COLORS = {
        "wood": (130, 88, 46),
        "stone": (122, 122, 122),
        "gold": (220, 188, 78),
        "sapling": (62, 156, 70),
    }

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
        self.sprite_offset_y = STRUCTURE_RENDER_OFFSETS.get(definition.key, 0)
        self.collision_mask_rect = self._get_collision_mask_local_rect(definition, level=1)
        if self.collision_mask_rect is not None:
            self.collision_size = self.collision_mask_rect.size
        else:
            self.collision_size = _footprint_for_key(definition.key)

        self.max_health = definition.max_health
        self.health = definition.max_health
        self.blocks_movement = definition.blocks_movement
        self.enemy_targetable = True
        self.cooldown_remaining = 0.0
        self.armed = definition.is_trap
        self.revealed = not definition.hidden_to_enemy
        self.attack_radius = max(self.collision_size) / 2 + 8
        self.level = 1
        self.max_level = max(1, len(STRUCTURE_UPGRADE_LEVELS.get(definition.key, ())))
        self.tower_range = definition.tower_range
        self.projectile_damage = definition.projectile_damage
        self.projectile_speed = definition.projectile_speed
        self.attack_cooldown = definition.attack_cooldown
        self.projectile_kind = definition.projectile_kind
        self.splash_radius = definition.splash_radius
        self.food_upkeep = definition.food_upkeep
        self.worker_resource_key = definition.worker_resource_key
        self.supports_regrowth = definition.supports_regrowth
        self.worker_count = self._default_worker_count() if self._uses_workers() else 0
        self.workers = self._create_workers(count=self.worker_count) if self._uses_workers() else []
        self.farm_plots = self._create_farm_plots() if definition.key == "farm" else []
        self.quarry_pits = self._create_quarry_pits() if self.definition.key in {"stone_quarry", "gold_quarry"} else []
        self.is_operational = True
        self.food_upkeep_timer = self._FOOD_UPKEEP_INTERVAL
        self.food_consumed = 0
        self.food_produced = 0
        self.wood_delivered = 0
        self.stone_delivered = 0
        self.gold_delivered = 0
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
        return self.definition.key in STRUCTURE_UPGRADE_LEVELS and self.level < self.max_level

    @property
    def is_repairable(self) -> bool:
        return self.definition.key == "arrow_tower" and self.health < self.max_health - 0.01

    def get_upgrade_cost(self) -> dict[str, int] | None:
        stages = STRUCTURE_UPGRADE_LEVELS.get(self.definition.key)
        if not stages or self.level >= len(stages):
            return None
        return stages[self.level].get("upgrade_cost")

    def get_repair_cost(self) -> dict[str, int] | None:
        if not self.is_repairable or self.max_health <= 0.0:
            return None

        missing_ratio = max(0.0, min(1.0, 1.0 - (self.health / self.max_health)))
        if missing_ratio <= 0.01:
            return None

        repair_cost: dict[str, int] = {}
        for resource_key, amount in self.definition.cost.items():
            scaled_amount = int(math.ceil(amount * missing_ratio * 0.55))
            if scaled_amount > 0:
                repair_cost[resource_key] = scaled_amount
        return repair_cost or None

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

    def repair(self) -> bool:
        if not self.is_repairable:
            return False

        self.health = self.max_health
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
            if self.workers:
                self._update_farm_workers(dt)

        if self.workers and self.definition.key != "farm" and self.is_operational:
            self._update_resource_hub(dt)

        super().update(dt)

    def draw(self, surface: pygame.Surface, camera=None, selected: bool = False) -> None:
        draw_image = self.image
        if self.is_trap and not self.revealed and (camera is None or getattr(camera, "name", "") != "minimap"):
            draw_image = self.image.copy()
            draw_image.set_alpha(150)

        if self.workers and getattr(camera, "name", "") != "minimap":
            self._draw_workers(surface, camera, behind_sprite=True)

        if self.definition.key in {"farm", "lumberyard", "stone_quarry", "gold_quarry", "main_base", "arrow_tower"}:
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

        if self.definition.key == "farm" and getattr(camera, "name", "") != "minimap":
            self._draw_farm_growth(surface, camera)
        elif self.definition.key in {"stone_quarry", "gold_quarry"} and getattr(camera, "name", "") != "minimap":
            self._draw_quarry_pits(surface, camera)

        if self.workers and getattr(camera, "name", "") != "minimap":
            self._draw_workers(surface, camera, behind_sprite=False)

        if getattr(camera, "name", "") != "minimap" and self.health < self.max_health:
            self._draw_health_bar(surface, camera)

        if selected and getattr(camera, "name", "") != "minimap":
            self._draw_selection_outline(surface, camera)

        if self.main.debug_mode and camera is not None and hasattr(camera, "world_rect_to_screen"):
            pygame.draw.rect(surface, RED, camera.world_rect_to_screen(self.get_collision_rect()), 1)

    def get_sprite_world_rect(self) -> pygame.Rect:
        return self._sprite_world_rect_for_position(self.pos)

    def get_depth_sort_bottom(self) -> int:
        return self.get_collision_rect().bottom

    def get_collision_rect(self, pos=None) -> pygame.Rect:
        position = Vector2(pos) if pos is not None else self.pos
        if self.collision_mask_rect is not None:
            sprite_rect = self._sprite_world_rect_for_position(position)
            return self.collision_mask_rect.move(sprite_rect.x, sprite_rect.y)
        return super().get_collision_rect(position)

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

    def _uses_workers(self) -> bool:
        return self.worker_resource_key is not None or self.definition.key == "farm"

    def _sprite_world_rect_for_position(self, position) -> pygame.Rect:
        draw_rect = self.image.get_rect()
        draw_rect.midbottom = (int(position.x), int(position.y + self.sprite_offset_y))
        return draw_rect

    def get_worker_door_position(self) -> Vector2:
        door_offset = self.sprite_offset_y if self.sprite_offset_y > 0 else self._WORKER_DOOR_OFFSET_Y
        return Vector2(self.pos.x, self.pos.y + min(door_offset, self._WORKER_DOOR_OFFSET_Y))

    def get_worker_exit_position(self) -> Vector2:
        return Vector2(self.pos.x, self.get_worker_door_position().y + self._WORKER_EXIT_OFFSET_Y)

    @classmethod
    def _load_worker_frames(cls, variant: str, direction: str, action: str) -> tuple[pygame.Surface, ...]:
        cache_key = (variant, direction, action)
        if cache_key in cls._WORKER_ANIMATION_CACHE:
            return cls._WORKER_ANIMATION_CACHE[cache_key]

        direction_code = cls._WORKER_ANIMATION_DIRECTION_CODES[direction]
        action_name = cls._WORKER_ANIMATION_ACTION_NAMES[action]
        sheet = Entity.load_image(
            "assets", "workers", variant, f"{direction_code}_{action_name}.png",
            fallback_size=(48 * 4, 48),
            fallback_color=(80, 150, 210),
        )
        frame_count = max(1, sheet.get_width() // max(1, sheet.get_height()))
        frame_width = max(1, sheet.get_width() // frame_count)

        frames = []
        for frame_index in range(frame_count):
            frame_rect = pygame.Rect(frame_index * frame_width, 0, frame_width, sheet.get_height())
            frame = sheet.subsurface(frame_rect).copy()
            if frame.get_size() != cls._WORKER_RENDER_SIZE:
                frame = pygame.transform.smoothscale(frame, cls._WORKER_RENDER_SIZE)
            frames.append(frame)

        cls._WORKER_ANIMATION_CACHE[cache_key] = tuple(frames)
        return cls._WORKER_ANIMATION_CACHE[cache_key]

    def _default_worker_count(self) -> int:
        return self._FARM_WORKER_COUNT if self.definition.key == "farm" else self._LUMBERYARD_WORKER_COUNT

    def _create_workers(self, count: int | None = None) -> list[dict]:
        worker_variants = list(WORKER_VARIANTS)
        random.shuffle(worker_variants)

        worker_count = int(count if count is not None else self._default_worker_count())

        workers: list[dict] = []
        for worker_index in range(worker_count):
            variant = worker_variants[worker_index % len(worker_variants)]
            sprite = self._load_worker_frames(variant, "down", "idle")[0].copy()
            workers.append(
                {
                    "pos": Vector2(self.pos),
                    "state": "idle",
                    "target": None,
                    "target_pos": None,
                    "timer": 0.0,
                    "variant": variant,
                    "base_sprite": sprite,
                    "animation_direction": "down",
                    "animation_action": "idle",
                    "animation_frame_index": 0,
                    "animation_timer": 0.0,
                    "flip_x": False,
                    "carrying_amount": 0,
                    "carrying_resource": None,
                    "carrying_sapling": False,
                    "route": [],
                }
            )

        return workers

    def _set_worker_route(self, worker: dict, waypoints) -> None:
        worker["route"] = [Vector2(point) for point in waypoints]

    def _follow_worker_route(self, worker: dict, dt: float) -> bool:
        route = worker.get("route", [])
        if not route:
            return True

        if self._move_worker_toward(worker, route[0], dt):
            route.pop(0)

        return not route

    def _begin_worker_departure(self, worker: dict, destination) -> None:
        self._set_worker_route(
            worker,
            (self.get_worker_door_position(), self.get_worker_exit_position(), Vector2(destination)),
        )

    def _begin_worker_return(self, worker: dict) -> None:
        worker["state"] = "returning"
        self._set_worker_route(
            worker,
            (self.get_worker_exit_position(), self.get_worker_door_position(), self.pos),
        )

    def _finish_worker_return(self, worker: dict) -> None:
        if worker.get("carrying_amount", 0) > 0:
            worker["state"] = "dropping_off"
            worker["timer"] = self._LUMBERYARD_DROP_TIME
            return

        worker["target"] = None
        worker["target_pos"] = None
        worker["carrying_sapling"] = False
        worker["state"] = "idle"

    def _update_resource_hub(self, dt: float) -> None:
        manager = self._world_objects()
        if manager is None:
            return

        for worker in self.workers:
            self._advance_worker_animation(worker, dt)
            state = worker["state"]
            target = worker.get("target")

            if state == "idle":
                if worker["carrying_amount"] > 0:
                    worker["state"] = "returning"
                    continue

                resource_target = self._find_resource_target(manager)
                if resource_target is not None:
                    worker["target"] = resource_target
                    self._begin_worker_departure(worker, resource_target.pos)
                    worker["state"] = "moving_to_resource"
                    continue

                if self.supports_regrowth:
                    plant_target = self._find_plant_target(manager)
                    if plant_target is not None:
                        worker["target_pos"] = plant_target
                        worker["carrying_sapling"] = True
                        self._begin_worker_departure(worker, plant_target)
                        worker["state"] = "moving_to_plant_site"
                        continue

                if self.definition.key in {"stone_quarry", "gold_quarry"}:
                    dig_target = self._find_quarry_dig_target()
                    if dig_target is not None:
                        worker["target_pos"] = dig_target
                        self._begin_worker_departure(worker, dig_target)
                        worker["state"] = "moving_to_dig_site"
                continue

            if state == "moving_to_resource":
                if target is None or not getattr(target, "alive", False):
                    worker["target"] = None
                    worker["state"] = "idle"
                    worker["route"] = []
                    continue

                if self._follow_worker_route(worker, dt):
                    worker["state"] = "harvesting"
                    worker["timer"] = max(self._LUMBERYARD_CHOP_TIME, getattr(target, "action_duration", self._LUMBERYARD_CHOP_TIME))
                continue

            if state == "harvesting":
                if target is None or not getattr(target, "alive", False):
                    worker["target"] = None
                    worker["state"] = "idle"
                    continue

                worker["timer"] -= dt
                if worker["timer"] <= 0.0:
                    harvest = target.harvest()
                    carried_resource = target.definition.resource_key
                    worker["carrying_amount"] = harvest.get(carried_resource, 0)
                    worker["carrying_resource"] = carried_resource if worker["carrying_amount"] > 0 else None
                    worker["target"] = None
                    worker["state"] = "returning" if worker["carrying_amount"] > 0 else "idle"
                continue

            if state == "moving_to_plant_site":
                plant_target = worker.get("target_pos")
                if plant_target is None:
                    worker["carrying_sapling"] = False
                    worker["state"] = "idle"
                    worker["route"] = []
                    continue

                if self._follow_worker_route(worker, dt):
                    worker["state"] = "planting"
                    worker["timer"] = self._LUMBERYARD_PLANT_TIME
                continue

            if state == "moving_to_dig_site":
                dig_target = worker.get("target_pos")
                if dig_target is None:
                    worker["state"] = "idle"
                    worker["route"] = []
                    continue

                if self._follow_worker_route(worker, dt):
                    worker["state"] = "digging"
                    worker["timer"] = self._get_quarry_dig_duration()
                continue

            if state == "planting":
                worker["timer"] -= dt
                if worker["timer"] <= 0.0:
                    clump_count = manager.rng.randint(1, RESOURCE_CLUSTER_MAX)
                    planted = manager.spawn_resource_node(
                        "tree",
                        worker["target_pos"],
                        total_yield=manager.rng.randint(6, 10) * clump_count,
                        planted_by=self,
                        cluster_count=clump_count,
                    )
                    if planted is not None:
                        self.trees_planted += 1
                    worker["target_pos"] = None
                    worker["carrying_sapling"] = False
                    self._begin_worker_return(worker)
                continue

            if state == "digging":
                worker["timer"] -= dt
                if worker["timer"] <= 0.0:
                    carried_resource = self._get_worker_inventory_resource_key()
                    worker["carrying_amount"] = 1 if carried_resource is not None else 0
                    worker["carrying_resource"] = carried_resource if worker["carrying_amount"] > 0 else None
                    worker["target_pos"] = None
                    if worker["carrying_amount"] > 0:
                        self._begin_worker_return(worker)
                    else:
                        worker["state"] = "idle"
                continue

            if state == "returning":
                if self._follow_worker_route(worker, dt):
                    self._finish_worker_return(worker)
                continue

            if state == "dropping_off":
                worker["timer"] -= dt
                if worker["timer"] <= 0.0:
                    self._deposit_worker_resources(worker)
                    worker["target"] = None
                    worker["target_pos"] = None
                    worker["carrying_sapling"] = False
                    worker["route"] = []
                    worker["state"] = "idle"

    def _find_farm_plot_target(self) -> Vector2 | None:
        reserved_targets = {
            tuple(worker["target_pos"])
            for worker in self.workers
            if worker["state"] in {"moving_to_plot", "tending_plot"} and worker.get("target_pos") is not None
        }

        available_plots = [
            self.pos + plot["offset"]
            for plot in self.farm_plots
            if tuple(self.pos + plot["offset"]) not in reserved_targets
        ]
        if not available_plots:
            return None

        return random.choice(available_plots)

    def _find_quarry_dig_target(self) -> Vector2 | None:
        reserved_targets = {
            tuple(worker["target_pos"])
            for worker in self.workers
            if worker["state"] in {"moving_to_dig_site", "digging"} and worker.get("target_pos") is not None
        }

        available_targets = [
            self.pos + pit["offset"]
            for pit in self.quarry_pits
            if tuple(self.pos + pit["offset"]) not in reserved_targets
        ]
        if not available_targets:
            return None

        return random.choice(available_targets)

    def _get_worker_inventory_resource_key(self) -> str | None:
        if self.worker_resource_key == "tree":
            return "wood"
        if self.worker_resource_key == "rock":
            return "stone"
        if self.worker_resource_key == "gold":
            return "gold"
        return None

    def _get_quarry_dig_duration(self) -> float:
        if self.definition.key == "gold_quarry":
            return self._QUARRY_DIG_TIME * 1.35
        return self._QUARRY_DIG_TIME

    def _update_farm_workers(self, dt: float) -> None:
        for worker in self.workers:
            self._advance_worker_animation(worker, dt)
            state = worker["state"]

            if state == "idle":
                plot_target = self._find_farm_plot_target()
                if plot_target is None:
                    continue

                worker["target_pos"] = Vector2(plot_target)
                self._begin_worker_departure(worker, plot_target)
                worker["state"] = "moving_to_plot"
                continue

            if state == "moving_to_plot":
                if self._follow_worker_route(worker, dt):
                    worker["state"] = "tending_plot"
                    worker["timer"] = random.uniform(1.6, 3.4)
                continue

            if state == "tending_plot":
                worker["timer"] -= dt
                if worker["timer"] <= 0.0:
                    worker["target_pos"] = None
                    self._begin_worker_return(worker)
                continue

            if state == "returning":
                if self._follow_worker_route(worker, dt):
                    self._finish_worker_return(worker)
                continue

    def _find_resource_target(self, manager):
        if self.worker_resource_key is None:
            return None

        nearby_nodes = manager.get_resource_nodes_in_radius(
            self.pos,
            self._LUMBERYARD_HARVEST_RADIUS,
            resource_key=self.worker_resource_key,
        )
        reserved_targets = {
            worker["target"]
            for worker in self.workers
            if worker["state"] in {"moving_to_resource", "harvesting"} and worker.get("target") is not None
        }

        available_nodes = [node for node in nearby_nodes if node not in reserved_targets]
        available_nodes = [node for node in available_nodes if getattr(node, "is_harvestable", True)]
        if not available_nodes:
            return None

        return min(available_nodes, key=lambda node: node.pos.distance_squared_to(self.pos))

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
            worker["animation_direction"] = "up" if direction.y < 0 else "down"
            worker["flip_x"] = False
        else:
            worker["animation_direction"] = "side"
            worker["flip_x"] = direction.x > 0.5

        step = min(distance, self._LUMBERYARD_WORKER_SPEED * dt)
        worker["pos"] += direction.normalize() * step
        return step >= distance - 0.001

    def _deposit_worker_resources(self, worker: dict) -> None:
        player = self._player()
        carried_amount = int(worker.get("carrying_amount", 0))
        carried_resource = worker.get("carrying_resource")
        if player is not None and carried_amount > 0 and carried_resource is not None:
            player.add_resource(carried_resource, carried_amount)
            if carried_resource == "wood":
                self.wood_delivered += carried_amount
            elif carried_resource == "stone":
                self.stone_delivered += carried_amount
            elif carried_resource == "gold":
                self.gold_delivered += carried_amount
        worker["carrying_amount"] = 0
        worker["carrying_resource"] = None

    def _draw_workers(self, surface: pygame.Surface, camera, behind_sprite: bool) -> None:
        for worker in self.workers:
            if worker["state"] == "idle" and worker["pos"].distance_squared_to(self.pos) < 4.0:
                continue

            if self._worker_should_draw_behind(worker) != behind_sprite:
                continue

            draw_image = worker["base_sprite"]
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

            carrying_resource = worker.get("carrying_resource")
            if worker.get("carrying_amount", 0) > 0 and carrying_resource is not None:
                indicator_color = self._WORKER_CARRY_COLORS.get(carrying_resource, WHITE)
                pygame.draw.circle(surface, indicator_color, (draw_rect.right - 4, draw_rect.top + 8), 4)
            elif worker.get("carrying_sapling"):
                pygame.draw.circle(surface, self._WORKER_CARRY_COLORS["sapling"], (draw_rect.right - 4, draw_rect.top + 8), 4)

    def _advance_worker_animation(self, worker: dict, dt: float) -> None:
        state = worker.get("state", "idle")
        if state in {"moving_to_resource", "moving_to_plant_site", "moving_to_dig_site", "moving_to_plot", "returning"}:
            action = "walk"
        elif state in {"harvesting", "planting", "digging", "tending_plot", "dropping_off"}:
            action = "special"
        else:
            action = "idle"

        direction = worker.get("animation_direction", "down")
        frames = self._load_worker_frames(worker.get("variant", "1"), direction, action)

        if worker.get("animation_action") != action:
            worker["animation_action"] = action
            worker["animation_frame_index"] = 0
            worker["animation_timer"] = 0.0

        frame_duration = self._WORKER_ANIMATION_FRAME_DURATIONS[action]
        worker["animation_timer"] += dt
        while worker["animation_timer"] >= frame_duration and len(frames) > 1:
            worker["animation_timer"] -= frame_duration
            worker["animation_frame_index"] = (worker["animation_frame_index"] + 1) % len(frames)

        worker["base_sprite"] = frames[worker["animation_frame_index"]]

    def _worker_should_draw_behind(self, worker: dict) -> bool:
        if self.image.get_height() <= TILE_SIZE:
            return False

        worker_rect = pygame.Rect(0, 0, self._WORKER_RENDER_SIZE[0], self._WORKER_RENDER_SIZE[1])
        worker_rect.midbottom = (int(worker["pos"].x), int(worker["pos"].y))
        if not self.get_sprite_world_rect().colliderect(worker_rect):
            return False

        return worker_rect.bottom <= self.get_collision_rect().bottom

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
        if self.food_upkeep <= 0:
            self.is_operational = True
            return

        self.food_upkeep_timer -= dt
        if self.food_upkeep_timer > 0.0:
            return

        player = self._player()
        upkeep_cost = {"food": self.food_upkeep}
        if player is not None and player.consume_resources(upkeep_cost):
            self.food_upkeep_timer = self._FOOD_UPKEEP_INTERVAL
            self.food_consumed += self.food_upkeep
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

    def _create_quarry_pits(self) -> list[dict]:
        return [
            {
                "offset": Vector2(offset),
                "radius_scale": random.uniform(0.8, 1.15),
            }
            for offset in self._QUARRY_PIT_OFFSETS
        ]

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

    def _draw_quarry_pits(self, surface: pygame.Surface, camera) -> None:
        spoil_color = (96, 88, 78) if self.definition.key == "stone_quarry" else (124, 104, 48)
        core_color = (38, 28, 24) if self.definition.key == "stone_quarry" else (58, 42, 18)
        accent_color = (146, 146, 146) if self.definition.key == "stone_quarry" else (216, 186, 74)

        for pit in self.quarry_pits:
            world_pos = self.pos + pit["offset"]
            if camera is not None and hasattr(camera, "world_to_screen"):
                screen_pos = camera.world_to_screen(world_pos)
                scale_x = camera.scale_x
                scale_y = camera.scale_y
            else:
                screen_pos = world_pos
                scale_x = 1.0
                scale_y = 1.0

            radius_scale = float(pit.get("radius_scale", 1.0))
            outer_w = max(12, int(22 * scale_x * radius_scale))
            outer_h = max(6, int(11 * scale_y * radius_scale))
            inner_w = max(8, int(14 * scale_x * radius_scale))
            inner_h = max(3, int(6 * scale_y * radius_scale))

            outer_rect = pygame.Rect(0, 0, outer_w, outer_h)
            outer_rect.midbottom = (int(screen_pos.x), int(screen_pos.y))
            inner_rect = pygame.Rect(0, 0, inner_w, inner_h)
            inner_rect.midbottom = (int(screen_pos.x), int(screen_pos.y + max(1, int(1.5 * scale_y))))

            pygame.draw.ellipse(surface, spoil_color, outer_rect)
            pygame.draw.ellipse(surface, core_color, inner_rect)
            pygame.draw.ellipse(surface, DARK_BROWN, outer_rect, 1)
            pygame.draw.circle(surface, accent_color, (outer_rect.centerx - outer_rect.width // 5, outer_rect.centery - 1), max(1, int(2 * scale_x)))

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
            self.projectile_kind = self.definition.projectile_kind
            self.splash_radius = self.definition.splash_radius
            self.food_upkeep = self.definition.food_upkeep
            if reset_health:
                self.health = self.max_health
            return

        self.max_health = float(stage_data.get("max_health", self.definition.max_health))
        self.tower_range = float(stage_data.get("tower_range", self.definition.tower_range))
        self.projectile_damage = float(stage_data.get("projectile_damage", self.definition.projectile_damage))
        self.projectile_speed = float(stage_data.get("projectile_speed", self.definition.projectile_speed))
        self.attack_cooldown = float(stage_data.get("attack_cooldown", self.definition.attack_cooldown))
        self.projectile_kind = str(stage_data.get("projectile_kind", self.definition.projectile_kind))
        self.splash_radius = float(stage_data.get("splash_radius", self.definition.splash_radius))
        self.food_upkeep = int(stage_data.get("food_upkeep", self.definition.food_upkeep))
        if self._uses_workers():
            self.worker_count = int(stage_data.get("worker_count", self._default_worker_count()))
            self.workers = self._create_workers(count=self.worker_count)
        if reset_health:
            self.health = self.max_health
        else:
            self.health = max(1.0, self.max_health * current_ratio)

        self.image = self._build_surface(self.definition, level=self.level)
        self.original_image = self.image.copy()
        self.collision_mask_rect = self._get_collision_mask_local_rect(self.definition, level=self.level)
        if self.collision_mask_rect is not None:
            self.collision_size = self.collision_mask_rect.size
        else:
            self.collision_size = _footprint_for_key(self.definition.key)
        self.rect = self.image.get_rect(center=(int(self.pos.x), int(self.pos.y)))

    def _get_level_data(self):
        stages = STRUCTURE_UPGRADE_LEVELS.get(self.definition.key)
        if not stages:
            return None
        return stages[self.level - 1]

    def _draw_health_bar(self, surface: pygame.Surface, camera) -> None:
        if camera is None or not hasattr(camera, "world_to_screen"):
            return
        screen_pos = camera.world_to_screen(Vector2(self.pos.x, self.pos.y + self.sprite_offset_y))
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
        elif definition.key == "bomb_tower":
            pygame.draw.rect(surface, (104, 80, 50), (15, 14, 18, 22))
            pygame.draw.rect(surface, accent, (11, 8, 26, 8))
            for battlement_x in range(12, 36, 6):
                pygame.draw.rect(surface, accent, (battlement_x, 4, 4, 4))
            pygame.draw.line(surface, (76, 56, 40), (22, 18), (35, 12), 4)
            pygame.draw.circle(surface, (42, 38, 34), (37, 11), 4)
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

        scaled_size = (
            max(1, int(round(image.get_width() * cls._BUILDING_SPRITE_SCALE))),
            max(1, int(round(image.get_height() * cls._BUILDING_SPRITE_SCALE))),
        )
        if scaled_size != image.get_size():
            image = pygame.transform.smoothscale(image, scaled_size)

        cls._BUILDING_SPRITE_CACHE[cache_key] = image
        return image.copy()

    @classmethod
    def _get_collision_mask_local_rect(cls, definition: BuildDefinition, level: int = 1) -> pygame.Rect | None:
        if definition.key in {"wall", "spike_trap"}:
            return None

        cache_key = f"{definition.key}:{level}:collision"
        if cache_key in cls._BUILDING_COLLISION_CACHE:
            return cls._BUILDING_COLLISION_CACHE[cache_key].copy()

        image = cls._load_building_sprite(definition, level=level)
        if image is None:
            return None

        opaque_bounds = image.get_bounding_rect(min_alpha=1)
        if opaque_bounds.width <= 0 or opaque_bounds.height <= 0:
            return None

        mask_fraction = 0.75 if definition.key == "arrow_tower" else 0.2
        lower_band_height = max(1, math.ceil(opaque_bounds.height * mask_fraction))
        lower_band = pygame.Rect(
            opaque_bounds.x,
            opaque_bounds.bottom - lower_band_height,
            opaque_bounds.width,
            lower_band_height,
        )
        lower_band_surface = image.subsurface(lower_band).copy()
        lower_band_bounds = lower_band_surface.get_bounding_rect(min_alpha=1)
        if lower_band_bounds.width <= 0 or lower_band_bounds.height <= 0:
            collision_rect = pygame.Rect(opaque_bounds)
        else:
            collision_rect = lower_band_bounds.move(lower_band.topleft)

        cls._BUILDING_COLLISION_CACHE[cache_key] = collision_rect.copy()
        return collision_rect.copy()

    @classmethod
    def get_preview_collision_rect(cls, definition: BuildDefinition, position, level: int = 1) -> pygame.Rect:
        local_collision_rect = cls._get_collision_mask_local_rect(definition, level=level)
        if local_collision_rect is None:
            rect = pygame.Rect(0, 0, *_footprint_for_key(definition.key))
            rect.center = (int(position.x), int(position.y))
            return rect

        preview_image = cls._load_building_sprite(definition, level=level)
        draw_rect = preview_image.get_rect()
        draw_rect.midbottom = (
            int(position.x),
            int(position.y + STRUCTURE_RENDER_OFFSETS.get(definition.key, 0)),
        )
        return local_collision_rect.move(draw_rect.x, draw_rect.y)


class ResourceNode(Entity):
    """One harvestable tree or rock node."""

    _ROCK_SPRITE_CACHE: dict[tuple[str, int], pygame.Surface] = {}
    _CLUSTER_LAYOUTS = {
        1: (Vector2(0, 0),),
        2: (Vector2(-10, 2), Vector2(10, -1)),
        3: (Vector2(-12, 3), Vector2(12, 1), Vector2(0, -9)),
        4: (Vector2(-13, 3), Vector2(13, 3), Vector2(-4, -10), Vector2(6, -12)),
        5: (Vector2(-14, 5), Vector2(14, 4), Vector2(-6, -8), Vector2(6, -12), Vector2(0, 0)),
    }
    _STACK_SCALE = {
        "tree": 0.58,
        "rock": 0.6,
        "gold": 0.62,
    }

    def __init__(self, main, definition: ResourceNodeDefinition, position: Vector2, total_yield: int, planted_by=None, cluster_count: int = 1) -> None:
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
        self.cluster_count = max(1, min(RESOURCE_CLUSTER_MAX, int(cluster_count)))
        self.cluster_offsets = tuple(self._CLUSTER_LAYOUTS[self.cluster_count])
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

    @property
    def visible_cluster_count(self) -> int:
        if self.remaining_yield <= 0:
            return 0
        if self.growth_ratio < 1.0:
            return 1
        if self.total_yield <= 0:
            return 1
        return max(1, math.ceil(self.cluster_count * (self.remaining_yield / self.total_yield)))

    def get_depth_sort_bottom(self) -> int:
        visible_offsets = self.cluster_offsets[:self.visible_cluster_count]
        if not visible_offsets:
            return int(self.pos.y)
        return int(max(self.pos.y + offset.y for offset in visible_offsets))

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
        if camera is not None and hasattr(camera, "world_to_screen"):
            screen_anchor = camera.world_to_screen(self.pos)
            scale_x = camera.scale_x
            scale_y = camera.scale_y
        else:
            screen_anchor = self.pos
            scale_x = 1.0
            scale_y = 1.0

        growth_scale = 1.0
        base_alpha = 255
        if self.definition.key == "tree" and self.growth_ratio < 1.0:
            growth_scale = 0.35 + self.growth_ratio * 0.65
            base_alpha = int(110 + self.growth_ratio * 145)

        visible_count = self.visible_cluster_count
        cluster_scale = 1.0 if self.cluster_count == 1 else self._STACK_SCALE.get(self.definition.key, 0.6)

        for offset in self.cluster_offsets[:visible_count]:
            draw_image = self.original_image.copy()
            if base_alpha < 255:
                draw_image.set_alpha(base_alpha)

            draw_size = (
                max(1, int(draw_image.get_width() * scale_x * growth_scale * cluster_scale)),
                max(1, int(draw_image.get_height() * scale_y * growth_scale * cluster_scale)),
            )
            if draw_size != draw_image.get_size():
                draw_image = pygame.transform.smoothscale(draw_image, draw_size)

            draw_rect = draw_image.get_rect(
                midbottom=(
                    int(screen_anchor.x + offset.x * scale_x),
                    int(screen_anchor.y + offset.y * scale_y),
                )
            )
            surface.blit(draw_image, draw_rect)

        if self.main.debug_mode and camera is not None and hasattr(camera, "world_to_screen"):
            screen_pos = camera.world_to_screen(self.pos)
            label = FONT_SMALL.render(str(self.remaining_yield), True, WHITE)
            surface.blit(label, (int(screen_pos.x) - label.get_width() // 2, int(screen_pos.y) - 26))

    @classmethod
    def _build_surface(cls, definition: ResourceNodeDefinition) -> pygame.Surface:
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

    _BASE_SPRITE_CACHE: dict[int, pygame.Surface] = {}
    _SPRITE_CACHE: dict[tuple[int, bool, bool, int], pygame.Surface] = {}
    _BASE_SPRITE_COUNT = 13

    def __init__(self, position: Vector2, target, damage: float, speed: float) -> None:
        self.pos = Vector2(position)
        self.target = target
        self.damage = float(damage)
        self.speed = float(speed)
        self.alive = True
        self.heading = Vector2(1, 0)

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
        self.heading = heading
        step = min(distance, self.speed * dt)
        self.pos += heading * step

        if distance <= step + max(6, getattr(self.target, "attack_radius", 8)):
            self._hit_target()

    def draw(self, surface: pygame.Surface, camera) -> None:
        if getattr(camera, "name", "") == "minimap":
            return

        screen_pos = camera.world_to_screen(self.pos)
        sprite = self._get_sprite_for_heading(self.heading)
        if sprite is None:
            pygame.draw.circle(surface, ORANGE, (int(screen_pos.x), int(screen_pos.y)), max(2, int(3 * camera.scale_x)))
            pygame.draw.circle(surface, WHITE, (int(screen_pos.x), int(screen_pos.y)), max(2, int(3 * camera.scale_x)), 1)
            return

        draw_size = (
            max(6, int(sprite.get_width() * camera.scale_x)),
            max(6, int(sprite.get_height() * camera.scale_y)),
        )
        if draw_size != sprite.get_size():
            sprite = pygame.transform.smoothscale(sprite, draw_size)
        draw_rect = sprite.get_rect(center=(int(screen_pos.x), int(screen_pos.y)))
        surface.blit(sprite, draw_rect)

    @classmethod
    def _get_sprite_for_heading(cls, heading: Vector2) -> pygame.Surface | None:
        if heading.length_squared() <= 0.0001:
            sprite_index = 1
            flip_x = False
            flip_y = False
            rotation = 0
        else:
            angle_from_up = math.degrees(math.atan2(heading.x, -heading.y)) % 360.0
            flip_x = False
            flip_y = False
            rotation = 0

            if angle_from_up <= 90.0:
                base_angle = angle_from_up
            elif angle_from_up <= 180.0:
                base_angle = 180.0 - angle_from_up
                flip_y = True
            elif angle_from_up <= 270.0:
                base_angle = angle_from_up - 180.0
                rotation = 180
            else:
                base_angle = 360.0 - angle_from_up
                flip_x = True

            sprite_index = int(round((base_angle / 90.0) * (cls._BASE_SPRITE_COUNT - 1))) + 1

        sprite_index = max(1, min(cls._BASE_SPRITE_COUNT, sprite_index))
        if sprite_index not in cls._BASE_SPRITE_CACHE:
            cls._BASE_SPRITE_CACHE[sprite_index] = Entity.load_image(
                "assets", "arrow", f"{sprite_index}.png",
                fallback_size=(18, 6),
                fallback_color=ORANGE,
            )

        cache_key = (sprite_index, flip_x, flip_y, rotation)
        if cache_key not in cls._SPRITE_CACHE:
            sprite = cls._BASE_SPRITE_CACHE[sprite_index]
            if flip_x or flip_y:
                sprite = pygame.transform.flip(sprite, flip_x, flip_y)
            if rotation:
                sprite = pygame.transform.rotate(sprite, rotation)
            cls._SPRITE_CACHE[cache_key] = sprite

        sprite = cls._SPRITE_CACHE.get(cache_key)
        return sprite.copy() if sprite is not None else None

    def _hit_target(self) -> None:
        if self.target is not None and getattr(self.target, "alive", False):
            self.target.take_damage(self.damage)
        self.alive = False


class BombProjectile:
    """Heavy projectile that damages enemies in a radius on impact."""

    def __init__(self, position: Vector2, target, damage: float, speed: float, splash_radius: float, targets) -> None:
        self.pos = Vector2(position)
        self.target = target
        self.damage = float(damage)
        self.speed = float(speed)
        self.splash_radius = float(splash_radius)
        self.targets = targets
        self.alive = True
        self.heading = Vector2(1, 0)

    def update(self, dt: float) -> None:
        if not self.alive:
            return

        if self.target is None or not getattr(self.target, "alive", False):
            self.alive = False
            return

        direction = self.target.pos - self.pos
        distance = direction.length()
        if distance <= 0.001:
            self._explode()
            return

        self.heading = direction.normalize()
        step = min(distance, self.speed * dt)
        self.pos += self.heading * step

        if distance <= step + max(8, getattr(self.target, "attack_radius", 10)):
            self._explode()

    def draw(self, surface: pygame.Surface, camera) -> None:
        if getattr(camera, "name", "") == "minimap":
            return

        screen_pos = camera.world_to_screen(self.pos)
        radius = max(4, int(6 * min(camera.scale_x, camera.scale_y)))
        pygame.draw.circle(surface, (74, 68, 60), (int(screen_pos.x), int(screen_pos.y)), radius)
        pygame.draw.circle(surface, ORANGE, (int(screen_pos.x), int(screen_pos.y)), max(2, radius - 2))
        pygame.draw.circle(surface, WHITE, (int(screen_pos.x), int(screen_pos.y)), radius, 1)

    def _explode(self) -> None:
        for enemy in self.targets:
            if not getattr(enemy, "alive", False):
                continue

            distance = enemy.pos.distance_to(self.pos)
            if distance > self.splash_radius:
                continue

            falloff = max(0.4, 1.0 - (distance / max(1.0, self.splash_radius)) * 0.6)
            enemy.take_damage(self.damage * falloff)

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
        self.projectiles: list[ArrowProjectile | BombProjectile] = []

        self.base_structure = self._create_main_base()
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

    def validate_structure_placement(
        self,
        building_key: str,
        world_position,
        player=None,
        *,
        check_resources: bool = False,
    ) -> tuple[bool, str, Vector2 | None]:
        definition = BUILD_DEFINITIONS.get(building_key)
        if definition is None:
            return False, "Unknown build option", None

        snapped = self._snap_to_tile_center(world_position)
        if player is not None:
            build_radius = float(getattr(player, "build_radius", TILE_SIZE * 2.75))
            if snapped.distance_to(player.pos) > build_radius:
                return False, "Build within the player's work radius", snapped

        tile = self.world.get_tile_at_world(snapped.x, snapped.y)
        if tile is None or not tile.traversable:
            return False, "That ground cannot support a structure", snapped

        placement_rect = self._structure_rect(snapped, definition)
        if player is not None and placement_rect.colliderect(player.get_collision_rect()):
            return False, "Do not place a building on top of the player", snapped

        if placement_rect.collidepoint(int(self.base_position.x), int(self.base_position.y)):
            return False, "Keep the central base clear", snapped

        if self.find_blocking_structure_for_rect(placement_rect) is not None:
            return False, "Another structure is already there", snapped

        for node in self.resource_nodes:
            if node.rect.colliderect(placement_rect.inflate(10, 10)):
                return False, "Harvest the nearby resource first", snapped

        if check_resources and player is not None and not player.has_resources(definition.cost):
            return False, "Not enough resources", snapped

        return True, definition.label, snapped

    def spawn_structure(self, building_key: str, world_position) -> Structure | None:
        definition = BUILD_DEFINITIONS.get(building_key)
        if definition is None:
            return None

        snapped = self._snap_to_tile_center(world_position)
        structure = Structure(self.main, definition, snapped)
        self.structures.append(structure)
        return structure

    def place_structure(self, building_key: str, world_position, player) -> tuple[bool, str]:
        definition = BUILD_DEFINITIONS.get(building_key)
        if definition is None:
            return False, "Unknown build option"

        valid, message, snapped = self.validate_structure_placement(
            building_key,
            world_position,
            player,
            check_resources=True,
        )
        if not valid or snapped is None:
            return False, message

        if not player.consume_resources(definition.cost):
            return False, "Not enough resources"

        structure = self.spawn_structure(building_key, snapped)
        if structure is None:
            player.refund_resources(definition.cost)
            return False, "Unknown build option"

        self._announce(f"Placed {definition.label}", accent=GOLD, duration=1.3)
        return True, definition.label

    def find_structure_at_world(self, world_position):
        point = Vector2(world_position)
        structures_by_depth = sorted(
            self.structures,
            key=lambda structure: structure.get_collision_rect().bottom,
            reverse=True,
        )
        for structure in structures_by_depth:
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

    def repair_structure(self, structure, player) -> tuple[bool, str]:
        if structure is None or not getattr(structure, "alive", False):
            return False, "Nothing selected"
        if not getattr(structure, "is_repairable", False):
            return False, "That tower does not need repairs"

        repair_cost = structure.get_repair_cost() or {}
        if not player.consume_resources(repair_cost):
            return False, "Not enough resources"
        if not structure.repair():
            player.refund_resources(repair_cost)
            return False, "Repair failed"

        self._announce(f"{structure.definition.label} repaired", accent=GREEN, duration=1.5)
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

    def spawn_resource_node(
        self,
        resource_key: str,
        world_position,
        total_yield: int | None = None,
        planted_by=None,
        ignore_structure=None,
        cluster_count: int | None = None,
    ):
        if resource_key not in RESOURCE_DEFINITIONS:
            return None

        snapped = self._snap_to_tile_center(world_position)
        if not self.can_spawn_resource_node(resource_key, snapped, ignore_structure=ignore_structure):
            return None

        definition = RESOURCE_DEFINITIONS[resource_key]
        cluster_count = max(1, min(RESOURCE_CLUSTER_MAX, int(cluster_count if cluster_count is not None else self.rng.randint(1, RESOURCE_CLUSTER_MAX))))
        yield_amount = (
            int(total_yield)
            if total_yield is not None
            else self.rng.randint(definition.min_yield, definition.max_yield) * cluster_count
        )
        node = ResourceNode(self.main, definition, snapped, yield_amount, planted_by=planted_by, cluster_count=cluster_count)
        self.resource_nodes.append(node)
        return node

    def find_blocking_structure_for_rect(self, collision_rect: pygame.Rect, ignore=None):
        for structure in self.structures:
            if structure is ignore or not structure.alive or not structure.blocks_movement:
                continue
            if structure.get_collision_rect().colliderect(collision_rect):
                return structure
        return None

    def find_blocking_resource_for_rect(self, collision_rect: pygame.Rect, resource_keys: set[str] | None = None):
        allowed_keys = resource_keys or {"tree", "rock", "gold"}
        for node in self.resource_nodes:
            if not node.alive or node.definition.key not in allowed_keys:
                continue
            if node.get_collision_rect().colliderect(collision_rect):
                return node
        return None

    def get_blocked_resource_tiles(self, resource_keys: set[str] | None = None) -> set[tuple[int, int]]:
        allowed_keys = resource_keys or {"tree", "rock", "gold"}
        return {
            self._tile_coord(node.pos)
            for node in self.resource_nodes
            if node.alive and node.definition.key in allowed_keys
        }

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
            if getattr(structure, "projectile_kind", "arrow") == "bomb":
                self.projectiles.append(
                    BombProjectile(
                        structure.pos,
                        target,
                        structure.projectile_damage,
                        structure.projectile_speed,
                        getattr(structure, "splash_radius", 0.0),
                        living_enemies,
                    )
                )
            else:
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
        return Structure.get_preview_collision_rect(definition, position)

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

    def _create_main_base(self) -> Structure:
        structure = Structure(self.main, BUILD_DEFINITIONS["main_base"], self.base_position)
        self.structures.append(structure)
        return structure

    def _announce(self, text: str, accent=GOLD, duration: float = 2.0) -> None:
        if callable(self.announce_callback):
            self.announce_callback(text, accent=accent, duration=duration)