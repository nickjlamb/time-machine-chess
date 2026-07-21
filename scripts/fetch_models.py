#!/usr/bin/env python3
"""Download the trained era models + Maia-2 pretrained base (~520MB total).

    python3 scripts/fetch_models.py

Without these the app still runs, using simple heuristic bots. With them you
get the real thing: era-fine-tuned Maia-2 models validated against the
historical record (see validation/baselines.md).
"""
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RELEASE = "https://github.com/nickjlamb/time-machine-chess/releases/download/weights-v1"
FILES = {
    "models/romantic.pt": f"{RELEASE}/romantic.pt",
    "models/classical.pt": f"{RELEASE}/classical.pt",
    "models/soviet.pt": f"{RELEASE}/soviet.pt",
    "maia2_models/rapid_model.pt": f"{RELEASE}/rapid_model.pt",
}

for rel_path, url in FILES.items():
    dest = ROOT / rel_path
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        print(f"  skip {rel_path} (exists)")
        continue
    print(f"  downloading {rel_path} ...")
    urllib.request.urlretrieve(url, dest)
print("Done — restart the server to load the era models.")
