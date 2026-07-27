#!/usr/bin/env python3
"""Download era piece sets (SVG) from the lichess-org/lila repository.

    python3 scripts/fetch_pieces.py

Sets used per era — each era gets the diagram style of its own time:
  romantic  -> merida  (classic 19th-century book diagrams; A. H. Marroquin)
  classical -> leipzig (early-20th-century German print style)
  soviet    -> alpha   (the Informator-era diagram font; Eric Bentzen)
  digital   -> pixel   (1990s computer chess, in actual pixels)
  modern    -> cburnett (the lichess default — the literal look of 2010s
               online chess; served by python-chess already, not downloaded)

Files land in frontend/pieces/{set}/{code}.svg and are committed to the repo
so deployments include them. After fetching new sets, check lila's COPYING.md
for their authors/licenses and extend the README attribution section.
"""
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BASE = "https://raw.githubusercontent.com/lichess-org/lila/master/public/piece"
SETS = ["merida", "alpha", "leipzig", "pixel"]
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
        with urllib.request.urlopen(url, timeout=15) as r:
            dest.write_bytes(r.read())
        print(f"  ok   {piece_set}/{code}.svg")
print("Done. Commit frontend/pieces/ so deployments include the sets.")
