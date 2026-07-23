#!/usr/bin/env python3
"""Split a large PGN database into era corpora by game date.

Streams the file (no full parse — header-only scan), so it handles
multi-GB databases. Usage:

    python scripts/filter_eras.py data/master_games.pgn
    python scripts/filter_eras.py data/first_half.pgn data/second_half.pgn --only modern

CAUTION: era output files are rewritten from scratch. When adding one new
era from a source file that only covers its window, pass --only so the
other eras' existing corpora are left untouched.
"""
import argparse
import re
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


def main(pgn_paths, only=None):
    eras, pipeline = load_eras()
    if only:
        unknown = set(only) - set(eras)
        if unknown:
            raise SystemExit(f"Unknown era(s) in --only: {sorted(unknown)}")
        eras = {k: v for k, v in eras.items() if k in only}
    out_dir = ROOT / "data" / "eras"
    out_dir.mkdir(parents=True, exist_ok=True)
    outs = {era: open(out_dir / f"{era}.pgn", "wb") for era in eras}
    counts = {era: 0 for era in eras}
    skipped = {"no_date": 0, "out_of_range": 0, "too_short": 0, "era_full": 0}

    total = 0
    for idx, pgn_path in enumerate(pgn_paths):
        # Spread the per-era cap across source files, so an era fed from two
        # half-decade files samples its whole window instead of filling the
        # cap from the first file alone.
        budget = pipeline["max_games_per_era"] * (idx + 1) // len(pgn_paths)
        game = []
        with open(pgn_path, "rb") as f:
            for line in f:
                if line.startswith(b"[Event ") and game:
                    total += process(b"".join(game), eras, pipeline, outs, counts, skipped, budget)
                    game = []
                game.append(line)
            if game:
                total += process(b"".join(game), eras, pipeline, outs, counts, skipped, budget)

    for fh in outs.values():
        fh.close()
    print(f"Scanned {total} games")
    for era, n in counts.items():
        print(f"  {era:<12} {n:>9} games -> data/eras/{era}.pgn")
    print(f"Skipped: {skipped}")


def process(game_bytes, eras, pipeline, outs, counts, skipped, budget=None):
    m = DATE_RE.search(game_bytes)
    if not m:
        skipped["no_date"] += 1
        return 1
    era = era_for_year(int(m.group(1)), eras)
    if era is None:
        skipped["out_of_range"] += 1
        return 1
    if counts[era] >= (budget if budget is not None else pipeline["max_games_per_era"]):
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
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("pgn", nargs="+", help="one or more source PGN files")
    p.add_argument("--only", help="comma-separated era ids to (re)build; "
                                  "other eras' files are left untouched")
    a = p.parse_args()
    main(a.pgn, only=a.only.split(",") if a.only else None)
