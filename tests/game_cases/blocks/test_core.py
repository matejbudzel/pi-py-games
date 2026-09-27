import random
from dataclasses import replace

from games.blocks.core import BOARD_HEIGHT, BOARD_WIDTH, Game, Piece
from games.blocks.progress import HighScoreStore
from games.blocks.input import actions_from_blocks_event
from common.input import Action, Release
import pygame
from games.blocks.config import load_settings
from games.blocks.main import App


def test_spawn_and_rotation_stay_inside_board():
    game = Game.new(random.Random(1))
    assert game.current is not None
    game.current = Piece("I", x=7, y=0, rotation=0)
    assert game.rotate(1)
    assert all(0 <= x + game.current.x < BOARD_WIDTH for x, _ in game.current.cells)


def test_full_line_scores_and_advances_line_count():
    game = Game.new(random.Random(2))
    game.board[-1] = ["I"] * BOARD_WIDTH
    game.current = Piece("O", x=3, y=BOARD_HEIGHT - 3)
    game._lock()
    assert game.lines == 1
    assert game.score == 100


def test_high_score_is_retained(tmp_path):
    path = tmp_path / "blocks.json"
    scores = HighScoreStore(path)
    assert scores.record(123)
    assert not scores.record(100)
    assert HighScoreStore(path).high_score == 123


def test_upper_pad_buttons_are_blocks_rotation_actions():
    assert actions_from_blocks_event(pygame.event.Event(pygame.JOYBUTTONDOWN, button=6)) == [Action.LEFT_UP]
    assert actions_from_blocks_event(pygame.event.Event(pygame.JOYBUTTONDOWN, button=7)) == [Action.RIGHT_UP]


def test_pause_resume_and_result_actions_are_immediate(tmp_path):
    app = App(replace(load_settings(), high_score_path=tmp_path / "scores.json"))
    app.handle(Action.START)
    assert app.screen_name == "game" and app.game is not None
    app.countdown_until = 0
    app.handle(Action.START)
    assert app.paused
    app.handle(Action.START)
    assert not app.paused and app.countdown_until > 0
    app.game.game_over = True
    app._check_game_over()
    assert app.screen_name == "result"
    app.handle(Action.START)
    assert app.screen_name == "game" and app.modal is None
    app.screen_name = "result"
    app.handle(Action.SELECT)
    assert not app.running


def test_soft_drop_holds_after_delay_and_stops_on_release(tmp_path):
    app = App(replace(load_settings(), high_score_path=tmp_path / "scores.json"))
    app.start_game()
    app.countdown_until = 0
    app.next_fall = float("inf")
    assert app.game is not None and app.game.current is not None
    initial_y = app.game.current.y
    app.handle(Action.DOWN)
    assert app.game.current.y == initial_y + 1
    app.next_soft_drop = 0
    app.update(1)
    assert app.game.current.y == initial_y + 2
    app.release(Release(Action.DOWN))
    app.update(2)
    assert app.game.current.y == initial_y + 2


def test_piece_and_performance_overlay_use_small_dirty_regions(tmp_path):
    app = App(replace(load_settings(), high_score_path=tmp_path / "scores.json"))
    pygame.font.init()
    app.screen = pygame.Surface((427, 240))
    app.canvas = pygame.Surface((427, 240))
    app.backgrounds = {name: pygame.Surface((427, 240)) for name in ("splash", "game", "result")}
    font, large = pygame.font.Font(None, 16), pygame.font.Font(None, 24)
    app.start_game()
    app.countdown_until = 0
    assert app._draw_pending(font, large) == [pygame.Rect(0, 0, 427, 240)]
    app.handle(Action.RIGHT)
    moved = app._draw_pending(font, large)
    assert moved and all(rect != pygame.Rect(0, 0, 427, 240) for rect in moved)
    app.handle(Action.DEBUG_TOGGLE_PERFORMANCE)
    overlay = app._draw_pending(font, large)
    assert overlay and all(rect != pygame.Rect(0, 0, 427, 240) for rect in overlay)
