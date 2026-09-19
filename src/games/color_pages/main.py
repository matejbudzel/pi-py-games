"""A compact, controller-first pixel coloring game."""
from __future__ import annotations

import time
import pygame

from common.assets import SWEET16_FONT_PATH
from common.console_input import ConsoleInput
from common.display import GameDisplay, display_settings, initialize_pygame
from common.error_logging import configure_logging
from common.input import Action, actions_from_event
from common.joystick_input import JoystickInput
from .pages import PAGES, Page

# The art and UI live on the deliberately chunky logical canvas.  GameDisplay
# presents this exact surface at 854x480 using a 2x nearest-neighbour scale.
WIDTH, HEIGHT, FPS = 427, 240, 30
OUTPUT_SIZE = (854, 480)
BG, INK, WHITE, GREY = (31, 35, 55), (12, 15, 25), (247, 245, 235), (126, 132, 146)
CELL, HUD_W = 5, 48
GRID_COLUMNS = 3
RAINBOW = ((255, 105, 112), (255, 181, 72), (255, 232, 92), (104, 221, 133), (94, 184, 255), (183, 126, 255))


class App:
    def __init__(self) -> None:
        self.screen_name, self.selected, self.modal = "splash", 0, None
        self.selection_scroll = 0
        self.cursor = [0, 0]
        self.colored: set[tuple[int, int]] = set()
        self.current_color, self.steps, self.started = 0, 0, 0.0
        self.camera = [0, 0]
        self.running = True

    @property
    def page(self) -> Page: return PAGES[self.selected]

    def begin(self) -> None:
        self.screen_name, self.cursor, self.colored = "drawing", [0, 0], set()
        self.current_color, self.steps, self.started, self.camera = 0, 0, time.monotonic(), [0, 0]
        self._advance_color()

    def _advance_color(self) -> None:
        while self.current_color < self.page.color_count and not any(
            value == self.current_color and (x, y) not in self.colored
            for y, row in enumerate(self.page.pixels) for x, value in enumerate(row)
        ):
            self.current_color += 1
        if self.current_color == self.page.color_count:
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
            elif action is Action.SELECT: self.modal = None
            elif action is Action.START:
                if self.modal == "yes": self.running = False if self.screen_name == "selection" else True; self.screen_name = "selection" if self.screen_name == "drawing" else self.screen_name
                self.modal = None
            return
        if self.screen_name == "splash":
            if action is Action.START: self.screen_name = "selection"
            elif action is Action.SELECT: self.running = False
        elif self.screen_name == "selection":
            if action is Action.SELECT: self.modal = "no"
            elif action is Action.START: self.begin()
            elif action in (Action.LEFT, Action.RIGHT, Action.UP, Action.DOWN):
                dx, dy = {Action.LEFT:(-1,0), Action.RIGHT:(1,0), Action.UP:(0,-1), Action.DOWN:(0,1)}[action]
                col, row = self.selected % GRID_COLUMNS, self.selected // GRID_COLUMNS
                proposed = (row + dy) * GRID_COLUMNS + col + dx
                if 0 <= col + dx < GRID_COLUMNS and 0 <= proposed < len(PAGES):
                    self.selected = proposed
                    self.selection_scroll = max(0, min(self.selected // GRID_COLUMNS - 1, max(0, (len(PAGES) - 1) // GRID_COLUMNS - 1)))
        elif self.screen_name == "drawing":
            if action is Action.SELECT: self.modal = "no"
            elif action in (Action.LEFT, Action.RIGHT, Action.UP, Action.DOWN): self.move(action)
        elif self.screen_name == "result" and action in (Action.START, Action.SELECT): self.screen_name = "selection"

    def draw(self, font: pygame.font.Font, small: pygame.font.Font) -> None:
        self.screen.fill(BG)
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
        scale = rect.width / page.size
        pygame.draw.rect(self.screen, INK, rect)
        for y, row in enumerate(page.pixels):
            for x, value in enumerate(row):
                if value >= 0: pygame.draw.rect(self.screen, page.palette[value], (rect.x+x*scale, rect.y+y*scale, max(1, scale), max(1, scale)))

    def _selection(self, font, small):
        self._rainbow_title((8, 8))
        for index, page in enumerate(PAGES):
            row = index // GRID_COLUMNS
            if not self.selection_scroll <= row < self.selection_scroll + 2: continue
            x, y = 8 + (index % GRID_COLUMNS)*74, 42 + (row-self.selection_scroll)*88
            rect = pygame.Rect(x, y, 64, 64); self._thumbnail(page, rect)
            if index == self.selected: pygame.draw.rect(self.screen, (255, 219, 84), rect.inflate(4, 4), 2)
        page = self.page
        panel = pygame.Rect(231, 0, 196, HEIGHT)
        pygame.draw.rect(self.screen, (45, 51, 75), panel)
        pygame.draw.rect(self.screen, (87, 95, 125), panel, 1)
        self._thumbnail(page, pygame.Rect(265, 32, 128, 128))
        self._text(self.bold_font, page.title, (247, 172))
        self._text(font, f"{page.color_count} colors", (247, 194))
        for index, color in enumerate(page.palette):
            pygame.draw.circle(self.screen, color, (249 + (index % 8)*21, 222 + (index // 8)*15), 7)

    def _drawing(self, font):
        page = self.page; max_x, max_y = (WIDTH-HUD_W)//CELL, HEIGHT//CELL
        for sy in range(min(max_y, page.size-self.camera[1])):
            for sx in range(min(max_x, page.size-self.camera[0])):
                x, y = sx+self.camera[0], sy+self.camera[1]; value = page.pixels[y][x]
                color = INK if value < 0 else (page.palette[value] if (x,y) in self.colored else GREY)
                rect = pygame.Rect(sx*CELL, sy*CELL, CELL, CELL); pygame.draw.rect(self.screen, color, rect)
                if value == self.current_color and (x,y) not in self.colored: pygame.draw.circle(self.screen, WHITE, rect.center, 1)
        sx, sy = (self.cursor[0]-self.camera[0])*CELL, (self.cursor[1]-self.camera[1])*CELL
        pygame.draw.rect(self.screen, WHITE, (sx, sy, CELL, CELL), 1)
        x = WIDTH-HUD_W+6; pygame.draw.rect(self.screen, (45, 51, 75), (WIDTH-HUD_W, 0, HUD_W, HEIGHT))
        total = sum(value >= 0 for row in page.pixels for value in row); pct = round(100*len(self.colored)/total) if total else 100
        for i, label in enumerate((f"{pct}%", f"{self.current_color+1}/{page.color_count}", f"{self.steps}", f"{int(time.monotonic()-self.started)}s")):
            self._text(font, label, (x, 9+i*17))
        if self.current_color < page.color_count: pygame.draw.circle(self.screen, page.palette[self.current_color], (WIDTH-HUD_W//2, 82), 7)
        for i, color in enumerate(page.palette): pygame.draw.circle(self.screen, color, (x+7+(i%2)*17, 104+(i//2)*15), 5)

    def _result(self, font, small):
        page = self.page; scale = min(160/page.size, 180/page.size); ox, oy = 90, (HEIGHT-page.size*scale)/2
        for y,row in enumerate(page.pixels):
            for x,value in enumerate(row):
                if value >= 0: pygame.draw.rect(self.screen, page.palette[value], (ox+x*scale, oy+y*scale, scale, scale))
        self._text(font, f"{int(time.monotonic()-self.started)}s", (285, 90)); self._text(font, f"{self.steps}", (285, 125))
        pygame.draw.circle(self.screen, (255,220,70), (267,86), 6); pygame.draw.polygon(self.screen, WHITE, [(262,118),(267,113),(272,118),(267,123)])

    def _modal(self, font, small):
        overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA); overlay.fill((0,0,0,175)); self.screen.blit(overlay,(0,0))
        rect=pygame.Rect(125,85,177,70); pygame.draw.rect(self.screen,(57,64,91),rect); pygame.draw.rect(self.screen,WHITE,rect,1)
        self._text(font, "LEAVE?", (WIDTH//2,98), center=True)
        self._text(small, "YES", (170,130), (255,219,84) if self.modal=="yes" else WHITE); self._text(small,"NO",(235,130),(255,219,84) if self.modal=="no" else WHITE)

    def run(self) -> None:
        settings=display_settings(); initialize_pygame(settings)
        display=GameDisplay(settings, OUTPUT_SIZE, logical_size=(WIDTH, HEIGHT)); self.screen=display.canvas
        # All layout dimensions, including the 16px Sweet16 type, are defined
        # on the 427x240 logical canvas.  Presentation scaling is separate.
        font=pygame.font.Font(SWEET16_FONT_PATH, 16); small=pygame.font.Font(SWEET16_FONT_PATH, 16)
        self.bold_font=pygame.font.Font(SWEET16_FONT_PATH, 16); self.bold_font.set_bold(True)
        glyphs = [self.bold_font.render(letter, False, RAINBOW[index % len(RAINBOW)]) for index, letter in enumerate("PIXEL COLORS")]
        self.rainbow_title = pygame.Surface((sum(glyph.get_width() for glyph in glyphs), self.bold_font.get_height()), pygame.SRCALPHA)
        x = 0
        for glyph in glyphs:
            self.rainbow_title.blit(glyph, (x, 0)); x += glyph.get_width()
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
    configure_logging(); App().run()


if __name__ == "__main__": main()
