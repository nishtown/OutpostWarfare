import random
import math

import pygame
from pygame import Vector2

from settings import *
from entity import *
from building import *
from particle_animation import *

class Player(Entity):
    def __init__(self, main, x, y, width, height):
        super().__init__(main, x, y, width, height)
        self.image = pygame.image.load(asset_path("assets", "player", "player.png")).convert_alpha()
        self.shooting_image = pygame.image.load(asset_path("assets", "player", "player_shoot.png")).convert_alpha()
        self.original_image = self.image.copy()
        self.pos = Vector2(x, y)
        self.rect = self.image.get_rect(center=self.pos)
        self.speed = 100
        self.facing_angle = 0
        self.shooting = False
        self.collision_size = (16, 16)




    def handle_event(self, event):
        if event.type == pygame.KEYDOWN:
            pass

        elif event.type == pygame.KEYUP:
            pass

        elif event.type == pygame.MOUSEBUTTONDOWN:
            pass

        elif event.type == pygame.MOUSEBUTTONUP:
            pass



    def get_collision_rect(self, pos=None):
        rect = pygame.Rect(0, 0, self.collision_size[0], self.collision_size[1])
        center = pos if pos is not None else self.pos
        rect.center = (int(center.x), int(center.y))
        return rect

    def update(self, dt, buildmode):
        keys = pygame.key.get_pressed()
        mouse_btn = pygame.mouse.get_pressed()

        img = self.original_image

        if not buildmode:
            if mouse_btn[0]:
                if not self.shooting:
                    self.shooting = True
            else:
                self.shooting = False

            if self.shooting:
                img = self.shooting_image

        move_x = int(keys[pygame.K_d] or keys[pygame.K_RIGHT]) - int(keys[pygame.K_a] or keys[pygame.K_LEFT])
        move_y = int(keys[pygame.K_s] or keys[pygame.K_DOWN]) - int(keys[pygame.K_w] or keys[pygame.K_UP])
        move = pygame.Vector2(move_x, move_y)

        if move.length_squared() > 0:
            move = move.normalize()
            step = move * self.speed * dt
            self.facing_angle = math.degrees(math.atan2(-move.y, move.x))

            game = getattr(self.main, "game", None)

            next_x = pygame.Vector2(self.pos.x + step.x, self.pos.y)
            if game is None or game.can_move_player_to(self.get_collision_rect(next_x)):
                self.pos.x = next_x.x

            next_y = pygame.Vector2(self.pos.x, self.pos.y + step.y)
            if game is None or game.can_move_player_to(self.get_collision_rect(next_y)):
                self.pos.y = next_y.y

        self.image = pygame.transform.rotate(img, self.facing_angle)
        self.rect = self.image.get_rect(center=self.pos)

        super().update(dt)


    def draw(self, surface):
        super().draw(surface)

        if self.main.debug_mode:
            pygame.draw.rect(surface, BLUE, self.get_collision_rect(), 1)






