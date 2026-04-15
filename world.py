import random

import pygame
from perlin_noise import PerlinNoise

from settings import *
from scene import Scene


class World():
    def __init__(self, main, seed=1, tile_size=16):
        super().__init__()
        self.font = pygame.font.SysFont(None, 60)
        random.seed()
        self.seed = random.randint(1,100000)
        self.tile_size = tile_size
        self.cols = MAP_WIDTH // self.tile_size
        self.rows = MAP_HEIGHT // self.tile_size
        self.world_width = MAP_WIDTH
        self.world_height = MAP_HEIGHT

        self.noise_surface = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT))

        self.minimap_surface = None


        self.heightmap = []
        self.terrain_map = []
        self.forest_map = []

        self.generate_noise()
        self.generate_forests()
        self.build_minimap()


    def handle_event(self, event):
        pass

    def get_scaled_minimap(self, width, height):
        return pygame.transform.smoothscale(self.minimap_surface, (width, height))

    def build_minimap(self):
        self.minimap_surface = pygame.Surface((self.cols, self.rows))

        for y in range(self.rows):
            for x in range(self.cols):
                height = self.heightmap[y][x]
                terrain = self.terrain_map[y][x]
                color = self.get_terrain_color(terrain, height)

                self.minimap_surface.set_at((x, y), color)

                if self.forest_map[y][x]:
                    forest_color = self.get_forest_color(terrain)
                    if forest_color is not None:
                        self.minimap_surface.set_at((x, y), forest_color)

    def generate_forests(self):
        forest_noise = PerlinNoise(octaves=3, seed=self.seed + 999)
        forest_scale = 100.0

        self.forest_map.clear()

        for y in range(self.rows):
            forest_row = []

            for x in range(self.cols):
                terrain = self.terrain_map[y][x]

                if terrain not in ("grass", "hill"):
                    forest_row.append(False)
                    continue

                value = forest_noise([x / forest_scale, y / forest_scale])
                value = (value + 1) / 2
                value = max(0.0, min(1.0, value))

                if terrain == "hill":
                    value -= 0.15

                forest_row.append(value > 0.58)

            self.forest_map.append(forest_row)

    def generate_noise(self):
        noise = PerlinNoise(octaves=5, seed=self.seed)
        scale = 450.0

        self.heightmap.clear()
        self.terrain_map.clear()

        for y in range(self.rows):
            height_row = []
            terrain_row = []

            for x in range(self.cols):
                layer1 = noise([x / scale, y / scale])
                layer2 = noise([x / (scale / 4), y / (scale / 4)]) * 0.35
                layer3 = noise([x / (scale / 16), y / (scale / 16)]) * 0.15

                value = (layer1 + layer2 + layer3) / 1.5

                # Normalize from roughly [-1, 1] to [0, 1]
                height = (value + 1) / 2
                height = max(0.0, min(1.0, height))

                terrain = self.get_terrain_type(height)

                height_row.append(height)
                terrain_row.append(terrain)

            self.heightmap.append(height_row)
            self.terrain_map.append(terrain_row)

    def get_terrain_type(self, height):
        if height < 0.38:
            return "deep_water"
        elif height < 0.44:
            return "shallow_water"
        elif height < 0.46:
            return "sand"
        elif height < 0.70:
            return "grass"
        elif height < 0.82:
            return "hill"
        else:
            return "mountain"

    def get_terrain_color(self, terrain, height):
        if terrain == "deep_water":
            return (0, 0, 120)
        elif terrain == "shallow_water":
            return (30, 80, 180)
        elif terrain == "sand":
            return (194, 178, 128)
        elif terrain == "grass":
            green = int(100 + height * 100)
            return (20, green, 20)
        elif terrain == "hill":
            return (100, 120, 80)
        elif terrain == "mountain":
            shade = int(180 + height * 50)
            shade = min(255, shade)
            return (shade, shade, shade)

        return (255, 0, 255)  # fallback/debug color

    def get_forest_color(self, terrain):
        if terrain == "grass":
            return (20, 90, 20)
        elif terrain == "hill":
            return (30, 80, 30)
        return None

    def update(self, dt):
        pass

    def draw(self, surface, camera):
        visible = camera.visible_rect()

        start_col = max(0, visible.left // self.tile_size)
        end_col = min(self.cols, (visible.right // self.tile_size) + 1)

        start_row = max(0, visible.top // self.tile_size)
        end_row = min(self.rows, (visible.bottom // self.tile_size) + 1)

        for y in range(start_row, end_row):
            for x in range(start_col, end_col):
                height = self.heightmap[y][x]
                terrain = self.terrain_map[y][x]
                color = self.get_terrain_color(terrain, height)

                world_rect = pygame.Rect(
                    x * self.tile_size,
                    y * self.tile_size,
                    self.tile_size,
                    self.tile_size,
                )

                screen_rect = camera.apply_rect(world_rect)

                # Expand slightly to hide gaps
                screen_rect.width += 1
                screen_rect.height += 1

                pygame.draw.rect(surface, color, screen_rect)


                if self.forest_map[y][x]:
                    forest_color = self.get_forest_color(terrain)
                    if forest_color is not None:
                        pygame.draw.rect(surface, forest_color, screen_rect)