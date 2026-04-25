import os
import pygame


class ParticleAnimation(pygame.sprite.Sprite):
    def __init__(
        self,
        x,
        y,
        frame_width=None,
        frame_height=None,
        sheet_path=None,
        folder_path=None,
        frame_count=None,
        row=0,
        fps=12,
        loop=False,
        kill_on_finish=True,
        center=True,
        scale=None,
        sound=None
    ):
        super().__init__()

        self.frames = []
        self.sound = sound

        # Load from sprite sheet
        if sheet_path:
            self.frames = self.load_from_spritesheet(
                sheet_path,
                frame_width,
                frame_height,
                frame_count,
                row=row,
                scale=scale
            )

        # Load from folder of images
        elif folder_path:
            self.frames = self.load_from_folder(folder_path, scale=scale)

        else:
            raise ValueError("You must provide either sheet_path or folder_path")

        if not self.frames:
            raise ValueError("No frames were loaded for ParticleAnimation")

        self.frame_index = 0
        self.image = self.frames[self.frame_index]
        self.rect = self.image.get_rect()

        if center:
            self.rect.center = (x, y)
        else:
            self.rect.topleft = (x, y)

        self.pos = pygame.Vector2(self.rect.topleft)

        self.fps = fps
        self.frame_duration = 1.0 / fps
        self.timer = 0

        self.loop = loop
        self.kill_on_finish = kill_on_finish
        self.finished = False

    def load_from_spritesheet(self, sheet_path, frame_width, frame_height, frame_count, row=0, scale=None):
        if frame_width is None or frame_height is None or frame_count is None:
            raise ValueError("frame_width, frame_height, and frame_count are required for sprite sheets")

        sheet = pygame.image.load(sheet_path).convert_alpha()
        frames = []

        for i in range(frame_count):
            frame = pygame.Surface((frame_width, frame_height), pygame.SRCALPHA)
            frame.blit(
                sheet,
                (0, 0),
                (i * frame_width, row * frame_height, frame_width, frame_height)
            )

            if scale is not None:
                frame = pygame.transform.scale(frame, scale)

            frames.append(frame)

        return frames

    def load_from_folder(self, folder_path, scale=None):
        valid_extensions = (".png", ".jpg", ".jpeg", ".webp")
        files = sorted(
            f for f in os.listdir(folder_path)
            if f.lower().endswith(valid_extensions)
        )

        frames = []
        for file_name in files:
            full_path = os.path.join(folder_path, file_name)
            image = pygame.image.load(full_path).convert_alpha()

            if scale is not None:
                image = pygame.transform.scale(image, scale)

            frames.append(image)

        return frames

    def update(self, dt):
        if self.finished:
            return

        self.timer += dt

        while self.timer >= self.frame_duration:
            self.timer -= self.frame_duration
            self.frame_index += 1

            if self.frame_index >= len(self.frames):
                if self.loop:
                    self.frame_index = 0
                else:
                    self.frame_index = len(self.frames) - 1
                    self.finished = True

                    if self.kill_on_finish:
                        self.kill()
                        return

            self.image = self.frames[self.frame_index]

    def draw(self, surface):
        if self.image is not None:
            img = self.image
            surface.blit(img, self.rect)
