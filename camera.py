"""
camera.py
---------
Reusable 2D camera used by both the main game view and the minimap.

The camera does two jobs:

1. It tracks a target (usually the player) by keeping that target near the
   centre of the visible area.
2. It converts world-space positions and rectangles into screen-space values
   for a particular render surface.

This implementation supports two important use cases:

* **Main camera**   – 1:1 world-to-screen rendering for the primary viewport.
* **Minimap camera** – a wider world view projected into a much smaller render
  surface, which lets the minimap show more area than the player currently
  sees on the main screen.
"""

from __future__ import annotations

import pygame
from pygame import Vector2


class Camera:
    """A rectangular view into a larger world.

    Parameters
    ----------
    world_width, world_height : int | float
        Size of the world in world-space pixels.
    surface_width, surface_height : int
        Pixel dimensions of the render target this camera projects onto.
    view_width, view_height : int | float | None
        How much world space the camera can see. If omitted, the camera shows
        a 1:1 area matching the render surface size.
    name : str
        Optional descriptive label useful when debugging multiple cameras.
    """

    def __init__(
        self,
        world_width: float,
        world_height: float,
        surface_width: int,
        surface_height: int,
        view_width: float | None = None,
        view_height: float | None = None,
        name: str = "camera",
    ) -> None:
        self.name = name

        self.world_width = float(world_width)
        self.world_height = float(world_height)

        self.surface_width = int(surface_width)
        self.surface_height = int(surface_height)

        self.view_width = float(view_width if view_width is not None else surface_width)
        self.view_height = float(view_height if view_height is not None else surface_height)

        self.offset = Vector2(0, 0)
        self.target = None

    @property
    def scale_x(self) -> float:
        """Horizontal world-to-screen scale."""
        return self.surface_width / self.view_width

    @property
    def scale_y(self) -> float:
        """Vertical world-to-screen scale."""
        return self.surface_height / self.view_height

    @property
    def view_rect(self) -> pygame.Rect:
        """Current visible rectangle in world-space coordinates."""
        return pygame.Rect(
            int(self.offset.x),
            int(self.offset.y),
            int(self.view_width),
            int(self.view_height),
        )

    def set_target(self, target) -> None:
        """Attach the camera to a target.

        The target can be any object with a ``pos`` attribute, or a raw
        ``Vector2`` / tuple world position.
        """
        self.target = target

    def resize(
        self,
        surface_width: int,
        surface_height: int,
        view_width: float | None = None,
        view_height: float | None = None,
    ) -> None:
        """Update the render-surface size and optionally the visible world size."""
        self.surface_width = int(surface_width)
        self.surface_height = int(surface_height)
        if view_width is not None:
            self.view_width = float(view_width)
        if view_height is not None:
            self.view_height = float(view_height)
        self.offset = self._clamp_offset(self.offset)

    def update(self) -> None:
        """Follow the current target and clamp the view to the world bounds."""
        if self.target is None:
            return

        position = getattr(self.target, "pos", self.target)
        self.center_on(position)

    def center_on(self, position) -> None:
        """Move the camera so *position* sits at the centre of the view."""
        pos = Vector2(position)

        target_offset = Vector2(
            pos.x - self.view_width / 2,
            pos.y - self.view_height / 2,
        )
        self.offset = self._clamp_offset(target_offset)

    def _clamp_offset(self, offset: Vector2) -> Vector2:
        """Clamp the camera's top-left offset so the view stays inside the world."""
        max_x = max(0.0, self.world_width - self.view_width)
        max_y = max(0.0, self.world_height - self.view_height)
        return Vector2(
            max(0.0, min(offset.x, max_x)),
            max(0.0, min(offset.y, max_y)),
        )

    def world_to_screen(self, position) -> Vector2:
        """Project a world-space point into screen-space for this camera."""
        pos = Vector2(position)
        return Vector2(
            (pos.x - self.offset.x) * self.scale_x,
            (pos.y - self.offset.y) * self.scale_y,
        )

    def world_rect_to_screen(self, rect: pygame.Rect) -> pygame.Rect:
        """Project a world-space rect into screen-space for this camera."""
        top_left = self.world_to_screen((rect.x, rect.y))
        width = max(1, int(rect.width * self.scale_x))
        height = max(1, int(rect.height * self.scale_y))
        return pygame.Rect(int(top_left.x), int(top_left.y), width, height)