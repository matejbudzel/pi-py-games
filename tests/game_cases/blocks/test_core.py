import random
from dataclasses import replace

from games.blocks.core import BOARD_HEIGHT, BOARD_WIDTH, Game, Piece
from games.blocks.progress import HighScoreStore
from games.blocks.input import actions_from_blocks_event
from common.input import Action
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
