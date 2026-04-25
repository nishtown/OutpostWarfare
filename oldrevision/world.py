import math
import random
import time
from concurrent.futures import ProcessPoolExecutor

import pygame
from perlin_noise import PerlinNoise

from oldrevision.settings import *
from oldrevision.rock import Rock
from oldrevision.tree import Tree


_NOISE_CACHE = {}


def _clamp01(value):
    return max(0.0, min(1.0, value))


def _get_noise_bundle(seed):
    bundle = _NOISE_CACHE.get(seed)
    if bundle is None:
        bundle = (
            PerlinNoise(octaves=5, seed=seed),
            PerlinNoise(octaves=3, seed=seed + 999),
            PerlinNoise(octaves=6, seed=seed + 1337),
        )
        _NOISE_CACHE[seed] = bundle
    return bundle


def _get_terrain_type(height):
    if height < 0.38:
        return "deep_water"
    if height < 0.44:
        return "shallow_water"
    if height < 0.46:
        return "sand"
    if height < 0.70:
        return "grass"
    if height < 0.82:
        return "hill"
    return "mountain"


def _blend_colors(color_a, color_b, amount):
    amount = _clamp01(amount)
    return (
        int(color_a[0] + (color_b[0] - color_a[0]) * amount),
        int(color_a[1] + (color_b[1] - color_a[1]) * amount),
        int(color_a[2] + (color_b[2] - color_a[2]) * amount),
    )


def _get_terrain_color(terrain, height):
    if terrain == "deep_water":
        return (0, 0, 120)
    if terrain == "shallow_water":
        return (30, 80, 180)
    if terrain == "sand":
        return (194, 178, 128)
    if terrain == "grass":
        green = int(100 + height * 100)
        return (20, green, 20)
    if terrain == "hill":
        return (100, 120, 80)

    shade = int(180 + height * 50)
    return (min(255, shade), min(255, shade), min(255, shade))


def _get_forest_color(terrain):
    if terrain == "grass":
        return (20, 90, 20)
    if terrain == "hill":
        return (30, 80, 30)
    return None


def _get_tile_info(seed, tile_x, tile_y):
    terrain_noise, _, _ = _get_noise_bundle(seed)
    scale = 450.0
    layer1 = terrain_noise([tile_x / scale, tile_y / scale])
    layer2 = terrain_noise([tile_x / (scale / 4), tile_y / (scale / 4)]) * 0.35
    layer3 = terrain_noise([tile_x / (scale / 16), tile_y / (scale / 16)]) * 0.15

    value = (layer1 + layer2 + layer3) / 1.5
    height = _clamp01((value + 1) / 2)
    terrain = _get_terrain_type(height)
    return height, terrain


def _get_forest_density(seed, tile_x, tile_y, terrain):
    if terrain not in ("grass", "hill"):
        return 0.0

    _, forest_noise, cluster_noise = _get_noise_bundle(seed)
    forest_scale = 100.0
    cluster_scale = 38.0
    value = forest_noise([tile_x / forest_scale, tile_y / forest_scale])
    cluster_value = cluster_noise([tile_x / cluster_scale, tile_y / cluster_scale])

    value = _clamp01((value + 1) / 2)
    cluster_value = _clamp01((cluster_value + 1) / 2)
    density = (value * 0.55) + (cluster_value * 0.45)

    if terrain == "hill":
        density -= 0.12

    return _clamp01(density)


def _get_rock_density(seed, tile_x, tile_y, terrain):
    if terrain not in ("grass", "hill", "mountain"):
        return 0.0

    _, forest_noise, cluster_noise = _get_noise_bundle(seed)
    ridge = _clamp01((cluster_noise([tile_x / 52.0, tile_y / 52.0]) + 1) / 2)
    scatter = _clamp01((forest_noise([tile_x / 150.0, tile_y / 150.0]) + 1) / 2)
    density = (ridge * 0.7) + (scatter * 0.3)

    if terrain == "grass":
        density -= 0.26
    elif terrain == "hill":
        density += 0.08
    else:
        density += 0.28

    return _clamp01(density)


def _choose_tree_variant(tree_count, density, tree_index, rng):
    if tree_count == 1:
        dead_tree_chance = 0.07 + max(0.0, 0.58 - density) * 0.18
        if rng.random() < dead_tree_chance:
            return "treeDead.png"
    elif tree_index == 0 and density < 0.62 and rng.random() < 0.01:
        return "treeDead.png"

    return None


