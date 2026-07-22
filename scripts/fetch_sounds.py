#!/usr/bin/env python3
"""Download the freely-licensed Lichess sound sets (Enigmahack, AGPLv3+).

    python3 scripts/fetch_sounds.py

Fetches piano, nes, sfx and futuristic — the four sets with proper licenses
(Lichess's *standard* sounds are non-free, see lila/COPYING.md). Files land in
frontend/sounds/{set}/ and are committed. Compare them at /soundlab in the app.
"""
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BASE = "https://raw.githubusercontent.com/lichess-org/lila/master/public/sound"
SETS = ["piano", "nes", "sfx", "futuristic"]
NAMES = ["Move", "Capture", "Check", "Victory", "Defeat", "Draw"]

for sound_set in SETS:
    out_dir = ROOT / "frontend" / "sounds" / sound_set
    out_dir.mkdir(parents=True, exist_ok=True)
    for name in NAMES:
        if any((out_dir / f"{name}.{ext}").exists() for ext in ("mp3", "ogg")):
            print(f"  skip {sound_set}/{name} (exists)")
            continue
        for ext in ("mp3", "ogg"):
            try:
                with urllib.request.urlopen(f"{BASE}/{sound_set}/{name}.{ext}", timeout=15) as r:
                    (out_dir / f"{name}.{ext}").write_bytes(r.read())
                print(f"  ok   {sound_set}/{name}.{ext}")
                break
            except urllib.error.HTTPError:
                continue
        else:
            print(f"  --   {sound_set}/{name}: not in set (synth fallback covers it)")

# tidy the old flat layout if present (pre-set-folders version of this script)
for old in (ROOT / "frontend" / "sounds").glob("*.mp3"):
    old.rename(ROOT / "frontend" / "sounds" / "piano" / old.name)
    print(f"  moved {old.name} -> piano/")
print("Done. Open /soundlab to compare, commit frontend/sounds/ when happy.")
