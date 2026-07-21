"""Time-Machine Chess API. Run: uvicorn backend.app:app --reload"""
from pathlib import Path

import chess
import yaml
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from backend.engines import HeuristicEraEngine, Maia2Engine

ROOT = Path(__file__).resolve().parent.parent
CFG = yaml.safe_load((ROOT / "config" / "eras.yaml").read_text())

app = FastAPI(title="Time-Machine Chess")

ENGINES = {}
for era_id, era in CFG["eras"].items():
    if era.get("engine") == "maia2":
        ENGINES[era_id] = Maia2Engine(str(ROOT / "models" / f"{era_id}.pt"))
    else:
        ENGINES[era_id] = HeuristicEraEngine(era.get("style", {}))


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
    resp = {"playerSan": player_san, "botMove": None, "botSan": None}
    if not board.is_game_over():
        bot_move = ENGINES[req.era].pick_move(board)
        resp["botSan"] = board.san(bot_move)
        resp["botMove"] = bot_move.uci()
        board.push(bot_move)
    resp.update({
        "fen": board.fen(),
        "gameOver": board.is_game_over(),
        "result": board.result() if board.is_game_over() else None,
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
    if board.is_game_over():
        return {"gameOver": True, "result": board.result()}
    bot_move = ENGINES[req.era].pick_move(board)
    san = board.san(bot_move)
    board.push(bot_move)
    return {
        "move": bot_move.uci(),
        "san": san,
        "fen": board.fen(),
        "gameOver": board.is_game_over(),
        "result": board.result() if board.is_game_over() else None,
    }


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
