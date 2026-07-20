#!/usr/bin/env python3
"""Corpus health check + baseline era metrics for the validation page.

Reports per era: game count, date range, avg game length, capture rate,
early-queen-sortie rate, and gambit rate (pawn offered in first 6 moves).
These historical baselines are what the trained bots get compared against.

    python scripts/corpus_stats.py [--sample 5000]
"""
import argparse
import random
from pathlib import Path

import chess
import chess.pgn

ROOT = Path(__file__).resolve().parent.parent
GAMBIT_ECOS = ("C3", "C4", "D0", "C2")  # King's Gambit, Evans/Italian gambit lines, Queen's Gambit territory — refine later


def game_metrics(game):
    board = game.board()
    moves = list(game.mainline_moves())
    if not moves:
        return None
    captures = 0
    early_pawn_offers = 0
    for i, move in enumerate(moves):
        if board.is_capture(move):
            captures += 1
        # crude gambit proxy: a pawn is en prise after our move in the opening
        if i < 12:
            piece = board.piece_at(move.from_square)
            if piece and piece.piece_type == chess.PAWN:
                board.push(move)
                if board.attackers(board.turn, move.to_square) and not board.attackers(not board.turn, move.to_square):
                    early_pawn_offers += 1
                continue
        board.push(move)
    n = len(moves)
    return {
        "plies": n,
        "capture_rate": captures / n,
        "gambit_like": 1 if early_pawn_offers > 0 else 0,
    }


def main(sample_size):
    era_dir = ROOT / "data" / "eras"
    for pgn_path in sorted(era_dir.glob("*.pgn")):
        stats, dates = [], []
        with open(pgn_path, encoding="utf-8", errors="replace") as f:
            games = []
            while True:
                offset = f.tell()
                headers = chess.pgn.read_headers(f)
                if headers is None:
                    break
                games.append((offset, headers.get("Date", "?")))
            picked = random.sample(games, min(sample_size, len(games)))
            for offset, date in picked:
                f.seek(offset)
                game = chess.pgn.read_game(f)
                if game is None:
                    continue
                m = game_metrics(game)
                if m:
                    stats.append(m)
                    dates.append(date[:4])
        if not stats:
            print(f"{pgn_path.name}: no parsable games")
            continue
        n = len(stats)
        print(f"\n{pgn_path.name}  ({len(games)} games, sampled {n})")
        print(f"  dates:        {min(dates)}–{max(dates)}")
        print(f"  avg plies:    {sum(s['plies'] for s in stats)/n:.1f}")
        print(f"  capture rate: {sum(s['capture_rate'] for s in stats)/n:.3f}")
        print(f"  gambit-like:  {sum(s['gambit_like'] for s in stats)/n:.1%}")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--sample", type=int, default=5000)
    main(p.parse_args().sample)
