#!/usr/bin/env python3
"""Generate self-play games from an era model for validation.

    python3 scripts/selfplay.py romantic --games 150
    python3 scripts/selfplay.py classical --games 150
    python3 scripts/selfplay.py soviet --games 150

Appends to validation/selfplay/{era}.pgn and resumes if interrupted
(counts existing games first). ~5-10s per game on CPU, faster on MPS.
"""
import argparse
import datetime
import sys
from pathlib import Path

import chess
import chess.pgn
import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from backend.draws import update_streak, wants_draw  # noqa: E402
from backend.engines import Maia2Engine  # noqa: E402

CFG = yaml.safe_load((ROOT / "config" / "eras.yaml").read_text())

MAX_PLIES = 300
RESIGN_THRESHOLD = 0.03   # White resigns below this white-win-prob (Black above 1-x)
RESIGN_STREAK = 4         # ... if it persists for this many consecutive evaluations


def play_game(engine: Maia2Engine, draw_params: dict = None) -> chess.pgn.Game:
    """Self-play with resignation and draw-agreement adjudication (humans resign
    lost positions and agree dead-equal draws; policy nets grind to the end).

    Both "players" are the same engine, so mutual agreement collapses to one
    check: the era agrees a draw once the evaluation has sat in its dead-equal
    band for its streak length past its minimum move (backend/draws.py — the
    same rule live play uses).
    """
    board = chess.Board()
    white_low = black_low = equal_streak = 0
    resigned = None
    agreed = False
    while not board.is_game_over(claim_draw=True) and board.ply() < MAX_PLIES:
        move, white_win = engine.pick_move_with_eval(board)
        white_low = white_low + 1 if white_win < RESIGN_THRESHOLD else 0
        black_low = black_low + 1 if white_win > 1 - RESIGN_THRESHOLD else 0
        if board.ply() > 20 and white_low >= RESIGN_STREAK:
            resigned = "0-1"
            break
        if board.ply() > 20 and black_low >= RESIGN_STREAK:
            resigned = "1-0"
            break
        if draw_params:
            equal_streak = update_streak(equal_streak, white_win, draw_params)
            if wants_draw(equal_streak, board.fullmove_number, draw_params):
                agreed = True
                break
        board.push(move)
    game = chess.pgn.Game.from_board(board)
    result = resigned or ("1/2-1/2" if agreed else board.result(claim_draw=True))
    game.headers["Result"] = "1/2-1/2" if result == "*" else result  # adjudicate marathons as draws
    if resigned:
        game.headers["Termination"] = "resignation (adjudicated)"
    elif agreed:
        game.headers["Termination"] = "draw agreed (adjudicated)"
    elif result == "*":
        game.headers["Adjudicated"] = "draw at %d plies" % MAX_PLIES
    return game


def main(era: str, n_games: int, temperature: float):
    out_dir = ROOT / "validation" / "selfplay"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{era}.pgn"
    done = out.read_text().count("[Event ") if out.exists() else 0
    if done >= n_games:
        print(f"{era}: already have {done} games")
        return
    print(f"{era}: {done} existing, generating {n_games - done} more")

    engine = Maia2Engine(str(ROOT / "models" / f"{era}.pt"), temperature=temperature)
    draw_params = CFG["eras"][era].get("draws")
    with open(out, "a") as fh:
        for i in range(done, n_games):
            game = play_game(engine, draw_params)
            game.headers["Event"] = f"Time-Machine self-play ({era})"
            game.headers["Date"] = datetime.date.today().strftime("%Y.%m.%d")
            game.headers["White"] = game.headers["Black"] = f"maia2-{era}"
            print(game, file=fh, end="\n\n")
            fh.flush()
            if (i + 1) % 10 == 0:
                print(f"  {i+1}/{n_games}")
    print(f"Done: {out}")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("era", choices=["romantic", "classical", "soviet"])
    p.add_argument("--games", type=int, default=150)
    p.add_argument("--temperature", type=float, default=0.6,
                   help="must match backend serving temperature for honest validation")
    a = p.parse_args()
    main(a.era, a.games, a.temperature)
