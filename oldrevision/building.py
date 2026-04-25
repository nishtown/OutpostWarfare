import math
import random

import pygame
from pygame import Vector2

from oldrevision.settings import *
from oldrevision.entity import *
from oldrevision.tree import Tree


class Building(Entity):
    display_name = "Building"
    sprite_name = "tower1.png"
    default_scale = (32, 32)
    default_tint = (255, 255, 255)
    default_build_time = 2.0
    default_cost = {}
    demolish_refund_ratio = 0.5

    def __init__(self, main, x, y, width=None, height=None, name=None, scale=None, tint=None, build_time=None):
        scale = scale or self.default_scale
        width = width or scale[0]
        height = height or scale[1]

        super().__init__(main, x, y, width, height)
        self.name = name or self.display_name
        self.pos = Vector2(x, y)
        self.scale = scale
        self.tint = tint or self.default_tint
        self.build_time = max(0.1, float(build_time if build_time is not None else self.default_build_time))
        self.build_elapsed = 0.0
        self.is_complete = False
        self.completion_triggered = False
        self.build_cost = {resource: int(amount) for resource, amount in self.default_cost.items()}

        self.image = self.load_image()
        self.rect = self.image.get_rect(center=self.pos)
        self.rect.center = self.pos

    @classmethod
    def format_cost(cls, cost=None):
        cost = cls.default_cost if cost is None else cost
        parts = []
        for resource_name in ("wood", "stone"):
            amount = int(cost.get(resource_name, 0))
            if amount > 0:
                parts.append(f"{amount} {resource_name}")
        return ", ".join(parts) if parts else "free"

    @classmethod
    def create_preview(cls):
        image = pygame.image.load(asset_path("assets", "buildings", cls.sprite_name)).convert_alpha()
        image = pygame.transform.smoothscale(image, cls.default_scale)

        if cls.default_tint is not None:
            image = image.copy()
            image.fill((*cls.default_tint, 255), special_flags=pygame.BLEND_RGBA_MULT)

        return image

    def load_image(self):
        image = pygame.image.load(asset_path("assets", "buildings", self.sprite_name)).convert_alpha()

        if self.scale is not None:
            image = pygame.transform.smoothscale(image, self.scale)

        if self.tint is not None:
            image = image.copy()
            image.fill((*self.tint, 255), special_flags=pygame.BLEND_RGBA_MULT)

        return image

    def on_complete(self):
        pass

    def get_build_progress(self):
        return min(1.0, self.build_elapsed / self.build_time)

    def get_demolition_refund(self):
        refund = {}
        for resource_name, amount in self.build_cost.items():
            refund_amount = int(amount * self.demolish_refund_ratio)
            if refund_amount > 0:
                refund[resource_name] = refund_amount
        return refund

    def get_selection_lines(self):
        lines = [self.name]
        if self.is_complete:
            lines.append("Status: Complete")
        else:
            lines.append(f"Building: {int(self.get_build_progress() * 100)}%")

        if self.build_cost:
            lines.append(f"Cost: {self.format_cost(self.build_cost)}")

        refund = self.get_demolition_refund()
        if refund:
            lines.append(f"Refund: {self.format_cost(refund)}")

        return lines

    def update(self, dt):
        if not self.is_complete:
            self.build_elapsed += dt
            if self.build_elapsed >= self.build_time:
                self.build_elapsed = self.build_time
                self.is_complete = True

        if self.is_complete and not self.completion_triggered:
            self.completion_triggered = True
            self.on_complete()

        super().update(dt)

    def draw(self, surface, camera_offset=None):
        if self.image is not None:
            img = self.image.copy()

            if not self.is_complete:
                img.set_alpha(140)

            original_image = self.image
            self.image = img
            super().draw(surface, camera_offset)
            self.image = original_image

    def draw_overlay(self, surface, camera_offset=None):
        if not self.is_complete:
            bar_width = self.rect.width
            bar_height = 6
            progress = self.get_build_progress()

            draw_rect = self.rect.copy()
            if camera_offset is not None:
                draw_rect = draw_rect.move(-int(camera_offset.x), -int(camera_offset.y))

            bar_x = draw_rect.left
            bar_y = draw_rect.top - 10

            pygame.draw.rect(surface, (40, 40, 40), (bar_x, bar_y, bar_width, bar_height))
            pygame.draw.rect(surface, YELLOW, (bar_x, bar_y, int(bar_width * progress), bar_height))
            pygame.draw.rect(surface, WHITE, (bar_x, bar_y, bar_width, bar_height), 1)


class Tower(Building):
    display_name = "Tower"
    default_scale = (32, 32)
    default_tint = (255, 255, 255)
    default_build_time = 2.0
    default_cost = {"wood": 8, "stone": 6}


