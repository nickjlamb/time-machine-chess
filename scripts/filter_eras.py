#!/usr/bin/env python3
"""Split a large PGN database into era corpora by game date.

Streams the file (no full parse — header-only scan), so it handles
multi-GB databases. Usage:

    python scripts/filter_eras.py data/master_games.pgn
"""
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
DATE_RE = re.compile(rb'\[Date "(\d{4})')


def load_eras():
    cfg = yaml.safe_load((ROOT / "config" / "eras.yaml").read_text())
    eras = {k: tuple(v["years"]) for k, v in cfg["eras"].items()}
    return eras, cfg["pipeline"]


def era_for_year(year, eras):
    for era, (start, end) in eras.items():
        if start <= year <= end:
            return era
    return None


def approx_move_count(game_bytes):
    # Cheap proxy: count move-number tokens like "10." in the movetext.
    return len(re.findall(rb"\d+\.", game_bytes))


def main(pgn_path):
    eras, pipeline = load_eras()
    out_dir = ROOT / "data" / "eras"
    out_dir.mkdir(parents=True, exist_ok=True)
    outs = {era: open(out_dir / f"{era}.pgn", "wb") for era in eras}
    counts = {era: 0 for era in eras}
    skipped = {"no_date": 0, "out_of_range": 0, "too_short": 0, "era_full": 0}

    game, total = [], 0
    with open(pgn_path, "rb") as f:
        for line in f:
            if line.startswith(b"[Event ") and game:
                total += process(b"".join(game), eras, pipeline, outs, counts, skipped)
                game = []
            game.append(line)
        if game:
            total += process(b"".join(game), eras, pipeline, outs, counts, skipped)

    for fh in outs.values():
        fh.close()
    print(f"Scanned {total} games")
    for era, n in counts.items():
        print(f"  {era:<12} {n:>9} games -> data/eras/{era}.pgn")
    print(f"Skipped: {skipped}")


def process(game_bytes, eras, pipeline, outs, counts, skipped):
    m = DATE_RE.search(game_bytes)
    if not m:
        skipped["no_date"] += 1
        return 1
    era = era_for_year(int(m.group(1)), eras)
    if era is None:
        skipped["out_of_range"] += 1
        return 1
    if counts[era] >= pipeline["max_games_per_era"]:
        skipped["era_full"] += 1
        return 1
    if approx_move_count(game_bytes) < pipeline["min_moves"]:
        skipped["too_short"] += 1
        return 1
    outs[era].write(game_bytes)
    if not game_bytes.endswith(b"\n\n"):
        outs[era].write(b"\n\n")
    counts[era] += 1
    return 1


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(sys.argv[1])
