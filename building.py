import random
import math

import pygame.draw
from pygame import Vector2

from settings import *
from entity import *

class Building(Entity):
    def __init__(self, main, x, y, width, height):
        super().__init__(main, x,y, width, height)
        self.pos = Vector2(x, y)
        self.image = pygame.image.load(asset_path("assets", "buildings", "tower1.png")).convert_alpha()
        self.rect = self.image.get_rect(center=self.pos)
        self.rect.center = self.pos

    def update(self, dt):
        super().update(dt)

    def draw(self, surface):

        super().draw(surface)
