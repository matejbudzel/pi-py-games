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

WIDTH, HEIGHT, FPS = 854, 480, 30
BG, INK, WHITE, GREY = (31, 35, 55), (12, 15, 25), (247, 245, 235), (126, 132, 146)
CELL, HUD_W = 5, 96


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
                col, row = self.selected % 4, self.selected // 4
                proposed = (row + dy) * 4 + col + dx
                if 0 <= col + dx < 4 and 0 <= proposed < len(PAGES):
                    self.selected = proposed
                    self.selection_scroll = max(0, min(self.selected // 4 - 1, max(0, (len(PAGES) - 1) // 4 - 1)))
        elif self.screen_name == "drawing":
            if action is Action.SELECT: self.modal = "no"
            elif action in (Action.LEFT, Action.RIGHT, Action.UP, Action.DOWN): self.move(action)
        elif self.screen_name == "result" and action in (Action.START, Action.SELECT): self.screen_name = "selection"

    def draw(self, font: pygame.font.Font, small: pygame.font.Font) -> None:
        self.screen.fill(BG)
        if self.screen_name == "splash": self._text(font, "PIXEL COLORS", (WIDTH//2, HEIGHT//2), center=True)
        elif self.screen_name == "selection": self._selection(font, small)
        elif self.screen_name == "drawing": self._drawing(small)
        else: self._result(font, small)
        if self.modal: self._modal(font, small)

    def _text(self, font, text, pos, color=WHITE, center=False):
        image = font.render(text, False, color); self.screen.blit(image, image.get_rect(center=pos) if center else pos)

    def _thumbnail(self, page, rect):
        scale = 64 / page.size
        pygame.draw.rect(self.screen, INK, rect)
        for y, row in enumerate(page.pixels):
            for x, value in enumerate(row):
                if value >= 0: pygame.draw.rect(self.screen, page.palette[value], (rect.x+x*scale, rect.y+y*scale, max(1, scale), max(1, scale)))

    def _selection(self, font, small):
        self._text(font, "PIXEL COLORS", (30, 20))
        for index, page in enumerate(PAGES):
            row = index // 4
            if not self.selection_scroll <= row < self.selection_scroll + 2: continue
            x, y = 72 + (index % 4)*156, 78 + (row-self.selection_scroll)*156
            rect = pygame.Rect(x, y, 64, 64); self._thumbnail(page, rect)
            if index == self.selected: pygame.draw.rect(self.screen, (255, 219, 84), rect.inflate(8, 8), 3)
        page = self.page; col = self.selected % 4
        x = 682 if col < 3 else 8
        pygame.draw.rect(self.screen, (57, 64, 91), (x, 248, 156, 92))
        self._text(small, page.title, (x+10, 260)); self._text(small, f"{page.size} x {page.size}", (x+10, 284)); self._text(small, f"{page.color_count} colors", (x+10, 308))

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
        x = WIDTH-HUD_W+12; pygame.draw.rect(self.screen, (45, 51, 75), (WIDTH-HUD_W, 0, HUD_W, HEIGHT))
        total = sum(value >= 0 for row in page.pixels for value in row); pct = round(100*len(self.colored)/total) if total else 100
        for i, label in enumerate((f"{pct}%", f"{self.current_color+1}/{page.color_count}", f"{self.steps}", f"{int(time.monotonic()-self.started)}s")):
            self._text(font, label, (x, 18+i*34))
        if self.current_color < page.color_count: pygame.draw.circle(self.screen, page.palette[self.current_color], (WIDTH-HUD_W//2, 164), 14)
        for i, color in enumerate(page.palette): pygame.draw.circle(self.screen, color, (x+14+(i%2)*34, 208+(i//2)*30), 10)

    def _result(self, font, small):
        page = self.page; scale = min(320/page.size, 360/page.size); ox, oy = 180, (HEIGHT-page.size*scale)/2
        for y,row in enumerate(page.pixels):
            for x,value in enumerate(row):
                if value >= 0: pygame.draw.rect(self.screen, page.palette[value], (ox+x*scale, oy+y*scale, scale, scale))
        self._text(font, f"{int(time.monotonic()-self.started)}s", (570, 180)); self._text(font, f"{self.steps}", (570, 250))
        pygame.draw.circle(self.screen, (255,220,70), (535,172), 12); pygame.draw.polygon(self.screen, WHITE, [(523,235),(533,225),(543,235),(533,245)])

    def _modal(self, font, small):
        overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA); overlay.fill((0,0,0,175)); self.screen.blit(overlay,(0,0))
        rect=pygame.Rect(250,170,354,140); pygame.draw.rect(self.screen,(57,64,91),rect); pygame.draw.rect(self.screen,WHITE,rect,2)
        self._text(font, "LEAVE?", (WIDTH//2,195), center=True)
        self._text(small, "YES", (340,260), (255,219,84) if self.modal=="yes" else WHITE); self._text(small,"NO",(470,260),(255,219,84) if self.modal=="no" else WHITE)

    def run(self) -> None:
        settings=display_settings(); initialize_pygame(settings)
        display=GameDisplay(settings,(WIDTH,HEIGHT)); self.screen=display.canvas
        font=pygame.font.Font(SWEET16_FONT_PATH, 24); small=pygame.font.Font(SWEET16_FONT_PATH, 16)
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
