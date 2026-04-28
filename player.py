"""
player.py
---------
Human-controlled player entity.

Architecture
------------
Player extends Entity and adds:

* **Movement** – WASD / arrow keys, frame-rate independent via ``dt``, with
  axis-split collision so the player can slide along walls.
* **Camera-follow position** – ``self.pos`` is the world-space centre; the
    game loop passes a ``Camera`` to ``draw`` so the player is projected into
    either the main viewport or the minimap.
* **Facing / rotation** – the sprite is rotated each frame to face the current
  movement direction (or the mouse cursor when stationary, once implemented).
* **Inventory** – a simple ``dict[str, int]`` mapping resource names to
  quantities.  Use the helper methods (``add_resource``, ``consume_resources``,
  etc.) rather than writing to the dict directly so validation stays central.
* **Harvest action** – a lightweight state machine for timed gather actions
  (chopping a tree, mining a rock).  Only one harvest can be active at a time;
  moving cancels it automatically.

Adding new features
-------------------
* Combat stats  → add ``health``, ``max_health``, ``attack_damage`` here.
* Animations    → swap ``self.image`` in ``update`` based on state flags
                  (``is_moving``, ``is_harvesting``, etc.).
* Equipment     → add an ``equipment`` dict and let items modify stats.
* Pathfinding   → the axis-split movement already works with a nav-mesh; just
                  replace the key-press input with waypoint targeting.
"""

from __future__ import annotations

import math
from typing import Optional

import pygame
from pygame import Vector2

from settings import *
from entity import Entity


STARTING_RESOURCES = {
    "wood": 120,
    "stone": 90,
    "gold": 100,
    "food": 50,
}


