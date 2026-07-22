#!/usr/bin/env python3
"""Download the Lichess "piano" sound set (Enigmahack, AGPLv3+).

    python3 scripts/fetch_sounds.py

Note: Lichess's *standard* sounds are non-free (see lila/COPYING.md) — the
piano/nes/sfx/futuristic sets by Enigmahack are the properly licensed ones.
Files land in frontend/sounds/ and are committed to the repo. The app falls
back to synthesized Web Audio sounds when files are missing.
"""
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BASE = "https://raw.githubusercontent.com/lichess-org/lila/master/public/sound/piano"
NAMES = ["Move", "Capture", "Check", "Victory", "Defeat", "Draw", "GenericNotify"]

out_dir = ROOT / "frontend" / "sounds"
out_dir.mkdir(parents=True, exist_ok=True)

for name in NAMES:
    if any((out_dir / f"{name}.{ext}").exists() for ext in ("mp3", "ogg")):
        print(f"  skip {name} (exists)")
        continue
    for ext in ("mp3", "ogg"):
        try:
            with urllib.request.urlopen(f"{BASE}/{name}.{ext}", timeout=15) as r:
                (out_dir / f"{name}.{ext}").write_bytes(r.read())
            print(f"  ok   {name}.{ext}")
            break
        except urllib.error.HTTPError:
            continue
    else:
        print(f"  --   {name}: not in this set (synth fallback will cover it)")
print("Done. Commit frontend/sounds/ so deployments include them.")
