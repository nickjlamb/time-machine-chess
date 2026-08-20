"""Era config + the lazy engine cache, shared by every process that plays.

Pulled out of backend/app.py so non-HTTP callers — the Lichess bot
(lichess_bot/engine.py), scripts — can get the same engines without importing
FastAPI and standing up the web app.

Era models are ~700MB resident each, so we keep at most MAX_LOADED_MODELS
loaded and evict least-recently-used. A one-era process (the Lichess bot)
should set MAX_LOADED_MODELS=1.
"""
import os
from collections import OrderedDict
from pathlib import Path
from threading import Lock

import yaml

from backend.engines import HeuristicEraEngine, Maia2Engine

ROOT = Path(__file__).resolve().parent.parent
CFG = yaml.safe_load((ROOT / "config" / "eras.yaml").read_text())

MAX_LOADED_MODELS = int(os.environ.get("MAX_LOADED_MODELS", "3"))
_maia_cache: "OrderedDict[str, Maia2Engine]" = OrderedDict()
_heuristics = {era_id: HeuristicEraEngine(era.get("style", {}))
               for era_id, era in CFG["eras"].items()}
_lock = Lock()


def era_ids() -> list:
    """Every configured era, in config order. Never hardcode this list."""
    return list(CFG["eras"])


def era_config(era_id: str) -> dict:
    return CFG["eras"][era_id]


def get_engine(era_id: str):
    era = CFG["eras"][era_id]
    if era.get("engine") != "maia2":
        return _heuristics[era_id]
    # Tests set this to get deterministic material-sigmoid evals even on
    # machines where the trained checkpoints exist (CI has no weights anyway).
    if os.environ.get("TMC_FORCE_HEURISTIC"):
        return _heuristics[era_id]
    with _lock:
        if era_id in _maia_cache:
            _maia_cache.move_to_end(era_id)
            return _maia_cache[era_id]
        checkpoint = ROOT / "models" / f"{era_id}.pt"
        if not checkpoint.exists():
            print(f"[warn] {checkpoint.name} not found — using heuristic engine. "
                  "Run scripts/fetch_models.py for the trained era models.")
            return _heuristics[era_id]
        engine = Maia2Engine(str(checkpoint))
        _maia_cache[era_id] = engine
        while len(_maia_cache) > MAX_LOADED_MODELS:
            evicted, _ = _maia_cache.popitem(last=False)
            print(f"Evicted era model: {evicted}")
        return engine
