"""
gameui.py
---------
Right-hand side UI panel for Outpost Warfare.

Layout (top → bottom inside the panel)
--------------------------------------
  ┌─────────────────────────────┐  ← panel_x, panel_y
  │         REGION MAP          │  Minimap  (_MM_H px)
  │  (live scaled world view)   │
  ├─────── [ CONSTRUCT ] ───────┤  section divider + header
  │  [Town Hall]  [Barracks]    │  2 × 3 grid of BuildingButtons
  │  [Farm]       [Workshop]    │  each _BTN_H px tall
  │  [Market]     [Lumberyard]  │
  ├─────── [ RESOURCES ] ───────┤  section divider + header
  │  icon  GOLD    ████░ 1500   │  4-row resource panel (_RES_PANEL_H px)
  │  icon  FOOD    ███░░  800   │
  │  icon  WOOD    ██░░░  600   │
  │  icon  STONE   █░░░░  400   │
  ├─────────────────────────────┤
  │  Selected: Town Hall        │  current placement selection
  │  Click map to place         │
  ├─────────────────────────────┤
  │  =  OUTPOST WARFARE  =      │  title plate
  └─────────────────────────────┘

Minimap world-surface pipeline
-------------------------------
Each frame ``Game.draw`` renders the full game world onto a dedicated
``world_surface`` (``VIEWPORT_WIDTH × VIEWPORT_HEIGHT``).  That surface is
passed here as ``world_surface`` and scaled down with
``pygame.transform.smoothscale`` to fill the minimap rect, giving a
real-time top-down overview of whatever is currently visible in-game.
"""

from dataclasses import dataclass
import math
import pygame
from settings import *
from world_objects import BUILD_DEFINITIONS, BUILD_MENU_ORDER, format_cost_text

# ── UI palette (medieval stone / parchment) ──────────────────────────────────
STONE_DARK   = (45,  38,  28)
STONE_MID    = (72,  60,  42)
STONE_LIGHT  = (108, 91,  63)
STONE_HILIT  = (148, 128, 88)
PARCHMENT    = (200, 175, 115)
PARCHMENT_DK = (140, 115, 70)
CRIMSON      = (140, 20,  20)
SHADOW_CLR   = (15,  12,  8)
GLOW_AMBER   = (255, 200, 60)

# ── Layout constants ─────────────────────────────────────────────────────────
# All measurements in pixels; prefixed with _ to mark them as module-private.
_PAD         = UI_PANEL_PADDING         # uniform padding inside the panel on all sides
_MM_H        = MINIMAP_SURFACE_HEIGHT   # height of the minimap image area
_MM_LABEL_H  = 18    # vertical space reserved below the minimap for the label
_SEC_HDR_H   = 26    # height of a section-divider + header row
_BTN_COLS    = 2     # number of build-button columns
_BTN_ROWS    = 4     # number of build-button rows  (cols × rows = total buttons)
_BTN_GAP     = 5     # pixel gap between adjacent buttons
_BTN_H       = 72    # height of each BuildingButton
_RES_PANEL_H = 132   # total height of the resources panel
_TOP_BAR_PAD = 10


@dataclass(frozen=True)
class Announcement:
    """One time-boxed UI announcement queued for on-screen display."""

    text: str
    accent: tuple[int, int, int]
    duration: float
    key: str | None = None


