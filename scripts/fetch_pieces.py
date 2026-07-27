#!/usr/bin/env python3
"""Download era piece sets (SVG) from the lichess-org/lila repository.

    python3 scripts/fetch_pieces.py

Sets used per era — each era gets the diagram style of its own time:
  romantic  -> merida   (classic 19th-century book diagrams; A. H. Marroquin)
  classical -> leipzig  (early-20th-century German print style)
  soviet    -> dubrovny (the Dubrovnik 1950 Olympiad set — THE Soviet-era
               tournament design)
  digital   -> alpha    (Eric Bentzen's font: the literal look of 1990s
               ChessBase/computer chess publishing)
  modern    -> cburnett (the lichess default — the look of 2010s online
               chess; served by python-chess already, not downloaded)

Files land in frontend/pieces/{set}/{code}.svg and are committed to the repo
so deployments include them. After fetching new sets, check lila's COPYING.md
for their authors/licenses and extend the README attribution section.
"""
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BASE = "https://raw.githubusercontent.com/lichess-org/lila/master/public/piece"
SETS = ["merida", "alpha", "leipzig", "dubrovny"]
CODES = [c + p for c in "wb" for p in "KQRBNP"]

for piece_set in SETS:
    out_dir = ROOT / "frontend" / "pieces" / piece_set
    out_dir.mkdir(parents=True, exist_ok=True)
    for code in CODES:
        url = f"{BASE}/{piece_set}/{code}.svg"
        dest = out_dir / f"{code}.svg"
        if dest.exists():
            print(f"  skip {piece_set}/{code}.svg (exists)")
            continue
        try:
            with urllib.request.urlopen(url, timeout=15) as r:
                dest.write_bytes(r.read())
            print(f"  ok   {piece_set}/{code}.svg")
        except Exception as exc:
            # A bad set name shouldn't kill the run — the frontend falls back
            # to the cburnett API for any missing file.
            print(f"  FAIL {piece_set}/{code}.svg ({exc})")
print("Done. Commit frontend/pieces/ so deployments include the sets.")
