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

from camera import Camera
from gameui import GameUI
from settings import *
from player import Player


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

        # ── Entities ──────────────────────────────────────────────────────
        self.player = Player(self.main, x=WORLD_WIDTH // 2, y=WORLD_HEIGHT // 2)

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

        # Static world landmarks make camera motion easier to read while the
        # project is still in its early gameplay stages.
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
        self.player.handle_event(event)
        self.ui.handle_events(event)

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
        self.camera.update()
        self.minimap_camera.update()

    def can_move_player_to(self, collision_rect):
        """Return True when *collision_rect* stays inside the world bounds."""
        return (
            collision_rect.left >= 0
            and collision_rect.top >= 0
            and collision_rect.right <= WORLD_WIDTH
            and collision_rect.bottom <= WORLD_HEIGHT
        )

    def _draw_ground(self, surface, camera):
        """Draw the world background, grid, and outer world border."""
        surface.fill((20, 80, 30))

        visible = camera.view_rect
        start_x = max(0, (visible.left // TILE_SIZE) * TILE_SIZE)
        end_x = min(WORLD_WIDTH, ((visible.right // TILE_SIZE) + 1) * TILE_SIZE)
        start_y = max(0, (visible.top // TILE_SIZE) * TILE_SIZE)
        end_y = min(WORLD_HEIGHT, ((visible.bottom // TILE_SIZE) + 1) * TILE_SIZE)

        major_step = TILE_SIZE * 4

        for x in range(start_x, end_x + TILE_SIZE, TILE_SIZE):
            screen_x = int((x - camera.offset.x) * camera.scale_x)
            color = (38, 110, 48) if x % major_step == 0 else (30, 96, 40)
            pygame.draw.line(surface, color, (screen_x, 0), (screen_x, surface.get_height()), 1)

        for y in range(start_y, end_y + TILE_SIZE, TILE_SIZE):
            screen_y = int((y - camera.offset.y) * camera.scale_y)
            color = (38, 110, 48) if y % major_step == 0 else (30, 96, 40)
            pygame.draw.line(surface, color, (0, screen_y), (surface.get_width(), screen_y), 1)

        border_rect = camera.world_rect_to_screen(pygame.Rect(0, 0, WORLD_WIDTH, WORLD_HEIGHT))
        pygame.draw.rect(surface, (95, 65, 28), border_rect, max(1, int(min(camera.scale_x, camera.scale_y) * 2)))

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
        self._draw_ground(surface, camera)
        self._draw_landmarks(surface, camera, show_labels=show_labels)
        self.player.draw(surface, camera)

        if self.main.debug_mode and show_labels:
            debug_text = FONT_SMALL.render(
                f"{camera.name} camera: view={camera.view_rect}",
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