class AnnouncementFeed:
    """Small queued announcement system for wave and combat events.

    Messages are shown one at a time near the top of the main viewport. The
    UI owns the presentation, while gameplay systems can push messages through
    ``GameUI.announce`` without knowing how the banner is drawn.
    """

    _FADE_TIME = 0.3
    _TOP_MARGIN = 18
    _BANNER_HEIGHT = 60
    _MIN_WIDTH = 260
    _SIDE_MARGIN = 24

    def __init__(self, viewport_rect):
        self.viewport_rect = pygame.Rect(viewport_rect)
        self.queue: list[Announcement] = []
        self.current: Announcement | None = None
        self.time_remaining = 0.0
        self.elapsed = 0.0
        self.current_time = 0.0
        self.last_push_times: dict[str, float] = {}

    def push(self, text, accent=GOLD, duration=3.0, key=None, cooldown=0.0):
        if key is not None and cooldown > 0.0:
            last_time = self.last_push_times.get(key, float("-inf"))
            if self.current_time - last_time < cooldown:
                return False
            self.last_push_times[key] = self.current_time

        announcement = Announcement(text=text, accent=accent, duration=max(0.8, duration), key=key)
        self.queue.append(announcement)
        if self.current is None:
            self._advance()
        return True

    def update(self, dt):
        self.current_time += dt
        if self.current is None:
            if self.queue:
                self._advance()
            return

        self.elapsed += dt
        self.time_remaining -= dt
        if self.time_remaining <= 0.0:
            self._advance()

    def draw(self, surface):
        if self.current is None:
            return

        alpha_scale = self._alpha_scale()
        if alpha_scale <= 0.0:
            return

        caption = FONT_SMALL.render("[ HERALD ]", True, PARCHMENT)
        text = FONT_MEDIUM.render(self.current.text, True, WHITE)
        banner_width = min(
            self.viewport_rect.width - self._SIDE_MARGIN * 2,
            max(self._MIN_WIDTH, text.get_width() + 76),
        )

        banner_rect = pygame.Rect(0, 0, banner_width, self._BANNER_HEIGHT)
        banner_rect.midtop = (self.viewport_rect.centerx, self.viewport_rect.y + self._TOP_MARGIN)

        overlay = pygame.Surface(banner_rect.size, pygame.SRCALPHA)
        overlay_rect = overlay.get_rect()
        bg_alpha = int(224 * alpha_scale)
        border_alpha = int(190 * alpha_scale)
        accent_alpha = int(245 * alpha_scale)

        pygame.draw.rect(overlay, (18, 14, 10, int(120 * alpha_scale)), overlay_rect.move(0, 4), border_radius=10)
        pygame.draw.rect(overlay, (*STONE_DARK, bg_alpha), overlay_rect, border_radius=10)
        pygame.draw.rect(overlay, (*STONE_HILIT, border_alpha), overlay_rect, 2, border_radius=10)
        pygame.draw.rect(overlay, (*self.current.accent, accent_alpha), (14, 9, overlay_rect.width - 28, 4), border_radius=2)
        pygame.draw.rect(overlay, (*SHADOW_CLR, border_alpha), (14, overlay_rect.height - 13, overlay_rect.width - 28, 2), border_radius=1)

        caption.set_alpha(int(210 * alpha_scale))
        text.set_alpha(int(255 * alpha_scale))
        overlay.blit(caption, (overlay_rect.centerx - caption.get_width() // 2, 11))
        overlay.blit(text, (overlay_rect.centerx - text.get_width() // 2, 28))

        surface.blit(overlay, banner_rect.topleft)

    def _advance(self):
        if self.queue:
            self.current = self.queue.pop(0)
            self.time_remaining = self.current.duration
            self.elapsed = 0.0
        else:
            self.current = None
            self.time_remaining = 0.0
            self.elapsed = 0.0

    def _alpha_scale(self):
        if self.current is None:
            return 0.0

        fade_in = min(1.0, self.elapsed / self._FADE_TIME)
        fade_out = min(1.0, self.time_remaining / self._FADE_TIME)
        return max(0.0, min(fade_in, fade_out))


# ── Low-level draw helpers ────────────────────────────────────────────────────
# These are pure drawing utilities with no state; kept module-level so any
# class can call them without needing a reference to the GameUI instance.

def _bevel(surface, rect, raised=True, width=2):
    """Draw a 3-D bevel border around *rect*.

    When ``raised=True`` the top and left edges are bright (``STONE_HILIT``)
    and the bottom and right edges are dark (``SHADOW_CLR``), making the
    element appear to protrude from the panel.  ``raised=False`` inverts the
    colours for a sunken / pressed look.

    Parameters
    ----------
    surface : pygame.Surface
    rect    : pygame.Rect
    raised  : bool   – True → raised (default); False → sunken
    width   : int    – number of border pixels on each side
    """
    hi = STONE_HILIT if raised else SHADOW_CLR
    sh = SHADOW_CLR  if raised else STONE_HILIT
    r = rect
    for i in range(width):
        pygame.draw.line(surface, hi, (r.x+i,       r.y+i),        (r.right-i-1, r.y+i))
        pygame.draw.line(surface, hi, (r.x+i,       r.y+i),        (r.x+i,       r.bottom-i-1))
        pygame.draw.line(surface, sh, (r.x+i,       r.bottom-i-1), (r.right-i-1, r.bottom-i-1))
        pygame.draw.line(surface, sh, (r.right-i-1, r.y+i),        (r.right-i-1, r.bottom-i-1))


def _stone_fill(surface, rect, color=STONE_MID):
    """Fill *rect* with *color* then add a thin edge-darkening vignette.

    The vignette is painted onto a temporary SRCALPHA surface and blitted at
    low opacity, so the fill colour still reads clearly through it.  This
    avoids the flat, uniform look of a plain ``pygame.draw.rect``.
    """
    pygame.draw.rect(surface, color, rect)
    darken = pygame.Surface((rect.width, rect.height), pygame.SRCALPHA)
    for d in range(5):
        alpha = 18 - d * 3
        if alpha <= 0:
            break
        inner = pygame.Rect(d, d, rect.width - d * 2, rect.height - d * 2)
        pygame.draw.rect(darken, (0, 0, 0, alpha), inner, 1)
    surface.blit(darken, rect.topleft)


def _stone_courses(surface, x, y, w, h, step=32):
    """Draw horizontal mortar lines every *step* pixels.

    Each course is two pixels tall: a dark shadow line and a mid-tone
    highlight, which together create the illusion of individual stone blocks
    laid in horizontal rows.
    """
    for cy in range(y, y + h, step):
        pygame.draw.line(surface, SHADOW_CLR, (x, cy),   (x + w, cy),   1)
        pygame.draw.line(surface, STONE_MID,  (x, cy+1), (x + w, cy+1), 1)


def _divider(surface, x, y, width):
    """Draw a single engraved horizontal rule at (*x*, *y*).

    Composed of two 1-px lines: a dark shadow on the top row and a bright
    highlight on the row below, producing a carved-into-stone effect.
    """
    pygame.draw.line(surface, SHADOW_CLR,  (x, y),   (x + width, y),   1)
    pygame.draw.line(surface, STONE_HILIT, (x, y+1), (x + width, y+1), 1)


def _section_header(surface, text, x, y, width, font=None):
    """Render a centred *text* label with engraved rules on each side.

    The rules are drawn at the vertical midpoint of the text so the label
    appears to sit inside a recessed banner, similar to section headings in
    classic RTS side-panels.
    """
    font = font or FONT_SMALL
    txt  = font.render(text, True, PARCHMENT)
    tw   = txt.get_width()
    th   = txt.get_height()
    ly   = y + th // 2
    margin = 6
    lw = (width - tw) // 2 - margin
    if lw > 0:
        pygame.draw.line(surface, SHADOW_CLR,  (x,                       ly),   (x + lw,             ly),   1)
        pygame.draw.line(surface, STONE_HILIT, (x,                       ly+1), (x + lw,             ly+1), 1)
        rx = x + (width + tw) // 2 + margin
        pygame.draw.line(surface, SHADOW_CLR,  (rx,                      ly),   (x + width,          ly),   1)
        pygame.draw.line(surface, STONE_HILIT, (rx,                      ly+1), (x + width,          ly+1), 1)
    surface.blit(txt, (x + (width - tw) // 2, y))


def _corner_bracket(surface, x, y, size=10, flip_x=False, flip_y=False):
    """Draw a small L-shaped ornamental bracket at a frame corner.

    Pass ``flip_x=True`` for right-side corners and ``flip_y=True`` for
    bottom corners.  Two overlapping lines (parchment outer + highlight inner)
    give the bracket a slight 3-D depth.
    """
    sx = -1 if flip_x else 1
    sy = -1 if flip_y else 1
    pts_outer = [(x, y + sy*size), (x, y), (x + sx*size, y)]
    pts_inner = [(x+sx, y + sy*(size-1)), (x+sx, y+sy), (x + sx*(size-1), y+sy)]
    pygame.draw.lines(surface, PARCHMENT,   False, pts_outer, 1)
    pygame.draw.lines(surface, STONE_HILIT, False, pts_inner, 1)


def _panel_left_edge(surface, x, y, height):
    """Draw the decorative multi-layer left edge of the UI panel.

    Four vertical lines at increasing x offsets (shadow → dark stone →
    mid stone → highlight) create the impression of a thick stone wall
    seen from slightly above.
    """
    pygame.draw.line(surface, SHADOW_CLR,  (x,   y), (x,   y+height), 1)
    pygame.draw.line(surface, STONE_DARK,  (x+1, y), (x+1, y+height), 2)
    pygame.draw.line(surface, STONE_MID,   (x+3, y), (x+3, y+height), 2)
    pygame.draw.line(surface, STONE_HILIT, (x+5, y), (x+5, y+height), 1)


# ── Resource icons ────────────────────────────────────────────────────────────
# Each icon is drawn from primitives centred on (cx, cy) within a ~14×14 px
# bounding box.  They are intentionally pixelated / heraldic in style to
# match the medieval aesthetic.

def _icon_gold(surface, cx, cy):  # Gold coin – two concentric circles
    pygame.draw.circle(surface, GOLD,           (cx, cy), 7)
    pygame.draw.circle(surface, (180, 140,  0), (cx, cy), 7, 1)
    pygame.draw.circle(surface, (255, 240, 80), (cx, cy), 4)
    pygame.draw.circle(surface, (200, 160,  0), (cx, cy), 4, 1)


def _icon_food(surface, cx, cy):  # Wheat stalk – vertical stem + grain ears
    pygame.draw.line(surface, (120, 180, 40), (cx, cy+7), (cx, cy-5), 2)
    for dy in (-5, -1, 3):
        pygame.draw.ellipse(surface, (90, 155, 28), (cx-5, cy+dy-3, 5, 5))
        pygame.draw.ellipse(surface, (90, 155, 28), (cx+1, cy+dy-3, 5, 5))


def _icon_wood(surface, cx, cy):  # Log end-grain – concentric circles + ring line
    pygame.draw.circle(surface, (100, 60, 20), (cx, cy), 7)
    pygame.draw.circle(surface, (65,  40, 10), (cx, cy), 7, 1)
    pygame.draw.circle(surface, (130, 80, 30), (cx, cy), 4)
    pygame.draw.circle(surface, (65,  40, 10), (cx, cy), 4, 1)
    pygame.draw.line(surface,   (65,  40, 10), (cx-3, cy-3), (cx+3, cy+3), 1)


def _icon_stone(surface, cx, cy):  # Rough hexagonal rock with highlight facet
    pts = [(cx + int(7*math.cos(math.radians(i*60-30))),
            cy + int(7*math.sin(math.radians(i*60-30)))) for i in range(6)]
    pygame.draw.polygon(surface, (110, 100, 90), pts)
    pygame.draw.polygon(surface, (75,  68,  58), pts, 1)
    pygame.draw.circle(surface,  (148, 135, 120), (cx-1, cy-1), 3)


# ── UIElement base ────────────────────────────────────────────────────────────

class UIElement:
    """Base class for all UI elements.

    Provides a pygame.Rect, a base fill colour, and hover tracking.  Subclasses
    override ``draw`` to add their own rendering on top of the stone-fill base.
    """

    def __init__(self, x, y, width, height, color=STONE_MID, border_color=STONE_HILIT):
        self.rect         = pygame.Rect(x, y, width, height)
        self.color        = color
        self.border_color = border_color
        self.hovered      = False

    def draw(self, surface):
        _stone_fill(surface, self.rect, self.color)
        _bevel(surface, self.rect)

    def is_hovered(self, pos):
        return self.rect.collidepoint(pos)


# ── Button ────────────────────────────────────────────────────────────────────

class Button(UIElement):
    """A simple clickable button with a text label.

    Renders with a raised bevel normally and a sunken bevel on hover to give
    tactile feedback.  The text colour is always ``PARCHMENT`` for legibility
    against the stone background.
    """

    def __init__(self, x, y, width, height, text,
                 color=STONE_MID, hover_color=STONE_LIGHT):
        super().__init__(x, y, width, height, color)
        self.text        = ""
        self.hover_color = hover_color
        self.text_surf   = None
        self.text_rect   = None
        self.set_text(text)

    def set_text(self, text):
        self.text = text
        self.text_surf = FONT_MEDIUM.render(text, True, PARCHMENT)
        self.text_rect = self.text_surf.get_rect(center=self.rect.center)

    def draw(self, surface):
        col = self.hover_color if self.hovered else self.color
        _stone_fill(surface, self.rect, col)
        _bevel(surface, self.rect, raised=not self.hovered)
        surface.blit(self.text_surf, self.text_rect)

    def click(self):
        return self.hovered


# ── BuildingButton (C&C-style square icon buttons) ────────────────────────────

class BuildingButton(Button):
    """Square icon button modelled after the C&C sidebar build panel.

    Each button is divided into two vertical zones:
    * **Icon area** (upper ~58 %) – coloured background + hand-drawn
      primitive silhouette representing the building type.
    * **Label strip** (lower ~42 %) – building name centred left, gold cost
      badge right-aligned at the bottom edge.

    States
    ------
    normal   – dark stone background, raised bevel
    hovered  – lighter stone, sunken bevel
    selected – crimson background, sunken bevel, amber glow outline

    Class attribute ``_ICON_COLOR`` maps building type strings to the
    dominant tint used in the icon area.
    """

    _ICON_COLOR = {
        "barracks":   (120,  35, 35),
        "farm":       ( 55, 135, 35),
        "workshop":   ( 95,  75, 35),
        "market":     (175, 155, 35),
        "lumberyard": ( 55,  95, 35),
        "stone_quarry": (110, 110, 110),
        "gold_quarry": (168, 138, 52),
        "arrow_tower": (135, 100, 58),
        "wall":       (130, 124, 114),
        "spike_trap": (110, 90, 58),
    }

    def __init__(self, x, y, width, height, text, cost_text, building_type):
        super().__init__(x, y, width, height, text)
        self.cost_text     = cost_text
        self.building_type = building_type
        self.selected      = False
        self.name_surf     = FONT_SMALL.render(text, True, PARCHMENT)
        self.cost_surf     = FONT_SMALL.render(cost_text, True, GOLD)

    def draw(self, surface):
        # Background
        if self.selected:
            bg = CRIMSON
        elif self.hovered:
            bg = STONE_LIGHT
        else:
            bg = STONE_DARK
        _stone_fill(surface, self.rect, bg)
        _bevel(surface, self.rect, raised=not (self.hovered or self.selected), width=2)

        # Icon area (upper ~58% of button)
        icon_h = int(self.rect.height * 0.58)
        icon_r = pygame.Rect(self.rect.x + 4, self.rect.y + 4,
                             self.rect.width - 8, icon_h - 4)
        icon_col = self._ICON_COLOR.get(self.building_type, STONE_MID)
        _stone_fill(surface, icon_r, icon_col)
        _bevel(surface, icon_r, raised=False, width=1)
        self._draw_icon_art(surface, icon_r)

        # Name label
        label_y = self.rect.y + icon_h + 4
        nx = self.rect.centerx - self.name_surf.get_width() // 2
        surface.blit(self.name_surf, (nx, label_y))

        # Cost badge (bottom-right)
        cw = self.cost_surf.get_width()
        surface.blit(self.cost_surf,
                     (self.rect.right - cw - 3,
                      self.rect.bottom - self.cost_surf.get_height() - 2))

        # Amber selection glow
        if self.selected:
            pygame.draw.rect(surface, GLOW_AMBER, self.rect.inflate(2, 2), 1)

    def _draw_icon_art(self, surface, icon_r):
        """Draw a simple building silhouette inside *icon_r* using primitives.

        Deliberately lo-fi / pixelated – uses only ``pygame.draw`` rectangles,
        polygons, and arcs so no external assets are required.  Replace with
        sprite blitting once proper building artwork is available.
        """
        cx  = icon_r.centerx
        cy  = icon_r.centery
        bw  = min(icon_r.width - 8, 30)
        bh  = min(icon_r.height - 6, 18)
        hi  = (220, 190, 130)
        drk = (30,  22,  12)
        base = pygame.Rect(cx - bw//2, cy - bh//2 + 4, bw, bh)
        t = self.building_type

        if t == "barracks":
            pygame.draw.rect(surface, hi, base)
            pygame.draw.polygon(surface, drk,
                                [(base.x, base.y), (cx, base.y-8), (base.right, base.y)])
        elif t == "farm":
            small = pygame.Rect(cx-8, cy-4, 16, 12)
            pygame.draw.rect(surface, hi, small)
            pygame.draw.polygon(surface, drk,
                                [(small.x, small.y), (cx, small.y-6), (small.right, small.y)])
            for fx in range(base.x, base.right, 5):
                pygame.draw.circle(surface, (60, 140, 30), (fx, cy+9), 2)
        elif t == "workshop":
            pygame.draw.rect(surface, hi, base)
            pygame.draw.rect(surface, drk, (cx+4, base.y-6, 4, 8))
        elif t == "market":
            pygame.draw.rect(surface, hi, base)
            for sx in range(base.x+2, base.right-2, 8):
                pygame.draw.rect(surface, drk, (sx, base.y, 1, base.height))
        elif t == "lumberyard":
            for ly_off in range(3):
                log_r = pygame.Rect(cx-10, cy-2 + ly_off*5, 20, 4)
                pygame.draw.rect(surface, (110, 70, 25), log_r)
                pygame.draw.rect(surface, drk, log_r, 1)
        elif t == "stone_quarry":
            pygame.draw.rect(surface, hi, (cx-10, cy-2, 20, 10))
            pygame.draw.circle(surface, (130, 130, 130), (cx-5, cy+1), 4)
            pygame.draw.circle(surface, (156, 156, 156), (cx+3, cy-2), 4)
        elif t == "gold_quarry":
            pygame.draw.rect(surface, hi, (cx-10, cy-2, 20, 10))
            pygame.draw.circle(surface, (190, 162, 66), (cx-5, cy+1), 4)
            pygame.draw.circle(surface, (224, 196, 86), (cx+3, cy-2), 4)
        elif t == "arrow_tower":
            pygame.draw.rect(surface, hi, (cx-7, base.y-8, 14, 18))
            pygame.draw.rect(surface, drk, (cx-10, base.y-10, 20, 4))
            pygame.draw.line(surface, GLOW_AMBER, (cx+1, base.y), (cx+11, base.y-8), 2)
        elif t == "wall":
            pygame.draw.rect(surface, hi, (base.x, cy-3, base.width, 8))
            for wx in range(base.x+2, base.right-2, 6):
                pygame.draw.rect(surface, drk, (wx, cy-7, 4, 4))
        elif t == "spike_trap":
            pygame.draw.rect(surface, drk, (cx-10, cy+2, 20, 5))
            for sx in range(cx-10, cx+8, 5):
                pygame.draw.polygon(surface, hi, [(sx, cy+2), (sx+2, cy-6), (sx+4, cy+2)])


# ── Minimap ───────────────────────────────────────────────────────────────────

class Minimap:
    """Real-time minimap rendered from a dedicated wider-range camera surface.

    The minimap sits at the very top of the right-hand UI panel inside a
    raised stone frame. Each frame it receives a pre-rendered surface from the
    minimap camera. That camera follows the player just like the main camera,
    but its visible world rectangle is much larger, so the minimap shows more
    area than the player sees on the main screen.

    On top of the minimap image we also draw:

    * the player's current position
    * a white rectangle showing the main camera's visible area inside the
      wider minimap region

    Attributes
    ----------
    rect : pygame.Rect
        The image area of the minimap (inside the stone frame).
    """

    def __init__(self, x, y, width, height):
        # The rect covers only the inner image area; the stone frame is
        # drawn by inflating this rect by 8 px in each direction.
        self.rect = pygame.Rect(x, y, width, height)

    def _render_point_to_ui(self, point, source_size):
        """Convert a point from the render-surface space into UI space."""
        scale_x = self.rect.width / source_size[0]
        scale_y = self.rect.height / source_size[1]
        return (
            self.rect.x + int(point.x * scale_x),
            self.rect.y + int(point.y * scale_y),
        )

    def _render_rect_to_ui(self, rect, source_size):
        """Convert a rect from the render-surface space into UI space."""
        scale_x = self.rect.width / source_size[0]
        scale_y = self.rect.height / source_size[1]
        return pygame.Rect(
            self.rect.x + int(rect.x * scale_x),
            self.rect.y + int(rect.y * scale_y),
            max(1, int(rect.width * scale_x)),
            max(1, int(rect.height * scale_y)),
        )

    def draw(
        self,
        surface,
        world_surface=None,
        minimap_camera=None,
        tracked_view_rect=None,
        player_pos=None,
    ):
        """Draw the minimap onto *surface*.

        Parameters
        ----------
        surface : pygame.Surface
            The main display surface (or the panel surface) to draw onto.
        world_surface : pygame.Surface or None
            The pre-rendered world surface produced for the minimap camera.
        minimap_camera : Camera or None
            The camera used to render ``world_surface``.
        tracked_view_rect : pygame.Rect or None
            The main camera's current world-space view rect.  It is projected
            onto the minimap so the player can see what the main screen covers.
        player_pos : pygame.Vector2 or None
            Current player world position for the gold minimap marker.
        """
        # ── Outer raised stone frame ──────────────────────────────────────
        frame = self.rect.inflate(8, 8)
        _stone_fill(surface, frame, STONE_DARK)
        _bevel(surface, frame, raised=True, width=3)

        # ── Map content ───────────────────────────────────────────────────
        source_size = (self.rect.width, self.rect.height)
        if world_surface is not None:
            source_size = world_surface.get_size()

            if world_surface.get_size() == self.rect.size:
                surface.blit(world_surface, self.rect.topleft)
            else:
                scaled = pygame.transform.smoothscale(
                    world_surface, (self.rect.width, self.rect.height)
                )
                surface.blit(scaled, self.rect.topleft)
        else:
            # ── Static placeholder (used before world is wired up) ────────
            # Fill with a dark-green base to suggest terrain.
            pygame.draw.rect(surface, (24, 55, 20), self.rect)

            # Faint grid lines to suggest the underlying tile grid.
            for i in range(0, self.rect.width, 18):
                pygame.draw.line(surface, (32, 65, 25),
                                 (self.rect.x+i, self.rect.y),
                                 (self.rect.x+i, self.rect.bottom), 1)
            for i in range(0, self.rect.height, 18):
                pygame.draw.line(surface, (32, 65, 25),
                                 (self.rect.x, self.rect.y+i),
                                 (self.rect.right, self.rect.y+i), 1)

            # Representative coloured dots for different structure types.
            pygame.draw.rect(surface, (170, 110, 35), (self.rect.x+48,  self.rect.y+28, 8, 8))  # town hall
            pygame.draw.rect(surface, (110,  30, 30), (self.rect.x+100, self.rect.y+68, 6, 6))  # barracks
            pygame.draw.rect(surface, ( 50, 130, 35), (self.rect.x+138, self.rect.y+48, 5, 5))  # farm
            pygame.draw.rect(surface, ( 50, 130, 35), (self.rect.x+65,  self.rect.y+95, 5, 5))  # farm

        # ── Main camera view box ──────────────────────────────────────────
        if minimap_camera is not None and tracked_view_rect is not None:
            view_box = minimap_camera.world_rect_to_screen(tracked_view_rect)
            view_box = self._render_rect_to_ui(view_box, source_size)
            pygame.draw.rect(surface, BLACK, view_box.inflate(2, 2), 1)
            pygame.draw.rect(surface, WHITE, view_box, 1)

        # ── Player position dot ───────────────────────────────────────────
        if minimap_camera is not None and player_pos is not None:
            player_render_pos = minimap_camera.world_to_screen(player_pos)
            cx, cy = self._render_point_to_ui(player_render_pos, source_size)
        else:
            cx, cy = self.rect.centerx, self.rect.centery

        pygame.draw.circle(surface, GOLD,  (cx, cy), 4)
        pygame.draw.circle(surface, WHITE, (cx, cy), 4, 1)   # thin white ring for contrast

        # ── Recessed inner border (drawn on top of content) ───────────────
        # This makes the map image appear to sit inside a carved stone recess.
        _bevel(surface, self.rect, raised=False, width=2)

        # ── Corner bracket ornaments ──────────────────────────────────────
        # Four L-shaped brackets, one per corner, for a heraldic map-frame look.
        for fx, fy in [(False, False), (True, False), (False, True), (True, True)]:
            ox = self.rect.right  if fx else self.rect.x
            oy = self.rect.bottom if fy else self.rect.y
            _corner_bracket(surface, ox, oy, size=10, flip_x=fx, flip_y=fy)

        # ── Label below the map ───────────────────────────────────────────
        lbl = FONT_SMALL.render("--  REGION MAP  --", True, PARCHMENT)
        surface.blit(lbl, (self.rect.centerx - lbl.get_width()//2, self.rect.bottom + 3))


# ── Main side-panel UI ────────────────────────────────────────────────────────

class GameUI:
    """The complete right-hand side panel.

    Composed of (top to bottom):
    * ``Minimap``             – real-time scaled view of the game world
    * Build grid              – 2 × 3 ``BuildingButton`` widgets
    * Resources panel         – four rows of icon / label / bar / value
    * Selected-building strip – shows the queued placement and hint text
    * Title plate             – decorative footer

    Resource values (``gold``, ``food``, ``wood``, ``stone``) are public
    attributes; the game systems should write to them each frame before
    calling ``draw`` so the panel always shows current totals.
    """

    def __init__(self):
        # Panel dimensions – width from settings so changing UI_PANEL_WIDTH
        # automatically adjusts the layout without touching this file.
        self.panel_width  = UI_PANEL_WIDTH
        self.panel_height = SCREEN_HEIGHT - TOP_BAR_HEIGHT
        self.panel_x      = SCREEN_WIDTH - self.panel_width
        self.panel_y      = TOP_BAR_HEIGHT
        self.top_bar_rect = pygame.Rect(0, 0, SCREEN_WIDTH, TOP_BAR_HEIGHT)

        px      = self.panel_x
        py      = self.panel_y
        inner_w = self.panel_width - _PAD * 2   # drawable width inside the panel

        # ── Minimap widget ────────────────────────────────────────────────
        # Positioned at the very top of the panel with _PAD margin on all sides.
        self.minimap = Minimap(px + _PAD, py + _PAD, inner_w, _MM_H)

        # ── Build grid layout ─────────────────────────────────────────────
        # Divider sits below the minimap image + its label gap.
        self._div1_y    = py + _PAD + _MM_H + _MM_LABEL_H
        # Buttons start below the section header.
        self._build_top = self._div1_y + _SEC_HDR_H

        # Button width fills inner_w split into _BTN_COLS columns with _BTN_GAP gaps.
        btn_w = (inner_w - (_BTN_COLS - 1) * _BTN_GAP) // _BTN_COLS

        building_defs = [
            (BUILD_DEFINITIONS[key].label, format_cost_text(BUILD_DEFINITIONS[key].cost), key)
            for key in BUILD_MENU_ORDER
        ]
        self.build_rows = max(1, math.ceil(len(building_defs) / _BTN_COLS))
        # Build the button grid, filling columns left-to-right, rows top-to-bottom.
        self.build_buttons = []
        for idx, (name, cost, btype) in enumerate(building_defs):
            col = idx % _BTN_COLS
            row = idx // _BTN_COLS
            bx  = px + _PAD + col * (btn_w + _BTN_GAP)
            by  = self._build_top + row * (_BTN_H + _BTN_GAP)
            self.build_buttons.append(
                BuildingButton(bx, by, btn_w, _BTN_H, name, cost, btype)
            )

        # y coordinate of the bottom edge of the last button row.
        last_btn_bottom = self._build_top + self.build_rows * (_BTN_H + _BTN_GAP) - _BTN_GAP

        # Current resource totals.  Write to these attributes each frame
        # (or whenever the economy ticks) to keep the display up to date.
        self.gold  = 0
        self.food  = 0
        self.wood  = 0
        self.stone = 0

        # The building type string that is queued for placement, or None.
        self.selected_building = None
        self.selected_structure = None

        # y coordinate where the selected-building status strip starts.
        self._status_y = last_btn_bottom + 18
        self._wave_button_y = self._status_y + 92

        # Announcements are drawn above the main viewport rather than inside
        # the side panel so important events stay visible during play.
        self.announcements = AnnouncementFeed(pygame.Rect(0, TOP_BAR_HEIGHT, VIEWPORT_WIDTH, VIEWPORT_HEIGHT))
        self.upgrade_button = Button(px + _PAD, self._wave_button_y, inner_w, 36, "Upgrade")
        self.repair_button = Button(px + _PAD, self._wave_button_y, inner_w, 36, "Repair")
        self.reset_button = Button(VIEWPORT_X + VIEWPORT_WIDTH // 2 - 84, VIEWPORT_Y + VIEWPORT_HEIGHT // 2 + 34, 168, 42, "Reset Outpost")
        self.next_wave_number = 1
        self.wave_timer_remaining = 10.0
        self.wave_in_progress = False
        self.game_over = False

    def _resource_rows(self):
        return [
            ("GOLD", self.gold, GOLD, _icon_gold),
            ("FOOD", self.food, (80, 200, 80), _icon_food),
            ("WOOD", self.wood, (170, 115, 45), _icon_wood),
            ("STONE", self.stone, LIGHT_GRAY, _icon_stone),
        ]

    def _draw_top_bar(self, surface):
        bar = self.top_bar_rect
        pygame.draw.rect(surface, STONE_DARK, bar)
        _stone_courses(surface, bar.x, bar.y, bar.width, bar.height, step=24)
        _bevel(surface, bar, raised=True, width=3)

        card_gap = 12
        card_width = (bar.width - (_TOP_BAR_PAD * 2) - (card_gap * 3)) // 4
        card_height = bar.height - 18
        card_y = bar.y + 9

        for index, (name, value, color, icon_fn) in enumerate(self._resource_rows()):
            card_x = bar.x + _TOP_BAR_PAD + index * (card_width + card_gap)
            card_rect = pygame.Rect(card_x, card_y, card_width, card_height)
            _stone_fill(surface, card_rect, STONE_MID if index % 2 == 0 else STONE_DARK)
            _bevel(surface, card_rect, raised=False, width=2)

            icon_fn(surface, card_rect.x + 16, card_rect.centery)
            label = FONT_SMALL.render(name, True, PARCHMENT_DK)
            value_surf = FONT_MEDIUM.render(str(value), True, color)
            surface.blit(label, (card_rect.x + 30, card_rect.y + 5))
            surface.blit(value_surf, (card_rect.right - value_surf.get_width() - 8, card_rect.y + 4))

            bar_x = card_rect.x + 30
            bar_width = card_rect.width - 40
            fill_width = int(bar_width * min(value / 2000.0, 1.0))
            bar_y = card_rect.bottom - 8
            pygame.draw.rect(surface, SHADOW_CLR, (bar_x, bar_y, bar_width, 4))
            if fill_width > 0:
                pygame.draw.rect(surface, color, (bar_x, bar_y, fill_width, 4))

    # ── Events ───────────────────────────────────────────────────────────────

    def handle_events(self, event):
        """Process a single pygame event.

        Updates hover and selection state for all build buttons.  Call this
        once per event inside the main event loop (forwarded from Game).
        """
        if event.type == pygame.MOUSEMOTION:
            if self.game_over:
                self.reset_button.hovered = self.reset_button.is_hovered(event.pos)
                self.upgrade_button.hovered = False
                self.repair_button.hovered = False
                return None

            # Update hover flag on each button based on the new cursor position.
            for btn in self.build_buttons:
                btn.hovered = btn.is_hovered(event.pos)
            self.upgrade_button.hovered = (
                self.selected_structure is not None
                and getattr(self.selected_structure, "is_upgradeable", False)
                and not getattr(self.selected_structure, "is_repairable", False)
                and self.upgrade_button.is_hovered(event.pos)
            )
            self.repair_button.hovered = (
                self.selected_structure is not None
                and getattr(self.selected_structure, "is_repairable", False)
                and self.repair_button.is_hovered(event.pos)
            )

        elif event.type == pygame.MOUSEBUTTONDOWN:
            if self.game_over and self.reset_button.hovered:
                return "reset_game"

            if self.game_over:
                return None

            if self.repair_button.hovered:
                return "repair_selected_structure"
            if self.upgrade_button.hovered:
                return "upgrade_selected_structure"

            # Left-click selects the hovered building and deselects all others.
            for btn in self.build_buttons:
                if btn.hovered:
                    if self.selected_building == btn.building_type:
                        self.clear_build_selection()
                    else:
                        self.clear_build_selection()
                        btn.selected = True
                        self.selected_building = btn.building_type
                        self.selected_structure = None
                    return "build_selection_changed"

        return None

    def clear_build_selection(self):
        self.selected_building = None
        for btn in self.build_buttons:
            btn.selected = False

    def set_selected_structure(self, structure):
        self.selected_structure = structure
        if structure is not None:
            self.clear_build_selection()

    def set_game_over(self, game_over: bool):
        self.game_over = bool(game_over)
        if self.game_over:
            self.clear_build_selection()
            self.selected_structure = None

    def update(self, dt):
        """Advance transient UI state such as queued announcements."""
        self.announcements.update(dt)

    def announce(self, text, accent=GOLD, duration=3.0, key=None, cooldown=0.0):
        """Queue a banner announcement for the player."""
        self.announcements.push(text, accent=accent, duration=duration, key=key, cooldown=cooldown)

    def set_wave_state(self, next_wave_number, wave_timer_remaining, wave_in_progress):
        self.next_wave_number = int(next_wave_number)
        self.wave_timer_remaining = max(0.0, float(wave_timer_remaining))
        self.wave_in_progress = bool(wave_in_progress)

    # ── Draw ─────────────────────────────────────────────────────────────────

    def draw(
        self,
        surface,
        world_surface=None,
        minimap_camera=None,
        tracked_view_rect=None,
        player_pos=None,
    ):
        """Render the entire UI panel onto *surface*.

        Parameters
        ----------
        surface : pygame.Surface
            The main display surface.  The panel is drawn at ``self.panel_x``
            which places it flush against the right edge of the window.
        world_surface : pygame.Surface or None
            The dedicated minimap render surface.
        minimap_camera : Camera or None
            The wider-range camera used to render ``world_surface``.
        tracked_view_rect : pygame.Rect or None
            The main camera's current world-space view rect.
        player_pos : pygame.Vector2 or None
            Current player world position for the minimap marker.
        """
        px = self.panel_x
        py = self.panel_y
        pw = self.panel_width
        ph = self.panel_height
        inner_w = pw - _PAD * 2

        self._draw_top_bar(surface)

        # ── Panel background ──────────────────────────────────────────────
        # Solid stone-dark base, horizontal mortar courses, decorative left edge.
        pygame.draw.rect(surface, STONE_DARK, (px, py, pw, ph))
        _stone_courses(surface, px, py, pw, ph, step=32)
        _panel_left_edge(surface, px, py, ph)

        # ── Minimap – passes the live world surface for real-time scaling ──
        self.minimap.draw(
            surface,
            world_surface,
            minimap_camera=minimap_camera,
            tracked_view_rect=tracked_view_rect,
            player_pos=player_pos,
        )

        # ── Construct section ─────────────────────────────────────────────
        _divider(surface, px + _PAD, self._div1_y, inner_w)
        _section_header(surface, "[ CONSTRUCT ]",
                        px + _PAD, self._div1_y + 4, inner_w, FONT_SMALL)
        # Draw each building button in the 2-column grid.
        for btn in self.build_buttons:
            btn.draw(surface)

        # ── Selected building status strip ────────────────────────────────
        # Only rendered if there is vertical space between here and the footer.
        sy = self._status_y
        if sy + 92 < py + ph - 40:
            _divider(surface, px + _PAD, sy, inner_w)
            if self.selected_structure is not None:
                structure = self.selected_structure
                title_text = structure.definition.label
                if getattr(structure, "max_level", 1) > 1:
                    title_text += f" Lv {structure.level}/{structure.max_level}"
                lbl = FONT_MEDIUM.render(title_text, True, GOLD)
                health_text = f"Health: {int(structure.health)}/{int(structure.max_health)}"
                hint_lines = [health_text]

                if structure.definition.key == "arrow_tower":
                    hint_lines.append(
                        f"Range {int(structure.tower_range)}  Damage {int(structure.projectile_damage)}"
                    )
                    if getattr(structure, "is_repairable", False):
                        hint_lines.append(f"Repair Cost: {format_cost_text(structure.get_repair_cost() or {})}")
                    else:
                        upkeep_status = "Supplied" if getattr(structure, "is_operational", True) else "No food - offline"
                        upkeep_interval = int(getattr(structure, "_FOOD_UPKEEP_INTERVAL", 0))
                        hint_lines.append(
                            f"Food {structure.definition.food_upkeep}/{upkeep_interval}s  {upkeep_status}"
                        )
                elif structure.definition.key == "farm":
                    ready_plots = sum(1 for plot in getattr(structure, "farm_plots", []) if plot.get("ready_timer", 0.0) > 0.0)
                    total_plots = len(getattr(structure, "farm_plots", []))
                    hint_lines.append(f"Food Produced: {structure.food_produced}")
                    hint_lines.append(f"Plots Ready: {ready_plots}/{total_plots}")
                elif getattr(structure, "worker_resource_key", None) == "tree":
                    hint_lines.append(f"Wood Delivered: {structure.wood_delivered}")
                    upkeep_status = "Supplied" if getattr(structure, "is_operational", True) else "No food - idle"
                    upkeep_interval = int(getattr(structure, "_FOOD_UPKEEP_INTERVAL", 0))
                    hint_lines.append(
                        f"Food {structure.definition.food_upkeep}/{upkeep_interval}s  {upkeep_status}"
                    )
                elif getattr(structure, "worker_resource_key", None) == "rock":
                    hint_lines.append(f"Stone Delivered: {getattr(structure, 'stone_delivered', 0)}")
                    upkeep_status = "Supplied" if getattr(structure, "is_operational", True) else "No food - idle"
                    upkeep_interval = int(getattr(structure, "_FOOD_UPKEEP_INTERVAL", 0))
                    hint_lines.append(
                        f"Food {structure.definition.food_upkeep}/{upkeep_interval}s  {upkeep_status}"
                    )
                elif getattr(structure, "worker_resource_key", None) == "gold":
                    hint_lines.append(f"Gold Delivered: {getattr(structure, 'gold_delivered', 0)}")
                    upkeep_status = "Supplied" if getattr(structure, "is_operational", True) else "No food - idle"
                    upkeep_interval = int(getattr(structure, "_FOOD_UPKEEP_INTERVAL", 0))
                    hint_lines.append(
                        f"Food {structure.definition.food_upkeep}/{upkeep_interval}s  {upkeep_status}"
                    )
                elif structure.definition.key == "main_base":
                    hint_lines.append("Protect the settlement core")
                    hint_lines.append("Enemy contact damages the base")
                else:
                    if structure.definition.food_upkeep > 0:
                        upkeep_status = "Supplied" if getattr(structure, "is_operational", True) else "No food - idle"
                        upkeep_interval = int(getattr(structure, "_FOOD_UPKEEP_INTERVAL", 0))
                        hint_lines.append(
                            f"Food {structure.definition.food_upkeep}/{upkeep_interval}s  {upkeep_status}"
                        )
                    hint_lines.append("Click the world to deselect")

                surface.blit(lbl, (px + _PAD + 4, sy + 6))
                for index, line in enumerate(hint_lines[:3]):
                    hint = FONT_SMALL.render(line, True, PARCHMENT_DK)
                    surface.blit(hint, (px + _PAD + 4, sy + 8 + lbl.get_height() + index * 16))
            elif self.selected_building:
                # Convert snake_case building type to a Title Case display name.
                name_txt = self.selected_building.replace("_", " ").title()
                lbl  = FONT_MEDIUM.render(name_txt, True, GOLD)
                cost_text = format_cost_text(BUILD_DEFINITIONS[self.selected_building].cost)
                hint = FONT_SMALL.render(f"Cost: {cost_text}  |  Click again to cancel", True, PARCHMENT_DK)
                surface.blit(lbl,  (px + _PAD + 4, sy + 6))
                surface.blit(hint, (px + _PAD + 4, sy + 6 + lbl.get_height() + 2))

        if self._wave_button_y + 36 < py + ph - 42:
            _divider(surface, px + _PAD, self._wave_button_y - 10, inner_w)
            if self.selected_structure is not None and getattr(self.selected_structure, "is_repairable", False):
                cost_text = format_cost_text(self.selected_structure.get_repair_cost() or {})
                self.repair_button.set_text(f"Repair {cost_text}")
                self.repair_button.draw(surface)
            elif self.selected_structure is not None and getattr(self.selected_structure, "is_upgradeable", False):
                cost_text = format_cost_text(self.selected_structure.get_upgrade_cost() or {})
                self.upgrade_button.set_text(f"Upgrade {cost_text}")
                self.upgrade_button.draw(surface)
            else:
                if self.wave_in_progress:
                    wave_text = f"Wave {self.next_wave_number - 1} underway"
                else:
                    wave_text = f"Next Wave {self.next_wave_number} in {self.wave_timer_remaining:0.1f}s"
                timer_text = FONT_SMALL.render(wave_text, True, PARCHMENT)
                timer_rect = timer_text.get_rect(center=(px + pw // 2, self._wave_button_y + 16))
                surface.blit(timer_text, timer_rect)

        # ── Bottom title plate ────────────────────────────────────────────
        title_y = py + ph - 34
        _divider(surface, px + _PAD, title_y - 4, inner_w)
        title = FONT_MEDIUM.render("=  OUTPOST WARFARE  =", True, GOLD)
        surface.blit(title, (px + pw//2 - title.get_width()//2, title_y + 2))

        # Draw announcement banners last so they stay above world content.
        self.announcements.draw(surface)

        if self.game_over:
            self._draw_game_over_overlay(surface)

    def _draw_game_over_overlay(self, surface):
        overlay = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
        overlay.fill((8, 6, 4, 170))
        surface.blit(overlay, (0, 0))

        panel_rect = pygame.Rect(0, 0, 360, 180)
        panel_rect.center = (VIEWPORT_X + VIEWPORT_WIDTH // 2, VIEWPORT_Y + VIEWPORT_HEIGHT // 2)
        _stone_fill(surface, panel_rect, STONE_DARK)
        _bevel(surface, panel_rect, raised=True, width=3)

        title = FONT_LARGE.render("Settlement Fallen", True, GOLD)
        hint = FONT_MEDIUM.render("Press R or reset to start again", True, PARCHMENT)
        subhint = FONT_SMALL.render("The main base was destroyed.", True, WHITE)
        surface.blit(title, title.get_rect(center=(panel_rect.centerx, panel_rect.y + 44)))
        surface.blit(subhint, subhint.get_rect(center=(panel_rect.centerx, panel_rect.y + 82)))
        surface.blit(hint, hint.get_rect(center=(panel_rect.centerx, panel_rect.y + 108)))
        self.reset_button.draw(surface)
