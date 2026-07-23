#!/usr/bin/env python3
"""Download the trained era models + Maia-2 pretrained base (~520MB total).

    python3 scripts/fetch_models.py

Without these the app still runs, using simple heuristic bots. With them you
get the real thing: era-fine-tuned Maia-2 models validated against the
historical record (see validation/baselines.md).
"""
import urllib.error
import urllib.request
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
RELEASE = "https://github.com/nickjlamb/time-machine-chess/releases/download/weights-v1"
ERAS = list(yaml.safe_load((ROOT / "config" / "eras.yaml").read_text())["eras"])
FILES = {f"models/{era}.pt": f"{RELEASE}/{era}.pt" for era in ERAS}
FILES["maia2_models/rapid_model.pt"] = f"{RELEASE}/rapid_model.pt"

for rel_path, url in FILES.items():
    dest = ROOT / rel_path
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        print(f"  skip {rel_path} (exists)")
        continue
    print(f"  downloading {rel_path} ...")
    try:
        urllib.request.urlretrieve(url, dest)
    except urllib.error.HTTPError as e:
        # A new era's weights may not be in the release yet — the app falls
        # back to its heuristic engine for that era, so warn and continue.
        print(f"  [warn] {rel_path}: {e} — not in the release yet? "
              "The app will use the heuristic engine for this era.")
print("Done — restart the server to load the era models.")
