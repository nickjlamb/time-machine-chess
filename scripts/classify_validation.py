#!/usr/bin/env python3
"""Validate the era classifier: confusion matrix on held-out historical games.

The receipt that makes the classifier honest — 1880s games should come out
Romantic and 1970s games Soviet. For each era we sample games from
data/eras/{era}.pgn that were NOT in the training subset (the training
selection is reproduced with its seed and per-era game cap, then excluded),
classify each game blind, and count where it lands. Results are written to
validation/classifier.json and rendered on /validation.

Single games are noisy by design — we also report accuracy when diagnosing
batches of games together (the "~20 games is a diagnosis" claim, measured).

Run on a machine with the trained checkpoints (heuristic engines will run the
plumbing but their confusion matrix is meaningless):

    python3 scripts/classify_validation.py
    python3 scripts/classify_validation.py --games 40 --positions-per-game 30
    python3 scripts/classify_validation.py --train-max-games classical=12000,soviet=12000

--train-max-games must match what prepare_training.py was run with per era
(default 10000), or the held-out exclusion reproduces the wrong subset.
"""
import argparse
import json
import random
import sys
from pathlib import Path

import chess.pgn
import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backend.app import get_engine  # noqa: E402  (heuristic fallback included)
from backend.classifier import sample_positions, score_positions  # noqa: E402

ERAS = list(yaml.safe_load((ROOT / "config" / "eras.yaml").read_text())["eras"])


def game_offsets(pgn_path):
    offsets = []
    with open(pgn_path, "rb") as f:
        pos = 0
        for line in f:
            if line.startswith(b"[Event "):
                offsets.append(pos)
            pos += len(line)
    return offsets


def held_out_offsets(pgn_path, n_games, train_max, train_seed, seed):
    """Sample n_games offsets excluding the training subset (reproduced with
    the same seed+cap sampling as scripts/prepare_training.py)."""
    offsets = game_offsets(pgn_path)
    random.seed(train_seed)
    trained = set(random.sample(offsets, train_max)) if len(offsets) > train_max else set(offsets)
    pool = [o for o in offsets if o not in trained]
    if not pool:
        print(f"  [warn] {pgn_path.name}: no held-out games (corpus <= training cap)")
        return []
    random.seed(seed)
    if len(pool) > n_games:
        pool = sorted(random.sample(pool, n_games))
    return pool


def read_games(pgn_path, offsets):
    games = []
    with open(pgn_path, encoding="utf-8", errors="replace") as f:
        for off in offsets:
            f.seek(off)
            g = chess.pgn.read_game(f)
            if g is not None:
                games.append(g)
    return games


def main(games_per_era, positions_per_game, seed, train_seed, train_max_games,
         batch_size):
    # ---- sample held-out games and their positions, per true era ----
    positions, spans = [], {}   # spans[era] = list of (start, end) per game
    for era in ERAS:
        corpus = ROOT / "data" / "eras" / f"{era}.pgn"
        if not corpus.exists():
            print(f"[skip] {era}: {corpus} missing (run filter_eras.py)")
            continue
        train_max = train_max_games.get(era, train_max_games.get("*", 10000))
        offs = held_out_offsets(corpus, games_per_era, train_max, train_seed, seed)
        games = read_games(corpus, offs)
        spans[era] = []
        for g in games:
            # Whole historical games: both players belong to the era.
            pos = sample_positions([g], both_colors=True,
                                   max_positions=positions_per_game)
            if len(pos) >= 5:
                spans[era].append((len(positions), len(positions) + len(pos)))
                positions.extend(pos)
        print(f"{era}: {len(spans[era])} held-out games, "
              f"{sum(b - a for a, b in spans[era])} positions")
    if not spans:
        raise SystemExit("No era corpora found under data/eras/")

    # ---- score every position under every era model (era-outer loop:  ----
    # ---- each checkpoint loads once, scores everything, gets evicted) ----
    logliks = {}
    for era in ERAS:
        print(f"scoring under {era} …")
        logliks[era] = score_positions(get_engine(era), positions)

    # ---- single-game confusion matrix ----
    confusion = {t: {p: 0 for p in ERAS} for t in spans}
    game_scores = {t: [] for t in spans}   # per game: {era: total loglik}
    for true_era, game_spans in spans.items():
        for a, b in game_spans:
            totals = {era: sum(logliks[era][a:b]) for era in ERAS}
            game_scores[true_era].append(totals)
            confusion[true_era][max(totals, key=totals.get)] += 1

    # ---- batched diagnosis (sum evidence across batch_size games) ----
    batch_confusion = {t: {p: 0 for p in ERAS} for t in spans}
    for true_era, scores in game_scores.items():
        for i in range(0, len(scores) - batch_size + 1, batch_size):
            batch = scores[i:i + batch_size]
            totals = {era: sum(s[era] for s in batch) for era in ERAS}
            batch_confusion[true_era][max(totals, key=totals.get)] += 1

    def acc(matrix):
        right = sum(matrix[t][t] for t in matrix)
        total = sum(sum(row.values()) for row in matrix.values())
        return round(right / total, 4) if total else None

    results = {
        "games_per_era": games_per_era,
        "positions_per_game": positions_per_game,
        "batch_size": batch_size,
        "confusion": confusion,
        "accuracy": {t: (round(confusion[t][t] / n, 4) if (n := sum(confusion[t].values())) else None)
                     for t in confusion},
        "overall_accuracy": acc(confusion),
        "batch_confusion": batch_confusion,
        "batch_overall_accuracy": acc(batch_confusion),
        "chance": round(1 / len(ERAS), 4),
    }

    header = "true \\ predicted"
    print(f"\n{header:<18}" + "".join(f"{p:>11}" for p in ERAS))
    for t in confusion:
        print(f"{t:<18}" + "".join(f"{confusion[t][p]:>11}" for p in ERAS))
    print(f"\nsingle-game accuracy: {results['overall_accuracy']} "
          f"(chance {results['chance']})")
    print(f"{batch_size}-game-batch accuracy: {results['batch_overall_accuracy']}")

    out = ROOT / "validation" / "classifier.json"
    json.dump(results, open(out, "w"), indent=2)
    print(f"Wrote {out}")


def parse_train_max(text):
    """'classical=12000,soviet=12000' -> {'classical': 12000, ...};
    a bare number sets the default for every era."""
    out = {}
    for part in text.split(","):
        part = part.strip()
        if not part:
            continue
        if "=" in part:
            era, n = part.split("=")
            out[era.strip()] = int(n)
        else:
            out["*"] = int(part)
    return out


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--games", type=int, default=40, help="held-out games per era")
    p.add_argument("--positions-per-game", type=int, default=30)
    p.add_argument("--seed", type=int, default=7, help="held-out sampling seed")
    p.add_argument("--train-seed", type=int, default=42,
                   help="must match prepare_training.py's --seed")
    p.add_argument("--train-max-games", default="10000",
                   help="per-era training caps to exclude, e.g. "
                        "'classical=12000,soviet=12000' (default 10000 for all)")
    p.add_argument("--batch-size", type=int, default=10,
                   help="games per batched diagnosis")
    a = p.parse_args()
    main(a.games, a.positions_per_game, a.seed, a.train_seed,
         parse_train_max(a.train_max_games), a.batch_size)
