"""Regenerate the static site-wide Open Graph card (frontend/img/og.png).

Every page's <meta property="og:image"> points at /img/og.png; this paints it
from the era portraits so link unfurls show the five eras. Run after changing
portraits, era names, or the house palette:

    python scripts/make_og.py
"""
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from backend.og import render_site_card  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent

if __name__ == "__main__":
    cfg = yaml.safe_load((ROOT / "config" / "eras.yaml").read_text())
    out = ROOT / "frontend" / "img" / "og.png"
    render_site_card(cfg["eras"]).save(out, "PNG", optimize=True)
    print(f"wrote {out} ({out.stat().st_size // 1024} KB)")
