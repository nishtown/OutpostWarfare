import random

import pygame
from perlin_noise import PerlinNoise

from settings import *
from scene import Scene
from tree import Tree


class World():
    def __init__(self, main, seed=1, tile_size=16):
        super().__init__()
        self.main = main
        self.font = pygame.font.SysFont(None, 60)
        random.seed()
        self.seed = random.randint(1, 100000)
        self.tile_size = tile_size
        self.cols = MAP_WIDTH // self.tile_size
        self.rows = MAP_HEIGHT // self.tile_size
        self.world_width = MAP_WIDTH
        self.world_height = MAP_HEIGHT

        self.noise_surface = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT))
        self.blend_subdivisions = 2

        self.minimap_surface = None

        self.heightmap = []
        self.terrain_map = []
        self.forest_map = []
        self.forest_density_map = []
        self.trees = []
        self.trees_by_tile = {}
        self.blocked_terrain = {"deep_water", "shallow_water"}

        self.generate_noise()
        self.generate_forests()
        self.generate_trees()
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
        cluster_noise = PerlinNoise(octaves=6, seed=self.seed + 1337)
        forest_scale = 100.0
        cluster_scale = 38.0

        self.forest_map.clear()
        self.forest_density_map.clear()

        for y in range(self.rows):
            forest_row = []
            density_row = []

            for x in range(self.cols):
                terrain = self.terrain_map[y][x]

                if terrain not in ("grass", "hill"):
                    forest_row.append(False)
                    density_row.append(0.0)
                    continue

                value = forest_noise([x / forest_scale, y / forest_scale])
                cluster_value = cluster_noise([x / cluster_scale, y / cluster_scale])

                value = max(0.0, min(1.0, (value + 1) / 2))
                cluster_value = max(0.0, min(1.0, (cluster_value + 1) / 2))
                density = (value * 0.55) + (cluster_value * 0.45)

                if terrain == "hill":
                    density -= 0.12

                density = max(0.0, min(1.0, density))
                forest_row.append(density > 0.52)
                density_row.append(density)

            self.forest_map.append(forest_row)
            self.forest_density_map.append(density_row)

    def choose_tree_variant(self, tree_count, density, tree_index):
        if tree_count == 1:
            dead_tree_chance = 0.07 + max(0.0, 0.58 - density) * 0.18
            if random.random() < dead_tree_chance:
                return "treeDead.png"
        elif tree_index == 0 and density < 0.62 and random.random() < 0.01:
            return "treeDead.png"

        return None

    def generate_trees(self):
        self.trees.clear()
        self.trees_by_tile.clear()

        for y in range(self.rows):
            for x in range(self.cols):
                if not self.forest_map[y][x]:
                    continue

                density = self.forest_density_map[y][x]
                tree_count = 1
                if density > 0.60:
                    tree_count += 1
                if density > 0.68:
                    tree_count += 1
                if density > 0.76:
                    tree_count += 1
                if random.random() < max(0.0, density - 0.55):
                    tree_count += 1

                tile_trees = []
                for tree_index in range(tree_count):
                    tree_x = (x * self.tile_size) + random.randint(1, self.tile_size - 1)
                    tree_y = (y * self.tile_size) + random.randint(self.tile_size // 2, self.tile_size + 4)

                    variant = self.choose_tree_variant(tree_count, density, tree_index)
                    tree = Tree(self.main, tree_x, tree_y, variant=variant)
                    tile_trees.append(tree)
                    self.trees.append(tree)

                self.trees_by_tile[(x, y)] = tile_trees

        self.trees.sort(key=lambda tree: tree.rect.bottom)

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

    def blend_colors(self, color_a, color_b, amount):
        amount = max(0.0, min(1.0, amount))
        return (
            int(color_a[0] + (color_b[0] - color_a[0]) * amount),
            int(color_a[1] + (color_b[1] - color_a[1]) * amount),
            int(color_a[2] + (color_b[2] - color_a[2]) * amount),
        )

    def get_tile_draw_color(self, x, y):
        height = self.heightmap[y][x]
        terrain = self.terrain_map[y][x]
        color = self.get_terrain_color(terrain, height)

        if self.forest_map[y][x]:
            forest_color = self.get_forest_color(terrain)
            if forest_color is not None:
                color = self.blend_colors(color, forest_color, 0.35)

        return color

    def draw_blended_tile(self, surface, world_rect, screen_rect, x, y):
        c00 = self.get_tile_draw_color(x, y)
        c10 = self.get_tile_draw_color(min(x + 1, self.cols - 1), y)
        c01 = self.get_tile_draw_color(x, min(y + 1, self.rows - 1))
        c11 = self.get_tile_draw_color(min(x + 1, self.cols - 1), min(y + 1, self.rows - 1))

        steps = max(1, self.blend_subdivisions)
        step_w = max(1, world_rect.width // steps)
        step_h = max(1, world_rect.height // steps)

        for sy in range(steps):
            ty = (sy + 0.5) / steps
            for sx in range(steps):
                tx = (sx + 0.5) / steps
                top = self.blend_colors(c00, c10, tx)
                bottom = self.blend_colors(c01, c11, tx)
                color = self.blend_colors(top, bottom, ty)

                sub_rect = pygame.Rect(
                    screen_rect.x + sx * step_w,
                    screen_rect.y + sy * step_h,
                    step_w + 1,
                    step_h + 1,
                )
                pygame.draw.rect(surface, color, sub_rect)

    def get_nearby_trees(self, position, radius):
        radius_sq = radius * radius
        nearby = []

        for tree in self.trees:
            if tree.is_depleted:
                continue
            if (tree.pos - position).length_squared() <= radius_sq:
                nearby.append(tree)

        nearby.sort(key=lambda tree: (tree.pos - position).length_squared())
        return nearby

    def is_rect_in_bounds(self, rect):
        return (
            rect.left >= 0
            and rect.top >= 0
            and rect.right <= self.world_width
            and rect.bottom <= self.world_height
        )

    def is_rect_on_blocked_terrain(self, rect):
        if not self.is_rect_in_bounds(rect):
            return True

        start_col = max(0, rect.left // self.tile_size)
        end_col = min(self.cols - 1, rect.right // self.tile_size)
        start_row = max(0, rect.top // self.tile_size)
        end_row = min(self.rows - 1, rect.bottom // self.tile_size)

        for y in range(start_row, end_row + 1):
            for x in range(start_col, end_col + 1):
                if self.terrain_map[y][x] in self.blocked_terrain:
                    return True

        return False

    def is_rect_blocked_by_trees(self, rect):
        for tree in self.trees:
            if not tree.is_depleted and tree.blocking_rect.colliderect(rect):
                return True
        return False

    def is_rect_walkable(self, rect):
        return not self.is_rect_on_blocked_terrain(rect) and not self.is_rect_blocked_by_trees(rect)

    def find_nearest_walkable_position(self, position, rect_size):
        test_rect = pygame.Rect(0, 0, rect_size[0], rect_size[1])
        test_rect.center = (int(position.x), int(position.y))
        if self.is_rect_walkable(test_rect):
            return pygame.Vector2(position)

        max_radius = self.tile_size * 12
        for radius in range(self.tile_size, max_radius + self.tile_size, self.tile_size):
            for offset_y in range(-radius, radius + self.tile_size, self.tile_size):
                for offset_x in range(-radius, radius + self.tile_size, self.tile_size):
                    test_pos = pygame.Vector2(position.x + offset_x, position.y + offset_y)
                    test_rect.center = (int(test_pos.x), int(test_pos.y))
                    if self.is_rect_walkable(test_rect):
                        return test_pos

        return pygame.Vector2(position)

    def remove_tree(self, tree):
        if tree in self.trees:
            self.trees.remove(tree)

        tile_x = int(tree.pos.x // self.tile_size)
        tile_y = int(tree.pos.y // self.tile_size)
        tile_key = (tile_x, tile_y)
        if tile_key in self.trees_by_tile and tree in self.trees_by_tile[tile_key]:
            self.trees_by_tile[tile_key].remove(tree)
            if not self.trees_by_tile[tile_key]:
                del self.trees_by_tile[tile_key]

    def update(self, dt):
        for tree in self.trees[:]:
            tree.update(dt)
            if tree.is_depleted:
                self.remove_tree(tree)

    def get_visible_rect(self, camera=None):
        if camera is None:
            return pygame.Rect(0, 0, SCREEN_WIDTH, SCREEN_HEIGHT)
        return camera.visible_rect()

    def draw_ground(self, surface, camera=None):
        visible = self.get_visible_rect(camera)

        start_col = max(0, visible.left // self.tile_size)
        end_col = min(self.cols, (visible.right // self.tile_size) + 1)

        start_row = max(0, visible.top // self.tile_size)
        end_row = min(self.rows, (visible.bottom // self.tile_size) + 1)

        for y in range(start_row, end_row):
            for x in range(start_col, end_col):
                world_rect = pygame.Rect(
                    x * self.tile_size,
                    y * self.tile_size,
                    self.tile_size,
                    self.tile_size,
                )

                screen_rect = world_rect if camera is None else camera.apply_rect(world_rect)
                self.draw_blended_tile(surface, world_rect, screen_rect, x, y)

    def draw_trees(self, surface, camera=None):
        visible = self.get_visible_rect(camera)
        for tree in self.trees:
            if visible.colliderect(tree.rect):
                tree.draw(surface)

    def draw(self, surface, camera=None):
        self.draw_ground(surface, camera)
        self.draw_trees(surface, camera)