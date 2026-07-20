#!/usr/bin/env python3
"""Convert era PGN corpora into Maia-2 training rows.

Row format (matches maia2.main.MAIA2Dataset exactly):
    (fen, move_uci, elo_self_cat, elo_oppo_cat, active_win)
- Positions with Black to move are mirrored (board + move), per Maia-2 convention.
- active_win is from the active player's perspective: 1 win / 0 draw / -1 loss.
- Historical games mostly lack Elo tags, so all positions get a fixed nominal
  Elo category (NOMINAL_ELO). Use the same value at inference time.

Usage (run per era; a few minutes each on a laptop):
    python scripts/prepare_training.py romantic
    python scripts/prepare_training.py classical --max-games 12000
    python scripts/prepare_training.py soviet   --max-games 12000

Writes data/training/{era}.pkl
"""
import argparse
import pickle
import random
from pathlib import Path

import chess
import chess.pgn

from maia2.utils import create_elo_dict, get_all_possible_moves, map_to_category, mirror_move

ROOT = Path(__file__).resolve().parent.parent
NOMINAL_ELO = 1900  # fixed skill conditioning for historical games

RESULT_MAP = {"1-0": 1, "0-1": -1, "1/2-1/2": 0}


def main(era: str, max_games: int, seed: int):
    elo_dict = create_elo_dict()
    all_moves = set(get_all_possible_moves())
    elo_cat = map_to_category(NOMINAL_ELO, elo_dict)

    pgn_path = ROOT / "data" / "eras" / f"{era}.pgn"
    out_dir = ROOT / "data" / "training"
    out_dir.mkdir(parents=True, exist_ok=True)

    # Pass 1: index game offsets so we can sample games uniformly (files are date-sorted).
    offsets = []
    with open(pgn_path, "rb") as f:
        pos = 0
        for line in f:
            if line.startswith(b"[Event "):
                offsets.append(pos)
            pos += len(line)
    random.seed(seed)
    if len(offsets) > max_games:
        offsets = sorted(random.sample(offsets, max_games))
    print(f"{era}: {len(offsets)} games selected of {len(offsets)}+")

    rows, bad = [], 0
    with open(pgn_path, encoding="utf-8", errors="replace") as f:
        for i, off in enumerate(offsets):
            f.seek(off)
            game = chess.pgn.read_game(f)
            if game is None:
                bad += 1
                continue
            white_win = RESULT_MAP.get(game.headers.get("Result", "*"))
            if white_win is None:
                bad += 1
                continue
            board = game.board()
            for move in game.mainline_moves():
                if board.turn == chess.WHITE:
                    fen, uci, active_win = board.fen(), move.uci(), white_win
                else:
                    fen, uci, active_win = board.mirror().fen(), mirror_move(move.uci()), -white_win
                if uci in all_moves:
                    rows.append((fen, uci, elo_cat, elo_cat, active_win))
                try:
                    board.push(move)
                except (ValueError, AssertionError):
                    bad += 1
                    break
            if (i + 1) % 1000 == 0:
                print(f"  {i+1}/{len(offsets)} games -> {len(rows)} positions")

    out = out_dir / f"{era}.pkl"
    with open(out, "wb") as fh:
        pickle.dump(rows, fh)
    print(f"Wrote {len(rows)} positions to {out} ({bad} games skipped/broken)")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("era", choices=["romantic", "classical", "soviet"])
    p.add_argument("--max-games", type=int, default=10000,
                   help="cap per era so corpora are balanced (romantic has ~10.7k total)")
    p.add_argument("--seed", type=int, default=42)
    a = p.parse_args()
    main(a.era, a.max_games, a.seed)
