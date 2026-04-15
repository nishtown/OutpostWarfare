import pygame


class Camera:
    def __init__(self, screen_width, screen_height, world_width, world_height, zoom=1.0, min_zoom=0.5, max_zoom=5.0):
        self.screen_width = screen_width
        self.screen_height = screen_height
        self.world_width = world_width
        self.world_height = world_height

        self.min_zoom = min_zoom
        self.max_zoom = max_zoom
        self.zoom = max(self.min_zoom, min(zoom, self.max_zoom))

        self.x = screen_width / 2
        self.y = screen_height / 2

    @property
    def view_width(self):
        return self.screen_width / self.zoom

    @property
    def view_height(self):
        return self.screen_height / self.zoom

    @property
    def left(self):
        return self.x - self.view_width / 2

    @property
    def top(self):
        return self.y - self.view_height / 2

    def update(self, target_x, target_y):
        self.x = target_x
        self.y = target_y
        self.clamp()

    def clamp(self):
        half_w = self.view_width / 2
        half_h = self.view_height / 2

        self.x = max(half_w, min(self.x, self.world_width - half_w))
        self.y = max(half_h, min(self.y, self.world_height - half_h))

    def set_zoom(self, new_zoom):
        self.zoom = max(self.min_zoom, min(new_zoom, self.max_zoom))
        self.clamp()

    def change_zoom(self, amount):
        self.set_zoom(self.zoom + amount)

    def world_to_screen(self, pos):
        wx, wy = pos
        sx = (wx - self.left) * self.zoom
        sy = (wy - self.top) * self.zoom
        return int(sx), int(sy)

    def screen_to_world(self, pos):
        sx, sy = pos
        wx = sx / self.zoom + self.left
        wy = sy / self.zoom + self.top
        return pygame.Vector2(wx, wy)

    def apply_rect(self, rect):
        return pygame.Rect(
            int((rect.x - self.left) * self.zoom),
            int((rect.y - self.top) * self.zoom),
            int(rect.width * self.zoom),
            int(rect.height * self.zoom),
        )

    def visible_rect(self):
        return pygame.Rect(
            int(self.left),
            int(self.top),
            int(self.view_width),
            int(self.view_height),
        )