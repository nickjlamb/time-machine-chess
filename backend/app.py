"""Time-Machine Chess API. Run: uvicorn backend.app:app --reload"""
from pathlib import Path

import chess
import chess.svg
import yaml
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from backend.engines import HeuristicEraEngine, Maia2Engine

ROOT = Path(__file__).resolve().parent.parent
CFG = yaml.safe_load((ROOT / "config" / "eras.yaml").read_text())

app = FastAPI(title="Time-Machine Chess")
(ROOT / "frontend" / "img").mkdir(parents=True, exist_ok=True)
app.mount("/img", StaticFiles(directory=ROOT / "frontend" / "img"), name="img")
(ROOT / "frontend" / "pieces").mkdir(parents=True, exist_ok=True)
app.mount("/pieces", StaticFiles(directory=ROOT / "frontend" / "pieces"), name="pieces")

# Lazy-loading engine cache. Maia-2 era models are ~700MB RAM each, so we keep
# at most MAX_LOADED_MODELS resident (LRU eviction) — set to 3 locally for zero
# load pauses, 1 on small cloud instances to stay ~1GB.
import os
from collections import OrderedDict
from threading import Lock

MAX_LOADED_MODELS = int(os.environ.get("MAX_LOADED_MODELS", "3"))
_maia_cache: "OrderedDict[str, Maia2Engine]" = OrderedDict()
_heuristics = {era_id: HeuristicEraEngine(era.get("style", {}))
               for era_id, era in CFG["eras"].items()}
_lock = Lock()


def get_engine(era_id: str):
    era = CFG["eras"][era_id]
    if era.get("engine") != "maia2":
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


ENGINES = CFG["eras"]  # era ids; kept for membership checks


# ---- games-played counter (file-backed; point DATA_DIR at a persistent volume) ----
import json as _json

STATS_PATH = Path(os.environ.get("DATA_DIR", ROOT / "data")) / "stats.json"
_stats_lock = Lock()


def _load_stats():
    try:
        return _json.loads(STATS_PATH.read_text())
    except (OSError, ValueError):
        return {"games_total": 0, "per_era": {}}


def record_game_start(era_id: str):
    with _stats_lock:
        stats = _load_stats()
        stats["games_total"] += 1
        stats["per_era"][era_id] = stats["per_era"].get(era_id, 0) + 1
        STATS_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = STATS_PATH.with_suffix(".tmp")
        tmp.write_text(_json.dumps(stats))
        tmp.replace(STATS_PATH)
        return stats


class GameStartEvent(BaseModel):
    era: str


@app.post("/api/event/game-start", status_code=204)
def game_start(ev: GameStartEvent):
    if ev.era in CFG["eras"]:
        record_game_start(ev.era)


@app.get("/api/stats")
def stats():
    s = _load_stats()
    return {"games_total": s["games_total"], "per_era": s["per_era"]}


class MoveRequest(BaseModel):
    era: str
    fen: str


class PlayRequest(BaseModel):
    era: str
    fen: str
    move: str  # player's move, UCI


@app.get("/api/legal")
def legal(fen: str):
    try:
        board = chess.Board(fen)
    except ValueError:
        raise HTTPException(400, "Invalid FEN")
    return {"moves": [m.uci() for m in board.legal_moves]}


@app.post("/api/play")
def play(req: PlayRequest):
    """Apply the player's move server-side, then reply with the bot's move."""
    if req.era not in ENGINES:
        raise HTTPException(404, f"Unknown era '{req.era}'")
    try:
        board = chess.Board(req.fen)
        player_move = chess.Move.from_uci(req.move)
    except ValueError:
        raise HTTPException(400, "Invalid FEN or move")
    if player_move not in board.legal_moves:
        raise HTTPException(400, f"Illegal move {req.move}")
    player_san = board.san(player_move)
    board.push(player_move)
    resp = {"playerSan": player_san, "botMove": None, "botSan": None,
            "fenAfterPlayer": board.fen()}
    if not board.is_game_over(claim_draw=True):
        bot_move = get_engine(req.era).pick_move(board)
        resp["botSan"] = board.san(bot_move)
        resp["botMove"] = bot_move.uci()
        board.push(bot_move)
    resp.update({
        "fen": board.fen(),
        "gameOver": board.is_game_over(claim_draw=True),
        "result": board.result(claim_draw=True) if board.is_game_over(claim_draw=True) else None,
        "check": board.is_check(),
    })
    return resp


@app.get("/api/eras")
def eras():
    return {
        era_id: {"name": e["name"], "years": e["years"], "flavor": e["flavor"].strip()}
        for era_id, e in CFG["eras"].items()
    }


@app.post("/api/move")
def move(req: MoveRequest):
    if req.era not in ENGINES:
        raise HTTPException(404, f"Unknown era '{req.era}'")
    try:
        board = chess.Board(req.fen)
    except ValueError:
        raise HTTPException(400, "Invalid FEN")
    if board.is_game_over(claim_draw=True):
        return {"gameOver": True, "result": board.result(claim_draw=True)}
    bot_move = get_engine(req.era).pick_move(board)
    san = board.san(bot_move)
    board.push(bot_move)
    return {
        "move": bot_move.uci(),
        "san": san,
        "fen": board.fen(),
        "gameOver": board.is_game_over(claim_draw=True),
        "result": board.result(claim_draw=True) if board.is_game_over(claim_draw=True) else None,
    }


@app.get("/api/piece/{code}.svg")
def piece_svg(code: str):
    """Serve cburnett piece SVGs from python-chess (e.g. wK, bQ)."""
    if len(code) != 2 or code[0] not in "wb" or code[1] not in "PNBRQK":
        raise HTTPException(404, "Unknown piece")
    symbol = code[1] if code[0] == "w" else code[1].lower()
    svg = chess.svg.piece(chess.Piece.from_symbol(symbol), size=128)
    return Response(svg, media_type="image/svg+xml",
                    headers={"Cache-Control": "public, max-age=604800"})


@app.get("/api/validation")
def validation_data():
    path = ROOT / "validation" / "results.json"
    if not path.exists():
        raise HTTPException(404, "Run scripts/selfplay.py + scripts/analyze_selfplay.py first")
    return FileResponse(path, media_type="application/json")


@app.get("/validation")
def validation_page():
    return FileResponse(ROOT / "frontend" / "validation.html")


@app.get("/")
def index():
    return FileResponse(ROOT / "frontend" / "index.html")
