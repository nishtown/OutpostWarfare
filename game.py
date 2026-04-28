"""
game.py
-------
Core game state, update loop, and frame renderer.

Surface and camera architecture
-------------------------------
Each frame is built in four steps:

1. **main camera** follows the player and renders the visible world into
    ``world_surface`` at the full viewport size.
2. **minimap camera** follows the same player but sees a wider patch of the
    world and renders that wider region into ``minimap_surface``.
3. ``world_surface`` is blitted onto the main display at ``(0, 0)``.
4. The UI draws the right-hand panel and uses ``minimap_surface`` plus camera
    metadata to show both the wider map view and the smaller main-camera box.
"""

import pygame
from pygame import Vector2

from camera import Camera
from enemy import EnemyDirector
from gameui import GameUI
from settings import *
from player import Player
from world_objects import BUILD_DEFINITIONS, STRUCTURE_RENDER_OFFSETS, Structure, WorldObjectManager
from world_gen import WorldGenerator


class Game:
    """Top-level game state manager.

    Receives the ``Main`` instance so it can reference the display surface
    and clock without creating circular-import problems.

    Attributes
    ----------
    world_surface : pygame.Surface
        Off-screen surface that the game world is rendered onto each frame
        before being composited onto the main display.
    ui : GameUI
        The right-hand side panel (minimap, build menu, resource counters).
    """

    def __init__(self, main):
        self.main = main
        self.layout = main.layout

        # Back-reference so other objects can reach Game through main.game.
        self.main.game = self

        # ── UI panel ──────────────────────────────────────────────────────
        self.ui = GameUI(self.layout)
        self.selected_structure = None
        self.pending_construction = None
        self.game_over = False

        world_width = self.layout.viewport_width * 3
        world_height = self.layout.viewport_height * 3

        # ── World generation ──────────────────────────────────────────────
        # The generated world is deterministic: the same WORLD_SEED always
        # produces the same terrain layout.
        self.world = WorldGenerator(
            world_width,
            world_height,
            tile_size=TILE_SIZE,
            seed=WORLD_SEED,
        )

        # ── Render targets ────────────────────────────────────────────────
        # Main camera render target: this is the surface blitted into the left
        # side of the game window every frame.
        self.world_surface = pygame.Surface((self.layout.viewport_width, self.layout.viewport_height))

        minimap_width, minimap_height = self.ui.minimap.rect.size
        self.minimap_surface = pygame.Surface((minimap_width, minimap_height))

        # ── Base anchor ──────────────────────────────────────────────────
        # The tower-defence prototype uses a fixed base near the middle of the
        # map. We snap it to a nearby traversable tile so both the player and
        # enemy pathing start from valid ground even if the exact centre lands
        # on water or rock for a future seed.
        center_guess = Vector2(self.world.world_width / 2, self.world.world_height / 2)
        self.base_position = (
            self.world.find_nearest_traversable(center_guess.x, center_guess.y, max_radius_tiles=10)
            or center_guess
        )

        # ── Entities ──────────────────────────────────────────────────────
        self.player = Player(self.main, x=self.base_position.x, y=self.base_position.y + (TILE_SIZE * 2))
        self.world_objects = WorldObjectManager(
            self.main,
            self.world,
            self.base_position,
            WORLD_SEED,
            announce_callback=self.ui.announce,
        )

        # Experimental enemy wave system. This is deliberately isolated in
        # enemy.py so the whole feature can be removed later by deleting this
        # instance plus the few update/draw hooks below.
        self.enemy_director = EnemyDirector(
            self.main,
            self.world,
            self.base_position,
            WORLD_SEED,
            announce_callback=self.ui.announce,
        )

        # ── Cameras ───────────────────────────────────────────────────────
        minimap_view_width, minimap_view_height = self._get_minimap_view_size(
            minimap_width,
            minimap_height,
            self.layout.viewport_width,
        )
        self.camera = Camera(
            self.world.world_width,
            self.world.world_height,
            self.layout.viewport_width,
            self.layout.viewport_height,
            name="main",
        )
        self.minimap_camera = Camera(
            self.world.world_width,
            self.world.world_height,
            minimap_width,
            minimap_height,
            view_width=minimap_view_width,
            view_height=minimap_view_height,
            name="minimap",
        )
        self.camera.set_target(self.player)
        self.minimap_camera.set_target(self.player)

        # Static landmarks sit on top of the generated terrain so camera motion
        # and map readability remain strong while the project is still early.
        self.landmarks = []

    def on_resize(self, layout) -> None:
        """Resize render targets, cameras, and UI to match a new window size."""
        self.layout = layout
        self.ui.set_layout(layout)
        self.world_surface = pygame.Surface((layout.viewport_width, layout.viewport_height))
        minimap_width, minimap_height = self.ui.minimap.rect.size
        self.minimap_surface = pygame.Surface((minimap_width, minimap_height))
        self.camera.resize(
            layout.viewport_width,
            layout.viewport_height,
            view_width=layout.viewport_width,
            view_height=layout.viewport_height,
        )
        minimap_view_width, minimap_view_height = self._get_minimap_view_size(
            minimap_width,
            minimap_height,
            layout.viewport_width,
        )
        self.minimap_camera.resize(
            minimap_width,
            minimap_height,
            view_width=minimap_view_width,
            view_height=minimap_view_height,
        )
        self.camera.update()
        self.minimap_camera.update()

    def _get_minimap_view_size(self, minimap_width: int, minimap_height: int, viewport_width: int) -> tuple[int, int]:
        target_width = min(
            float(self.world.world_width),
            float(int(viewport_width * MINIMAP_VIEW_MULTIPLIER)),
        )
        aspect_ratio = minimap_width / max(1, minimap_height)
        target_height = target_width / max(0.01, aspect_ratio)

        if target_height > self.world.world_height:
            target_height = float(self.world.world_height)
            target_width = target_height * aspect_ratio

        if target_width > self.world.world_width:
            target_width = float(self.world.world_width)
            target_height = target_width / max(0.01, aspect_ratio)

        return max(1, int(target_width)), max(1, int(target_height))

    # ── Event handling ────────────────────────────────────────────────────────

    def handle_event(self, event):
        """Forward raw pygame events to sub-systems that need them.

        Add further dispatch here as new systems (player input, camera pan,
        building placement, etc.) are introduced.
        """
        ui_action = self.ui.handle_events(event)
        if ui_action == "reset_game":
            self.reset()
            return
        if ui_action == "upgrade_selected_structure":
            success, message = self.world_objects.upgrade_structure(self.selected_structure, self.player)
            if not success:
                self.ui.announce(message, accent=RED, duration=1.5)
            self.ui.set_selected_structure(self.selected_structure)
            return
        if ui_action == "repair_selected_structure":
            success, message = self.world_objects.repair_structure(self.selected_structure, self.player)
            if not success:
                self.ui.announce(message, accent=RED, duration=1.5)
            self.ui.set_selected_structure(self.selected_structure)
            return
        if ui_action == "build_selection_changed":
            if self.ui.selected_building is not None:
                self._set_selected_structure(None)
            return

        if self.game_over:
            if event.type == pygame.KEYDOWN and event.key == pygame.K_r:
                self.reset()
            return

        self.player.handle_event(event)

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self._is_world_screen_position(event.pos):
                if self.ui.selected_building:
                    if self.pending_construction is not None:
                        self.ui.announce("Finish the current build first", accent=RED, duration=1.4)
                        return
                    self.try_place_selected_building(event.pos)
                    return

                clicked_world = self._screen_to_world(event.pos)
                structure = self.world_objects.find_structure_at_world(clicked_world)
                if structure is self.selected_structure:
                    self._set_selected_structure(None)
                elif structure is not None:
                    self._set_selected_structure(structure)
                elif self.try_start_player_attack(clicked_world):
                    self._set_selected_structure(None)
                else:
                    self._set_selected_structure(None)

    # ── Update ────────────────────────────────────────────────────────────────

    def update(self, dt):
        """Advance all game logic by ``dt`` seconds.

        Parameters
        ----------
        dt : float
            Elapsed time since the last frame in seconds.  Computed by the
            main loop as ``clock.tick(FPS) / 1000``.

        Notes
        -----
        Add entity updates, chunk streaming, animation ticks, economy
        processing, etc. here as the game systems are built out.
        """
        if not self.game_over:
            self.player.update(dt)
            self._update_pending_construction(dt)
            self.enemy_director.update(dt)
            self.world_objects.update(dt, self.enemy_director.enemies)

            if not getattr(self.world_objects.base_structure, "alive", True):
                self._trigger_game_over()

        if self.selected_structure is not None and not getattr(self.selected_structure, "alive", False):
            self._set_selected_structure(None)

        self.ui.gold = self.player.get_resource_amount("gold")
        self.ui.food = self.player.get_resource_amount("food")
        self.ui.wood = self.player.get_resource_amount("wood")
        self.ui.stone = self.player.get_resource_amount("stone")
        self.ui.set_selected_structure(self.selected_structure)
        self.ui.set_wave_state(
            self.enemy_director.next_wave_number,
            self.enemy_director.time_until_next_wave,
            self.enemy_director.wave_in_progress,
        )
        self.ui.set_game_over(self.game_over)

        self.ui.update(dt)
        if not self.game_over:
            self.camera.update()
            self.minimap_camera.update()

    def can_move_player_to(self, collision_rect):
        """Return True when *collision_rect* stays inside walkable world tiles."""
        corners = [
            (collision_rect.left, collision_rect.top),
            (collision_rect.right - 1, collision_rect.top),
            (collision_rect.left, collision_rect.bottom - 1),
            (collision_rect.right - 1, collision_rect.bottom - 1),
        ]

        for world_x, world_y in corners:
            if not (0 <= world_x < self.world.world_width and 0 <= world_y < self.world.world_height):
                return False
            if not self.world.is_traversable_at_world(world_x, world_y):
                return False
        if self.world_objects.find_blocking_structure_for_rect(collision_rect) is not None:
            return False
        return True

    def try_start_player_harvest(self, screen_pos) -> bool:
        if self.game_over:
            return False

        if not self._is_world_screen_position(screen_pos):
            return False

        clicked_world = self._screen_to_world(screen_pos)
        target = self.world_objects.find_harvest_target(
            clicked_world,
            self.player.pos,
            self.player.harvest_range,
        )
        if target is None:
            return False

        self.player.start_harvest(target)
        return True

    def try_start_player_attack(self, world_position) -> bool:
        if self.game_over:
            return False

        clicked = Vector2(world_position)
        clicked_candidates = []
        for enemy in self.enemy_director.enemies:
            if not getattr(enemy, "alive", False):
                continue

            click_distance = enemy.pos.distance_to(clicked)
            if click_distance > 40.0:
                continue

            player_distance = enemy.pos.distance_to(self.player.pos)
            clicked_candidates.append((click_distance, player_distance, enemy))

        if not clicked_candidates:
            return False

        _, player_distance, target = min(clicked_candidates, key=lambda item: (item[0], item[1]))
        max_distance = self.player.attack_range + getattr(target, "attack_radius", 8)
        if player_distance > max_distance:
            self.ui.announce("Target out of range", accent=RED, duration=1.0)
            return True

        return self.player.start_attack(target)

    def try_place_selected_building(self, screen_pos) -> bool:
        building_key = self.ui.selected_building
        if building_key is None:
            return False

        world_pos = self._screen_to_world(screen_pos)
        definition = BUILD_DEFINITIONS.get(building_key)
        if definition is None:
            self.ui.announce("Unknown build option", accent=RED, duration=1.4)
            return False

        success, message, snapped = self.world_objects.validate_structure_placement(
            building_key,
            world_pos,
            self.player,
            check_resources=True,
        )
        if not success or snapped is None:
            self.ui.announce(message, accent=RED, duration=1.4)
            return False

        if not self.player.consume_resources(definition.cost):
            self.ui.announce("Not enough resources", accent=RED, duration=1.4)
            return False

        self.pending_construction = {
            "building_key": building_key,
            "definition": definition,
            "position": Vector2(snapped),
            "progress": 0.0,
            "duration": max(0.25, float(definition.build_time)),
        }
        self.ui.announce(f"Constructing {definition.label}", accent=GOLD, duration=1.4)
        return True

    def _update_pending_construction(self, dt: float) -> None:
        if self.pending_construction is None:
            return

        pending = self.pending_construction
        position = pending["position"]
        if self.player.pos.distance_to(position) > self.player.build_assist_radius:
            return

        pending["progress"] = min(1.0, pending["progress"] + (dt / pending["duration"]))
        if pending["progress"] < 1.0:
            return

        structure = self.world_objects.spawn_structure(pending["building_key"], position)
        if structure is None:
            self.player.refund_resources(pending["definition"].cost)
            self.ui.announce("Build failed", accent=RED, duration=1.5)
        else:
            self.ui.announce(f"Built {pending['definition'].label}", accent=GREEN, duration=1.5)
        self.pending_construction = None

    def _screen_to_world(self, screen_pos) -> Vector2:
        screen_x, screen_y = screen_pos
        return Vector2(
            self.camera.offset.x + (screen_x - self.layout.viewport_x) / self.camera.scale_x,
            self.camera.offset.y + (screen_y - self.layout.viewport_y) / self.camera.scale_y,
        )

    def _is_world_screen_position(self, screen_pos) -> bool:
        screen_x, screen_y = screen_pos
        return (
            self.layout.viewport_x <= screen_x < self.layout.viewport_x + self.layout.viewport_width
            and self.layout.viewport_y <= screen_y < self.layout.viewport_y + self.layout.viewport_height
        )

    def _draw_landmarks(self, surface, camera, show_labels=False):
        """Draw a few fixed landmarks so camera movement is easy to read."""
        screen_bounds = pygame.Rect(0, 0, surface.get_width(), surface.get_height())

        for landmark in self.landmarks:
            draw_rect = camera.world_rect_to_screen(landmark["rect"])
            if not draw_rect.colliderect(screen_bounds):
                continue

            pygame.draw.rect(surface, landmark["color"], draw_rect)
            pygame.draw.rect(surface, DARK_BROWN, draw_rect, 1)

            if show_labels and draw_rect.width >= 50:
                label = FONT_SMALL.render(landmark["name"], True, WHITE)
                label_pos = (draw_rect.x, max(0, draw_rect.y - label.get_height() - 2))
                surface.blit(label, label_pos)

    def _set_selected_structure(self, structure):
        self.selected_structure = structure
        self.ui.set_selected_structure(structure)

    def _trigger_game_over(self):
        if self.game_over:
            return

        self.game_over = True
        self._set_selected_structure(None)
        self.ui.announce("The main base has fallen", accent=RED, duration=4.0, key="game_over", cooldown=0.0)

    def reset(self):
        self.__init__(self.main)

    def _scene_sort_key(self, obj) -> tuple[int, int]:
        if hasattr(obj, "get_depth_sort_bottom"):
            depth_bottom = obj.get_depth_sort_bottom()
            position = getattr(obj, "pos", Vector2())
            return int(depth_bottom), int(position.x)

        if hasattr(obj, "get_collision_rect"):
            collision_rect = obj.get_collision_rect()
            return collision_rect.bottom, collision_rect.centerx
        position = getattr(obj, "pos", Vector2())
        return int(position.y), int(position.x)

    def _draw_scene_object(self, surface, camera, obj) -> None:
        if obj is self.player:
            self.player.draw(surface, camera)
            return

        if hasattr(obj, "tier"):
            obj.draw(surface, camera)
            return

        if hasattr(obj, "definition") and hasattr(obj, "sprite_offset_y"):
            obj.draw(surface, camera, selected=obj is self.selected_structure)
            return

        obj.draw(surface, camera)

    def _get_build_preview(self, screen_pos=None):
        building_key = self.ui.selected_building
        if building_key is None:
            return None

        definition = BUILD_DEFINITIONS.get(building_key)
        if definition is None:
            return None

        mouse_pos = screen_pos if screen_pos is not None else pygame.mouse.get_pos()
        if not self._is_world_screen_position(mouse_pos):
            return None

        world_pos = self._screen_to_world(mouse_pos)
        valid, message, snapped = self.world_objects.validate_structure_placement(
            building_key,
            world_pos,
            self.player,
            check_resources=True,
        )
        if snapped is None:
            return None

        return {
            "definition": definition,
            "position": Vector2(snapped),
            "valid": valid,
            "message": message,
        }

    def _draw_build_radius(self, surface, camera) -> None:
        if getattr(camera, "name", "") == "minimap":
            return
        if self.ui.selected_building is None and self.pending_construction is None:
            return

        screen_pos = camera.world_to_screen(self.player.pos)
        radius = max(8, int(self.player.build_radius * min(camera.scale_x, camera.scale_y)))
        overlay = pygame.Surface(surface.get_size(), pygame.SRCALPHA)
        pygame.draw.circle(overlay, (255, 248, 220, 20), (int(screen_pos.x), int(screen_pos.y)), radius)
        pygame.draw.circle(overlay, (255, 248, 220, 42), (int(screen_pos.x), int(screen_pos.y)), radius, 1)
        surface.blit(overlay, (0, 0))

    def _draw_structure_ghost(self, surface, camera, definition, position, *, valid: bool, alpha: int, progress: float | None = None) -> None:
        sprite = Structure._load_building_sprite(definition) or Structure._build_surface(definition)
        sprite = sprite.copy()
        if not valid:
            sprite.fill((255, 120, 120, 255), special_flags=pygame.BLEND_RGBA_MULT)
        sprite.set_alpha(alpha)

        world_rect = sprite.get_rect()
        world_rect.midbottom = (
            int(position.x),
            int(position.y + STRUCTURE_RENDER_OFFSETS.get(definition.key, 0)),
        )
        draw_rect = camera.world_rect_to_screen(world_rect)
        if draw_rect.width <= 0 or draw_rect.height <= 0:
            return

        if draw_rect.size != sprite.get_size():
            sprite = pygame.transform.smoothscale(sprite, draw_rect.size)
        surface.blit(sprite, draw_rect)

        collision_rect = camera.world_rect_to_screen(Structure.get_preview_collision_rect(definition, position))
        outline_color = GREEN if valid else RED
        pygame.draw.ellipse(surface, outline_color, collision_rect.inflate(10, 8), 2)

        if progress is not None:
            bar_width = max(18, int(44 * camera.scale_x))
            bar_height = max(4, int(6 * camera.scale_y))
            bar_rect = pygame.Rect(0, 0, bar_width, bar_height)
            bar_rect.midbottom = (collision_rect.centerx, draw_rect.top - 6)
            fill_rect = pygame.Rect(bar_rect.x, bar_rect.y, int(bar_width * max(0.0, min(1.0, progress))), bar_height)
            pygame.draw.rect(surface, (40, 26, 18), bar_rect)
            pygame.draw.rect(surface, GOLD if valid else ORANGE, fill_rect)
            pygame.draw.rect(surface, WHITE, bar_rect, 1)

    def _draw_build_overlays(self, surface, camera) -> None:
        if getattr(camera, "name", "") == "minimap":
            return

        self._draw_build_radius(surface, camera)

        if self.pending_construction is not None:
            pending = self.pending_construction
            is_active = self.player.pos.distance_to(pending["position"]) <= self.player.build_assist_radius
            self._draw_structure_ghost(
                surface,
                camera,
                pending["definition"],
                pending["position"],
                valid=is_active,
                alpha=140,
                progress=pending["progress"],
            )
            return

        preview = self._get_build_preview()
        if preview is None:
            return

        self._draw_structure_ghost(
            surface,
            camera,
            preview["definition"],
            preview["position"],
            valid=preview["valid"],
            alpha=120,
        )

    def _render_world(self, surface, camera, show_labels=False):
        """Render the world into *surface* from the perspective of *camera*."""
        self.world.draw(surface, camera)
        self._draw_landmarks(surface, camera, show_labels=show_labels)
        self.enemy_director.draw_overlays(surface, camera)

        scene_objects = [
            *[node for node in self.world_objects.resource_nodes if node.alive],
            *[structure for structure in self.world_objects.structures if structure.alive],
            *[enemy for enemy in self.enemy_director.enemies if enemy.alive or enemy.death_animation_active],
            self.player,
        ]
        scene_objects.sort(key=self._scene_sort_key)
        for scene_object in scene_objects:
            self._draw_scene_object(surface, camera, scene_object)

        self._draw_build_overlays(surface, camera)
        self.world_objects.draw_projectiles(surface, camera)

        if self.main.debug_mode and show_labels:
            debug_text = FONT_SMALL.render(
                (
                    f"{camera.name} camera: view={camera.view_rect}  "
                    f"wave={self.enemy_director.wave_number}  "
                    f"active={self.enemy_director.active_enemy_count}  "
                    f"queued={len(self.enemy_director.pending_spawns)}  "
                    f"structures={len(self.world_objects.structures)}  "
                    f"base_hits={self.enemy_director.base_hits}"
                ),
                True,
                WHITE,
            )
            surface.blit(debug_text, (10, 10))

    # ── Draw ──────────────────────────────────────────────────────────────────

    def draw(self, screen):
        """Render one complete frame onto ``screen``.

        Draw order
        ----------
        1. Clear ``world_surface`` and draw the entire game world onto it.
        2. Blit ``world_surface`` onto the main display at ``(0, 0)`` so it
           occupies the viewport area to the left of the UI panel.
        3. Draw the UI panel (which samples ``world_surface`` for its minimap)
           directly onto the main display surface.

        Parameters
        ----------
        screen : pygame.Surface
            The primary display surface, passed in from ``Main.run``.
        """
        # ── Step 1: render the main view and the minimap view ─────────────
        self._render_world(self.world_surface, self.camera, show_labels=True)
        self._render_world(self.minimap_surface, self.minimap_camera)

        # ── Step 2: composite the main camera surface onto the display ────
        screen.blit(self.world_surface, (self.layout.viewport_x, self.layout.viewport_y))

        # ── Step 3: draw the UI using the wider minimap camera surface ────
        self.ui.draw(
            screen,
            world_surface=self.minimap_surface,
            minimap_camera=self.minimap_camera,
            tracked_view_rect=self.camera.view_rect,
            player_pos=self.player.pos,
        )


