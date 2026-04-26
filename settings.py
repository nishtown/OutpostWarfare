"""
settings.py
-----------
Global constants shared across all game modules.

Import with ``from settings import *`` for convenient namespace access.

Sections
--------
- Paths          – base directory and asset helper
- Display        – window and viewport dimensions
- Timing         – target frame rate
- Colour palette – named colours for terrain, UI, and effects
- Fonts          – pre-created SysFont instances (one cost, shared everywhere)
- World / tile   – fundamental tile sizing
"""

import os
import pygame

# ── Initialise pygame early so font creation below succeeds ──────────────────
pygame.init()

# ── Paths ─────────────────────────────────────────────────────────────────────
# Absolute path to the project root (the folder that contains this file).
BASE_DIR = os.path.dirname(__file__)


def asset_path(*parts):
    """Build an absolute path to a file under the project root.

    Example::

        asset_path("assets", "trees", "oak.png")
        # → "<project>/assets/trees/oak.png"
    """
    return os.path.join(BASE_DIR, *parts)


# ── Display ───────────────────────────────────────────────────────────────────
SCREEN_WIDTH  = 1536   # Total window width  (pixels)
SCREEN_HEIGHT = 1024   # Total window height (pixels)

# Width of the right-hand side UI panel (minimap + build menu + resources).
# Changing this constant automatically adjusts VIEWPORT_WIDTH.
UI_PANEL_WIDTH = 300
UI_PANEL_PADDING = 8
TOP_BAR_HEIGHT = 56

# The portion of the window used for rendering the game world.
# This is the area to the LEFT of the UI panel.
VIEWPORT_X = 0
VIEWPORT_Y = TOP_BAR_HEIGHT
VIEWPORT_WIDTH  = SCREEN_WIDTH - UI_PANEL_WIDTH   # 1236 px
VIEWPORT_HEIGHT = SCREEN_HEIGHT - TOP_BAR_HEIGHT

# The overall world is larger than the main viewport so the camera has room
# to move and the minimap can show a broader local region.
WORLD_WIDTH = VIEWPORT_WIDTH * 3
WORLD_HEIGHT = VIEWPORT_HEIGHT * 3

# Seed used by world generation. Changing this value gives you a different,
# but still deterministic, map layout.
WORLD_SEED = 20260426

# The minimap uses its own camera and its own render surface. Its surface size
# matches the pixel area reserved for the map inside the UI panel.
MINIMAP_SURFACE_WIDTH = UI_PANEL_WIDTH - UI_PANEL_PADDING * 2
MINIMAP_SURFACE_HEIGHT = 190

# How much wider the minimap camera's world view is compared to the main view.
# A value above 1.0 means the minimap shows more area than the player can see
# in the main camera.
MINIMAP_VIEW_MULTIPLIER = 3.5
MINIMAP_VIEW_WIDTH = int(VIEWPORT_WIDTH * MINIMAP_VIEW_MULTIPLIER)
MINIMAP_VIEW_HEIGHT = int(
    MINIMAP_VIEW_WIDTH * MINIMAP_SURFACE_HEIGHT / MINIMAP_SURFACE_WIDTH
)

# Legacy aliases – kept for any old code that still references MAP_WIDTH/HEIGHT.
MAP_WIDTH  = SCREEN_WIDTH
MAP_HEIGHT = SCREEN_HEIGHT

# ── Timing ────────────────────────────────────────────────────────────────────
FPS = 60   # Maximum frames per second; actual dt from clock.tick() is used

# ── Colour palette ────────────────────────────────────────────────────────────
# Earth / brown tones – used mainly for UI panels and wooden structures
DARK_BROWN  = (65,  40,  10)
LIGHT_BROWN = (139, 69,  19)

# Greys – borders, stone surfaces, shadows
DARK_GRAY  = (30,  30,  30)
LIGHT_GRAY = (100, 100, 100)

# Accent / resource colours
GOLD   = (255, 215,   0)   # Gold resource / UI highlights
RED    = (220,  20,  60)   # Danger, health, crimson accents
GREEN  = ( 50, 205,  50)   # Food, nature
BLUE   = ( 30, 144, 255)   # Water, information
WHITE  = (255, 255, 255)   # Text, highlights
BLACK  = (  0,   0,   0)   # Outlines, shadows
ORANGE = (255, 165,   0)   # Wood resource indicator

# ── Fonts ─────────────────────────────────────────────────────────────────────
# Created once at import time; re-used everywhere to avoid repeated allocation.
FONT_LARGE  = pygame.font.SysFont('Arial', 24, bold=True)   # Titles, banners
FONT_MEDIUM = pygame.font.SysFont('Arial', 18)              # Labels, buttons
FONT_SMALL  = pygame.font.SysFont('Arial', 14)              # Tooltips, stats

# ── World / tile ──────────────────────────────────────────────────────────────
TILE_SIZE = 64   # Pixel width and height of one square world tile