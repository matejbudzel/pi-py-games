from __future__ import annotations
from enum import Enum, auto
import time
import pygame
from common.assets import SWEET16_FONT_PATH
from common.display import DisplaySettings, GameDisplay, initialize_pygame
from common.input import Action, Release, actions_from_event
from common.selection import move_selection, visible_window
from .config import FPS, HEIGHT, OUTPUT_SIZE, WIDTH, Settings
from .courses import COURSES, PROFILES
from .core import Run
from .gestures import GestureTracker
from .tuning import DEFAULTS, load, save

class Screen(Enum): SPORTS = auto(); COURSES = auto(); TUNING = auto(); COUNTDOWN = auto(); EVENT = auto(); RESULT = auto()
class App:
    def __init__(self, settings: Settings, seed: int | None = None) -> None:
        self.settings, self.seed = settings, seed if seed is not None else int(time.time())
        platform = DisplaySettings(settings.display_backend, settings.framebuffer_device)
        initialize_pygame(platform)
        self.display = GameDisplay(platform, OUTPUT_SIZE, logical_size=(WIDTH, HEIGHT)); self.canvas = self.display.canvas
        # Sweet16 was drawn for these native pixel sizes.  Rendering it at 12
        # and 20 produces uneven glyph strokes after the canvas is doubled.
        self.font = pygame.font.Font(SWEET16_FONT_PATH, 16)
        self.big = pygame.font.Font(SWEET16_FONT_PATH, 24)
        self.clock, self.running, self.screen, self.held = pygame.time.Clock(), True, Screen.SPORTS, set()
        self.sports, self.selected, self.first = list(COURSES), 0, 0
        self.course_selected = self.tune_selected = 0; self.tuning = load(settings.tuning_path); self.countdown_started = 0.0
        self.gestures, self.run, self.overlay = GestureTracker(), None, False
    @property
    def sport(self) -> str: return self.sports[self.selected]
    @property
    def course(self): return COURSES[self.sport][self.course_selected]
    def run_loop(self) -> None:
        last = time.monotonic()
        while self.running:
            now = time.monotonic(); dt = min(.1, now-last); last = now
            self.events(); self.update(now, dt); self.draw(); self.display.present(); self.clock.tick(FPS)
        self.display.close(); pygame.quit()
    def events(self) -> None:
        for event in pygame.event.get():
            if event.type == pygame.QUIT: self.running = False
            for item in actions_from_event(event):
                if isinstance(item, Release): self.held.discard(item.action.name.lower()); continue
                action = item
                if action in (Action.LEFT, Action.RIGHT, Action.UP, Action.DOWN): self.held.add(action.name.lower())
                if action is Action.DEBUG_TOGGLE_PERFORMANCE: self.overlay = not self.overlay
                if action is Action.SELECT:
                    if self.screen in (Screen.SPORTS,): self.running=False
                    elif self.screen is Screen.EVENT: self.screen=Screen.RESULT
                    else: self.screen=Screen.SPORTS
                elif action is Action.UP: self.navigate(-1)
                elif action is Action.DOWN: self.navigate(1)
                elif action is Action.LEFT and self.screen is Screen.TUNING: self.adjust(-.1)
                elif action is Action.RIGHT and self.screen is Screen.TUNING: self.adjust(.1)
                elif action is Action.START: self.confirm()
    def navigate(self, delta: int) -> None:
        if self.screen is Screen.SPORTS:
            self.selected=move_selection(self.selected,delta,len(self.sports)); self.first=visible_window(self.first,self.selected,len(self.sports),8)
        elif self.screen is Screen.COURSES: self.course_selected=move_selection(self.course_selected,delta,len(COURSES[self.sport]))
        elif self.screen is Screen.TUNING: self.tune_selected=move_selection(self.tune_selected,delta,len(DEFAULTS)+1)
    def adjust(self, delta: float) -> None:
        keys=list(DEFAULTS)
        if self.tune_selected < len(keys):
            key=keys[self.tune_selected]; self.tuning[key]=round(max(0,min(2,self.tuning[key]+delta)),1); save(self.settings.tuning_path,self.tuning)
    def confirm(self) -> None:
        if self.screen is Screen.SPORTS: self.screen=Screen.COURSES
        elif self.screen is Screen.COURSES: self.screen=Screen.TUNING
        elif self.screen is Screen.TUNING:
            if self.tune_selected == len(DEFAULTS): self.tuning=dict(DEFAULTS); save(self.settings.tuning_path,self.tuning)
            else: self.screen=Screen.COUNTDOWN; self.countdown_started=time.monotonic()
        elif self.screen is Screen.RESULT: self.screen=Screen.SPORTS
    def update(self, now: float, dt: float) -> None:
        if self.screen is Screen.COUNTDOWN and now-self.countdown_started >= 3:
            self.run=Run(self.course,PROFILES[self.sport],self.tuning.copy(),self.seed); self.screen=Screen.EVENT
        if self.screen is Screen.EVENT and self.run:
            self.run.update(dt,self.gestures.update(self.held,now),self.sport)
            if self.run.complete: self.screen=Screen.RESULT
    def text(self, value: str, x: int, y: int, selected=False, big=False) -> None:
        self.canvas.blit((self.big if big else self.font).render(value,False,(255,220,90) if selected else (235,245,255)),(x,y))
    def draw(self) -> None:
        self.canvas.fill((35,75,110)); pygame.draw.rect(self.canvas,(225,240,248),(0,0,WIDTH,HEIGHT),2)
        if self.screen is Screen.SPORTS:
            self.text(self.settings.title,22,18, big=True)
            for row,name in enumerate(self.sports[self.first:self.first+8]): self.text(("> " if self.first+row==self.selected else "  ")+name,25,55+row*20,self.first+row==self.selected)
        elif self.screen is Screen.COURSES:
            self.text(self.sport,22,18,big=True)
            for index,course in enumerate(COURSES[self.sport]): self.text(("> " if index==self.course_selected else "  ")+course.name,25,62+index*24,index==self.course_selected)
        elif self.screen is Screen.TUNING:
            self.text(self.sport,22,18,big=True)
            for index,key in enumerate(list(DEFAULTS)+["Reset defaults"]): self.text(("> " if index==self.tune_selected else "  ")+key+("  %.1f"%self.tuning[key] if key in self.tuning else ""),25,54+index*22,index==self.tune_selected)
        elif self.screen is Screen.COUNTDOWN: self.text(str(max(1,3-int(time.monotonic()-self.countdown_started))),205,105,big=True)
        elif self.run:
            self.draw_run()
            if self.screen is Screen.RESULT:
                self.draw_result_stars(self.run.stars())
                self.draw_snowflake(WIDTH // 2, 136)

    def draw_result_stars(self, earned: int) -> None:
        """Draw result symbols ourselves: Sweet16 intentionally has no Unicode stars."""
        for index in range(5):
            center = (145 + index * 34, 105)
            color = (255, 220, 90) if index < earned else (98, 130, 153)
            self.draw_star(center, color)

    def draw_star(self, center: tuple[int, int], color: tuple[int, int, int]) -> None:
        x, y = center
        points = ((x, y - 10), (x + 3, y - 3), (x + 10, y - 3), (x + 5, y + 2),
                  (x + 7, y + 9), (x, y + 5), (x - 7, y + 9), (x - 5, y + 2),
                  (x - 10, y - 3), (x - 3, y - 3))
        pygame.draw.polygon(self.canvas, color, points)

    def draw_snowflake(self, x: int, y: int) -> None:
        """A simple landmark instead of a missing-font-glyph box."""
        color = (235, 245, 255)
        pygame.draw.line(self.canvas, color, (x - 10, y), (x + 10, y), 2)
        pygame.draw.line(self.canvas, color, (x, y - 10), (x, y + 10), 2)
        pygame.draw.line(self.canvas, color, (x - 7, y - 7), (x + 7, y + 7), 2)
        pygame.draw.line(self.canvas, color, (x - 7, y + 7), (x + 7, y - 7), 2)
    def draw_run(self) -> None:
        assert self.run
        cx=WIDTH//2; pygame.draw.line(self.canvas,(245,250,255),(70,230),(cx,10),3); pygame.draw.line(self.canvas,(245,250,255),(357,230),(cx,10),3)
        for mark in range(30, int(self.run.course.length),30):
            y=220-int((mark-self.run.distance)*2)
            if 0<y<235: pygame.draw.line(self.canvas,(120,170,200),(cx-8,y),(cx+8,y),1)
        player=pygame.Rect(int(cx+self.run.lateral*10)-5,185,10,14); pygame.draw.rect(self.canvas,(240,70,60),player)
        if self.overlay: self.text("v %.1f  b %.2f  w %.2f  d %.0f"%(self.run.speed,self.run.balance,self.run.wind,self.run.distance),5,5)
