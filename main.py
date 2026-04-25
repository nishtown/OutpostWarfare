"""
main.py
-------
Application entry point for Outpost Warfare.

Responsibilities
----------------
- Initialise pygame and open the display window at the configured resolution.
- Own the master game clock and drive the fixed-step game loop.
- Pump the pygame event queue each frame and dispatch events to sub-systems.
- Toggle a global debug-overlay mode with Ctrl+D (forwarded via self.debug_mode).

Usage
-----
    python main.py

or as an asyncio target (Pyodide / web export)::

    python -m asyncio main
"""

import pygame

from settings import *
from game import Game


class Main:
    """Application shell – owns the display surface and the game clock.

    The ``game`` attribute is set by ``Game.__init__`` via a back-reference
    (``main.game = self``) so that deep sub-systems can reach ``Main`` through
    ``game.main`` if they need the display surface, clock, or debug flag.

    Attributes
    ----------
    display_surface : pygame.Surface
        The primary window surface.  The game world is blitted onto this at
        ``(0, 0)`` by ``Game.draw``; the UI panel is drawn on top of it.
    clock : pygame.time.Clock
        Controls the frame rate cap and provides delta-time values.
    debug_mode : bool
        When ``True``, sub-systems may draw extra diagnostic overlays
        (collision boxes, chunk borders, FPS counter, etc.).
    game : Game
        Set during ``Game.__init__``; the top-level game state object.
    """

    def __init__(self):
        pygame.init()
        pygame.mixer.init()   # Initialise audio subsystem for sound effects / music

        # Primary display surface – full window size.
        # Game world is rendered onto a separate surface inside Game and
        # composited here; the UI panel is drawn directly on this surface.
        self.display_surface = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
        pygame.display.set_caption("Outpost Warfare")

        # Clock drives frame-rate capping and delta-time calculation.
        self.clock = pygame.time.Clock()

        # When True, additional diagnostic overlays are rendered by sub-systems.
        # Toggle at runtime with Ctrl+D.
        self.debug_mode = False

        # Instantiate the top-level game state.
        # Game.__init__ also sets self.game via back-reference.
        self.game = Game(self)

    # ── Main loop ─────────────────────────────────────────────────────────────

    def run(self):
        """Start and run the game loop until the window is closed."""
        running = True

        while running:
            # dt: time elapsed since the last frame, in seconds.
            # Capped by FPS so physics and movement stay frame-rate independent.
            dt = self.clock.tick(FPS) / 1000

            # ── Event pump ────────────────────────────────────────────────
            for event in pygame.event.get():

                # Window close button or OS kill signal.
                if event.type == pygame.QUIT:
                    running = False
                    break

                # Keyboard shortcuts handled at the application level.
                if event.type == pygame.KEYDOWN:
                    # Ctrl+D – toggle debug overlays across all sub-systems.
                    if event.key == pygame.K_d and (event.mod & pygame.KMOD_CTRL):
                        self.debug_mode = not self.debug_mode

                # Forward all other events to the active game state.
                self.game.handle_event(event)

            # ── Update ────────────────────────────────────────────────────
            # Advance game logic (entities, chunks, economy, animations …).
            self.game.update(dt)

            # ── Draw ──────────────────────────────────────────────────────
            # Renders world surface then composites UI onto the display.
            self.game.draw(self.display_surface)

            # ── Present ───────────────────────────────────────────────────
            # Flip the display buffer to make the completed frame visible.
            pygame.display.flip()

        pygame.quit()


if __name__ == '__main__':
    main = Main()
    main.run()
