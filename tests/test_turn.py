"""The shared era turn (backend/turn.py) — the recipe both the website and the
Lichess BOT accounts play by.

Everything here runs on a stub engine with a dictated win probability. That is
deliberate: these tests assert the *rules* (when an era resigns, when it offers,
when it must not), never a neural model's opinion, which is neither stable nor
meaningful to assert on. Era parameters come from config/eras.yaml so retuning
the constants can't quietly break the rules they drive.
"""
import os
import sys
from pathlib import Path

os.environ["TMC_FORCE_HEURISTIC"] = "1"

import chess
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from backend.engine_pool import CFG  # noqa: E402
from backend.turn import play_turn, would_accept_draw  # noqa: E402

ROMANTIC = CFG["eras"]["romantic"]


class StubEngine:
    """Plays the first legal move and reports whatever win prob it's told to."""

    def __init__(self, win_prob=0.5, move=None):
        self.win_prob = win_prob
        self.forced = move
        self.calls = 0

    def _move(self, board):
        if self.forced is not None:
            return chess.Move.from_uci(self.forced)
        return sorted(board.legal_moves, key=lambda m: m.uci())[0]

    def pick_move(self, board):
        self.calls += 1
        return self._move(board)

    def pick_move_with_eval(self, board):
        self.calls += 1
        return self._move(board), self.win_prob


class NoEvalEngine:
    """An engine with no win-probability head — manners must degrade, not crash."""

    def pick_move(self, board):
        return sorted(board.legal_moves, key=lambda m: m.uci())[0]


def test_engine_without_eval_head_still_moves():
    turn = play_turn(NoEvalEngine(), ROMANTIC, chess.Board())
    assert turn.move in chess.Board().legal_moves
    assert turn.win_prob is None
    assert turn.resigns is False and turn.offers_draw is False


def test_board_is_not_mutated():
    board = chess.Board()
    before = board.fen()
    play_turn(StubEngine(), ROMANTIC, board)
    assert board.fen() == before


def test_resign_needs_streak_and_minimum_ply():
    """A hopeless evaluation isn't enough on its own: the era's streak and
    min_ply both have to be satisfied (Romantics play on for a while)."""
    params = ROMANTIC["resign"]
    hopeless = StubEngine(win_prob=params["threshold"] / 2)   # White is lost
    board = chess.Board()                                     # ply 0, White to move

    streak = 0
    for _ in range(params["streak"] + 2):
        turn = play_turn(hopeless, ROMANTIC, board, resign_streak=streak)
        streak = turn.resign_streak
        assert turn.resigns is False, "resigned before min_ply — too early"

    # Deep enough now: same evaluations, past the era's minimum ply.
    deep = chess.Board("7k/8/8/8/8/8/6q1/K7 w - - 0 40")
    assert deep.ply() >= params["min_ply"]
    streak = 0
    resigned_at = None
    for i in range(1, params["streak"] + 3):
        turn = play_turn(hopeless, ROMANTIC, deep, resign_streak=streak)
        streak = turn.resign_streak
        if turn.resigns:
            resigned_at = i
            break
    assert resigned_at == params["streak"], "resigned on the wrong evaluation"


def test_resign_uses_the_resigning_side_perspective():
    """win_prob is always White's. A White win prob of ~1.0 is Black losing."""
    params = ROMANTIC["resign"]
    board = chess.Board("7k/8/8/8/8/8/6Q1/K7 b - - 0 40")   # Black to move, lost
    engine = StubEngine(win_prob=0.999)
    streak = 0
    for _ in range(params["streak"]):
        turn = play_turn(engine, ROMANTIC, board, resign_streak=streak)
        streak = turn.resign_streak
    assert turn.resigns is True

    # The same evaluation with White to move is White winning — nobody resigns.
    white_to_move = chess.Board("7k/8/8/8/8/8/6Q1/K7 w - - 0 40")
    turn = play_turn(engine, ROMANTIC, white_to_move, resign_streak=99)
    assert turn.resigns is False


def test_hopeful_evaluation_resets_the_resign_streak():
    params = ROMANTIC["resign"]
    board = chess.Board("7k/8/8/8/8/8/6q1/K7 w - - 0 40")
    turn = play_turn(StubEngine(win_prob=0.5), ROMANTIC, board,
                     resign_streak=params["streak"] - 1)
    assert turn.resign_streak == 0 and turn.resigns is False


def test_draw_offer_rides_along_when_the_era_is_willing():
    era = {"draws": {"band": 0.1, "streak": 2, "min_move": 30}}
    board = chess.Board("3rk3/8/8/8/8/8/8/3RK3 w - - 0 40")
    turn = play_turn(StubEngine(win_prob=0.5), era, board, draw_streak=1)
    assert turn.draw_streak == 2
    assert turn.offers_draw is True


def test_draw_is_not_offered_before_the_era_agrees_to_talk():
    era = {"draws": {"band": 0.1, "streak": 2, "min_move": 60}}
    board = chess.Board("3rk3/8/8/8/8/8/8/3RK3 w - - 0 40")   # move 40 < min_move 60
    assert play_turn(StubEngine(0.5), era, board, draw_streak=9).offers_draw is False


def test_never_offer_a_draw_with_a_move_that_ends_the_game():
    """Mate in one, but the position looks 'equal' to a stub eval: offering
    (or worse, having it accepted) would throw away a won game."""
    era = {"draws": {"band": 0.5, "streak": 1, "min_move": 1}}
    board = chess.Board("7k/5Q2/6K1/8/8/8/8/8 w - - 0 40")
    turn = play_turn(StubEngine(win_prob=0.5, move="f7g7"), era, board, draw_streak=5)
    assert turn.move == chess.Move.from_uci("f7g7")
    assert turn.offers_draw is False


def test_resignation_takes_precedence_over_a_draw_offer():
    era = {"draws": {"band": 0.5, "streak": 1, "min_move": 1},
           "resign": {"threshold": 0.9, "streak": 1, "min_ply": 0}}
    turn = play_turn(StubEngine(win_prob=0.1), era, chess.Board())
    assert turn.resigns is True and turn.offers_draw is False


@pytest.mark.parametrize("win_prob,streak,move_no,expected", [
    (0.5, 5, 40, True),      # equal, patient enough, deep enough
    (0.9, 5, 40, False),     # winning — no thanks
    (0.5, 1, 40, False),     # hasn't been equal for long enough
    (0.5, 5, 10, False),     # too early in the game
    (None, 5, 40, False),    # no evaluation available at all
])
def test_would_accept_draw(win_prob, streak, move_no, expected):
    era = {"draws": {"band": 0.1, "streak": 2, "min_move": 30}}
    assert would_accept_draw(era, win_prob, streak, move_no) is expected


def test_one_evaluation_per_turn():
    """The engine is the expensive part: exactly one forward pass per turn."""
    engine = StubEngine()
    play_turn(engine, ROMANTIC, chess.Board())
    assert engine.calls == 1
