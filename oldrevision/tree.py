import random

import pygame
from pygame import Vector2

from oldrevision.settings import *
from oldrevision.entity import *


class Tree(Entity):
    display_name = "Tree"
    resource_type = "wood"
    action_label = "Chopping"
    action_duration = 1.15
    resource_yield = 1
    asset_names = ["tree.png", "treeDead.png", "treeLong.png", "treePine.png"]
    weighted_assets = [
        "tree.png", "tree.png", "tree.png", "tree.png",
        "treeLong.png", "treeLong.png", "treeLong.png",
        "treePine.png", "treePine.png", "treePine.png", "treePine.png",
    ]
    live_weighted_assets = [
        "tree.png", "tree.png", "tree.png", "tree.png",
        "treeLong.png", "treeLong.png", "treeLong.png",
        "treePine.png", "treePine.png", "treePine.png", "treePine.png",
    ]
    _image_cache = {}
    tint_color = (170, 190, 170)

    def __init__(self, main, x, y, variant=None, scale=None, farm_tree=False, mature=True, growth_time=22.0, owner=None):
        scale = scale or self.get_random_scale()
        super().__init__(main, x, y, scale[0], scale[1])

        self.pos = Vector2(x, y)
        self.base_scale = scale
        variant_pool = self.live_weighted_assets if farm_tree else self.weighted_assets
        self.variant = variant or random.choice(variant_pool)
        self.scale = scale
        self.flip_x = random.random() < 0.5
        self.is_farm_tree = farm_tree
        self.owner = owner
        self.growth_time = max(0.1, growth_time)
        self.growth_elapsed = self.growth_time if (mature or not farm_tree) else 0.0
        self.is_mature = mature or not farm_tree
        self.max_health = random.randint(2, 4)
        self.health = self.max_health
        self.is_depleted = False
        self._visual_signature = None

        self.image = None
        self.rect = pygame.Rect(0, 0, scale[0], scale[1])
        self.rect.midbottom = (x, y)
        self.blocking_rect = pygame.Rect(0, 0, 1, 1)
        self.refresh_visual(force=True)

    @classmethod
    def load_image(cls, variant, scale, flip_x=False):
        cache_key = (variant, scale, flip_x)
        if cache_key not in cls._image_cache:
            image = pygame.image.load(asset_path("assets", "trees", variant)).convert_alpha()
            image = pygame.transform.smoothscale(image, scale)
            image = image.copy()
            image.fill((*cls.tint_color, 255), special_flags=pygame.BLEND_RGBA_MULT)
            if flip_x:
                image = pygame.transform.flip(image, True, False)
            cls._image_cache[cache_key] = image

        return cls._image_cache[cache_key]

    def get_growth_ratio(self):
        if not self.is_farm_tree:
            return 1.0
        return max(0.0, min(1.0, self.growth_elapsed / self.growth_time))

    def get_visual_scale(self):
        growth_ratio = self.get_growth_ratio()
        scale_factor = 1.0 if self.is_mature else (0.35 + (growth_ratio * 0.65))
        return (
            max(12, int(self.base_scale[0] * scale_factor)),
            max(18, int(self.base_scale[1] * scale_factor)),
        )

    def refresh_visual(self, force=False):
        scale = self.get_visual_scale()
        growth_stage = 5 if self.is_mature else int(self.get_growth_ratio() * 4)
        visual_signature = (scale, self.flip_x, self.is_mature, growth_stage)
        if not force and visual_signature == self._visual_signature:
            return False

        self.scale = scale
        self.image = self.load_image(self.variant, self.scale, self.flip_x)
        self.rect = self.image.get_rect(midbottom=(int(self.pos.x), int(self.pos.y)))
        self.blocking_rect = self.get_blocking_rect()
        self._visual_signature = visual_signature
        return True

    def get_blocking_rect(self):
        trunk_width = max(10, int(self.rect.width * 0.35))
        trunk_height = max(10, int(self.rect.height * 0.22))
        blocking_rect = pygame.Rect(0, 0, trunk_width, trunk_height)
        blocking_rect.midbottom = self.rect.midbottom
        return blocking_rect

    def can_harvest(self):
        return not self.is_depleted and self.is_mature

    def needs_growth_update(self):
        return self.is_farm_tree and not self.is_mature

    def begin_regrowth(self):
        self.health = self.max_health
        self.is_depleted = False
        self.is_mature = False
        self.growth_elapsed = 0.0
        self.refresh_visual(force=True)

    def harvest(self, amount=1):
        if not self.can_harvest():
            return False

        self.health -= amount
        if self.health <= 0:
            if self.is_farm_tree:
                self.begin_regrowth()
            else:
                self.health = 0
                self.is_depleted = True

        return True

    def update(self, dt):
        if not self.needs_growth_update():
            return False

        self.growth_elapsed = min(self.growth_time, self.growth_elapsed + dt)
        if self.growth_elapsed >= self.growth_time:
            self.is_mature = True

        return self.refresh_visual()

    def draw(self, surface, camera_offset=None):
        super().draw(surface, camera_offset)
        if self.main.debug_mode:
            blocking_rect = self.blocking_rect.copy()
            if camera_offset is not None:
                blocking_rect = blocking_rect.move(-int(camera_offset.x), -int(camera_offset.y))
            pygame.draw.rect(surface, BLUE, blocking_rect, 1)

    @staticmethod
    def get_random_scale():
        width = random.randint(28, 54)
        height = random.randint(42, 78)
        return width, height
