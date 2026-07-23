#!/usr/bin/env python3
"""Compare self-play era-bot games against the historical corpora.

Computes identical metrics on both sources (apples-to-apples, move-sequence
based — no reliance on ECO tags):
  - King's Gambit rate (1.e4 e5 2.f4), Queen's Gambit rate (1.d4 d5 2.c4)
  - first-move distribution, draw rate, avg game length, capture rate

    python3 scripts/analyze_selfplay.py            # all eras
    python3 scripts/analyze_selfplay.py --corpus-sample 400

Writes validation/results.json (consumed by the validation page).
"""
import argparse
import json
import random
from pathlib import Path

import chess
import chess.pgn
import yaml

ROOT = Path(__file__).resolve().parent.parent
ERAS = list(yaml.safe_load((ROOT / "config" / "eras.yaml").read_text())["eras"])


def game_metrics(game):
    board = game.board()
    moves = list(game.mainline_moves())
    if len(moves) < 4:
        return None
    ucis = [m.uci() for m in moves[:4]]
    kings_gambit = ucis[:3] == ["e2e4", "e7e5", "f2f4"]
    queens_gambit = ucis[:3] == ["d2d4", "d7d5", "c2c4"]
    captures = 0
    for m in moves:
        if board.is_capture(m):
            captures += 1
        board.push(m)
    result = game.headers.get("Result", "*")
    return {
        "first": ucis[0],
        "kg": kings_gambit,
        "qg": queens_gambit,
        "plies": len(moves),
        "capture_rate": captures / len(moves),
        "draw": result == "1/2-1/2",
    }


def iter_sampled_games(pgn_path, sample):
    """Yield up to `sample` games, uniformly sampled by byte offset."""
    offsets = []
    with open(pgn_path, "rb") as f:
        pos = 0
        for line in f:
            if line.startswith(b"[Event "):
                offsets.append(pos)
            pos += len(line)
    random.seed(42)
    if sample and len(offsets) > sample:
        offsets = sorted(random.sample(offsets, sample))
    with open(pgn_path, encoding="utf-8", errors="replace") as f:
        for off in offsets:
            f.seek(off)
            g = chess.pgn.read_game(f)
            if g:
                yield g


def summarize(pgn_path, sample=None):
    stats = [m for g in iter_sampled_games(pgn_path, sample) if (m := game_metrics(g))]
    n = len(stats)
    if n == 0:
        return None
    firsts = {}
    for s in stats:
        firsts[s["first"]] = firsts.get(s["first"], 0) + 1
    return {
        "games": n,
        "kings_gambit_pct": round(100 * sum(s["kg"] for s in stats) / n, 2),
        "queens_gambit_pct": round(100 * sum(s["qg"] for s in stats) / n, 2),
        "draw_pct": round(100 * sum(s["draw"] for s in stats) / n, 2),
        "avg_plies": round(sum(s["plies"] for s in stats) / n, 1),
        "capture_rate": round(sum(s["capture_rate"] for s in stats) / n, 3),
        "first_moves": {k: round(100 * v / n, 1)
                        for k, v in sorted(firsts.items(), key=lambda kv: -kv[1])[:5]},
    }


def main(corpus_sample):
    results = {}
    for era in ERAS:
        corpus = ROOT / "data" / "eras" / f"{era}.pgn"
        selfplay = ROOT / "validation" / "selfplay" / f"{era}.pgn"
        results[era] = {
            "historical": summarize(corpus, corpus_sample) if corpus.exists() else None,
            "bot": summarize(selfplay) if selfplay.exists() else None,
        }
        print(f"\n=== {era} ===")
        for src in ("historical", "bot"):
            r = results[era][src]
            print(f"  {src:>10}: " + (json.dumps(r) if r else "no data"))
    out = ROOT / "validation" / "results.json"
    json.dump(results, open(out, "w"), indent=2)
    print(f"\nWrote {out}")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--corpus-sample", type=int, default=400)
    main(p.parse_args().corpus_sample)
