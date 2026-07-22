"""Draw-rule coverage: fifty-move rule is server-side (halfmove clock is in the
FEN); threefold repetition is client-side (history isn't in the FEN) and is
covered by the frontend, so here we just pin the server behaviour."""
import sys
from pathlib import Path

import chess
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from backend.app import app  # noqa: E402

client = TestClient(app)


def test_fifty_move_rule_auto_draws():
    # halfmove clock at 99; a quiet rook move makes it 100 => claimable draw
    fen = "k7/8/8/8/8/8/8/K6R w - - 99 80"
    r = client.post("/api/play", json={"era": "soviet", "fen": fen, "move": "h1h2"}).json()
    assert r["gameOver"] is True
    assert r["result"] == "1/2-1/2"
    assert r["botMove"] is None  # bot doesn't move in a finished game


def test_stalemate_detected():
    # black to move, stalemated after Qc7 (classic KQ vs K stalemate net)
    fen = "k7/8/1K6/8/8/8/8/2Q5 w - - 0 1"
    r = client.post("/api/play", json={"era": "soviet", "fen": fen, "move": "c1c7"}).json()
    assert r["gameOver"] is True and r["result"] == "1/2-1/2"
