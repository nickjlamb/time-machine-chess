#!/usr/bin/env python3
"""Day-4 sanity gate: are the era engines distinguishable?

Runs each era engine on test positions with a tactical/positional tension
(sacrifice available vs. quiet consolidation) and prints each engine's move
distribution over 50 samples. PASS criterion: romantic clearly prefers the
aggressive option more often than soviet does. Works on the heuristic
placeholders today; the real gate is running it on the Maia-2 checkpoints.

    python -m scripts.sanity_gate   (from repo root)
"""
from collections import Counter
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import chess
import yaml
from backend.app import ENGINES  # noqa: E402  (reuses engine construction)

# FEN, description, the aggressive move to watch for
POSITIONS = [
    ("r1bqkb1r/pppp1ppp/2n2n2/4p3/2B1P3/5N2/PPPP1PPP/RNBQK2R w KQkq - 4 4",
     "Italian: Ng5!? raid vs quiet d3/castle", "f3g5"),
    ("r1bqk2r/pppp1ppp/2n2n2/2b1p3/2B1P3/2P2N2/PP1P1PPP/RNBQK2R w KQkq - 4 5",
     "Evans-style: b4!? pawn offer vs d3", "b2b4"),
    ("rnbqkb1r/ppp2ppp/3p1n2/4p3/2B1P3/2N2N2/PPPP1PPP/R1BQK2R w KQkq - 0 5",
     "Philidor: Nxe5!? sac ideas vs O-O", "f3e5"),
]
SAMPLES = 50


def main():
    for fen, desc, aggressive in POSITIONS:
        print(f"\n{desc}\n  aggressive move: {aggressive}")
        for era, engine in ENGINES.items():
            board = chess.Board(fen)
            picks = Counter(engine.pick_move(board).uci() for _ in range(SAMPLES))
            agg_pct = picks.get(aggressive, 0) / SAMPLES
            top = ", ".join(f"{m}×{c}" for m, c in picks.most_common(3))
            print(f"  {era:<10} aggressive {agg_pct:>4.0%}   top: {top}")
    print("\nGATE: romantic's aggressive % should clearly exceed soviet's on most positions.")


if __name__ == "__main__":
    main()
