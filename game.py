"""
game.py
-------
Core game state, update loop, and frame renderer.

Surface architecture
--------------------
Each frame is built in three layers:

1. **world_surface** – an off-screen ``pygame.Surface`` sized to the viewport
   (``VIEWPORT_WIDTH × VIEWPORT_HEIGHT``).  Every in-world element (terrain
   chunks, entities, particles, the player) is drawn here.  Nothing UI-related
   ever touches this surface, which makes it straightforward to:

   * blit it at ``(0, 0)`` on the main display so it fills the left side of
     the window, and
   * pass it to the ``Minimap`` so it can be scaled down into a real-time
     overhead view.

2. **display surface** (owned by ``Main``) – the full window.  After blitting
   the world, the right-hand UI panel is drawn directly on this surface.

3. *(future)* HUD / post-processing overlays composited on the display surface
   after the world but before the UI.
"""

import pygame

from gameui import GameUI
from settings import *


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

        # ── World render surface ───────────────────────────────────────────
        # Sized to the viewport (left of the UI panel).  All terrain, entity,
        # and effect drawing targets this surface rather than the display
        # directly – that keeps world and UI rendering cleanly separated.
        self.world_surface = pygame.Surface((VIEWPORT_WIDTH, VIEWPORT_HEIGHT))

        # ── UI panel ──────────────────────────────────────────────────────
        self.ui = GameUI()

    # ── Event handling ────────────────────────────────────────────────────────

    def handle_event(self, event):
        """Forward raw pygame events to sub-systems that need them.

        Add further dispatch here as new systems (player input, camera pan,
        building placement, etc.) are introduced.
        """
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
        # TODO: update player, entities, chunks, animations, economy …
        pass

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
        # ── Step 1: game-world render ──────────────────────────────────────
        # Clear the world surface each frame before drawing anything.
        # The solid fill acts as the base terrain colour; the actual chunk
        # and entity rendering will layer on top of this.
        self.world_surface.fill((20, 80, 30))   # dark-green grass placeholder

        # TODO: draw terrain chunks, trees, rocks, buildings, entities,
        #       particles, player sprite, and any world-space HUD overlays.

        # ── Step 2: composite world surface onto the main display ──────────
        # The world surface starts at (0, 0); the UI panel occupies the
        # rightmost UI_PANEL_WIDTH pixels and is drawn in the next step.
        screen.blit(self.world_surface, (0, 0))

        # ── Step 3: UI panel (includes minimap that reads world_surface) ───
        self.ui.draw(screen, world_surface=self.world_surface)

