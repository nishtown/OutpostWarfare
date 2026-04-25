import pygame
from oldrevision.player import Player
from oldrevision.building import Depot, Lumberyard, Tower, Wall
from oldrevision.world import World
from oldrevision.settings import *


class Camera:
    def __init__(self):
        self.offset = pygame.Vector2()

    def update(self, target_pos):
        self.offset.x = target_pos.x - (SCREEN_WIDTH / 2)
        self.offset.y = target_pos.y - (SCREEN_HEIGHT / 2)

    def apply_rect(self, rect):
        return rect.move(-int(self.offset.x), -int(self.offset.y))

    def screen_to_world(self, screen_pos):
        return pygame.Vector2(screen_pos[0] + self.offset.x, screen_pos[1] + self.offset.y)

    def visible_rect(self):
        return pygame.Rect(int(self.offset.x), int(self.offset.y), SCREEN_WIDTH, SCREEN_HEIGHT)


class Game:
    def __init__(self, main):
        self.main = main
        self.main.game = self

        self.font = pygame.font.SysFont(None, 60)
        self.ui_font = pygame.font.SysFont(None, 28)
        self.small_font = pygame.font.SysFont(None, 22)

        self.player = Player(main, 100, 100, 16, 16)
        self.world = World(main, tile_size=16)
        spawn_pos = self.world.find_nearest_walkable_position(self.player.pos, self.player.collision_size)
        self.player.pos = spawn_pos
        self.player.rect = self.player.image.get_rect(center=self.player.pos)

        self.camera = Camera()
        self.camera.update(self.player.pos)

        self.buildings = set()
        self.buildrange = 200

        self.buildmode = False
        self.build_menu_open = False
        self.can_place = False
        self.placeable_object = None
        self.selected_building = None
        self.selected_structure = None
        self.placement_error = None

        self.build_catalog = [
            self.create_build_option(pygame.K_1, Tower),
            self.create_build_option(pygame.K_2, Wall),
            self.create_build_option(pygame.K_3, Depot),
            self.create_build_option(pygame.K_4, Lumberyard),
        ]

        self.world.prime(self.camera, self.get_tracked_entities())

    def get_tracked_entities(self):
        return [self.player, *self.buildings]

    def create_build_option(self, key, building_class):
        return {
            "key": key,
            "class": building_class,
            "name": building_class.display_name,
            "build_time": building_class.default_build_time,
            "cost": dict(building_class.default_cost),
            "preview": building_class.create_preview(),
        }

    def can_afford_building_class(self, building_class):
        return self.player.has_resources(building_class.default_cost)

    def find_building_at_screen_pos(self, screen_pos):
        for building in sorted(self.buildings, key=lambda structure: structure.rect.bottom, reverse=True):
            if self.camera.apply_rect(building.rect).collidepoint(screen_pos):
                return building
        return None

    def select_structure_at(self, screen_pos):
        self.selected_structure = self.find_building_at_screen_pos(screen_pos)
        if self.selected_structure is not None:
            self.player.stop_harvest()

    def demolish_selected_structure(self):
        if self.selected_structure is None or self.selected_structure not in self.buildings:
            self.selected_structure = None
            return

        refund = self.selected_structure.get_demolition_refund()
        if refund:
            self.player.refund_resources(refund)

        self.buildings.remove(self.selected_structure)
        self.selected_structure = None

    def start_harvesting_nearest_resource(self):
        if self.buildmode or self.build_menu_open:
            self.player.stop_harvest()
            return

        nearby_resources = self.world.get_nearby_resource_nodes(self.player.pos, self.player.harvest_range)
        if not nearby_resources:
            self.player.stop_harvest()
            return

        target = nearby_resources[0]
        if self.player.harvest_action is not None and self.player.harvest_action["target"] is target:
            return

        self.selected_structure = None
        self.player.start_harvest(target)

    def update_harvest_input(self):
        if self.buildmode or self.build_menu_open:
            self.player.stop_harvest()
            return

        right_mouse_down = pygame.mouse.get_pressed()[2]
        if not right_mouse_down:
            self.player.stop_harvest()
            return

        action = self.player.harvest_action
        if action is not None:
            target = action["target"]
            if target is not None and hasattr(target, "can_harvest") and target.can_harvest():
                if self.player.pos.distance_to(target.pos) <= self.player.harvest_range:
                    return

        self.start_harvesting_nearest_resource()

    def update_player_harvest(self, dt):
        action = self.player.harvest_action
        if action is None:
            return

        if self.buildmode or self.build_menu_open or not pygame.mouse.get_pressed()[2]:
            self.player.stop_harvest()
            return

        target = action["target"]
        if target is None or not hasattr(target, "can_harvest") or not target.can_harvest():
            self.player.stop_harvest()
            return

        if self.player.pos.distance_to(target.pos) > self.player.harvest_range:
            self.player.stop_harvest()
            return

        action["progress"] += dt
        if action["progress"] < action["duration"]:
            return

        action["progress"] -= action["duration"]
        if target.harvest(1):
            self.player.add_resource(target.resource_type, getattr(target, "resource_yield", 1))

            chunk_key = getattr(target, "chunk_key", None)
            if chunk_key is not None:
                chunk = self.world.get_available_chunk(chunk_key)
                if chunk is not None and target.resource_type == "wood":
                    self.world.refresh_chunk_tree_metadata(chunk_key, chunk)

        if not target.can_harvest():
            self.player.stop_harvest()

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
            self.player.stop_harvest()
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
        self.selected_structure = None
        self.player.stop_harvest()

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
        if not self.player.consume_resources(building_class.default_cost):
            self.placement_error = "Not enough resources"
            return

        building = building_class(
            self.main,
            self.placeable_object.pos.x,
            self.placeable_object.pos.y,
        )
        self.buildings.add(building)
        self.selected_structure = building
        self.cancel_build_action()

    def get_build_menu_rects(self):
        option_width = 105
        option_height = 94
        gap = 10
        padding = 15
        menu_width = (len(self.build_catalog) * option_width) + ((len(self.build_catalog) - 1) * gap) + (padding * 2)
        menu_height = 158
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

            if event.key in (pygame.K_DELETE, pygame.K_BACKSPACE, pygame.K_x):
                self.demolish_selected_structure()
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

            if event.button == 1 and not self.buildmode:
                self.select_structure_at(event.pos)
                return

            if event.button == 3 and (self.buildmode or self.build_menu_open):
                self.cancel_build_action()
                return

        elif event.type == pygame.MOUSEBUTTONUP:
            if event.button == 1 and self.buildmode and self.can_place:
                self.place_selected_building()
                return

            if event.button == 3:
                self.player.stop_harvest()
                return

    def update(self, dt):
        self.player.update(dt, self.buildmode or self.build_menu_open)
        self.camera.update(self.player.pos)
        self.world.update(dt, self.camera, self.get_tracked_entities())
        self.update_harvest_input()
        self.update_player_harvest(dt)

        for building in list(self.buildings):
            building.update(dt)

        if self.selected_structure is not None and self.selected_structure not in self.buildings:
            self.selected_structure = None

        if self.buildmode and self.placeable_object is not None:
            world_mouse_pos = self.camera.screen_to_world(pygame.mouse.get_pos())
            self.placeable_object.pos = pygame.Vector2(world_mouse_pos.x, world_mouse_pos.y)
            self.placeable_object.rect.center = self.placeable_object.pos
            in_range = self.player.pos.distance_to(world_mouse_pos) < self.buildrange
            can_afford = self.can_afford_building_class(self.selected_building["class"])
            can_build_here = self.can_place_building_rect(self.placeable_object.rect)
            self.can_place = in_range and can_build_here and can_afford

            if not in_range:
                self.placement_error = "Out of range"
            elif not can_afford:
                self.placement_error = "Missing resources"
            elif not can_build_here:
                self.placement_error = "Blocked"
            else:
                self.placement_error = None
        else:
            self.can_place = False
            self.placement_error = None

    def draw(self, surface):
        self.world.draw_ground(surface, self.camera)

        for building in sorted(self.buildings, key=lambda structure: structure.rect.bottom):
            building.draw(surface, self.camera.offset)

        if self.selected_structure is not None and self.selected_structure in self.buildings:
            selection_rect = self.camera.apply_rect(self.selected_structure.rect.inflate(8, 8))
            pygame.draw.rect(surface, YELLOW, selection_rect, 2, border_radius=6)

        placement_hint = None
        if self.buildmode:
            self.draw_build_range(surface)
            if self.placeable_object is not None:
                preview = self.placeable_object.image.copy()
                preview.set_alpha(170 if self.can_place else 90)
                preview_rect = self.camera.apply_rect(self.placeable_object.rect)
                surface.blit(preview, preview_rect)
                pygame.draw.rect(surface, GREEN if self.can_place else RED, preview_rect, 2)

                name = self.selected_building["name"] if self.selected_building else "Building"
                reason_text = f"  |  {self.placement_error}" if self.placement_error else ""
                placement_hint = self.small_font.render(
                    f"Placing: {name}  |  Left click to place  |  Right click or ESC to cancel{reason_text}",
                    True,
                    WHITE,
                )

        self.player.draw(surface, self.camera.offset)
        self.world.draw_rocks(surface, self.camera)
        self.world.draw_trees(surface, self.camera)

        if placement_hint is not None:
            surface.blit(placement_hint, (20, 20))

        self.draw_inventory_panel(surface)
        self.draw_coordinates_panel(surface)
        self.draw_selected_structure_panel(surface)

        if self.build_menu_open:
            self.draw_build_menu(surface)

        for building in self.buildings:
            building.draw_overlay(surface, self.camera.offset)

        self.draw_player_harvest_overlay(surface)

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
            label_rect = label.get_rect(center=(rect.centerx, rect.bottom - 36))
            surface.blit(label, label_rect)

            cost_label = self.small_font.render(option["class"].format_cost(option["cost"]), True, WHITE)
            cost_rect = cost_label.get_rect(center=(rect.centerx, rect.bottom - 21))
            surface.blit(cost_label, cost_rect)

            time_label = self.small_font.render(f"{option['build_time']:.1f}s", True, LIGHT_GRAY)
            time_rect = time_label.get_rect(center=(rect.centerx, rect.bottom - 8))
            surface.blit(time_label, time_rect)

        footer = self.small_font.render("Press 1-4 or click an option", True, WHITE)
        surface.blit(footer, (menu_rect.x + 15, menu_rect.bottom - 20))

    def draw_coordinates_panel(self, surface):
        chunk_x, chunk_y = self.world.get_chunk_key_for_position(self.player.pos)
        lines = [
            f"X: {int(self.player.pos.x)}",
            f"Y: {int(self.player.pos.y)}",
            f"Chunk: {chunk_x}, {chunk_y}",
        ]

        padding = 10
        line_height = self.small_font.get_height()
        panel_width = max(self.small_font.size(line)[0] for line in lines) + (padding * 2)
        panel_height = (line_height * len(lines)) + (padding * 2)
        panel_rect = pygame.Rect(SCREEN_WIDTH - panel_width - 20, 20, panel_width, panel_height)

        panel = pygame.Surface(panel_rect.size, pygame.SRCALPHA)
        panel.fill((20, 20, 20, 185))
        surface.blit(panel, panel_rect.topleft)
        pygame.draw.rect(surface, LIGHT_GRAY, panel_rect, 1, border_radius=8)

        for index, line in enumerate(lines):
            label = self.small_font.render(line, True, WHITE)
            label_y = panel_rect.y + padding + (index * line_height)
            surface.blit(label, (panel_rect.x + padding, label_y))

    def draw_inventory_panel(self, surface):
        lines = [
            f"Wood: {self.player.get_resource_amount('wood')}",
            f"Stone: {self.player.get_resource_amount('stone')}",
            "Hold Right Mouse: harvest  |  X/Delete: demolish",
        ]

        padding = 10
        line_height = self.small_font.get_height()
        panel_width = max(self.small_font.size(line)[0] for line in lines) + (padding * 2)
        panel_height = (line_height * len(lines)) + (padding * 2)

        panel_y = 56 if self.buildmode else 20
        panel_rect = pygame.Rect(20, panel_y, panel_width, panel_height)
        panel = pygame.Surface(panel_rect.size, pygame.SRCALPHA)
        panel.fill((20, 20, 20, 185))
        surface.blit(panel, panel_rect.topleft)
        pygame.draw.rect(surface, LIGHT_GRAY, panel_rect, 1, border_radius=8)

        for index, line in enumerate(lines):
            label = self.small_font.render(line, True, WHITE)
            surface.blit(label, (panel_rect.x + padding, panel_rect.y + padding + (index * line_height)))

    def draw_player_harvest_overlay(self, surface):
        action = self.player.harvest_action
        if action is None:
            return

        progress = max(0.0, min(1.0, action["progress"] / action["duration"]))
        player_screen_x = int(self.player.pos.x - self.camera.offset.x)
        player_screen_y = int(self.player.pos.y - self.camera.offset.y)

        label = self.small_font.render(action["label"], True, WHITE)
        bar_width = 86
        bar_height = 9
        padding = 6
        panel_width = max(label.get_width(), bar_width) + (padding * 2)
        panel_height = label.get_height() + bar_height + (padding * 3)
        panel_rect = pygame.Rect(0, 0, panel_width, panel_height)
        panel_rect.midbottom = (player_screen_x, player_screen_y - 28)

        panel = pygame.Surface(panel_rect.size, pygame.SRCALPHA)
        panel.fill((20, 20, 20, 210))
        surface.blit(panel, panel_rect.topleft)
        pygame.draw.rect(surface, WHITE, panel_rect, 1, border_radius=8)

        label_x = panel_rect.x + (panel_rect.width - label.get_width()) // 2
        label_y = panel_rect.y + padding
        surface.blit(label, (label_x, label_y))

        bar_rect = pygame.Rect(0, 0, bar_width, bar_height)
        bar_rect.midtop = (panel_rect.centerx, label_y + label.get_height() + padding)
        pygame.draw.rect(surface, (40, 40, 40), bar_rect)
        pygame.draw.rect(surface, GREEN, (bar_rect.x, bar_rect.y, int(bar_rect.width * progress), bar_rect.height))
        pygame.draw.rect(surface, WHITE, bar_rect, 1)

    def draw_selected_structure_panel(self, surface):
        if self.selected_structure is None or self.selected_structure not in self.buildings:
            return

        lines = self.selected_structure.get_selection_lines() + ["Press X/Delete to demolish"]
        padding = 10
        line_height = self.small_font.get_height()
        panel_width = max(self.small_font.size(line)[0] for line in lines) + (padding * 2)
        panel_height = (line_height * len(lines)) + (padding * 2)
        panel_rect = pygame.Rect(SCREEN_WIDTH - panel_width - 20, 110, panel_width, panel_height)

        panel = pygame.Surface(panel_rect.size, pygame.SRCALPHA)
        panel.fill((20, 20, 20, 185))
        surface.blit(panel, panel_rect.topleft)
        pygame.draw.rect(surface, LIGHT_GRAY, panel_rect, 1, border_radius=8)

        for index, line in enumerate(lines):
            label = self.small_font.render(line, True, WHITE)
            surface.blit(label, (panel_rect.x + padding, panel_rect.y + padding + (index * line_height)))

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
        screen_center = (
            int(self.player.pos.x - self.camera.offset.x),
            int(self.player.pos.y - self.camera.offset.y),
        )
        surface.blit(range_image, range_image.get_rect(center=screen_center))

    def shutdown(self):
        self.world.shutdown()