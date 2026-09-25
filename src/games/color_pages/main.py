"""A compact, controller-first pixel coloring game."""
from __future__ import annotations

import time
from pathlib import Path
import pygame

from common.assets import SWEET16_FONT_PATH
from common.console_input import ConsoleInput
from common.display import GameDisplay, display_settings, initialize_pygame
from common.error_logging import configure_logging
from common.input import Action, actions_from_event
from common.joystick_input import JoystickInput
from .config import Settings, load_settings
from .art import Page, load_pages
from .progress import ProgressStore

# The art and UI live on the deliberately chunky logical canvas.  GameDisplay
# presents this exact surface at 854x480 using a 2x nearest-neighbour scale.
WIDTH, HEIGHT, FPS = 427, 240, 30
OUTPUT_SIZE = (854, 480)
BG, INK, WHITE, GREY = (31, 35, 55), (12, 15, 25), (247, 245, 235), (126, 132, 146)
# 16 cells at this pitch occupy 352 of the 363px drawing viewport.  The
# remaining space avoids clipping while each logical image pixel stays large.
CELL, HUD_W = 22, 64
GRID_COLUMNS = 3
RAINBOW = ((255, 105, 112), (255, 181, 72), (255, 232, 92), (104, 221, 133), (94, 184, 255), (183, 126, 255))


