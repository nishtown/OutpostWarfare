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




    def handle_event(self, event):
        if event.type == pygame.KEYDOWN:
            pass

        elif event.type == pygame.KEYUP:
            pass

        elif event.type == pygame.MOUSEBUTTONDOWN:
            pass

        elif event.type == pygame.MOUSEBUTTONUP:
            pass



    def update(self, dt, buildmode):
        keys = pygame.key.get_pressed()
        mouse_btn = pygame.mouse.get_pressed()

        img = self.original_image
        img_changed = False


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
            move = move.normalize()  # keeps diagonal speed consistent
            self.pos += move * self.speed * dt
            # Convert movement direction into an angle
            self.facing_angle = math.degrees(math.atan2(-move.y, move.x))

            # Rotate from the original image every time


        self.image = pygame.transform.rotate(img, self.facing_angle)
        self.rect = self.image.get_rect(center=self.pos)


        super().update(dt)


    def draw(self, surface):
        #pygame.draw.rect(surface, GREEN, self.rect, 1)



        super().draw(surface)






