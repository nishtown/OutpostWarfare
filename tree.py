import random

import pygame
from pygame import Vector2

from settings import *
from entity import *


class Tree(Entity):
    asset_names = ["tree.png", "treeDead.png", "treeLong.png", "treePine.png"]
    weighted_assets = [
        "tree.png", "tree.png", "tree.png", "tree.png",
        "treeLong.png", "treeLong.png", "treeLong.png",
        "treePine.png", "treePine.png", "treePine.png", "treePine.png",
    ]
    _image_cache = {}
    tint_color = (170, 190, 170)

    def __init__(self, main, x, y, variant=None, scale=None):
        scale = scale or self.get_random_scale()
        super().__init__(main, x, y, scale[0], scale[1])

        self.pos = Vector2(x, y)
        self.variant = variant or random.choice(self.weighted_assets)
        self.scale = scale
        self.max_health = random.randint(2, 4)
        self.health = self.max_health
        self.is_depleted = False

        self.image = self.load_image(self.variant, self.scale)
        self.rect = self.image.get_rect(midbottom=(x, y))
        self.blocking_rect = self.get_blocking_rect()

    @classmethod
    def load_image(cls, variant, scale):
        cache_key = (variant, scale)
        if cache_key not in cls._image_cache:
            image = pygame.image.load(asset_path("assets", "trees", variant)).convert_alpha()
            image = pygame.transform.smoothscale(image, scale)
            image = image.copy()
            image.fill((*cls.tint_color, 255), special_flags=pygame.BLEND_RGBA_MULT)
            cls._image_cache[cache_key] = image

        image = cls._image_cache[cache_key].copy()
        if random.random() < 0.5:
            image = pygame.transform.flip(image, True, False)
        return image

    def get_blocking_rect(self):
        trunk_width = max(10, int(self.rect.width * 0.35))
        trunk_height = max(10, int(self.rect.height * 0.22))
        blocking_rect = pygame.Rect(0, 0, trunk_width, trunk_height)
        blocking_rect.midbottom = self.rect.midbottom
        return blocking_rect

    def harvest(self, amount=1):
        if self.is_depleted:
            return False

        self.health -= amount
        if self.health <= 0:
            self.health = 0
            self.is_depleted = True
            return True

        return False

    def draw(self, surface):
        super().draw(surface)
        if self.main.debug_mode:
            pygame.draw.rect(surface, BLUE, self.blocking_rect, 1)

    @staticmethod
    def get_random_scale():
        width = random.randint(28, 54)
        height = random.randint(42, 78)
        return width, height
