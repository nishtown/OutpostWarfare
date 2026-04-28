from __future__ import annotations

import os
import random

import pygame

from settings import asset_path


class AudioManager:
    """Load and play grouped sound effects while exposing a master volume."""

    _GROUP_GAINS = {
        "arrow_fire": 0.45,
        "bomb_impact": 0.72,
        "building_destroyed": 0.78,
        "tree_chop": 0.55,
        "pickaxe_mining": 0.58,
        "goblin_walk": 0.22,
    }

    def __init__(self, master_volume: float = 0.6) -> None:
        self.enabled = pygame.mixer.get_init() is not None
        self.master_volume = max(0.0, min(1.0, float(master_volume)))
        self._rng = random.Random()
        self._sound_groups: dict[str, list[pygame.mixer.Sound]] = {}
        self._prepared_music: dict[str, str] = {}
        self._enemy_walk_active = False
        self._enemy_walk_channel: pygame.mixer.Channel | None = None

        if not self.enabled:
            return

        pygame.mixer.set_reserved(1)
        self._enemy_walk_channel = pygame.mixer.Channel(0)

        self._load_default_sounds()
        self._apply_master_volume()

    def _load_default_sounds(self) -> None:
        self._sound_groups["arrow_fire"] = self._load_group("arrow_firing_1.mp3")
        self._sound_groups["bomb_impact"] = self._load_group(
            "canon_ball_smashing_1.mp3",
            "canon_ball_smashing_2.mp3",
            "canon_ball_smashing_3.mp3",
        )
        self._sound_groups["building_destroyed"] = self._load_group(
            "building_getting_destroyed_1.mp3",
            "building_getting_destroyed_2.mp3",
        )
        self._sound_groups["tree_chop"] = self._load_group(
            "tree_chopping_1.mp3",
            "tree_chopping_2.mp3",
        )
        self._sound_groups["pickaxe_mining"] = self._load_group("pickaxe_mining_stone_1.mp3")
        self._sound_groups["goblin_walk"] = self._load_group("goblin_walking.mp3")

    def _load_group(self, *filenames: str) -> list[pygame.mixer.Sound]:
        sounds: list[pygame.mixer.Sound] = []
        for filename in filenames:
            path = asset_path("assets", "sounds", filename)
            if not os.path.exists(path):
                continue

            try:
                sounds.append(pygame.mixer.Sound(path))
            except pygame.error:
                continue

        return sounds

    def _apply_master_volume(self) -> None:
        if not self.enabled:
            return

        for group_name, sounds in self._sound_groups.items():
            gain = self._GROUP_GAINS.get(group_name, 1.0) * self.master_volume
            for sound in sounds:
                sound.set_volume(gain)

        if self._enemy_walk_channel is not None:
            self._enemy_walk_channel.set_volume(self._GROUP_GAINS.get("goblin_walk", 1.0) * self.master_volume)

        pygame.mixer.music.set_volume(self.master_volume)

    def get_master_volume(self) -> float:
        return self.master_volume

    def set_master_volume(self, value: float) -> float:
        self.master_volume = max(0.0, min(1.0, float(value)))
        self._apply_master_volume()
        return self.master_volume

    def play(self, group_name: str) -> bool:
        if not self.enabled:
            return False

        sounds = self._sound_groups.get(group_name, [])
        if not sounds:
            return False

        channel = pygame.mixer.find_channel()
        if channel is None:
            return False

        channel.play(self._rng.choice(sounds))
        return True

    def set_enemy_walking_active(self, active: bool) -> None:
        if not self.enabled or self._enemy_walk_channel is None:
            return

        active = bool(active)
        if active == self._enemy_walk_active:
            return

        self._enemy_walk_active = active
        walk_sounds = self._sound_groups.get("goblin_walk", [])
        if not walk_sounds:
            return

        if active:
            self._enemy_walk_channel.play(walk_sounds[0], loops=-1, fade_ms=140)
        else:
            self._enemy_walk_channel.fadeout(180)

    def prepare_music_track(self, track_name: str, track_path: str) -> bool:
        if not os.path.exists(track_path):
            return False

        self._prepared_music[str(track_name)] = track_path
        return True

    def play_music(self, track_name: str, loops: int = -1) -> bool:
        if not self.enabled:
            return False

        track_path = self._prepared_music.get(track_name)
        if not track_path:
            return False

        try:
            pygame.mixer.music.load(track_path)
            pygame.mixer.music.play(loops=loops)
            pygame.mixer.music.set_volume(self.master_volume)
        except pygame.error:
            return False

        return True

    def stop_music(self) -> None:
        if self.enabled:
            pygame.mixer.music.stop()