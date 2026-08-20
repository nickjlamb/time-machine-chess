"""One era turn: pick a move, then decide the era's manners about it.

This is *the* move-selection recipe — the thing that makes a Time-Machine
Chess game a Time-Machine Chess game. It used to live inside the /api/play
handler; it lives here so the website (backend/app.py) and the Lichess BOT
accounts (lichess_bot/engine.py) play demonstrably identically rather than
"identically" by copy-paste drift.

The pieces:
  - the move comes from the era engine's own policy, sampled at temperature
    1.0 for the first 10 plies and 0.6 after (inside Maia2Engine — opening
    character lives in opening *diversity*, so we don't sharpen there);
  - resignation manners (backend/manners.py) get first refusal: an era that
    is ready to resign resigns instead of moving;
  - draw agreement (backend/draws.py) rides along with the move, which is
    proper etiquette and, on Lichess, is also how you accept an offer.

Both social rules are streak-based and the counters are caller-owned: the
website is stateless so the browser carries them, the Lichess bot keeps them
per game on the engine instance. Same rules, same numbers, different carrier.
"""
from dataclasses import dataclass

import chess

from backend.draws import in_band, update_streak, wants_draw
from backend.manners import update_resign_streak, wants_to_resign


@dataclass
class EraTurn:
    """What the era decided to do with its turn."""
    move: chess.Move | None      # None only if the position was already over
    win_prob: float | None       # White's perspective; None if the engine has no eval head
    draw_streak: int
    resign_streak: int
    offers_draw: bool
    resigns: bool


def play_turn(engine, era_cfg: dict, board: chess.Board,
              draw_streak: int = 0, resign_streak: int = 0) -> EraTurn:
    """Choose this era's move for `board` (side to move = the era), with manners.

    `engine` is any object from backend.engine_pool.get_engine; `era_cfg` is
    that era's block from config/eras.yaml. The board is not mutated.
    """
    draw_params = era_cfg.get("draws")
    resign_params = era_cfg.get("resign")

    if not ((draw_params or resign_params) and hasattr(engine, "pick_move_with_eval")):
        return EraTurn(move=engine.pick_move(board), win_prob=None,
                       draw_streak=draw_streak, resign_streak=resign_streak,
                       offers_draw=False, resigns=False)

    move, win_prob = engine.pick_move_with_eval(board)

    if resign_params:
        own = win_prob if board.turn == chess.WHITE else 1.0 - win_prob
        resign_streak = update_resign_streak(resign_streak, own, resign_params)
        if wants_to_resign(resign_streak, board.ply(), resign_params):
            # The era resigns rather than move — its manners, its era. The
            # move is carried anyway so callers can log what it would have played.
            return EraTurn(move=move, win_prob=win_prob, draw_streak=draw_streak,
                           resign_streak=resign_streak, offers_draw=False, resigns=True)

    offers_draw = False
    if draw_params:
        draw_streak = update_streak(draw_streak, win_prob, draw_params)
        offers_draw = wants_draw(draw_streak, board.fullmove_number, draw_params)
        if offers_draw:
            # Never offer a draw with a move that ends the game (mate, stalemate,
            # a repetition claim) — the offer would be absurd, or accepting it
            # would rob a won game.
            board.push(move)
            try:
                if board.is_game_over(claim_draw=True):
                    offers_draw = False
            finally:
                board.pop()

    return EraTurn(move=move, win_prob=win_prob, draw_streak=draw_streak,
                   resign_streak=resign_streak, offers_draw=offers_draw, resigns=False)


def would_accept_draw(era_cfg: dict, win_prob: float | None, draw_streak: int,
                      fullmove_number: int) -> bool:
    """The draw rule as a pure predicate, for callers that already have an
    evaluation in hand (the Lichess bot evaluates once per turn and reuses it).
    """
    draw_params = era_cfg.get("draws")
    if not draw_params or win_prob is None:
        return False
    return (in_band(win_prob, draw_params)
            and wants_draw(draw_streak, fullmove_number, draw_params))


def accepts_draw(engine, era_cfg: dict, board: chess.Board, draw_streak: int):
    """Would this era accept a draw offer right now? -> (accepted, win_prob).

    Same rule it offers by: the current evaluation is dead equal AND the
    carried streak is long enough AND the game is deep enough. The streak is
    NOT advanced here — only real moves advance it — so an opponent spamming
    the draw button can't manufacture agreement.
    """
    if not era_cfg.get("draws") or not hasattr(engine, "pick_move_with_eval"):
        return False, None
    _, win_prob = engine.pick_move_with_eval(board)
    return (would_accept_draw(era_cfg, win_prob, draw_streak, board.fullmove_number),
            win_prob)
