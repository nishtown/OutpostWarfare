import random
import math

import pygame
from pygame import Vector2

from oldrevision.settings import *
from oldrevision.entity import *
from oldrevision.building import *
from oldrevision.particle_animation import *

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
        self.inventory = {"wood": 0, "stone": 0}
        self.harvest_range = 78
        self.harvest_action = None




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

    def add_resource(self, resource_name, amount=1):
        self.inventory[resource_name] = self.inventory.get(resource_name, 0) + int(amount)

    def get_resource_amount(self, resource_name):
        return self.inventory.get(resource_name, 0)

    def has_resources(self, cost):
        return all(self.get_resource_amount(resource_name) >= int(amount) for resource_name, amount in cost.items())

    def consume_resources(self, cost):
        if not self.has_resources(cost):
            return False

        for resource_name, amount in cost.items():
            self.inventory[resource_name] -= int(amount)
        return True

    def refund_resources(self, refund):
        for resource_name, amount in refund.items():
            self.add_resource(resource_name, amount)

    def start_harvest(self, target):
        self.harvest_action = {
            "target": target,
            "progress": 0.0,
            "duration": float(getattr(target, "action_duration", 1.0)),
            "label": getattr(target, "action_label", "Harvesting"),
        }

    def stop_harvest(self):
        self.harvest_action = None

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

        if move.length_squared() > 0 and self.harvest_action is not None:
            self.stop_harvest()

        super().update(dt)


    def draw(self, surface, camera_offset=None):
        super().draw(surface, camera_offset)

        if self.main.debug_mode:
            collision_rect = self.get_collision_rect()
            if camera_offset is not None:
                collision_rect = collision_rect.move(-int(camera_offset.x), -int(camera_offset.y))
            pygame.draw.rect(surface, BLUE, collision_rect, 1)





