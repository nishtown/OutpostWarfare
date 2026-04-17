import random
import pygame
from particle_animation import ParticleAnimation
from player import Player
from building import Building
from settings import *


class Game:
    def __init__(self, main):
        self.font = pygame.font.SysFont(None, 60)
        self.player = Player(main, 100,100,16,16)
        self.building = Building(main, 100,100,16,16)
        self.buildings = set()
        self.main = main
        self.buildrange = 200
        self.buildmode = False
        self.can_place = False
        self.placeable_object = None

    def handle_event(self, event):
        self.player.handle_event(event)

        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_b:
                self.buildmode = not self.buildmode
                if self.placeable_object != None:
                    self.placeable_object = None
                else:
                    self.placeable_object = self.building
        elif event.type == pygame.KEYUP:
            pass

        elif event.type == pygame.MOUSEBUTTONDOWN:
            pass

        elif event.type == pygame.MOUSEBUTTONUP:
            if self.buildmode and self.can_place:
                self.buildings.add(Building(self.main, self.placeable_object.pos.x, self.placeable_object.pos.y, self.placeable_object.rect.width, self.placeable_object.rect.height))
                self.buildmode = False
                self.placeable_object = None
            pass



        pass

    def update(self, dt):
        self.player.update(dt, self.buildmode)
        mouse_pos = pygame.mouse.get_pos()

        if self.buildmode:
            if self.player.pos.distance_to(mouse_pos) < self.buildrange:
                self.can_place = True
                self.placeable_object = self.building
                self.placeable_object.pos = pygame.math.Vector2(mouse_pos[0], mouse_pos[1])
            else:
                self.can_place = False

            if self.placeable_object != None:
                self.placeable_object.pos = pygame.math.Vector2(mouse_pos[0], mouse_pos[1])
                self.placeable_object.rect.center = self.placeable_object.pos


        pass

    def draw(self, surface):
        surface.fill(DARK_GREEN)
        for building in self.buildings:
            building.draw(surface)

        if self.buildmode:
            self.draw_build_range(surface)
            if self.can_place and self.placeable_object != None:
                self.placeable_object.draw(surface)

        self.player.draw(surface)

    def draw_build_range(self, surface):
        range_image = pygame.Surface((self.buildrange * 2, self.buildrange * 2))
        range_image.fill((0, 0, 0))
        range_image.set_colorkey((0, 0, 0))
        pygame.draw.circle(
            range_image,
            (220, 220, 220),
            (self.buildrange, self.buildrange),
            self.buildrange,
            self.buildrange
        )

        range_image.set_alpha(20)
        range_image.get_rect(center=self.player.rect.center)
        surface.blit(range_image, range_image.get_rect(center=self.player.rect.center))