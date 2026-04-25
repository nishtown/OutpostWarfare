import pygame

from oldrevision.settings import *
from oldrevision.game import Game

class Main:
    def __init__(self):
        pygame.init()
        pygame.mixer.init()
        self.display_surface = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
        pygame.display.set_caption("Outpost Warfare")
        self.clock = pygame.time.Clock()
        self.debug_mode = False

        self.game = Game(self)

    def run(self):
        running = True

        while running:
            dt = self.clock.tick(FPS) / 1000  # delta time in seconds

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                    break

                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_d and (event.mod & pygame.KMOD_CTRL):
                        self.debug_mode = not self.debug_mode


                self.game.handle_event(event)

            self.game.update(dt)
            self.game.draw(self.display_surface)




            pygame.display.update()

        self.game.shutdown()
        pygame.quit()



if __name__ == '__main__':
    main = Main()
    main.run()