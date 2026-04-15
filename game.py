import random

import pygame
from player import Player

from settings import *
from scene import Scene
from world import World
from camera import Camera


class Game(Scene):
    def __init__(self, main):
        super().__init__(main)
        self.font = pygame.font.SysFont(None, 60)

        self.world = World(main)
        self.player = Player(main, SCREEN_WIDTH // 2,SCREEN_HEIGHT // 2,4,4)
        self.particle_group = pygame.sprite.LayeredUpdates()
        self.camera = Camera(
            screen_width=SCREEN_WIDTH,
            screen_height=SCREEN_HEIGHT,
            world_width=MAP_WIDTH,
            world_height=MAP_HEIGHT,
            zoom=2
        )
        self.minimap_width = 240
        self.minimap_height = 160
        self.minimap_margin = 20



    def handle_event(self, event):
        if event.type == pygame.MOUSEWHEEL:
            keys = pygame.key.get_pressed()
            ctrl_held = keys[pygame.K_LCTRL] or keys[pygame.K_RCTRL]

            if ctrl_held:
                zoom_step = 0.1
                self.camera.change_zoom(event.y * zoom_step)
        pass

    def update(self, dt):

        self.player.update(dt, self.camera)
        self.camera.update(self.player.rect.centerx, self.player.rect.centery)


        pass

    def draw(self, surface):
        surface.fill(BLACK)

        self.draw_world(surface)
        self.draw_entities(surface)
        self.draw_minimap(surface)
        self.draw_ui(surface)

    def draw_minimap(self, surface):
        minimap = self.world.get_scaled_minimap(self.minimap_width, self.minimap_height)

        minimap_x = SCREEN_WIDTH - self.minimap_width - self.minimap_margin
        minimap_y = self.minimap_margin

        # Background/frame
        border_rect = pygame.Rect(
            minimap_x - 2,
            minimap_y - 2,
            self.minimap_width + 4,
            self.minimap_height + 4
        )
        pygame.draw.rect(surface, (30, 30, 30), border_rect)
        pygame.draw.rect(surface, WHITE, border_rect, 2)

        surface.blit(minimap, (minimap_x, minimap_y))

        # Draw player marker
        player_ratio_x = self.player.pos.x / self.world.world_width
        player_ratio_y = self.player.pos.y / self.world.world_height

        player_map_x = minimap_x + int(player_ratio_x * self.minimap_width)
        player_map_y = minimap_y + int(player_ratio_y * self.minimap_height)

        pygame.draw.circle(surface, RED, (player_map_x, player_map_y), 3)

        # Draw camera view rectangle
        visible = self.camera.visible_rect()

        cam_ratio_x = visible.x / self.world.world_width
        cam_ratio_y = visible.y / self.world.world_height
        cam_ratio_w = visible.width / self.world.world_width
        cam_ratio_h = visible.height / self.world.world_height

        cam_rect = pygame.Rect(
            minimap_x + int(cam_ratio_x * self.minimap_width),
            minimap_y + int(cam_ratio_y * self.minimap_height),
            max(1, int(cam_ratio_w * self.minimap_width)),
            max(1, int(cam_ratio_h * self.minimap_height)),
        )

        pygame.draw.rect(surface, WHITE, cam_rect, 1)


    def draw_world(self, surface):
        self.world.draw(surface, self.camera)

    def draw_entities(self, surface):
        self.player.draw(surface, self.camera)
        #pygame.draw.rect(surface, (220, 80, 80), self.camera.apply_rect(self.player))

    def draw_ui(self, surface):
        text = self.font.render("Outpost Warfare", True, WHITE)
        surface.blit(text, (20, 20))

    def draw_particles(self, surface):
        dt = self.main.clock.get_fps(FPS) / 1000
        for particle in self.particle_group:
            particle.update(dt)
            particle.draw(surface)