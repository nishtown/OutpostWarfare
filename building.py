import pygame
from pygame import Vector2

from settings import *
from entity import *


class Building(Entity):
    display_name = "Building"
    sprite_name = "tower1.png"
    default_scale = (32, 32)
    default_tint = (255, 255, 255)
    default_build_time = 2.0

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

        self.image = self.load_image()
        self.rect = self.image.get_rect(center=self.pos)
        self.rect.center = self.pos

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

    def draw(self, surface):
        if self.image is not None:
            img = self.image.copy()

            if not self.is_complete:
                img.set_alpha(140)

            surface.blit(img, self.rect)

            if self.main.debug_mode:
                pygame.draw.rect(surface, RED, self.rect, 1)

            if not self.is_complete:
                bar_width = self.rect.width
                bar_height = 6
                bar_x = self.rect.left
                bar_y = self.rect.top - 10
                progress = self.get_build_progress()

                pygame.draw.rect(surface, (40, 40, 40), (bar_x, bar_y, bar_width, bar_height))
                pygame.draw.rect(surface, YELLOW, (bar_x, bar_y, int(bar_width * progress), bar_height))
                pygame.draw.rect(surface, WHITE, (bar_x, bar_y, bar_width, bar_height), 1)


class Tower(Building):
    display_name = "Tower"
    default_scale = (32, 32)
    default_tint = (255, 255, 255)
    default_build_time = 2.0


class Wall(Building):
    display_name = "Wall"
    default_scale = (24, 24)
    default_tint = (185, 185, 205)
    default_build_time = 1.2


class Depot(Building):
    display_name = "Depot"
    default_scale = (40, 40)
    default_tint = (220, 190, 140)
    default_build_time = 3.5


class Lumberyard(Building):
    display_name = "Lumberyard"
    default_scale = (40, 40)
    default_tint = (150, 205, 120)
    default_build_time = 4.0

    def __init__(self, main, x, y, width=None, height=None, name=None, scale=None, tint=None, build_time=None):
        super().__init__(main, x, y, width, height, name, scale, tint, build_time)
        self.worker_count = 2
        self.harvest_radius = 140
        self.workers = []
        self.worker_speed = 55
        self.harvest_time = 1.1
        self.wood_stored = 0
        self.label_font = pygame.font.SysFont(None, 18)

    def on_complete(self):
        self.workers = []
        for _ in range(self.worker_count):
            self.workers.append({
                "pos": Vector2(self.pos.x, self.pos.y),
                "state": "idle",
                "target": None,
                "timer": 0.0,
            })

    def find_tree_target(self):
        game = getattr(self.main, "game", None)
        if game is None or not hasattr(game, "world"):
            return None

        world = game.world
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

    def move_worker_toward(self, worker, destination, dt):
        direction = destination - worker["pos"]
        distance = direction.length()
        if distance <= 1:
            worker["pos"] = destination.copy()
            return True

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

        world = self.main.game.world

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
                if target is None or target.is_depleted:
                    worker["target"] = None
                    worker["state"] = "idle"
                    continue

                reached = self.move_worker_toward(worker, target.pos, dt)
                if reached:
                    worker["state"] = "chopping"
                    worker["timer"] = self.harvest_time
                continue

            if state == "chopping":
                if target is None or target.is_depleted:
                    worker["target"] = None
                    worker["state"] = "idle"
                    continue

                worker["timer"] -= dt
                if worker["timer"] <= 0:
                    target.harvest(1)
                    worker["state"] = "returning"
                continue

            if state == "returning":
                reached = self.move_worker_toward(worker, self.pos, dt)
                if reached:
                    self.wood_stored += 1
                    worker["target"] = None
                    worker["state"] = "idle"

    def draw(self, surface):
        super().draw(surface)

        if self.is_complete:
            radius = int(self.harvest_radius)
            center = (int(self.pos.x), int(self.pos.y))
            pygame.draw.circle(surface, (80, 120, 60), center, radius, 1)

            for worker in self.workers:
                pos = (int(worker["pos"].x), int(worker["pos"].y))
                pygame.draw.circle(surface, (235, 210, 120), pos, 4)

            wood_text = self.label_font.render(f"Wood: {self.wood_stored}", True, WHITE)
            text_rect = wood_text.get_rect(midbottom=(self.rect.centerx, self.rect.top - 12))
            surface.blit(wood_text, text_rect)
