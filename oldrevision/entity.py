from oldrevision.settings import *


class Entity(pygame.sprite.Sprite):
    def __init__(self, main, x, y, width, height):
        pygame.sprite.Sprite.__init__(self)
        self.main = main

        self.image = None
        self.rect = pygame.Rect(x, y, width, height)
        self.rect.center = x, y

    def handle_event(self, event):
        pass

    def update(self, dt):
        pass

    def draw(self, surface, camera_offset=None):
        if self.image is not None:
            draw_rect = self.rect.copy()
            if camera_offset is not None:
                draw_rect = draw_rect.move(-int(camera_offset.x), -int(camera_offset.y))

            surface.blit(self.image, draw_rect)
            if self.main.debug_mode:
                pygame.draw.rect(surface, RED, draw_rect, 1)
