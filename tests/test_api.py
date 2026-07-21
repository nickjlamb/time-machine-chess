"""API smoke tests. Run: pytest
Work without model weights (heuristic fallback), so CI stays light."""
import sys
from pathlib import Path

import chess
import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from backend.app import app  # noqa: E402

client = TestClient(app)
START = chess.Board().fen()


def test_eras():
    eras = client.get("/api/eras").json()
    assert set(eras) == {"romantic", "classical", "soviet"}
    for era in eras.values():
        assert era["name"] and len(era["years"]) == 2


def test_legal_moves():
    moves = client.get("/api/legal", params={"fen": START}).json()["moves"]
    assert len(moves) == 20 and "e2e4" in moves


@pytest.mark.parametrize("era", ["romantic", "classical", "soviet"])
def test_play_round_trip(era):
    r = client.post("/api/play", json={"era": era, "fen": START, "move": "e2e4"}).json()
    assert r["playerSan"] == "e4"
    assert r["botMove"] and not r["gameOver"]
    board = chess.Board(r["fenAfterPlayer"])
    assert board.turn == chess.BLACK
    chess.Board(r["fen"])  # final fen parses


def test_illegal_move_rejected():
    assert client.post("/api/play", json={"era": "soviet", "fen": START, "move": "e2e5"}).status_code == 400


def test_unknown_era():
    assert client.post("/api/play", json={"era": "jazz", "fen": START, "move": "e2e4"}).status_code == 404


def test_piece_svgs():
    r = client.get("/api/piece/wK.svg")
    assert r.status_code == 200 and b"<svg" in r.content
    assert client.get("/api/piece/zz.svg").status_code == 404


def test_pages_serve():
    assert client.get("/").status_code == 200
    assert client.get("/validation").status_code == 200
