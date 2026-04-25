import random

import pygame
from pygame import Vector2

from oldrevision.settings import *
from oldrevision.entity import *


class Rock(Entity):
    display_name = "Rock"
    resource_type = "stone"
    action_label = "Mining"
    action_duration = 1.4
    resource_yield = 1
    asset_names = ["rock1.png", "rock2.png", "rock3.png", "rock4.png", "rock5.png"]
    _base_image_cache = {}
    _image_cache = {}

    def __init__(self, main, x, y, scale=None, variant=None):
        scale = scale or self.get_random_scale()
        super().__init__(main, x, y, 1, 1)

        self.pos = Vector2(x, y)
        self.scale = scale
        self.variant = variant or random.choice(self.asset_names)
        self.flip_x = random.random() < 0.5
        self.max_health = random.randint(3, 5)
        self.health = self.max_health
        self.is_depleted = False

        self.image = self.load_image(self.variant, self.scale, self.flip_x)
        self.rect = self.image.get_rect(midbottom=(x, y))
        self.blocking_rect = self.get_blocking_rect()

    @classmethod
    def load_base_image(cls, variant):
        if variant not in cls._base_image_cache:
            cls._base_image_cache[variant] = pygame.image.load(asset_path("assets", "rocks", variant)).convert_alpha()
        return cls._base_image_cache[variant]

    @classmethod
    def load_image(cls, variant, scale, flip_x=False):
        cache_key = (variant, scale, flip_x)
        if cache_key not in cls._image_cache:
            image = cls.load_base_image(variant)
            if scale != 1.0:
                scaled_size = (
                    max(14, int(image.get_width() * scale)),
                    max(12, int(image.get_height() * scale)),
                )
                image = pygame.transform.smoothscale(image, scaled_size)
            else:
                image = image.copy()

            if flip_x:
                image = pygame.transform.flip(image, True, False)

            cls._image_cache[cache_key] = image

        return cls._image_cache[cache_key]

    def get_local_opaque_rect(self):
        mask = pygame.mask.from_surface(self.image)
        rects = mask.get_bounding_rects()
        if not rects:
            return self.image.get_rect()

        opaque_rect = rects[0].copy()
        for rect in rects[1:]:
            opaque_rect.union_ip(rect)
        return opaque_rect

    def get_blocking_rect(self):
        opaque_rect = self.get_local_opaque_rect()
        block_height = max(10, int(opaque_rect.height * 0.42))
        block_width = min(self.rect.width, max(14, int(opaque_rect.width * 0.9) + 4))
        blocking_rect = pygame.Rect(0, 0, block_width, block_height)
        blocking_rect.centerx = self.rect.left + opaque_rect.centerx
        blocking_rect.bottom = self.rect.top + opaque_rect.bottom
        return blocking_rect

    def can_harvest(self):
        return not self.is_depleted

    def harvest(self, amount=1):
        if not self.can_harvest():
            return False

        self.health -= amount
        if self.health <= 0:
            self.health = 0
            self.is_depleted = True

        return True

    def draw(self, surface, camera_offset=None):
        super().draw(surface, camera_offset)
        if self.main.debug_mode:
            blocking_rect = self.blocking_rect.copy()
            if camera_offset is not None:
                blocking_rect = blocking_rect.move(-int(camera_offset.x), -int(camera_offset.y))
            pygame.draw.rect(surface, BLUE, blocking_rect, 1)

    @staticmethod
    def get_random_scale():
        return round(random.uniform(0.95, 1.45), 2)