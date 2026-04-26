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
from world_objects import WorldObjectManager
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

        # Back-reference so other objects can reach Game through main.game.
        self.main.game = self

        # ── Render targets ────────────────────────────────────────────────
        # Main camera render target: this is the surface blitted into the left
        # side of the game window every frame.
        self.world_surface = pygame.Surface((VIEWPORT_WIDTH, VIEWPORT_HEIGHT))

        # Minimap render target: smaller than the main world surface, but its
        # camera sees a wider range of world space.
        self.minimap_surface = pygame.Surface(
            (MINIMAP_SURFACE_WIDTH, MINIMAP_SURFACE_HEIGHT)
        )

        # ── UI panel ──────────────────────────────────────────────────────
        self.ui = GameUI()

        # ── World generation ──────────────────────────────────────────────
        # The generated world is deterministic: the same WORLD_SEED always
        # produces the same terrain layout.
        self.world = WorldGenerator(
            WORLD_WIDTH,
            WORLD_HEIGHT,
            tile_size=TILE_SIZE,
            seed=WORLD_SEED,
        )

        # ── Base anchor ──────────────────────────────────────────────────
        # The tower-defence prototype uses a fixed base near the middle of the
        # map. We snap it to a nearby traversable tile so both the player and
        # enemy pathing start from valid ground even if the exact centre lands
        # on water or rock for a future seed.
        center_guess = Vector2(WORLD_WIDTH / 2, WORLD_HEIGHT / 2)
        self.base_position = (
            self.world.find_nearest_traversable(center_guess.x, center_guess.y, max_radius_tiles=10)
            or center_guess
        )

        # ── Entities ──────────────────────────────────────────────────────
        self.player = Player(self.main, x=self.base_position.x, y=self.base_position.y)
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
        self.camera = Camera(
            WORLD_WIDTH,
            WORLD_HEIGHT,
            VIEWPORT_WIDTH,
            VIEWPORT_HEIGHT,
            name="main",
        )
        self.minimap_camera = Camera(
            WORLD_WIDTH,
            WORLD_HEIGHT,
            MINIMAP_SURFACE_WIDTH,
            MINIMAP_SURFACE_HEIGHT,
            view_width=MINIMAP_VIEW_WIDTH,
            view_height=MINIMAP_VIEW_HEIGHT,
            name="minimap",
        )
        self.camera.set_target(self.player)
        self.minimap_camera.set_target(self.player)

        # Static landmarks sit on top of the generated terrain so camera motion
        # and map readability remain strong while the project is still early.
        self.landmarks = [
            {"name": "North Watch", "rect": pygame.Rect(480, 320, 120, 120), "color": (125, 80, 35)},
            {"name": "Stone Yard", "rect": pygame.Rect(2200, 540, 96, 96), "color": (120, 120, 120)},
            {"name": "Market Green", "rect": pygame.Rect(1450, 1500, 140, 100), "color": (70, 140, 60)},
            {"name": "South Gate", "rect": pygame.Rect(700, 2300, 150, 110), "color": (140, 60, 50)},
        ]

    # ── Event handling ────────────────────────────────────────────────────────

    def handle_event(self, event):
        """Forward raw pygame events to sub-systems that need them.

        Add further dispatch here as new systems (player input, camera pan,
        building placement, etc.) are introduced.
        """
        ui_action = self.ui.handle_events(event)
        if ui_action == "start_next_wave":
            self.enemy_director.start_next_wave()
            return

        self.player.handle_event(event)

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if event.pos[0] < VIEWPORT_WIDTH and self.ui.selected_building:
                self.try_place_selected_building(event.pos)

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
        self.player.update(dt)
        self.enemy_director.update(dt)
        self.world_objects.update(dt, self.enemy_director.enemies)

        self.ui.gold = self.player.get_resource_amount("gold")
        self.ui.food = self.player.get_resource_amount("food")
        self.ui.wood = self.player.get_resource_amount("wood")
        self.ui.stone = self.player.get_resource_amount("stone")
        self.ui.set_wave_state(self.enemy_director.can_start_next_wave, self.enemy_director.next_wave_number)

        self.ui.update(dt)
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
            if not (0 <= world_x < WORLD_WIDTH and 0 <= world_y < WORLD_HEIGHT):
                return False
            if not self.world.is_traversable_at_world(world_x, world_y):
                return False
        if self.world_objects.find_blocking_structure_for_rect(collision_rect) is not None:
            return False
        return True

    def try_start_player_harvest(self, screen_pos) -> bool:
        if screen_pos[0] >= VIEWPORT_WIDTH:
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

    def try_place_selected_building(self, screen_pos) -> bool:
        building_key = self.ui.selected_building
        if building_key is None:
            return False

        world_pos = self._screen_to_world(screen_pos)
        success, message = self.world_objects.place_structure(building_key, world_pos, self.player)
        if not success:
            self.ui.announce(message, accent=RED, duration=1.4)
        return success

    def _screen_to_world(self, screen_pos) -> Vector2:
        screen_x, screen_y = screen_pos
        return Vector2(
            self.camera.offset.x + screen_x / self.camera.scale_x,
            self.camera.offset.y + screen_y / self.camera.scale_y,
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

    def _render_world(self, surface, camera, show_labels=False):
        """Render the world into *surface* from the perspective of *camera*."""
        self.world.draw(surface, camera)
        self._draw_landmarks(surface, camera, show_labels=show_labels)
        self.world_objects.draw(surface, camera)
        self.enemy_director.draw(surface, camera)
        self.world_objects.draw_projectiles(surface, camera)
        self.player.draw(surface, camera)

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
        screen.blit(self.world_surface, (0, 0))

        # ── Step 3: draw the UI using the wider minimap camera surface ────
        self.ui.draw(
            screen,
            world_surface=self.minimap_surface,
            minimap_camera=self.minimap_camera,
            tracked_view_rect=self.camera.view_rect,
            player_pos=self.player.pos,
        )