class App:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or load_settings()
        self.screen_name, self.selected, self.modal = "splash", 0, None
        self.modal_kind: str | None = None
        self.pages: tuple[Page, ...] = ()
        self.selection_scroll = 0
        self.cursor = [0, 0]
        self.colored: set[tuple[int, int]] = set()
        self.current_color, self.steps, self.started = 0, 0, 0.0
        self.finished_at: float | None = None
        self.completed = False
        self.camera = [0, 0]
        self.running = True

    @property
    def page(self) -> Page: return self.pages[self.selected]

    def begin(self) -> None:
        saved = self.progress.get(self.page.source, self.page.signature)
        resetting_completed = bool(saved and saved.get("completed"))
        if resetting_completed:
            saved = None
        self.screen_name = "drawing"
        self.cursor = self._saved_cursor(saved)
        self.colored = self._saved_colored(saved)
        saved_steps = saved.get("steps", 0) if saved and isinstance(saved.get("steps", 0), int) else 0
        saved_seconds = saved.get("seconds", 0) if saved and isinstance(saved.get("seconds", 0), int) else 0
        self.current_color, self.steps = 0, saved_steps
        self.started, self.camera = time.monotonic() - saved_seconds, [0, 0]
        self.finished_at = None
        self.completed = False
        self._advance_color()
        self._follow()
        if resetting_completed:
            self._save_progress()

    def _saved_colored(self, saved: dict | None) -> set[tuple[int, int]]:
        if not saved:
            return set()
        valid = {(x, y) for y, row in enumerate(self.page.pixels) for x, value in enumerate(row) if value >= 0}
        return {(item[0], item[1]) for item in saved.get("colored", []) if isinstance(item, list) and len(item) == 2 and all(isinstance(value, int) for value in item) and (item[0], item[1]) in valid}

    def _saved_cursor(self, saved: dict | None) -> list[int]:
        cursor = saved.get("cursor", [0, 0]) if saved else [0, 0]
        if not isinstance(cursor, list) or len(cursor) != 2:
            return [0, 0]
        if not all(isinstance(value, int) for value in cursor):
            return [0, 0]
        return [max(0, min(self.page.size - 1, cursor[0])), max(0, min(self.page.size - 1, cursor[1]))]

    def _elapsed_seconds(self) -> int:
        return int((self.finished_at if self.finished_at is not None else time.monotonic()) - self.started)

    def _save_progress(self) -> None:
        self.progress.save(self.page.source, self.page.signature, self.colored, self.cursor, self._elapsed_seconds(), self.steps, self.completed)

    def clear_image(self) -> None:
        self.cursor, self.colored, self.current_color, self.steps = [0, 0], set(), 0, 0
        self.started, self.finished_at, self.completed, self.camera = time.monotonic(), None, False, [0, 0]
        self._save_progress()

    def reload_pages(self) -> None:
        """Refresh external art while retaining the same file focus when possible."""
        focused = self.page.source if self.pages else None
        self.pages = load_pages(self.settings.art_directory)
        self.selected = next((index for index, page in enumerate(self.pages) if page.source == focused), min(self.selected, max(0, len(self.pages) - 1)))
        self.selection_scroll = max(0, min(self.selected // GRID_COLUMNS - 1, max(0, (len(self.pages) - 1) // GRID_COLUMNS - 1))) if self.pages else 0
        self.page_surfaces = {page: self._page_surface(page) for page in self.pages}
        self.preview_surfaces = {page: self._page_surface(page, self._saved_colored(self.progress.get(page.source, page.signature))) for page in self.pages}
        self.scaled_pages = {}

    def return_to_selection(self) -> None:
        if self.screen_name in ("drawing", "result") and self.pages:
            self._save_progress()
        self.reload_pages()
        self.screen_name = "selection"

    def _advance_color(self) -> None:
        while self.current_color < self.page.color_count and not any(
            value == self.current_color and (x, y) not in self.colored
            for y, row in enumerate(self.page.pixels) for x, value in enumerate(row)
        ):
            self.current_color += 1
        if self.current_color == self.page.color_count:
            self.finished_at = time.monotonic()
            self.completed = True
            self._save_progress()
            self.screen_name = "result"

    def move(self, action: Action) -> None:
        dx, dy = {Action.LEFT: (-1, 0), Action.RIGHT: (1, 0), Action.UP: (0, -1), Action.DOWN: (0, 1)}[action]
        size = self.page.size
        self.cursor[0] = max(0, min(size - 1, self.cursor[0] + dx))
        self.cursor[1] = max(0, min(size - 1, self.cursor[1] + dy))
        self.steps += 1
        x, y = self.cursor
        if self.page.pixels[y][x] == self.current_color:
            self.colored.add((x, y)); self._advance_color()
        self._follow()

    def _follow(self) -> None:
        visible_x, visible_y = (WIDTH - HUD_W) // CELL, HEIGHT // CELL
        for axis, visible in enumerate((visible_x, visible_y)):
            pos = self.cursor[axis]
            low, high = self.camera[axis] + 4, self.camera[axis] + visible - 5
            if pos < low: self.camera[axis] = max(0, pos - 4)
            if pos > high: self.camera[axis] = min(max(0, self.page.size - visible), pos - visible + 5)

    def handle(self, action: Action) -> None:
        if self.modal:
            if action in (Action.LEFT, Action.RIGHT, Action.UP, Action.DOWN): self.modal = "yes" if self.modal == "no" else "no"
            elif action is Action.SELECT:
                self.modal = None; self.modal_kind = None
            elif action is Action.START:
                if self.modal == "yes":
                    if self.modal_kind == "exit_game": self.running = False
                    elif self.modal_kind == "exit_drawing": self.return_to_selection()
                    elif self.modal_kind == "clear": self.clear_image()
                self.modal = None; self.modal_kind = None
            return
        if self.screen_name == "splash":
            if action is Action.START: self.screen_name = "selection"
            elif action is Action.SELECT: self.running = False
        elif self.screen_name == "selection":
            if action is Action.SELECT: self.modal, self.modal_kind = "no", "exit_game"
            elif action is Action.START and self.pages: self.begin()
            elif action in (Action.LEFT, Action.RIGHT, Action.UP, Action.DOWN):
                dx, dy = {Action.LEFT:(-1,0), Action.RIGHT:(1,0), Action.UP:(0,-1), Action.DOWN:(0,1)}[action]
                col, row = self.selected % GRID_COLUMNS, self.selected // GRID_COLUMNS
                proposed = (row + dy) * GRID_COLUMNS + col + dx
                # A partial last row still accepts Down from a missing column:
                # land on its final available item.  Up stays a plain column move.
                if action is Action.DOWN and proposed >= len(self.pages) and (row + 1) * GRID_COLUMNS < len(self.pages):
                    proposed = len(self.pages) - 1
                if 0 <= col + dx < GRID_COLUMNS and 0 <= proposed < len(self.pages):
                    self.selected = proposed
                    self.selection_scroll = max(0, min(self.selected // GRID_COLUMNS - 1, max(0, (len(self.pages) - 1) // GRID_COLUMNS - 1)))
        elif self.screen_name == "drawing":
            if action is Action.SELECT: self.modal, self.modal_kind = "no", "exit_drawing"
            elif action is Action.START: self.modal, self.modal_kind = "no", "clear"
            elif action is Action.DEBUG_JUMP_END:
                self.finished_at = time.monotonic()
                self.screen_name = "result"
            elif action in (Action.LEFT, Action.RIGHT, Action.UP, Action.DOWN): self.move(action)
        elif self.screen_name == "result" and action in (Action.START, Action.SELECT): self.return_to_selection()

    def draw(self, font: pygame.font.Font, small: pygame.font.Font) -> None:
        background = {"splash": "intro", "selection": "selection", "drawing": "drawing", "result": "result"}[self.screen_name]
        self.screen.blit(self.backgrounds[background], (0, 0))
        if self.screen_name == "splash": self._rainbow_title((WIDTH//2, HEIGHT//2), center=True)
        elif self.screen_name == "selection": self._selection(font, small)
        elif self.screen_name == "drawing": self._drawing(small)
        else: self._result(font, small)
        if self.modal: self._modal(font, small)

    def _text(self, font, text, pos, color=WHITE, center=False):
        image = font.render(text, False, color); self.screen.blit(image, image.get_rect(center=pos) if center else pos)

    def _rainbow_title(self, pos, center=False):
        self.screen.blit(self.rainbow_title, self.rainbow_title.get_rect(center=pos) if center else pos)

    def _thumbnail(self, page, rect):
        key = (page, rect.size)
        image = self.scaled_pages.get(key)
        if image is None:
            image = pygame.transform.scale(self.preview_surfaces[page], rect.size)
            self.scaled_pages[key] = image
        self.screen.blit(image, rect)

    def _page_surface(self, page: Page, colored: set[tuple[int, int]] | None = None) -> pygame.Surface:
        """Build one native-resolution page; scaling the whole image avoids seams."""
        surface = pygame.Surface((page.size, page.size))
        surface.fill(INK)
        for y, row in enumerate(page.pixels):
            for x, value in enumerate(row):
                if value >= 0:
                    surface.set_at((x, y), page.palette[value] if colored is None or (x, y) in colored else GREY)
        return surface

    def _selection(self, font, small):
        self._rainbow_title((8, 8))
        if not self.pages:
            self._text(font, self.settings.no_images_text, (WIDTH // 2, HEIGHT // 2), center=True)
            return
        for index, page in enumerate(self.pages):
            row = index // GRID_COLUMNS
            if not self.selection_scroll <= row < self.selection_scroll + 2: continue
            x, y = 8 + (index % GRID_COLUMNS)*74, 42 + (row-self.selection_scroll)*88
            rect = pygame.Rect(x, y, 64, 64); self._thumbnail(page, rect)
            if index == self.selected: pygame.draw.rect(self.screen, (255, 219, 84), rect.inflate(4, 4), 2)
        page = self.page
        content_x = 257
        self._thumbnail(page, pygame.Rect(content_x, 10, 144, 144))
        self._text(self.bold_font, page.title, (content_x, 166))
        self._text(font, f"{page.size}x{page.size}  {page.color_count} colors", (content_x, 186))
        # Reserve a stable 8x2 palette block.  Empty slots remain transparent,
        # so pages with fewer colours keep the same centered composition.
        for index in range(16):
            if index < page.color_count:
                pygame.draw.circle(self.screen, page.palette[index], (content_x + 7 + (index % 8)*15, 214 + (index // 8)*18), 7)

    def _drawing(self, font):
        page = self.page; max_x, max_y = (WIDTH-HUD_W)//CELL, HEIGHT//CELL
        canvas_x = ((WIDTH - HUD_W) - max_x * CELL) // 2
        canvas_y = (HEIGHT - max_y * CELL) // 2
        for sy in range(min(max_y, page.size-self.camera[1])):
            for sx in range(min(max_x, page.size-self.camera[0])):
                x, y = sx+self.camera[0], sy+self.camera[1]; value = page.pixels[y][x]
                color = INK if value < 0 else (page.palette[value] if (x,y) in self.colored else GREY)
                rect = pygame.Rect(canvas_x + sx*CELL, canvas_y + sy*CELL, CELL, CELL)
                pygame.draw.rect(self.screen, INK, rect)
                if value >= 0:
                    pygame.draw.rect(self.screen, color, rect.inflate(-2, -2))
                if value == self.current_color and (x,y) not in self.colored: pygame.draw.circle(self.screen, WHITE, rect.center, 3)
        sx = canvas_x + (self.cursor[0]-self.camera[0])*CELL
        sy = canvas_y + (self.cursor[1]-self.camera[1])*CELL
        pygame.draw.rect(self.screen, WHITE, (sx, sy, CELL, CELL), 1)
        hud_x = WIDTH-HUD_W
        total = sum(value >= 0 for row in page.pixels for value in row); pct = round(100*len(self.colored)/total) if total else 100
        percent = self.hud_percent_font.render(f"{pct}%", False, WHITE)
        self.screen.blit(percent, percent.get_rect(center=(hud_x + HUD_W // 2, 20)))
        elapsed = self._elapsed_seconds()
        self.screen.blit(self.hud_icons["time"], (hud_x + 2, 44)); self._text(font, f"{elapsed}s", (hud_x + 30, 48))
        self.screen.blit(self.hud_icons["feet"], (hud_x + 2, 72)); self._text(font, str(self.steps), (hud_x + 30, 76))
        upcoming = page.palette[self.current_color + 1:]
        # Keep the palette immediately after the step counter, independent of
        # the number of remaining colours.  Empty lower slots simply stay open.
        label_y, active_y, palette_y = 104, 138, 161
        used_colors = len({page.pixels[y][x] for x, y in self.colored})
        self.screen.blit(self.hud_icons["palette"], (hud_x + 2, label_y - 4))
        self._text(font, f"{used_colors}/{page.color_count}", (hud_x + 30, label_y))
        palette_backdrop = pygame.Surface((HUD_W - 8, 116), pygame.SRCALPHA)
        palette_backdrop.fill((8, 12, 30, 185))
        self.screen.blit(palette_backdrop, (hud_x + 4, 124))
        if self.current_color < page.color_count:
            pygame.draw.circle(self.screen, page.palette[self.current_color], (hud_x + HUD_W // 2, active_y), 10)
        for index, color in enumerate(upcoming):
            pygame.draw.circle(self.screen, color, (hud_x + 23 + (index % 2)*18, palette_y + (index // 2)*10), 5)

    def _result(self, font, small):
        page = self.page
        values = (("time", f"{self._elapsed_seconds()}s"), ("feet", str(self.steps)), ("palette", f"{page.color_count}/{page.color_count}"))
        value_images = [(self.icons[name], font.render(text, False, WHITE)) for name, text in values]
        values_width = max(icon.get_width() + 8 + text.get_width() for icon, text in value_images)
        image_size, gap = 160, 24
        block_width = image_size + gap + values_width
        left = (WIDTH - block_width) // 2
        result_shade = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        result_shade.fill((8, 12, 30, 185))
        self.screen.blit(result_shade, (0, 0))
        image_key = (page, (image_size, image_size))
        image = self.scaled_pages.get(image_key)
        if image is None:
            image = pygame.transform.scale(self.page_surfaces[page], image_key[1])
            self.scaled_pages[image_key] = image
        image_position = (left, (HEIGHT - image_size) // 2)
        self.screen.blit(image, image_position)
        values_y = (HEIGHT - len(value_images) * 48) // 2
        values_x = left + image_size + gap
        for index, (icon, text) in enumerate(value_images):
            y = values_y + index * 48
            self.screen.blit(icon, (values_x, y))
            self.screen.blit(text, (values_x + icon.get_width() + 8, y + (icon.get_height() - text.get_height()) // 2))

    def _modal(self, font, small):
        overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA); overlay.fill((0,0,0,175)); self.screen.blit(overlay,(0,0))
        rect=pygame.Rect(125,85,177,70); pygame.draw.rect(self.screen,(57,64,91),rect); pygame.draw.rect(self.screen,WHITE,rect,1)
        question_text = self.settings.clear_confirmation_text if self.modal_kind == "clear" else self.settings.exit_confirmation_text
        question = self.bold_font.render(question_text, False, WHITE)
        yes = small.render(self.settings.exit_confirm_button, False, (255,219,84) if self.modal=="yes" else WHITE)
        no = small.render(self.settings.exit_cancel_button, False, (255,219,84) if self.modal=="no" else WHITE)
        gap = 16
        block_height = question.get_height() + 6 + max(yes.get_height(), no.get_height())
        top = rect.centery - block_height // 2
        self.screen.blit(question, question.get_rect(center=(rect.centerx, top + question.get_height() // 2)))
        buttons_width = yes.get_width() + gap + no.get_width()
        buttons_x = rect.centerx - buttons_width // 2
        buttons_y = top + question.get_height() + 6
        self.screen.blit(yes, (buttons_x, buttons_y))
        self.screen.blit(no, (buttons_x + yes.get_width() + gap, buttons_y))

    def run(self) -> None:
        settings=display_settings(); initialize_pygame(settings)
        if settings.backend == "pygame": pygame.display.set_caption(self.settings.title)
        display=GameDisplay(settings, OUTPUT_SIZE, logical_size=(WIDTH, HEIGHT)); self.screen=display.canvas
        # All layout dimensions, including the 16px Sweet16 type, are defined
        # on the 427x240 logical canvas.  Presentation scaling is separate.
        font=pygame.font.Font(SWEET16_FONT_PATH, 16); small=pygame.font.Font(SWEET16_FONT_PATH, 16)
        self.bold_font=pygame.font.Font(SWEET16_FONT_PATH, 16); self.bold_font.set_bold(True)
        glyphs = [self.bold_font.render(letter, False, RAINBOW[index % len(RAINBOW)]) for index, letter in enumerate(self.settings.title)]
        self.rainbow_title = pygame.Surface((sum(glyph.get_width() for glyph in glyphs), self.bold_font.get_height()), pygame.SRCALPHA)
        x = 0
        for glyph in glyphs:
            self.rainbow_title.blit(glyph, (x, 0)); x += glyph.get_width()
        asset_directory = Path(__file__).with_name("assets")
        # fbdev intentionally has no SDL display surface, so neither convert()
        # nor convert_alpha() is available here.  Keep the loaded PNG surfaces
        # in their native format; Pygame can still blit their alpha correctly.
        self.icons = {name: pygame.image.load(asset_directory / f"{name}.png") for name in ("feet", "palette", "time")}
        self.backgrounds = {name: pygame.image.load(asset_directory / "backgrounds" / f"{name}.png") for name in ("intro", "selection", "drawing", "result")}
        self.hud_icons = {name: pygame.transform.scale(image, (24, 24)) for name, image in self.icons.items()}
        self.hud_percent_font = pygame.font.Font(SWEET16_FONT_PATH, 24)
        self.progress = ProgressStore(Path(__file__).resolve().parents[3] / ".pixel-colors-progress.json")
        self.scaled_pages: dict[tuple[Page, tuple[int, int]], pygame.Surface] = {}
        self.reload_pages()
        joystick=JoystickInput() if settings.backend=="pygame" else None; console=ConsoleInput() if settings.backend=="fbdev" else None; clock=pygame.time.Clock()
        try:
            with console or _NullContext():
                while self.running:
                    actions=[]
                    if console: actions.extend(a for a in console.poll_actions() if isinstance(a,Action))
                    else:
                        for event in pygame.event.get():
                            if event.type==pygame.QUIT: self.running=False
                            if joystick: joystick.handle_event(event)
                            actions.extend(actions_from_event(event))
                    for action in actions:
                        if isinstance(action,Action): self.handle(action)
                    self.draw(font,small); display.present(); clock.tick(FPS)
        finally: display.close(); pygame.quit()


class _NullContext:
    def __enter__(self): return self
    def __exit__(self,*unused): return False


def main() -> None:
    configure_logging(); App(load_settings()).run()


if __name__ == "__main__": main()