class Wall(Building):
    display_name = "Wall"
    default_scale = (24, 24)
    default_tint = (185, 185, 205)
    default_build_time = 1.2
    default_cost = {"wood": 2, "stone": 2}


class Depot(Building):
    display_name = "Depot"
    default_scale = (40, 40)
    default_tint = (220, 190, 140)
    default_build_time = 3.5
    default_cost = {"wood": 10, "stone": 4}


class Lumberyard(Building):
    display_name = "Lumberyard"
    default_scale = (96, 96)
    default_tint = (150, 205, 120)
    default_build_time = 4.0
    default_cost = {"wood": 12, "stone": 6}
    sprite_name = "lumberyard.png"
    worker_sprite_names = [
        "characterBlue (1).png",
        "characterBlue (2).png",
        "characterBlue (3).png",
        "characterBlue (4).png",
        "characterBlue (5).png",
    ]
    worker_sprite_cache = {}

    def __init__(self, main, x, y, width=None, height=None, name=None, scale=None, tint=None, build_time=None):
        super().__init__(main, x, y, width, height, name, scale, tint, build_time)
        self.worker_count = 2
        self.harvest_radius = 140
        self.workers = []
        self.worker_speed = 55
        self.harvest_time = 1.1
        self.dropoff_time = 0.6
        self.wood_stored = 0
        self.label_font = pygame.font.SysFont(None, 18)
        self.worker_scale = (12, 16)
        self.farm_mode = False
        self.farm_trees = []
        self.farm_tree_count = 5
        self.farm_spawn_radius = 140
        self.farm_growth_time = 24.0
        self.farm_retry_cooldown = 4.0
        self.farm_retry_timer = 0.0

    def get_worker_sprite(self, sprite_name):
        if sprite_name not in self.worker_sprite_cache:
            image = pygame.image.load(asset_path("assets", "workers", sprite_name)).convert_alpha()
            image = pygame.transform.smoothscale(image, self.worker_scale)
            self.worker_sprite_cache[sprite_name] = image
        return self.worker_sprite_cache[sprite_name]

    def on_complete(self):
        self.workers = []
        for _ in range(self.worker_count):
            sprite_name = random.choice(self.worker_sprite_names)
            self.workers.append({
                "pos": Vector2(self.pos.x, self.pos.y),
                "state": "idle",
                "target": None,
                "timer": 0.0,
                "sprite_name": sprite_name,
                "base_sprite": self.get_worker_sprite(sprite_name),
                "angle": 0.0,
                "carrying": 0,
            })

    def get_world(self):
        game = getattr(self.main, "game", None)
        if game is None or not hasattr(game, "world"):
            return None
        return game.world

    def prune_farm_trees(self):
        world = self.get_world()
        if world is None:
            self.farm_trees = []
            return

        active_farm_trees = []
        for tree in self.farm_trees:
            chunk = world.get_available_chunk(getattr(tree, "chunk_key", None)) if getattr(tree, "chunk_key", None) is not None else None
            if chunk is not None and tree in chunk["trees"]:
                active_farm_trees.append(tree)
        self.farm_trees = active_farm_trees

    def plant_farm_trees(self):
        world = self.get_world()
        if world is None:
            return

        planted = 0
        attempt_count = self.farm_tree_count * 12
        for attempt in range(attempt_count):
            if len(self.farm_trees) + planted >= self.farm_tree_count:
                break

            angle = math.radians((attempt * (360 / max(1, attempt_count))) + random.uniform(-18.0, 18.0))
            radius = random.randint(int(self.farm_spawn_radius * 0.45), int(self.farm_spawn_radius * 1.1))
            tree_x = self.pos.x + math.cos(angle) * radius
            tree_y = self.pos.y + math.sin(angle) * radius
            tree = Tree(
                self.main,
                tree_x,
                tree_y,
                variant=random.choice(Tree.live_weighted_assets),
                scale=Tree.get_random_scale(),
                farm_tree=True,
                mature=False,
                growth_time=self.farm_growth_time,
                owner=self,
            )

            if not world.can_place_tree(tree, ignore_building=self):
                continue

            world.add_tree(tree)
            self.farm_trees.append(tree)
            planted += 1

        if planted > 0:
            self.farm_mode = True

    def update_tree_farm(self, dt):
        world = self.get_world()
        if world is None:
            return

        self.prune_farm_trees()
        nearby_trees = world.get_nearby_trees(self.pos, self.harvest_radius)
        wild_trees = [tree for tree in nearby_trees if getattr(tree, "owner", None) is not self]

        if wild_trees:
            self.farm_mode = False
            self.farm_retry_timer = self.farm_retry_cooldown
            return

        self.farm_mode = True
        self.farm_retry_timer = max(0.0, self.farm_retry_timer - dt)
        if len(self.farm_trees) < self.farm_tree_count and self.farm_retry_timer <= 0:
            self.plant_farm_trees()
            self.farm_retry_timer = self.farm_retry_cooldown

    def is_valid_tree_target(self, target):
        return target is not None and target.can_harvest()

    def find_tree_target(self):
        world = self.get_world()
        if world is None:
            return None

        nearby_trees = world.get_nearby_trees(self.pos, self.harvest_radius)
        reserved = {
            worker["target"]
            for worker in self.workers
            if worker.get("state") in ("moving_to_tree", "chopping") and worker.get("target") is not None
        }

        for tree in nearby_trees:
            if tree not in reserved:
                return tree

        return nearby_trees[0] if nearby_trees else None

    def update_worker_rotation(self, worker, direction):
        if direction.length_squared() > 0:
            worker["angle"] = -math.degrees(math.atan2(direction.x, direction.y))

    def move_worker_toward(self, worker, destination, dt):
        direction = destination - worker["pos"]
        distance = direction.length()
        if distance <= 1:
            worker["pos"] = destination.copy()
            return True

        self.update_worker_rotation(worker, direction)

        step = self.worker_speed * dt
        if step >= distance:
            worker["pos"] = destination.copy()
            return True

        worker["pos"] += direction.normalize() * step
        return False

    def update(self, dt):
        super().update(dt)

        if not self.is_complete or not self.workers:
            return

        self.update_tree_farm(dt)

        for worker in self.workers:
            state = worker["state"]
            target = worker.get("target")

            if state == "idle":
                tree = self.find_tree_target()
                if tree is not None:
                    worker["target"] = tree
                    worker["state"] = "moving_to_tree"
                continue

            if state == "moving_to_tree":
                if not self.is_valid_tree_target(target):
                    worker["target"] = None
                    worker["state"] = "idle"
                    continue

                reached = self.move_worker_toward(worker, target.pos, dt)
                if reached:
                    worker["state"] = "chopping"
                    worker["timer"] = self.harvest_time
                continue

            if state == "chopping":
                if not self.is_valid_tree_target(target):
                    worker["target"] = None
                    worker["state"] = "idle"
                    continue

                worker["timer"] -= dt
                if worker["timer"] <= 0:
                    if target.harvest(1):
                        worker["carrying"] = getattr(target, "resource_yield", 1)
                    worker["state"] = "returning"
                continue

            if state == "returning":
                reached = self.move_worker_toward(worker, self.pos, dt)
                if reached:
                    worker["state"] = "dropping_off"
                    worker["timer"] = self.dropoff_time
                continue

            if state == "dropping_off":
                worker["timer"] -= dt
                if worker["timer"] <= 0:
                    if worker.get("carrying", 0) > 0:
                        self.wood_stored += worker["carrying"]
                        worker["carrying"] = 0
                    worker["target"] = None
                    worker["state"] = "idle"

    def draw(self, surface, camera_offset=None):
        if self.is_complete:
            radius = int(self.harvest_radius)
            center_x = int(self.pos.x)
            center_y = int(self.pos.y)
            if camera_offset is not None:
                center_x -= int(camera_offset.x)
                center_y -= int(camera_offset.y)
            pygame.draw.circle(surface, (80, 120, 60), (center_x, center_y), radius, 1)

            for worker in self.workers:
                worker_image = pygame.transform.rotate(worker["base_sprite"], worker["angle"])
                worker_x = int(worker["pos"].x)
                worker_y = int(worker["pos"].y)
                if camera_offset is not None:
                    worker_x -= int(camera_offset.x)
                    worker_y -= int(camera_offset.y)
                worker_rect = worker_image.get_rect(midbottom=(worker_x, worker_y))
                surface.blit(worker_image, worker_rect)

        super().draw(surface, camera_offset)

    def draw_overlay(self, surface, camera_offset=None):
        super().draw_overlay(surface, camera_offset)

        if self.is_complete:
            text_midbottom = (self.rect.centerx, self.rect.top - 12)
            if camera_offset is not None:
                text_midbottom = (
                    int(text_midbottom[0] - camera_offset.x),
                    int(text_midbottom[1] - camera_offset.y),
                )
            wood_text = self.label_font.render(f"Wood: {self.wood_stored}", True, WHITE)
            text_rect = wood_text.get_rect(midbottom=text_midbottom)
            surface.blit(wood_text, text_rect)

    def get_selection_lines(self):
        lines = super().get_selection_lines()
        if self.is_complete:
            lines.append(f"Wood Stored: {self.wood_stored}")
            lines.append(f"Mode: {'Tree Farm' if self.farm_mode else 'Lumberyard'}")
            if self.farm_trees:
                growing_trees = sum(1 for tree in self.farm_trees if not tree.can_harvest())
                lines.append(f"Farm Trees: {len(self.farm_trees)} ({growing_trees} growing)")
        return lines
