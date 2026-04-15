import random
import math

from pygame import Vector2

from settings import *
from entity import *
from particle_animation import *

class Player(Entity):
    def __init__(self, main, x, y, width, height):
        super().__init__(main, x, y, width, height)
        self.image = pygame.image.load(asset_path("assets", "player", "player.png")).convert_alpha()
        self.original_image = self.image.copy()
        self.pos = Vector2(x, y)
        self.speed = 35
        self.angle = 0
        self.direction = Vector2()
        self.is_dead = False

        w = self.original_image.get_width()
        h = self.original_image.get_height()

        # Fixed box large enough for any rotation
        self.render_box_size = math.ceil((w * w + h * h) ** 0.5)

        self.render_surface = pygame.Surface(
            (self.render_box_size, self.render_box_size),
            pygame.SRCALPHA
        )


    def update(self, dt, camera):
        mouse_screen = pygame.mouse.get_pos()
        mouse_world = camera.screen_to_world(mouse_screen)

        direction = mouse_world - self.pos

        if direction.length() > 0:
            self.angle = direction.as_polar()[1]




        keys = pygame.key.get_pressed()

        if keys[pygame.K_w]:
            self.pos = self.pos.move_towards(mouse_world, self.speed * dt)

        if keys[pygame.K_s]:
            backward_target = self.pos - direction * 1000
            self.pos = self.pos.move_towards(backward_target, self.speed * dt)

        right = pygame.Vector2(-direction.y, direction.x)

        if keys[pygame.K_d]:
            target = self.pos + right * 1000
            self.pos = self.pos.move_towards(target, self.speed * dt)

        if keys[pygame.K_a]:
            target = self.pos - right * 1000
            self.pos = self.pos.move_towards(target, self.speed * dt)


        self.rect.center = self.pos


        super().update(dt)

    def get_rotated_render(self):
        rotated = pygame.transform.rotate(self.original_image, -self.angle)

        self.render_surface.fill((0, 0, 0, 0))
        rotated_rect = rotated.get_rect(
            center=(self.render_box_size // 2, self.render_box_size // 2)
        )
        self.render_surface.blit(rotated, rotated_rect)

        return self.render_surface

    def draw(self, surface, camera):
        render_image = self.get_rotated_render()
        super().draw(surface, camera, image_override=render_image)