def _build_chunk_data(seed, tile_size, chunk_size_tiles, chunk_key):
    rng_seed = (seed * 1000003) ^ (chunk_key[0] * 92837111) ^ (chunk_key[1] * 689287499)
    rng = random.Random(rng_seed)

    chunk_x, chunk_y = chunk_key
    start_tile_x = chunk_x * chunk_size_tiles
    start_tile_y = chunk_y * chunk_size_tiles

    tile_colors = []
    tree_specs = []
    rock_specs = []
    best_rock_candidate = None
    best_rock_density = 0.0

    for local_y in range(chunk_size_tiles + 1):
        color_row = []
        for local_x in range(chunk_size_tiles + 1):
            tile_x = start_tile_x + local_x
            tile_y = start_tile_y + local_y
            height, terrain = _get_tile_info(seed, tile_x, tile_y)
            color = _get_terrain_color(terrain, height)

            density = _get_forest_density(seed, tile_x, tile_y, terrain)
            rock_density = _get_rock_density(seed, tile_x, tile_y, terrain)
            if local_x < chunk_size_tiles and local_y < chunk_size_tiles and rock_density > best_rock_density:
                best_rock_density = rock_density
                best_rock_candidate = (tile_x, tile_y)
            if density > 0.52:
                forest_color = _get_forest_color(terrain)
                if forest_color is not None:
                    color = _blend_colors(color, forest_color, 0.35)

            color_row.append(color)

            if local_x >= chunk_size_tiles or local_y >= chunk_size_tiles:
                continue

            if density > 0.52:
                tree_count = 1
                if density > 0.60:
                    tree_count += 1
                if density > 0.68:
                    tree_count += 1
                if density > 0.76:
                    tree_count += 1
                if rng.random() < max(0.0, density - 0.55):
                    tree_count += 1

                for tree_index in range(tree_count):
                    tree_x = (tile_x * tile_size) + rng.randint(1, tile_size - 1)
                    tree_y = (tile_y * tile_size) + rng.randint(tile_size // 2, tile_size + 4)
                    variant = _choose_tree_variant(tree_count, density, tree_index, rng)
                    tree_specs.append((tree_x, tree_y, variant))

            if rock_density > 0.48:
                rock_count = 1
                if terrain == "mountain" and rock_density > 0.68:
                    rock_count += 1
                if rng.random() < max(0.0, rock_density - 0.58):
                    rock_count += 1

                for _ in range(rock_count):
                    rock_x = (tile_x * tile_size) + rng.randint(2, tile_size - 2)
                    rock_y = (tile_y * tile_size) + rng.randint(tile_size // 2, tile_size + 2)
                    rock_scale = round(rng.uniform(0.95, 1.45), 2)
                    rock_variant = rng.choice(Rock.asset_names)
                    rock_specs.append((rock_x, rock_y, rock_scale, rock_variant))

        tile_colors.append(color_row)

    if not rock_specs and best_rock_candidate is not None and best_rock_density > 0.34:
        tile_x, tile_y = best_rock_candidate
        rock_x = (tile_x * tile_size) + rng.randint(2, tile_size - 2)
        rock_y = (tile_y * tile_size) + rng.randint(tile_size // 2, tile_size + 2)
        rock_scale = round(rng.uniform(0.98, 1.3), 2)
        rock_variant = rng.choice(Rock.asset_names)
        rock_specs.append((rock_x, rock_y, rock_scale, rock_variant))

    return {"tile_colors": tile_colors, "tree_specs": tree_specs, "rock_specs": rock_specs}


class World:
    def __init__(self, main, seed=1, tile_size=16, chunk_size_tiles=32):
        super().__init__()
        self.main = main
        self.font = pygame.font.SysFont(None, 60)
        random.seed()
        self.seed = random.randint(1, 100000) if seed == 1 else seed
        self.tile_size = tile_size
        self.chunk_size_tiles = chunk_size_tiles
        self.chunk_pixel_size = self.chunk_size_tiles * self.tile_size
        self.blend_subdivisions = 2
        self.buffer_multiplier = 2.25
        self.retention_multiplier = 2.75
        self.lead_buffer_multiplier = 1.25
        self.chunk_finalize_budget_ms = 0.8
        self.chunk_finalize_tile_batch = 8
        self.max_active_chunk_builds = 3
        self.blocked_terrain = {"deep_water", "shallow_water"}

        self.chunk_cache = {}
        self.pending_chunk_jobs = {}
        self.completed_chunk_data = {}
        self.chunk_build_states = {}
        self.loaded_chunk_keys = set()
        self.last_focus_position = None
        self.chunk_executor = ProcessPoolExecutor(max_workers=1)
        self.minimap_surface = pygame.Surface((1, 1))

    def handle_event(self, event):
        pass

    def get_scaled_minimap(self, width, height):
        return pygame.transform.smoothscale(self.minimap_surface, (width, height))

    def get_chunk_key_for_position(self, position):
        return (
            math.floor(position.x / self.chunk_pixel_size),
            math.floor(position.y / self.chunk_pixel_size),
        )

    def get_chunk_rect(self, chunk_key):
        return pygame.Rect(
            chunk_key[0] * self.chunk_pixel_size,
            chunk_key[1] * self.chunk_pixel_size,
            self.chunk_pixel_size,
            self.chunk_pixel_size,
        )

    def iter_chunk_keys_for_rect(self, rect):
        start_x = math.floor(rect.left / self.chunk_pixel_size)
        end_x = math.floor((rect.right - 1) / self.chunk_pixel_size)
        start_y = math.floor(rect.top / self.chunk_pixel_size)
        end_y = math.floor((rect.bottom - 1) / self.chunk_pixel_size)

        for chunk_y in range(start_y, end_y + 1):
            for chunk_x in range(start_x, end_x + 1):
                yield chunk_x, chunk_y

    def get_tile_info(self, tile_x, tile_y):
        return _get_tile_info(self.seed, tile_x, tile_y)

    def get_forest_density(self, tile_x, tile_y, terrain):
        return _get_forest_density(self.seed, tile_x, tile_y, terrain)

    def choose_tree_variant(self, tree_count, density, tree_index, rng):
        return _choose_tree_variant(tree_count, density, tree_index, rng)

    def build_chunk_data(self, chunk_key):
        return _build_chunk_data(self.seed, self.tile_size, self.chunk_size_tiles, chunk_key)

    def build_chunk_trees(self, chunk_key, tree_specs):
        trees = []
        for tree_x, tree_y, variant in tree_specs:
            tree = Tree(self.main, tree_x, tree_y, variant=variant)
            tree.chunk_key = chunk_key
            trees.append(tree)

        trees.sort(key=lambda tree: tree.rect.bottom)
        return trees

    def build_chunk_rocks(self, chunk_key, rock_specs):
        rocks = []
        for rock_x, rock_y, scale, variant in rock_specs:
            rock = Rock(self.main, rock_x, rock_y, scale=scale, variant=variant)
            rock.chunk_key = chunk_key
            rocks.append(rock)

        rocks.sort(key=lambda rock: rock.rect.bottom)
        return rocks

    def build_chunk_item_bounds(self, chunk_key, items):
        if not items:
            return self.get_chunk_rect(chunk_key)

        bounds = items[0].rect.copy()
        for item in items[1:]:
            bounds.union_ip(item.rect)
        return bounds

    def build_chunk_surface(self, tile_colors):
        surface = pygame.Surface((self.chunk_pixel_size, self.chunk_pixel_size))
        steps = max(1, self.blend_subdivisions)
        step_w = max(1, self.tile_size // steps)
        step_h = max(1, self.tile_size // steps)

        for tile_y in range(self.chunk_size_tiles):
            for tile_x in range(self.chunk_size_tiles):
                c00 = tile_colors[tile_y][tile_x]
                c10 = tile_colors[tile_y][tile_x + 1]
                c01 = tile_colors[tile_y + 1][tile_x]
                c11 = tile_colors[tile_y + 1][tile_x + 1]
                base_x = tile_x * self.tile_size
                base_y = tile_y * self.tile_size

                for sub_y in range(steps):
                    ty = (sub_y + 0.5) / steps
                    for sub_x in range(steps):
                        tx = (sub_x + 0.5) / steps
                        top = self.blend_colors(c00, c10, tx)
                        bottom = self.blend_colors(c01, c11, tx)
                        color = self.blend_colors(top, bottom, ty)
                        surface.fill(
                            color,
                            pygame.Rect(
                                base_x + sub_x * step_w,
                                base_y + sub_y * step_h,
                                step_w + 1,
                                step_h + 1,
                            ),
                        )

        return surface

    def create_chunk_build_state(self, chunk_key, chunk_data):
        center_index = self.chunk_size_tiles // 2
        fallback_color = chunk_data["tile_colors"][center_index][center_index]
        surface = pygame.Surface((self.chunk_pixel_size, self.chunk_pixel_size))
        surface.fill(fallback_color)
        trees = self.build_chunk_trees(chunk_key, chunk_data["tree_specs"])
        rocks = self.build_chunk_rocks(chunk_key, chunk_data["rock_specs"])
        return {
            "surface": surface,
            "trees": trees,
            "rocks": rocks,
            "tree_bounds": self.build_chunk_item_bounds(chunk_key, trees),
            "rock_bounds": self.build_chunk_item_bounds(chunk_key, rocks),
            "tile_colors": chunk_data["tile_colors"],
            "tile_index": 0,
        }

    def finalize_chunk(self, chunk_key, chunk_data):
        trees = self.build_chunk_trees(chunk_key, chunk_data["tree_specs"])
        rocks = self.build_chunk_rocks(chunk_key, chunk_data["rock_specs"])
        return {
            "surface": self.build_chunk_surface(chunk_data["tile_colors"]),
            "trees": trees,
            "rocks": rocks,
            "tree_bounds": self.build_chunk_item_bounds(chunk_key, trees),
            "rock_bounds": self.build_chunk_item_bounds(chunk_key, rocks),
        }

    def begin_chunk_finalization(self, chunk_key, chunk_data):
        if chunk_key in self.chunk_cache or chunk_key in self.chunk_build_states:
            return

        self.chunk_build_states[chunk_key] = self.create_chunk_build_state(chunk_key, chunk_data)

    def finalize_chunk_step(self, chunk_key, chunk_state):
        steps = max(1, self.blend_subdivisions)
        step_w = max(1, self.tile_size // steps)
        step_h = max(1, self.tile_size // steps)
        total_tiles = self.chunk_size_tiles * self.chunk_size_tiles
        tiles_processed = 0
        tile_colors = chunk_state["tile_colors"]
        surface = chunk_state["surface"]

        while chunk_state["tile_index"] < total_tiles and tiles_processed < self.chunk_finalize_tile_batch:
            tile_index = chunk_state["tile_index"]
            tile_x = tile_index % self.chunk_size_tiles
            tile_y = tile_index // self.chunk_size_tiles
            c00 = tile_colors[tile_y][tile_x]
            c10 = tile_colors[tile_y][tile_x + 1]
            c01 = tile_colors[tile_y + 1][tile_x]
            c11 = tile_colors[tile_y + 1][tile_x + 1]
            base_x = tile_x * self.tile_size
            base_y = tile_y * self.tile_size

            for sub_y in range(steps):
                ty = (sub_y + 0.5) / steps
                for sub_x in range(steps):
                    tx = (sub_x + 0.5) / steps
                    top = self.blend_colors(c00, c10, tx)
                    bottom = self.blend_colors(c01, c11, tx)
                    color = self.blend_colors(top, bottom, ty)
                    surface.fill(
                        color,
                        pygame.Rect(
                            base_x + sub_x * step_w,
                            base_y + sub_y * step_h,
                            step_w + 1,
                            step_h + 1,
                        ),
                    )

            chunk_state["tile_index"] += 1
            tiles_processed += 1

        if chunk_state["tile_index"] >= total_tiles:
            self.chunk_cache[chunk_key] = {
                "surface": chunk_state["surface"],
                "trees": chunk_state["trees"],
                "rocks": chunk_state["rocks"],
                "tree_bounds": chunk_state["tree_bounds"],
                "rock_bounds": chunk_state["rock_bounds"],
            }
            del self.chunk_build_states[chunk_key]

    def get_focus_position(self, camera=None, tracked_entities=None):
        if tracked_entities:
            focus = tracked_entities[0].pos if hasattr(tracked_entities[0], "pos") else tracked_entities[0]
            return pygame.Vector2(focus)

        visible = self.get_visible_rect(camera)
        return pygame.Vector2(visible.centerx, visible.centery)

    def get_chunk_priority(self, chunk_key, focus_position):
        center_x = (chunk_key[0] + 0.5) * self.chunk_pixel_size
        center_y = (chunk_key[1] + 0.5) * self.chunk_pixel_size
        delta_x = center_x - focus_position.x
        delta_y = center_y - focus_position.y
        return (delta_x * delta_x) + (delta_y * delta_y)

    def process_chunk_finalization(self, camera=None, tracked_entities=None):
        if not self.completed_chunk_data and not self.chunk_build_states:
            return

        focus_position = self.get_focus_position(camera, tracked_entities)
        deadline = time.perf_counter() + (self.chunk_finalize_budget_ms / 1000.0)

        ready_keys = sorted(
            [chunk_key for chunk_key in self.completed_chunk_data if chunk_key in self.loaded_chunk_keys],
            key=lambda chunk_key: self.get_chunk_priority(chunk_key, focus_position),
        )
        while (
            ready_keys
            and len(self.chunk_build_states) < self.max_active_chunk_builds
            and time.perf_counter() < deadline
        ):
            chunk_key = ready_keys.pop(0)
            chunk_data = self.completed_chunk_data.pop(chunk_key, None)
            if chunk_data is None:
                continue
            self.begin_chunk_finalization(chunk_key, chunk_data)

        active_keys = sorted(
            [chunk_key for chunk_key in self.chunk_build_states if chunk_key in self.loaded_chunk_keys],
            key=lambda chunk_key: self.get_chunk_priority(chunk_key, focus_position),
        )[: self.max_active_chunk_builds]
        while active_keys and time.perf_counter() < deadline:
            for chunk_key in active_keys:
                if time.perf_counter() >= deadline:
                    return
                chunk_state = self.chunk_build_states.get(chunk_key)
                if chunk_state is None:
                    continue
                self.finalize_chunk_step(chunk_key, chunk_state)

            active_keys = sorted(
                [chunk_key for chunk_key in self.chunk_build_states if chunk_key in self.loaded_chunk_keys],
                key=lambda chunk_key: self.get_chunk_priority(chunk_key, focus_position),
            )[: self.max_active_chunk_builds]

    def get_available_chunk(self, chunk_key):
        chunk = self.chunk_cache.get(chunk_key)
        if chunk is not None:
            return chunk
        return self.chunk_build_states.get(chunk_key)

    def queue_chunk_generation(self, chunk_key):
        if (
            chunk_key in self.chunk_cache
            or chunk_key in self.pending_chunk_jobs
            or chunk_key in self.completed_chunk_data
            or chunk_key in self.chunk_build_states
        ):
            return
        self.pending_chunk_jobs[chunk_key] = self.chunk_executor.submit(
            _build_chunk_data,
            self.seed,
            self.tile_size,
            self.chunk_size_tiles,
            chunk_key,
        )

    def load_chunk_immediately(self, chunk_key):
        if chunk_key in self.chunk_cache:
            return self.chunk_cache[chunk_key]

        future = self.pending_chunk_jobs.pop(chunk_key, None)
        if future is not None:
            chunk_data = future.result()
        else:
            chunk_data = self.build_chunk_data(chunk_key)

        chunk = self.finalize_chunk(chunk_key, chunk_data)
        self.chunk_cache[chunk_key] = chunk
        return chunk

    def pump_completed_chunks(self, max_chunks_per_frame=2):
        completed = []
        for chunk_key, future in self.pending_chunk_jobs.items():
            if future.done():
                completed.append(chunk_key)
            if len(completed) >= max_chunks_per_frame:
                break

        for chunk_key in completed:
            future = self.pending_chunk_jobs.pop(chunk_key)
            self.completed_chunk_data[chunk_key] = future.result()

    def prime(self, camera=None, tracked_entities=None):
        focus_position = self.get_focus_position(camera, tracked_entities)
        wanted_keys = self.compute_wanted_chunk_keys(camera, tracked_entities, focus_position=focus_position)
        for chunk_key in wanted_keys:
            self.load_chunk_immediately(chunk_key)
        self.loaded_chunk_keys = wanted_keys
        self.last_focus_position = pygame.Vector2(focus_position)

    def compute_wanted_chunk_keys(self, camera=None, tracked_entities=None, buffer_multiplier=None, focus_position=None, reference_focus_position=None):
        visible = self.get_visible_rect(camera)
        buffer_multiplier = self.buffer_multiplier if buffer_multiplier is None else buffer_multiplier
        focus_position = self.get_focus_position(camera, tracked_entities) if focus_position is None else pygame.Vector2(focus_position)
        reference_focus_position = self.last_focus_position if reference_focus_position is None else reference_focus_position
        buffer_rect = visible.inflate(
            int(SCREEN_WIDTH * buffer_multiplier),
            int(SCREEN_HEIGHT * buffer_multiplier),
        )

        if reference_focus_position is not None:
            travel_vector = focus_position - reference_focus_position
            lead_offset = pygame.Vector2()
            if abs(travel_vector.x) > 1:
                lead_offset.x = math.copysign(SCREEN_WIDTH * self.lead_buffer_multiplier, travel_vector.x)
            if abs(travel_vector.y) > 1:
                lead_offset.y = math.copysign(SCREEN_HEIGHT * self.lead_buffer_multiplier, travel_vector.y)
            if lead_offset.length_squared() > 0:
                buffer_rect = buffer_rect.union(buffer_rect.move(int(lead_offset.x), int(lead_offset.y)))

        wanted_keys = set(self.iter_chunk_keys_for_rect(buffer_rect))

        if tracked_entities is not None:
            for entity in tracked_entities:
                pos = entity.pos if hasattr(entity, "pos") else entity
                wanted_keys.add(self.get_chunk_key_for_position(pos))

        return wanted_keys

    def refresh_loaded_chunks(self, camera=None, tracked_entities=None):
        focus_position = self.get_focus_position(camera, tracked_entities)
        reference_focus_position = self.last_focus_position
        wanted_keys = self.compute_wanted_chunk_keys(
            camera,
            tracked_entities,
            buffer_multiplier=self.buffer_multiplier,
            focus_position=focus_position,
            reference_focus_position=reference_focus_position,
        )
        retained_keys = self.compute_wanted_chunk_keys(
            camera,
            tracked_entities,
            buffer_multiplier=self.retention_multiplier,
            focus_position=focus_position,
            reference_focus_position=reference_focus_position,
        )

        for chunk_key in wanted_keys:
            if not self.loaded_chunk_keys:
                self.load_chunk_immediately(chunk_key)
            else:
                self.queue_chunk_generation(chunk_key)

        for chunk_key in list(self.chunk_cache.keys()):
            if chunk_key not in retained_keys:
                del self.chunk_cache[chunk_key]

        for chunk_key in list(self.pending_chunk_jobs.keys()):
            if chunk_key not in retained_keys:
                future = self.pending_chunk_jobs.pop(chunk_key)
                future.cancel()

        for chunk_key in list(self.completed_chunk_data.keys()):
            if chunk_key not in retained_keys:
                del self.completed_chunk_data[chunk_key]

        for chunk_key in list(self.chunk_build_states.keys()):
            if chunk_key not in retained_keys:
                del self.chunk_build_states[chunk_key]

        self.loaded_chunk_keys = wanted_keys
        self.last_focus_position = pygame.Vector2(focus_position)

    def get_terrain_type(self, height):
        return _get_terrain_type(height)

    def get_terrain_color(self, terrain, height):
        return _get_terrain_color(terrain, height)

    def get_forest_color(self, terrain):
        return _get_forest_color(terrain)

    def blend_colors(self, color_a, color_b, amount):
        return _blend_colors(color_a, color_b, amount)

    def refresh_chunk_tree_metadata(self, chunk_key, chunk):
        chunk["tree_bounds"] = self.build_chunk_item_bounds(chunk_key, chunk["trees"])

    def refresh_chunk_rock_metadata(self, chunk_key, chunk):
        chunk["rock_bounds"] = self.build_chunk_item_bounds(chunk_key, chunk["rocks"])

    def add_tree(self, tree):
        chunk_key = self.get_chunk_key_for_position(tree.pos)
        chunk = self.get_available_chunk(chunk_key)
        if chunk is None:
            chunk = self.load_chunk_immediately(chunk_key)

        tree.chunk_key = chunk_key
        chunk["trees"].append(tree)
        chunk["trees"].sort(key=lambda item: item.rect.bottom)
        self.refresh_chunk_tree_metadata(chunk_key, chunk)
        return tree

    def can_place_tree(self, tree, ignore_building=None):
        if self.is_rect_on_blocked_terrain(tree.blocking_rect):
            return False

        game = getattr(self.main, "game", None)
        if game is not None:
            if game.player.get_collision_rect().colliderect(tree.blocking_rect):
                return False

            for building in game.buildings:
                if building is ignore_building:
                    continue
                if building.rect.colliderect(tree.blocking_rect):
                    return False

        search_rect = tree.blocking_rect.inflate(self.tile_size * 2, self.tile_size * 2)
        for chunk_key in self.iter_chunk_keys_for_rect(search_rect):
            chunk = self.get_available_chunk(chunk_key)
            if chunk is None:
                continue

            for existing_tree in chunk["trees"]:
                if existing_tree.blocking_rect.colliderect(tree.blocking_rect):
                    return False

            for rock in chunk["rocks"]:
                if rock.blocking_rect.colliderect(tree.blocking_rect):
                    return False

        return True

    def get_nearby_resource_nodes(self, position, radius):
        search_rect = pygame.Rect(int(position.x - radius), int(position.y - radius), int(radius * 2), int(radius * 2))
        nearby = []

        for chunk_key in self.iter_chunk_keys_for_rect(search_rect):
            chunk = self.get_available_chunk(chunk_key)
            if chunk is None:
                self.queue_chunk_generation(chunk_key)
                continue

            for tree in chunk["trees"]:
                if not tree.can_harvest():
                    continue
                if (tree.pos - position).length_squared() <= radius * radius:
                    nearby.append(tree)

            for rock in chunk["rocks"]:
                if not rock.can_harvest():
                    continue
                if (rock.pos - position).length_squared() <= radius * radius:
                    nearby.append(rock)

        nearby.sort(key=lambda item: (item.pos - position).length_squared())
        return nearby

    def get_nearby_trees(self, position, radius):
        search_rect = pygame.Rect(int(position.x - radius), int(position.y - radius), int(radius * 2), int(radius * 2))
        nearby = []

        for chunk_key in self.iter_chunk_keys_for_rect(search_rect):
            chunk = self.get_available_chunk(chunk_key)
            if chunk is None:
                self.queue_chunk_generation(chunk_key)
                continue

            for tree in chunk["trees"]:
                if not tree.can_harvest():
                    continue
                if (tree.pos - position).length_squared() <= radius * radius:
                    nearby.append(tree)

        nearby.sort(key=lambda tree: (tree.pos - position).length_squared())
        return nearby

    def is_rect_on_blocked_terrain(self, rect):
        start_col = math.floor(rect.left / self.tile_size)
        end_col = math.floor((rect.right - 1) / self.tile_size)
        start_row = math.floor(rect.top / self.tile_size)
        end_row = math.floor((rect.bottom - 1) / self.tile_size)

        for tile_y in range(start_row, end_row + 1):
            for tile_x in range(start_col, end_col + 1):
                _, terrain = self.get_tile_info(tile_x, tile_y)
                if terrain in self.blocked_terrain:
                    return True

        return False

    def is_rect_blocked_by_resources(self, rect):
        search_rect = rect.inflate(self.tile_size * 2, self.tile_size * 2)
        for chunk_key in self.iter_chunk_keys_for_rect(search_rect):
            chunk = self.get_available_chunk(chunk_key)
            if chunk is None:
                self.queue_chunk_generation(chunk_key)
                continue

            for tree in chunk["trees"]:
                if not tree.is_depleted and tree.blocking_rect.colliderect(rect):
                    return True

            for rock in chunk["rocks"]:
                if not rock.is_depleted and rock.blocking_rect.colliderect(rect):
                    return True
        return False

    def is_rect_walkable(self, rect):
        return not self.is_rect_on_blocked_terrain(rect) and not self.is_rect_blocked_by_resources(rect)

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
        chunk_key = getattr(tree, "chunk_key", None)
        if chunk_key is None:
            return

        chunk = self.get_available_chunk(chunk_key)
        if chunk is None:
            return

        if tree in chunk["trees"]:
            chunk["trees"].remove(tree)
            self.refresh_chunk_tree_metadata(chunk_key, chunk)

    def remove_rock(self, rock):
        chunk_key = getattr(rock, "chunk_key", None)
        if chunk_key is None:
            return

        chunk = self.get_available_chunk(chunk_key)
        if chunk is None:
            return

        if rock in chunk["rocks"]:
            chunk["rocks"].remove(rock)
            self.refresh_chunk_rock_metadata(chunk_key, chunk)

    def update(self, dt, camera=None, tracked_entities=None):
        self.refresh_loaded_chunks(camera, tracked_entities)
        self.pump_completed_chunks()
        self.process_chunk_finalization(camera, tracked_entities)

        for chunk_key in list(self.loaded_chunk_keys):
            chunk = self.get_available_chunk(chunk_key)
            if chunk is None:
                continue

            tree_bounds_dirty = False
            for tree in chunk["trees"][:]:
                if tree.needs_growth_update() and tree.update(dt):
                    tree_bounds_dirty = True

                if tree.is_depleted:
                    self.remove_tree(tree)

            if tree_bounds_dirty:
                self.refresh_chunk_tree_metadata(chunk_key, chunk)

            for rock in chunk["rocks"][:]:
                if rock.is_depleted:
                    self.remove_rock(rock)

    def get_visible_rect(self, camera=None):
        if camera is None:
            return pygame.Rect(0, 0, SCREEN_WIDTH, SCREEN_HEIGHT)
        return camera.visible_rect()

    def draw_ground(self, surface, camera=None):
        visible = self.get_visible_rect(camera)

        for chunk_key in sorted(self.loaded_chunk_keys):
            chunk_rect = self.get_chunk_rect(chunk_key)
            if not visible.colliderect(chunk_rect):
                continue

            draw_rect = chunk_rect if camera is None else camera.apply_rect(chunk_rect)
            chunk = self.get_available_chunk(chunk_key)
            if chunk is None:
                center_tile_x = (chunk_key[0] * self.chunk_size_tiles) + (self.chunk_size_tiles // 2)
                center_tile_y = (chunk_key[1] * self.chunk_size_tiles) + (self.chunk_size_tiles // 2)
                height, terrain = self.get_tile_info(center_tile_x, center_tile_y)
                color = self.get_terrain_color(terrain, height)
                pygame.draw.rect(surface, color, draw_rect)
                self.queue_chunk_generation(chunk_key)
                continue

            surface.blit(chunk["surface"], draw_rect)

    def draw_rocks(self, surface, camera=None):
        visible = self.get_visible_rect(camera)
        camera_x = 0 if camera is None else int(camera.offset.x)
        camera_y = 0 if camera is None else int(camera.offset.y)

        if self.main.debug_mode:
            camera_offset = None if camera is None else camera.offset
            visible_rocks = []

            for chunk_key in sorted(self.loaded_chunk_keys):
                chunk = self.get_available_chunk(chunk_key)
                if chunk is None or not visible.colliderect(chunk["rock_bounds"]):
                    continue

                for rock in chunk["rocks"]:
                    if visible.colliderect(rock.rect):
                        visible_rocks.append(rock)

            visible_rocks.sort(key=lambda rock: rock.rect.bottom)
            for rock in visible_rocks:
                rock.draw(surface, camera_offset)
            return

        for chunk_key in sorted(self.loaded_chunk_keys, key=lambda item: (item[1], item[0])):
            chunk = self.get_available_chunk(chunk_key)
            if chunk is None or not visible.colliderect(chunk["rock_bounds"]):
                continue

            blit_sequence = []
            for rock in chunk["rocks"]:
                if visible.colliderect(rock.rect):
                    blit_sequence.append((rock.image, (rock.rect.x - camera_x, rock.rect.y - camera_y)))

            if blit_sequence:
                surface.blits(blit_sequence, doreturn=False)

    def draw_trees(self, surface, camera=None):
        visible = self.get_visible_rect(camera)
        camera_x = 0 if camera is None else int(camera.offset.x)
        camera_y = 0 if camera is None else int(camera.offset.y)

        if self.main.debug_mode:
            camera_offset = None if camera is None else camera.offset
            visible_trees = []

            for chunk_key in sorted(self.loaded_chunk_keys):
                chunk = self.get_available_chunk(chunk_key)
                if chunk is None or not visible.colliderect(chunk["tree_bounds"]):
                    continue

                for tree in chunk["trees"]:
                    if visible.colliderect(tree.rect):
                        visible_trees.append(tree)

            visible_trees.sort(key=lambda tree: tree.rect.bottom)
            for tree in visible_trees:
                tree.draw(surface, camera_offset)
            return

        for chunk_key in sorted(self.loaded_chunk_keys, key=lambda item: (item[1], item[0])):
            chunk = self.get_available_chunk(chunk_key)
            if chunk is None or not visible.colliderect(chunk["tree_bounds"]):
                continue

            blit_sequence = []
            for tree in chunk["trees"]:
                if visible.colliderect(tree.rect):
                    blit_sequence.append((tree.image, (tree.rect.x - camera_x, tree.rect.y - camera_y)))

            if blit_sequence:
                surface.blits(blit_sequence, doreturn=False)

    def draw(self, surface, camera=None):
        self.draw_ground(surface, camera)
        self.draw_trees(surface, camera)

    def shutdown(self):
        self.chunk_executor.shutdown(wait=False, cancel_futures=True)