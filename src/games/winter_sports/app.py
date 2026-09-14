from __future__ import annotations
from enum import Enum, auto
from dataclasses import replace
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
from .speed_skating import OVALS, SpeedSkatingRun, point_at
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
        self.gestures, self.latest_gesture, self.run, self.speed_run, self.overlay = GestureTracker(), None, None, None, False
    @property
    def sport(self) -> str: return self.sports[self.selected]
    @property
    def course(self): return COURSES[self.sport][self.course_selected]
    @property
    def tuning_keys(self) -> tuple[str, ...]:
        if self.sport == "Speed skating":
            return ("cadence", "curve_loss", "airborne_loss", "inertia", "imbalance", "wall")
        return ("wind", "steering", "balance", "cadence")
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
        elif self.screen is Screen.TUNING: self.tune_selected=move_selection(self.tune_selected,delta,len(self.tuning_keys)+1)
    def adjust(self, delta: float) -> None:
        keys=self.tuning_keys
        if self.tune_selected < len(keys):
            key=keys[self.tune_selected]; self.tuning[key]=round(max(0,min(2,self.tuning[key]+delta)),1); save(self.settings.tuning_path,self.tuning)
    def confirm(self) -> None:
        if self.screen is Screen.SPORTS: self.screen=Screen.COURSES
        elif self.screen is Screen.COURSES: self.screen=Screen.TUNING
        elif self.screen is Screen.TUNING:
            if self.tune_selected == len(self.tuning_keys): self.tuning=dict(DEFAULTS); save(self.settings.tuning_path,self.tuning)
            else: self.screen=Screen.COUNTDOWN; self.countdown_started=time.monotonic()
        elif self.screen is Screen.RESULT: self.screen=Screen.SPORTS
    def update(self, now: float, dt: float) -> None:
        if self.screen is Screen.COUNTDOWN and now-self.countdown_started >= 3:
            if self.sport == "Speed skating":
                oval = OVALS[self.course.name]
                self.speed_run = SpeedSkatingRun(replace(
                    oval,
                    cadence_gain=oval.cadence_gain * self.tuning["cadence"],
                    curve_loss=oval.curve_loss * self.tuning["curve_loss"],
                    airborne_loss=oval.airborne_loss * self.tuning["airborne_loss"],
                    inertia=oval.inertia * self.tuning["inertia"],
                    imbalance_gain=oval.imbalance_gain * self.tuning["imbalance"],
                    wall_speed_factor=min(.95, oval.wall_speed_factor * self.tuning["wall"]),
                ))
                self.run = None
            else:
                self.run=Run(self.course,PROFILES[self.sport],self.tuning.copy(),self.seed)
                self.speed_run = None
            self.screen=Screen.EVENT
        if self.screen is Screen.EVENT and self.speed_run:
            self.latest_gesture = self.gestures.update(self.held, now)
            self.speed_run.update(dt, self.latest_gesture)
            if self.speed_run.complete:
                self.screen = Screen.RESULT
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
            for index,key in enumerate(list(self.tuning_keys)+["Reset defaults"]): self.text(("> " if index==self.tune_selected else "  ")+key+("  %.1f"%self.tuning[key] if key in self.tuning else ""),25,54+index*22,index==self.tune_selected)
        elif self.screen is Screen.COUNTDOWN: self.text(str(max(1,3-int(time.monotonic()-self.countdown_started))),205,105,big=True)
        elif self.speed_run:
            self.draw_speed_skating()
            if self.screen is Screen.RESULT:
                self.draw_result_stars(self.speed_run.stars())
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

    def draw_speed_skating(self) -> None:
        """Render a fixed-orientation local camera through a real stadium oval."""
        assert self.speed_run
        run, oval, scale = self.speed_run, self.speed_run.oval, 3.0
        player_x, player_y, _ = point_at(oval, run.distance, run.offset)
        center = (WIDTH // 2, HEIGHT // 2)

        def screen_point(distance: float, offset: float) -> tuple[int, int]:
            world_x, world_y, _ = point_at(oval, distance, offset)
            return (round(center[0] + (world_x - player_x) * scale), round(center[1] + (world_y - player_y) * scale))

        # Two separately sampled racing-line offsets form the inner and outer
        # oval borders.  The camera translates only; it never rotates.
        for offset in (-oval.track_width / 2, oval.track_width / 2):
            points = [screen_point(run.distance - 100 + 200 * index / 100, offset) for index in range(101)]
            pygame.draw.lines(self.canvas, (245, 250, 255), False, points, 2)
        for offset in (-oval.track_width / 4, oval.track_width / 4):
            points = [screen_point(run.distance - 100 + 200 * index / 80, offset) for index in range(81)]
            pygame.draw.lines(self.canvas, (110, 170, 205), False, points, 1)
        # The line is both start and finish, rendered whenever it is near the
        # player.  It crosses the complete width of the ice lane.
        if min(run.distance % oval.lap_metres, oval.lap_metres - run.distance % oval.lap_metres) < 35:
            a, b = screen_point(0, -oval.track_width / 2), screen_point(0, oval.track_width / 2)
            pygame.draw.line(self.canvas, (255, 205, 70), a, b, 2)
        pygame.draw.rect(self.canvas, (240, 70, 60), pygame.Rect(center[0] - 4, center[1] - 4, 8, 8))
        self.draw_speed_hud(run)

    def draw_speed_hud(self, run: SpeedSkatingRun) -> None:
        oval = run.oval
        self.text("WR %.3f" % oval.record_seconds, 7, 7)
        self.text("%05.2f" % run.elapsed, 336, 7)
        self.text("%04.1f m/s" % run.speed, 324, 26)
        # Contact circles deliberately remain in the HUD as input diagnostics.
        gesture = self.latest_gesture
        if gesture is None:
            return
        for x, pressed in ((377, gesture.left), (402, gesture.right)):
            pygame.draw.circle(self.canvas, (245, 230, 100) if pressed else (55, 85, 110), (x, 53), 7)
            pygame.draw.circle(self.canvas, (235, 245, 255), (x, 53), 7, 1)
        # Balance is a direction/edge indicator: vertical is efficient, and a
        # sideways tip warns that the next step will give less acceleration.
        angle = max(-1.25, min(1.25, run.balance))
        base, tip = (352, 55), (round(352 + sin(angle) * 15), round(55 - cos(angle) * 15))
        pygame.draw.line(self.canvas, (255, 220, 90), base, tip, 2)
        pygame.draw.circle(self.canvas, (255, 220, 90), tip, 3)
    def draw_run(self) -> None:
        assert self.run
        cx=WIDTH//2; pygame.draw.line(self.canvas,(245,250,255),(70,230),(cx,10),3); pygame.draw.line(self.canvas,(245,250,255),(357,230),(cx,10),3)
        for mark in range(30, int(self.run.course.length),30):
            y=220-int((mark-self.run.distance)*2)
            if 0<y<235: pygame.draw.line(self.canvas,(120,170,200),(cx-8,y),(cx+8,y),1)
        player=pygame.Rect(int(cx+self.run.lateral*10)-5,185,10,14); pygame.draw.rect(self.canvas,(240,70,60),player)
        if self.overlay: self.text("v %.1f  b %.2f  w %.2f  d %.0f"%(self.run.speed,self.run.balance,self.run.wind,self.run.distance),5,5)
