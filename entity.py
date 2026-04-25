"""
entity.py
---------
Base class for every game object that lives in the world.

All characters (player, enemies, NPCs), harvestable resources (trees, rocks),
and interactive objects should subclass ``Entity``.  The base class intentionally
keeps only the minimum shared state so that each subclass can opt in to the
features it needs rather than carrying unused overhead.

Subclassing guide
-----------------
* Override ``handle_event(event)`` to react to raw pygame events (keyboard /
  mouse clicks that target this entity specifically).
* Override ``update(dt)`` to advance your own logic, then call ``super().update(dt)``
  at the **end** so that the base class syncs ``self.rect`` from ``self.pos`` and
  decrements any active timers.
* Override ``draw(surface, camera_offset)`` when you need layers beyond the
  default sprite blit (e.g. health bars, shadows, debug shapes).  Call
  ``super().draw(...)`` first to get the base sprite, then add your extras.
* To load a sprite image safely (with a coloured fallback if the file is absent)
  use the ``Entity.load_image`` static helper.
"""

from __future__ import annotations

from typing import Optional

import pygame
from pygame import Vector2

from settings import *


class Entity(pygame.sprite.Sprite):
    """World-space game object base class.

    Every entity lives at a world-space position (``self.pos``) and is
    represented on screen by a pygame ``Rect`` (``self.rect``).  Each frame
    the base ``update`` syncs the rect centre to the position so subclasses
    only need to move ``self.pos``.

    Attributes
    ----------
    main : Main
        Back-reference to the application shell.  Provides access to
        ``main.debug_mode`` and (via ``main.game``) the world systems.
    pos : pygame.Vector2
        World-space position (centre of the entity).  Move this, not the rect.
    vel : pygame.Vector2
        Current velocity in world pixels per second.  The base class does NOT
        apply velocity automatically – subclasses that want simple kinematic
        movement should apply it in their own ``update``::

            self.pos += self.vel * dt

    facing_angle : float
        Heading in degrees, measured counter-clockwise from the positive X
        axis (matching ``pygame.transform.rotate``).  0° = facing right.
    alive : bool
        Set to ``False`` to mark the entity for removal.  The game loop
        should check this flag and call ``entity.kill()`` or remove it from
        its collection.
    tags : set[str]
        Arbitrary string labels (e.g. ``{"enemy", "flying"}``).  Useful for
        querying entity type without ``isinstance`` chains.
    image : pygame.Surface | None
        Sprite surface for rendering.  ``None`` means nothing is drawn (handy
        for invisible trigger volumes, etc.).
    rect : pygame.Rect
        Bounding / render rectangle.  Its centre is kept in sync with ``pos``
        by the base ``update``.
    collision_size : tuple[int, int]
        Width and height of the collision box in pixels.  Defaults to the
        sprite size at construction time and can be overridden by subclasses
        for a tighter hitbox (e.g. player feet only).
    """

    def __init__(
        self,
        main,
        x: float,
        y: float,
        width: int,
        height: int,
        tags: Optional[set] = None,
    ) -> None:
        """
        Parameters
        ----------
        main    : Main    application shell
        x, y    : float   world-space centre position
        width   : int     initial sprite / collision width
        height  : int     initial sprite / collision height
        tags    : set     optional string labels (see class docstring)
        """
        super().__init__()

        self.main = main

        # ── Position & motion ─────────────────────────────────────────────
        # Use Vector2 so arithmetic (+, -, *) works naturally with dt.
        self.pos = Vector2(x, y)
        self.vel = Vector2(0, 0)          # pixels per second
        self.facing_angle: float = 0.0   # degrees, CCW from +X

        # ── Sprite ────────────────────────────────────────────────────────
        self.image: Optional[pygame.Surface] = None
        self.rect  = pygame.Rect(0, 0, width, height)
        self.rect.center = (int(x), int(y))

        # Collision box dimensions (can be overridden by subclasses).
        self.collision_size: tuple[int, int] = (width, height)

        # ── Lifecycle ─────────────────────────────────────────────────────
        self.alive: bool = True

        # ── Metadata ──────────────────────────────────────────────────────
        # String tags allow fast type queries without isinstance chains.
        # e.g.  if "harvestable" in entity.tags: …
        self.tags: set[str] = tags if tags is not None else set()

    # ── Static helpers ────────────────────────────────────────────────────────

    @staticmethod
    def load_image(
        *path_parts: str,
        fallback_size: tuple[int, int] = (32, 32),
        fallback_color: tuple[int, int, int] = (200, 0, 200),
    ) -> pygame.Surface:
        """Load a sprite image, returning a coloured rectangle on failure.

        Uses ``asset_path`` from settings so callers only need to provide the
        path relative to the project root::

            self.image = Entity.load_image("assets", "player", "player.png")

        Parameters
        ----------
        *path_parts    : path components relative to the project root
        fallback_size  : (w, h) of the fallback surface
        fallback_color : RGB colour of the fallback surface (magenta by default
                         so missing art is visually obvious during development)

        Returns
        -------
        pygame.Surface with ``convert_alpha()`` applied.
        """
        try:
            return pygame.image.load(asset_path(*path_parts)).convert_alpha()
        except (FileNotFoundError, pygame.error):
            # Create a solid-colour placeholder so the game can still run.
            surf = pygame.Surface(fallback_size, pygame.SRCALPHA)
            surf.fill(fallback_color)
            return surf

    # ── Collision ─────────────────────────────────────────────────────────────

    def get_collision_rect(self, pos: Optional[Vector2] = None) -> pygame.Rect:
        """Return a collision rect centred on *pos* (or ``self.pos`` if None).

        Subclasses can override ``collision_size`` to use a hitbox that is
        smaller than the visible sprite (e.g. feet-only collision for a top-
        down character).

        Parameters
        ----------
        pos : Vector2 | None
            World-space centre to use.  Defaults to the entity's current pos.
        """
        centre = pos if pos is not None else self.pos
        r = pygame.Rect(0, 0, self.collision_size[0], self.collision_size[1])
        r.center = (int(centre.x), int(centre.y))
        return r

    # ── Event handling ────────────────────────────────────────────────────────

    def handle_event(self, event: pygame.event.Event) -> None:
        """Process a raw pygame event.  Override in subclasses as needed."""
        pass

    # ── Update ────────────────────────────────────────────────────────────────

    def update(self, dt: float) -> None:
        """Advance base entity state by *dt* seconds.

        Call ``super().update(dt)`` at the **end** of every subclass ``update``
        so this always runs last.  It keeps ``self.rect`` in sync with
        ``self.pos`` so subclasses only have to move the Vector2.
        """
        # Keep the render rect centred on the world-space position.
        self.rect.center = (int(self.pos.x), int(self.pos.y))

    # ── Draw ──────────────────────────────────────────────────────────────────

    def draw(self, surface: pygame.Surface, camera_offset: Optional[Vector2] = None) -> None:
        """Blit the entity sprite onto *surface*, adjusted for *camera_offset*.

        Parameters
        ----------
        surface       : target surface (the game world_surface)
        camera_offset : world-space offset of the camera top-left corner.
                        Subtract this from world coordinates to get screen
                        coordinates.  Pass ``None`` if no camera is in use.
        """
        if self.image is None:
            return

        # Translate from world space to screen space.
        draw_rect = self.rect.copy()
        if camera_offset is not None:
            draw_rect = draw_rect.move(-int(camera_offset.x), -int(camera_offset.y))

        surface.blit(self.image, draw_rect)

        # ── Debug overlays ────────────────────────────────────────────────
        if self.main.debug_mode:
            # Sprite bounding box (red)
            pygame.draw.rect(surface, RED, draw_rect, 1)

            # Collision box (yellow) – may differ from sprite rect
            col_rect = self.get_collision_rect()
            if camera_offset is not None:
                col_rect = col_rect.move(-int(camera_offset.x), -int(camera_offset.y))
            pygame.draw.rect(surface, (255, 220, 0), col_rect, 1)

