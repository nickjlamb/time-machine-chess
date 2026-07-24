#!/usr/bin/env python3
"""Probe every era model's move distribution in one position — receipts for
"why did the bot play that?" questions.

    python3 scripts/probe_position.py --moves "e4 e5 Nc3 Nf6 f4"
    python3 scripts/probe_position.py --fen "<any FEN>" --top 8
    python3 scripts/probe_position.py --moves "e4 e5 f4" --era romantic

Prints each era's top moves with probabilities (the raw model distribution —
serving adds temperature on top: full diversity for the first 10 plies, then
sharpened). Era list comes from config/eras.yaml. Runs with heuristic engines
where checkpoints are absent; use the Mac with real models for real answers.
"""
import argparse
import sys
from pathlib import Path

import chess
import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backend.app import get_engine  # noqa: E402

ERAS = list(yaml.safe_load((ROOT / "config" / "eras.yaml").read_text())["eras"])


def build_board(moves: str | None, fen: str | None) -> chess.Board:
    if fen:
        return chess.Board(fen)
    board = chess.Board()
    for san in (moves or "").replace(",", " ").split():
        board.push_san(san)
    return board


def main(moves, fen, eras, top):
    board = build_board(moves, fen)
    print(f"Position: {board.fen()}")
    print(f"{'White' if board.turn else 'Black'} to move\n")
    for era in eras:
        probs = get_engine(era).move_probs(board)
        ranked = sorted(probs.items(), key=lambda kv: -kv[1])[:top]
        line = "  ".join(f"{board.san(chess.Move.from_uci(u))} {100*p:.1f}%"
                         for u, p in ranked)
        print(f"{era:<12} {line}")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--moves", help='SAN moves from the start, e.g. "e4 e5 Nc3 Nf6 f4"')
    p.add_argument("--fen", help="or a FEN")
    p.add_argument("--era", action="append", choices=ERAS,
                   help="probe only this era (repeatable); default all")
    p.add_argument("--top", type=int, default=6, help="moves to show per era")
    a = p.parse_args()
    if not a.moves and not a.fen:
        p.error("provide --moves or --fen")
    main(a.moves, a.fen, a.era or ERAS, a.top)
