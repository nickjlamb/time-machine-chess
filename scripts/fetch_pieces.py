#!/usr/bin/env python3
"""Download era piece sets (SVG) from the lichess-org/lila repository.

    python3 scripts/fetch_pieces.py

Sets used per era:
  romantic  -> merida  (Armando Hernandez Marroquin)
  classical -> cburnett (served by python-chess already; not downloaded)
  soviet    -> alpha   (Eric Bentzen)

Files land in frontend/pieces/{set}/{code}.svg and are committed to the repo
so deployments include them. See README for attribution/licenses.
"""
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BASE = "https://raw.githubusercontent.com/lichess-org/lila/master/public/piece"
SETS = ["merida", "alpha"]
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
