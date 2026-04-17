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

    def draw(self, surface):
        if self.image is not None:
            img = self.image
            surface.blit(img, self.rect)
            if self.main.debug_mode:
                pygame.draw.rect(surface, RED, self.rect, 1)
