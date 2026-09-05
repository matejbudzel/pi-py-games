"""Preloaded fonts and sprites shared by all game views."""

from __future__ import annotations

import pygame

from .config import BACKGROUND, FONT_PATH, FOREGROUND, TITLE
from .gameplay import Judgement
from .songs import Song


class Assets:
    def __init__(self, songs: list[Song], canvas: pygame.Surface) -> None:
        self.title_font = pygame.font.Font(FONT_PATH, 38)
        self.title_font.set_bold(True)
        self.list_font = pygame.font.Font(FONT_PATH, 28)
        self.question_font = pygame.font.Font(FONT_PATH, 28)
        self.question_font.set_bold(True)
        self.shrug_font = pygame.font.Font(FONT_PATH, 24)
        self.performance_font = pygame.font.Font(FONT_PATH, 16)
        self.rainbow_title = self._make_rainbow_title()
        self.receptors = self._load_rotated("arrow.png")
        self.flow_arrows = self._load_rotated("arrow-flow.png")
        self.receptor_glows = {direction: pygame.transform.scale(arrow, (42, 42)) for direction, arrow in self.flow_arrows.items()}
        self.feedback_icons = self._load_feedback_icons()
        self.feedback_patches = self._make_feedback_patches(canvas)
        self.draft_star, self.earned_star = self._load_result_stars()
        self.reload_covers(songs, canvas)

    def reload_covers(self, songs: list[Song], canvas: pygame.Surface) -> None:
        self.covers = {
            song.path: pygame.transform.scale(pygame.image.load(song.cover_path).convert(canvas), (256, 256))
            for song in songs
        }

    def cover_for(self, song: Song) -> pygame.Surface:
        return self.covers[song.path]

    def _load_rotated(self, filename: str) -> dict[str, pygame.Surface]:
        arrow = pygame.image.load(FONT_PATH.parent.parent / "gameplay" / filename).convert_alpha()
        return {
            "up": arrow,
            "down": pygame.transform.rotate(arrow, 180),
            "left": pygame.transform.rotate(arrow, 90),
            "right": pygame.transform.rotate(arrow, -90),
        }

    def _load_feedback_icons(self) -> dict[Judgement, pygame.Surface]:
        asset_directory = FONT_PATH.parent.parent / "gameplay"
        return {
            Judgement.GREAT: pygame.image.load(asset_directory / "heart.png").convert_alpha(),
            Judgement.OK: pygame.image.load(asset_directory / "thumb.png").convert_alpha(),
            Judgement.MISS: pygame.image.load(asset_directory / "shrug.png").convert_alpha(),
        }

    def _load_result_stars(self) -> tuple[pygame.Surface, pygame.Surface]:
        star = pygame.image.load(FONT_PATH.parent.parent / "gameplay" / "star.png").convert_alpha()
        draft = star.copy()
        draft.fill((110, 110, 110), special_flags=pygame.BLEND_RGBA_MULT)
        earned = star.copy()
        earned.fill((255, 220, 45), special_flags=pygame.BLEND_RGBA_MULT)
        return draft, earned

    def _make_feedback_patches(self, canvas: pygame.Surface) -> dict[Judgement, pygame.Surface]:
        """Pre-compose large transparent feedback art for the RGB565 game canvas."""
        patches: dict[Judgement, pygame.Surface] = {}
        for judgement, icon in self.feedback_icons.items():
            patch = pygame.Surface((170, 145), depth=canvas.get_bitsize(), masks=canvas.get_masks())
            patch.fill(BACKGROUND)
            patch.blit(icon, icon.get_rect(midtop=(75, 4)))
            patches[judgement] = patch
        return patches

    def _make_rainbow_title(self) -> pygame.Surface:
        colors = ((75, 255, 105), (255, 235, 60), (60, 230, 255), (85, 125, 255), (235, 85, 255), (255, 85, 125))
        glyphs = [self.title_font.render(letter, False, colors[index % len(colors)]) for index, letter in enumerate(TITLE)]
        width = sum(glyph.get_width() for glyph in glyphs)
        rainbow = pygame.Surface((width, self.title_font.get_height()), pygame.SRCALPHA)
        x = 0
        for glyph in glyphs:
            rainbow.blit(glyph, (x, 0))
            x += glyph.get_width()
        return rainbow
