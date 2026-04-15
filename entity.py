from settings import *

class Entity(pygame.sprite.Sprite):
    def __init__(self, main, x, y, width, height):
        pygame.sprite.Sprite.__init__(self)
        self.main = main
        self.image = None
        self.rect = pygame.Rect(x, y , width, height)
        self.rect.center = x,y



    def handle_event(self, event):
        pass

    def update(self, dt):
        pass

    def draw(self, surface, camera, image_override=None):
        img = image_override if image_override is not None else self.image
        if img is None:
            return

        screen_pos = camera.world_to_screen(self.rect.center)

        draw_width = max(1, int(img.get_width())* camera.zoom)
        draw_height = max(1, int(img.get_height()) * camera.zoom)
        draw_image = pygame.transform.scale(img, (draw_width, draw_height))

        draw_rect = draw_image.get_rect(center=screen_pos)
        surface.blit(draw_image, draw_rect)

        if self.main.debug_mode:
            pygame.draw.rect(surface, RED, camera.apply_rect(self.rect), 1)
