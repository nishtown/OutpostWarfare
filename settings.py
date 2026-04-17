import pygame
import os

BASE_DIR = os.path.dirname(__file__)

def asset_path(*parts):
    return os.path.join(BASE_DIR, *parts)


SCREEN_WIDTH = 1024
SCREEN_HEIGHT = 1024
MAP_WIDTH = SCREEN_WIDTH
MAP_HEIGHT = SCREEN_HEIGHT

FPS = 60

BLACK = (0, 0, 0)
WHITE = (255, 255, 255)
LIGHT_GRAY = (100, 100, 100)
GRAY = (50, 50, 50)
GREEN = (0, 255, 0)
DARK_GREEN = (0, 75, 0)
RED = (255, 0, 0)
BLUE = (0, 0, 255)
YELLOW = (255, 255, 0)

TILE_SIZE = 64