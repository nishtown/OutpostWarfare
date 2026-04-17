import pygame
from player import Player
from building import Depot, Lumberyard, Tower, Wall
from world import World
from settings import *


class Game:
    def __init__(self, main):
        self.main = main
        self.font = pygame.font.SysFont(None, 60)
        self.ui_font = pygame.font.SysFont(None, 28)
        self.small_font = pygame.font.SysFont(None, 22)

        self.player = Player(main, 100, 100, 16, 16)
        self.world = World(main, tile_size=16)
        spawn_pos = self.world.find_nearest_walkable_position(self.player.pos, self.player.collision_size)
        self.player.pos = spawn_pos
        self.player.rect = self.player.image.get_rect(center=self.player.pos)
        self.buildings = set()
        self.buildrange = 200

        self.buildmode = False
        self.build_menu_open = False
        self.can_place = False
        self.placeable_object = None
        self.selected_building = None

        self.build_catalog = [
            self.create_build_option(pygame.K_1, Tower),
            self.create_build_option(pygame.K_2, Wall),
            self.create_build_option(pygame.K_3, Depot),
            self.create_build_option(pygame.K_4, Lumberyard),
        ]

    def create_build_option(self, key, building_class):
        return {
            "key": key,
            "class": building_class,
            "name": building_class.display_name,
            "build_time": building_class.default_build_time,
            "preview": building_class.create_preview(),
        }

    def can_move_player_to(self, rect):
        if not self.world.is_rect_walkable(rect):
            return False

        for building in self.buildings:
            if building.rect.colliderect(rect):
                return False

        return True

    def can_place_building_rect(self, rect):
        if not self.world.is_rect_walkable(rect):
            return False

        for building in self.buildings:
            if building.rect.colliderect(rect):
                return False

        if self.player.get_collision_rect().colliderect(rect):
            return False

        return True

    def toggle_build_menu(self):
        if self.buildmode or self.build_menu_open:
            self.cancel_build_action()
        else:
            self.build_menu_open = True

    def cancel_build_action(self):
        self.buildmode = False
        self.build_menu_open = False
        self.can_place = False
        self.placeable_object = None
        self.selected_building = None

    def start_build_placement(self, option):
        self.selected_building = option
        self.buildmode = True
        self.build_menu_open = False

        building_class = option["class"]
        self.placeable_object = building_class(
            self.main,
            self.player.pos.x,
            self.player.pos.y,
        )

    def place_selected_building(self):
        if self.placeable_object is None or self.selected_building is None:
            return

        option = self.selected_building
        building_class = option["class"]
        building = building_class(
            self.main,
            self.placeable_object.pos.x,
            self.placeable_object.pos.y,
        )
        self.buildings.add(building)
        self.cancel_build_action()

    def get_build_menu_rects(self):
        option_width = 105
        option_height = 78
        gap = 10
        padding = 15
        menu_width = (len(self.build_catalog) * option_width) + ((len(self.build_catalog) - 1) * gap) + (padding * 2)
        menu_height = 140
        menu_rect = pygame.Rect(20, SCREEN_HEIGHT - menu_height - 20, menu_width, menu_height)
        option_y = menu_rect.y + 38

        option_rects = []
        for index, option in enumerate(self.build_catalog):
            option_x = menu_rect.x + padding + index * (option_width + gap)
            option_rects.append((option, pygame.Rect(option_x, option_y, option_width, option_height)))

        return menu_rect, option_rects

    def handle_event(self, event):
        self.player.handle_event(event)

        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_b:
                self.toggle_build_menu()
                return

            if event.key == pygame.K_ESCAPE:
                self.cancel_build_action()
                return

            if self.build_menu_open:
                for option in self.build_catalog:
                    if event.key == option["key"]:
                        self.start_build_placement(option)
                        return

        elif event.type == pygame.MOUSEBUTTONDOWN:
            if event.button == 1 and self.build_menu_open:
                _, option_rects = self.get_build_menu_rects()
                for option, rect in option_rects:
                    if rect.collidepoint(event.pos):
                        self.start_build_placement(option)
                        return

            if event.button == 3 and (self.buildmode or self.build_menu_open):
                self.cancel_build_action()
                return

        elif event.type == pygame.MOUSEBUTTONUP:
            if event.button == 1 and self.buildmode and self.can_place:
                self.place_selected_building()
                return

    def update(self, dt):
        self.player.update(dt, self.buildmode or self.build_menu_open)
        mouse_pos = pygame.mouse.get_pos()

        self.world.update(dt)

        for building in self.buildings:
            building.update(dt)

        if self.buildmode and self.placeable_object is not None:
            self.placeable_object.pos = pygame.math.Vector2(mouse_pos[0], mouse_pos[1])
            self.placeable_object.rect.center = self.placeable_object.pos
            in_range = self.player.pos.distance_to(mouse_pos) < self.buildrange
            self.can_place = in_range and self.can_place_building_rect(self.placeable_object.rect)
        else:
            self.can_place = False

    def draw(self, surface):
        self.world.draw_ground(surface)

        for building in self.buildings:
            building.draw(surface)

        placement_hint = None
        if self.buildmode:
            self.draw_build_range(surface)
            if self.placeable_object is not None:
                preview = self.placeable_object.image.copy()
                preview.set_alpha(170 if self.can_place else 90)
                surface.blit(preview, self.placeable_object.rect)
                pygame.draw.rect(surface, GREEN if self.can_place else RED, self.placeable_object.rect, 2)

                name = self.selected_building["name"] if self.selected_building else "Building"
                placement_hint = self.small_font.render(
                    f"Placing: {name}  |  Left click to place  |  Right click or ESC to cancel",
                    True,
                    WHITE,
                )

        self.player.draw(surface)
        self.world.draw_trees(surface)

        if placement_hint is not None:
            surface.blit(placement_hint, (20, 20))

        if self.build_menu_open:
            self.draw_build_menu(surface)

        for building in self.buildings:
            building.draw_overlay(surface)

    def draw_build_menu(self, surface):
        menu_rect, option_rects = self.get_build_menu_rects()

        panel = pygame.Surface(menu_rect.size, pygame.SRCALPHA)
        panel.fill((20, 20, 20, 220))
        surface.blit(panel, menu_rect.topleft)
        pygame.draw.rect(surface, LIGHT_GRAY, menu_rect, 2, border_radius=10)

        title = self.ui_font.render("Choose what to build", True, WHITE)
        surface.blit(title, (menu_rect.x + 15, menu_rect.y + 10))

        mouse_pos = pygame.mouse.get_pos()
        for index, (option, rect) in enumerate(option_rects, start=1):
            hovered = rect.collidepoint(mouse_pos)
            fill_color = (80, 80, 80) if hovered else (55, 55, 55)
            pygame.draw.rect(surface, fill_color, rect, border_radius=8)
            pygame.draw.rect(surface, WHITE, rect, 1, border_radius=8)

            preview_rect = option["preview"].get_rect(center=(rect.centerx, rect.centery - 8))
            surface.blit(option["preview"], preview_rect)

            label = self.small_font.render(f"{index}. {option['name']}", True, WHITE)
            label_rect = label.get_rect(center=(rect.centerx, rect.bottom - 22))
            surface.blit(label, label_rect)

            time_label = self.small_font.render(f"{option['build_time']:.1f}s", True, LIGHT_GRAY)
            time_rect = time_label.get_rect(center=(rect.centerx, rect.bottom - 9))
            surface.blit(time_label, time_rect)

        footer = self.small_font.render("Press 1-4 or click an option", True, WHITE)
        surface.blit(footer, (menu_rect.x + 15, menu_rect.bottom - 20))

    def draw_build_range(self, surface):
        range_image = pygame.Surface((self.buildrange * 2, self.buildrange * 2))
        range_image.fill((0, 0, 0))
        range_image.set_colorkey((0, 0, 0))
        pygame.draw.circle(
            range_image,
            (220, 220, 220),
            (self.buildrange, self.buildrange),
            self.buildrange,
            self.buildrange,
        )

        range_image.set_alpha(20)
        range_image.get_rect(center=self.player.rect.center)
        surface.blit(range_image, range_image.get_rect(center=self.player.rect.center))