class Player(Entity):
    """The human-controlled character.

    Attributes
    ----------
    speed : float
        Movement speed in world pixels per second.
    original_image : pygame.Surface
        Unrotated base sprite.  ``self.image`` is derived from this each frame
        by rotating to ``self.facing_angle``.
    inventory : dict[str, int]
        Maps resource names (e.g. ``"wood"``, ``"stone"``) to quantities held.
    harvest_range : float
        Maximum world-pixel distance at which the player can start harvesting
        a resource node.
    harvest_action : dict | None
        Currently active harvest action, or ``None`` if idle.
        Keys: ``"target"``, ``"progress"`` (0.0 – 1.0), ``"duration"``,
        ``"label"``.
    is_moving : bool
        ``True`` while the player has non-zero input this frame.
    """

    # Collision box is narrower than the sprite to allow tight gap navigation.
    _COLLISION_W = 16
    _COLLISION_H = 16
    _ANIMATION_DIRECTION_CODES = {
        "down": "D",
        "side": "S",
        "up": "U",
    }
    _ANIMATION_ACTION_NAMES = {
        "idle": "Idle",
        "walk": "Walk",
        "preattack": "Special",
        "attack": "Special",
    }
    _ANIMATION_FRAME_DURATIONS = {
        "idle": 0.18,
        "walk": 0.12,
        "preattack": 0.08,
        "attack": 0.08,
    }
    _ANIMATION_CACHE: dict[tuple[str, str], tuple[pygame.Surface, ...]] = {}

    def __init__(self, main, x: float, y: float) -> None:
        """
        Parameters
        ----------
        main : Main   application shell (provides debug_mode and game reference)
        x, y : float  initial world-space centre position
        """
        # Load the sprite before calling super so we can pass real dimensions.
        base_image = self._get_animation_frames("down", "idle")[0].copy()


        super().__init__(
            main,
            x, y,
            base_image.get_width(),
            base_image.get_height(),
            tags={"player"},
        )

        # ── Sprite ────────────────────────────────────────────────────────
        # Keep the original unrotated image; self.image is a rotated copy.
        self.original_image: pygame.Surface = base_image
        self.image = self.original_image.copy()

        # Tight collision box (feet / body only, not the full sprite quad).
        self.collision_size = (self._COLLISION_W, self._COLLISION_H)

        # ── Movement ──────────────────────────────────────────────────────
        self.speed: float = 120.0   # pixels per second

        # Runtime state flags
        self.is_moving: bool = False

        # ── Inventory ─────────────────────────────────────────────────────
        # Initialise all known resource keys to 0 so callers can always use
        # integer arithmetic without checking for key existence.
        self.inventory: dict[str, int] = dict(STARTING_RESOURCES)

        # ── Harvest action ────────────────────────────────────────────────
        # Only one harvest can be active at a time.  Moving cancels it.
        self.harvest_range: float = 78.0
        self.build_radius: float = TILE_SIZE * 2.75
        self.build_assist_radius: float = TILE_SIZE * 1.5
        self.attack_range: float = TILE_SIZE * 1.8
        self.attack_damage: float = 20.0
        self.attack_cooldown: float = 0.65
        self.attack_cooldown_remaining: float = 0.0
        self.attack_windup: float = 0.12
        self.attack_recovery: float = 0.2
        self.attack_action: Optional[dict] = None
        self.harvest_action: Optional[dict] = None
        self.harvest_button_held: bool = False
        self.harvest_screen_pos: tuple[int, int] | None = None
        self.animation_action: str = "idle"
        self.animation_direction: str = "down"
        self.animation_frame_index: int = 0
        self.animation_timer: float = 0.0
        self.flip_x: bool = False

    # =========================================================================
    # Event handling
    # =========================================================================

    def handle_event(self, event: pygame.event.Event) -> None:
        """Handle discrete input events (key presses, mouse clicks).

        Continuous input (held keys for movement) is polled inside ``update``
        because it needs delta-time; discrete actions belong here.
        """
        if event.type == pygame.KEYDOWN:
            # TODO: hotkeys, ability triggers, inventory open, etc.
            pass

        elif event.type == pygame.KEYUP:
            pass

        elif event.type == pygame.MOUSEBUTTONDOWN:
            if event.button == 3:   # right mouse – begin harvesting
                self.harvest_button_held = True
                self.harvest_screen_pos = event.pos
                game = getattr(self.main, "game", None)
                if game is not None:
                    game.try_start_player_harvest(event.pos)

        elif event.type == pygame.MOUSEMOTION:
            if self.harvest_button_held:
                self.harvest_screen_pos = event.pos

        elif event.type == pygame.MOUSEBUTTONUP:
            if event.button == 3:
                self.harvest_button_held = False
                self.harvest_screen_pos = None
                self.stop_harvest()

    # =========================================================================
    # Inventory helpers
    # =========================================================================

    def add_resource(self, resource: str, amount: int = 1) -> None:
        """Add *amount* of *resource* to the inventory.

        If *resource* is not yet a known key it is created automatically so
        that adding new resource types later requires no changes here.
        """
        self.inventory[resource] = self.inventory.get(resource, 0) + max(0, int(amount))

    def get_resource_amount(self, resource: str) -> int:
        """Return how many of *resource* the player is carrying (0 if none)."""
        return self.inventory.get(resource, 0)

    def has_resources(self, cost: dict[str, int]) -> bool:
        """Return ``True`` if the player can afford *cost*.

        Parameters
        ----------
        cost : dict mapping resource name → required amount
               e.g. ``{"wood": 50, "stone": 20}``
        """
        return all(
            self.get_resource_amount(res) >= int(qty)
            for res, qty in cost.items()
        )

    def consume_resources(self, cost: dict[str, int]) -> bool:
        """Deduct *cost* from the inventory.

        Returns ``True`` on success, ``False`` (with no deduction) if the
        player cannot afford it.
        """
        if not self.has_resources(cost):
            return False
        for res, qty in cost.items():
            self.inventory[res] -= int(qty)
        return True

    def refund_resources(self, refund: dict[str, int]) -> None:
        """Return *refund* amounts to the inventory (e.g. on building cancel)."""
        for res, qty in refund.items():
            self.add_resource(res, qty)

    # =========================================================================
    # Harvest action state machine
    # =========================================================================

    def start_harvest(self, target) -> None:
        """Begin a timed harvest action against *target*.

        The target is expected to expose:
        * ``action_duration`` (float, seconds)  – how long the harvest takes
        * ``action_label``    (str)              – label shown in the progress bar

        Any currently active harvest is replaced.
        """
        self.harvest_action = {
            "target":   target,
            "progress": 0.0,
            "duration": float(getattr(target, "action_duration", 1.0)),
            "label":    getattr(target, "action_label", "Harvesting"),
        }

    def stop_harvest(self) -> None:
        """Cancel any active harvest without yielding resources."""
        self.harvest_action = None

    def start_attack(self, target) -> bool:
        if self.attack_cooldown_remaining > 0.0:
            return False
        if not self._is_attack_target_valid(target):
            return False
        if target.pos.distance_to(self.pos) > self.attack_range + getattr(target, "attack_radius", 8):
            return False

        self.stop_harvest()
        self.attack_action = {
            "target": target,
            "timer": 0.0,
            "damage_applied": False,
        }
        return True

    def _tick_harvest(self, dt: float) -> None:
        """Advance the active harvest timer by *dt* seconds (called from update).

        When progress reaches 1.0 the harvest is completed: resources are
        collected and the action is cleared.  Subclasses or the game can also
        trigger completion externally via ``stop_harvest``.
        """
        if self.harvest_action is None:
            return

        action = self.harvest_action
        action["progress"] += dt / action["duration"]

        if action["progress"] >= 1.0:
            # Harvest complete – collect the yield from the target.
            target = action["target"]
            if hasattr(target, "harvest"):
                # target.harvest() should return a dict of {resource: amount}
                loot = target.harvest()
                if isinstance(loot, dict):
                    for res, qty in loot.items():
                        self.add_resource(res, qty)
            self.stop_harvest()

    # =========================================================================
    # Update
    # =========================================================================

    def update(self, dt: float) -> None:
        """Advance player state by *dt* seconds.

        Order of operations
        -------------------
        1. Read input and compute movement direction.
        2. Apply axis-split collision (slide along walls).
        3. Rotate sprite to face movement direction.
        4. Tick active harvest action (cancels if the player moved).
        5. Call ``super().update(dt)`` to sync ``self.rect`` from ``self.pos``.
        """
        keys = pygame.key.get_pressed()
        self.attack_cooldown_remaining = max(0.0, self.attack_cooldown_remaining - dt)

        # ── 1. Input → movement vector ─────────────────────────────────────
        # Support both WASD and arrow keys simultaneously.
        move_x = int(keys[pygame.K_d] or keys[pygame.K_RIGHT]) \
               - int(keys[pygame.K_a] or keys[pygame.K_LEFT])
        move_y = int(keys[pygame.K_s] or keys[pygame.K_DOWN]) \
               - int(keys[pygame.K_w] or keys[pygame.K_UP])
        move = Vector2(move_x, move_y)

        self.is_moving = move.length_squared() > 0

        if self.is_moving and self.attack_action is None:
            # Normalise so diagonal movement isn't √2 faster.
            move = move.normalize()
            step = move * self.speed * dt

            # Update facing angle from movement direction.
            # atan2 with negated Y because pygame Y increases downward.
            self.facing_angle = math.degrees(math.atan2(-move.y, move.x))

            # ── 2. Axis-split collision ──────────────────────────────────
            # Try X and Y independently so the player slides along walls
            # instead of stopping dead when a corner is touched.
            game = getattr(self.main, "game", None)

            # Try horizontal move
            next_x = Vector2(self.pos.x + step.x, self.pos.y)
            if game is None or game.can_move_player_to(self.get_collision_rect(next_x)):
                self.pos.x = next_x.x

            # Try vertical move
            next_y = Vector2(self.pos.x, self.pos.y + step.y)
            if game is None or game.can_move_player_to(self.get_collision_rect(next_y)):
                self.pos.y = next_y.y

        # ── 3. Update combat / animation state ────────────────────────────
        if self.attack_action is not None:
            self._tick_attack(dt)
        else:
            if self.is_moving:
                self._set_animation_direction(move)
                self._update_animation("walk", dt)
            else:
                self._update_animation("idle", dt)

        # ── 4. Harvest tick (moving cancels it) ────────────────────────────
        if self.is_moving and self.harvest_action is not None:
            self.stop_harvest()
        else:
            self._tick_harvest(dt)
            if self.harvest_action is None and self.harvest_button_held and self.harvest_screen_pos is not None:
                game = getattr(self.main, "game", None)
                if game is not None:
                    game.try_start_player_harvest(self.harvest_screen_pos)

        # ── 5. Sync rect from pos (base class) ─────────────────────────────
        # NOTE: we already set self.rect above from the rotated image, but
        # calling super keeps the contract intact for any future base changes.
        super().update(dt)

    def _tick_attack(self, dt: float) -> None:
        action = self.attack_action
        if action is None:
            return

        target = action.get("target")
        if not self._is_attack_target_valid(target):
            self.attack_action = None
            self._update_animation("idle", dt)
            return

        max_distance = self.attack_range + getattr(target, "attack_radius", 8)
        if target.pos.distance_to(self.pos) > max_distance:
            self.attack_action = None
            self._update_animation("idle", dt)
            return

        self._set_animation_direction(target.pos - self.pos)
        action["timer"] += dt

        if action["timer"] < self.attack_windup:
            self._update_animation("preattack", dt, loop=False)
            return

        if not action["damage_applied"] and hasattr(target, "take_damage"):
            target.take_damage(self.attack_damage)
            action["damage_applied"] = True

        self._update_animation("attack", dt, loop=False)
        if action["timer"] >= self.attack_windup + self.attack_recovery:
            self.attack_action = None
            self.attack_cooldown_remaining = self.attack_cooldown

    def _is_attack_target_valid(self, target) -> bool:
        return target is not None and getattr(target, "alive", False)

    @classmethod
    def _get_animation_frames(cls, direction: str, action: str) -> tuple[pygame.Surface, ...]:
        cache_key = (direction, action)
        if cache_key in cls._ANIMATION_CACHE:
            return cls._ANIMATION_CACHE[cache_key]

        direction_code = cls._ANIMATION_DIRECTION_CODES[direction]
        action_name = cls._ANIMATION_ACTION_NAMES[action]
        sheet = Entity.load_image(
            "assets", "player", f"{direction_code}_{action_name}.png",
            fallback_size=(48 * 4, 48),
            fallback_color=(60, 180, 240),
        )
        frame_count = max(1, sheet.get_width() // max(1, sheet.get_height()))
        frame_width = max(1, sheet.get_width() // frame_count)

        frames = []
        for frame_index in range(frame_count):
            frame_rect = pygame.Rect(frame_index * frame_width, 0, frame_width, sheet.get_height())
            frames.append(sheet.subsurface(frame_rect).copy())

        cls._ANIMATION_CACHE[cache_key] = tuple(frames)
        return cls._ANIMATION_CACHE[cache_key]

    def _set_animation_direction(self, direction: Vector2) -> None:
        if direction.length_squared() <= 0.0001:
            return

        if abs(direction.x) > abs(direction.y):
            self.animation_direction = "side"
            self.flip_x = direction.x > 0
        elif direction.y < 0:
            self.animation_direction = "up"
            self.flip_x = False
        else:
            self.animation_direction = "down"
            self.flip_x = False

    def _update_animation(self, action: str, dt: float, loop: bool = True) -> None:
        frames = self._get_animation_frames(self.animation_direction, action)
        if action != self.animation_action:
            self.animation_action = action
            self.animation_frame_index = 0
            self.animation_timer = 0.0

        self.animation_timer += dt
        frame_duration = self._ANIMATION_FRAME_DURATIONS[action]

        while self.animation_timer >= frame_duration and len(frames) > 1:
            self.animation_timer -= frame_duration
            next_index = self.animation_frame_index + 1
            if loop:
                self.animation_frame_index = next_index % len(frames)
            else:
                self.animation_frame_index = min(next_index, len(frames) - 1)

        frame = frames[self.animation_frame_index]
        if self.animation_direction == "side" and self.flip_x:
            frame = pygame.transform.flip(frame, True, False)

        self.original_image = frame
        self.image = frame
        self.rect = self.image.get_rect(center=(int(self.pos.x), int(self.pos.y)))

    # =========================================================================
    # Draw
    # =========================================================================

    def draw(self, surface: pygame.Surface, camera=None) -> None:
        """Render the player sprite and optional overlays.

        Layers (bottom → top)
        ---------------------
        1. Rotated player sprite           (base class)
        2. Harvest progress bar            (if harvesting)
        3. Debug overlays                  (if debug_mode: collision box)
        """
        # ── 1. Sprite via base class ───────────────────────────────────────
        super().draw(surface, camera)

        # ── 2. Harvest progress bar ────────────────────────────────────────
        if self.harvest_action is not None:
            self._draw_harvest_bar(surface, camera)

    def _draw_harvest_bar(
        self,
        surface: pygame.Surface,
        camera,
    ) -> None:
        """Draw a progress bar above the player's sprite while harvesting."""
        action = self.harvest_action
        if action is None:
            return

        progress = max(0.0, min(1.0, action["progress"]))

        # Position the bar just above the sprite bounding box. When the camera
        # zooms out for the minimap the bar also scales down so it does not
        # dominate the tiny preview.
        bar_w, bar_h = 40, 5

        if camera is not None and hasattr(camera, "world_to_screen"):
            screen_pos = camera.world_to_screen(self.pos)
            cx = int(screen_pos.x)
            cy = int(screen_pos.y) - max(4, int(self.rect.height * camera.scale_y / 2)) - 6
            bar_w = max(8, int(bar_w * camera.scale_x))
            bar_h = max(2, int(bar_h * camera.scale_y))
        else:
            camera_offset = camera
            cx = int(self.pos.x)
            cy = int(self.pos.y) - self.rect.height // 2 - 8

            if camera_offset is not None:
                cx -= int(camera_offset.x)
                cy -= int(camera_offset.y)

        bar_rect  = pygame.Rect(cx - bar_w // 2, cy, bar_w, bar_h)
        fill_rect = pygame.Rect(bar_rect.x, bar_rect.y,
                                int(bar_w * progress), bar_h)

        # Background trough
        pygame.draw.rect(surface, (40, 30, 20), bar_rect)
        # Filled portion
        pygame.draw.rect(surface, GOLD, fill_rect)
        # Border
        pygame.draw.rect(surface, WHITE, bar_rect, 1)
