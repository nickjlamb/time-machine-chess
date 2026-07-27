"""API smoke tests. Run: pytest
Work without model weights (heuristic fallback), so CI stays light."""
import sys
from pathlib import Path

import chess
import pytest
import yaml
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from backend.app import app  # noqa: E402

client = TestClient(app)
START = chess.Board().fen()
CFG_ERAS = list(yaml.safe_load(
    (Path(__file__).resolve().parent.parent / "config" / "eras.yaml").read_text()
)["eras"])


def test_eras():
    eras = client.get("/api/eras").json()
    assert set(eras) == set(CFG_ERAS)   # every configured era is served
    assert {"romantic", "classical", "soviet"} <= set(eras)
    for era in eras.values():
        assert era["name"] and len(era["years"]) == 2


def test_legal_moves():
    moves = client.get("/api/legal", params={"fen": START}).json()["moves"]
    assert len(moves) == 20 and "e2e4" in moves


@pytest.mark.parametrize("era", CFG_ERAS)
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


def test_era_elo_served_when_measured():
    """scripts/estimate_elo.py output, if present, surfaces through the API."""
    from backend.app import ROOT
    if not (ROOT / "validation" / "elo.json").exists():
        return  # not measured yet — /api/elo should then 404
    eras = client.get("/api/eras").json()
    assert any(isinstance(e.get("elo"), int) for e in eras.values())
    r = client.get("/api/elo").json()
    assert "eras" in r and "method" in r


def test_hint_endpoint():
    r = client.post("/api/hint", json={"era": "romantic", "fen": START}).json()
    assert len(r["hints"]) == 3
    probs = [h["prob"] for h in r["hints"]]
    assert probs == sorted(probs, reverse=True)          # best first
    board = chess.Board(START)
    for h in r["hints"]:
        assert chess.Move.from_uci(h["uci"]) in board.legal_moves
        assert board.san(chess.Move.from_uci(h["uci"])) == h["san"]
    assert client.post("/api/hint", json={"era": "jazz", "fen": START}).status_code == 404
    assert client.post("/api/hint", json={"era": "soviet", "fen": "nonsense"}).status_code == 400
    mate = "rnb1kbnr/pppp1ppp/8/4p3/6Pq/5P2/PPPPP2P/RNBQKBNR w KQkq - 1 3"
    assert client.post("/api/hint", json={"era": "soviet", "fen": mate}).json()["gameOver"] is True


def test_faq_and_seo_routes():
    r = client.get("/faq")
    assert r.status_code == 200 and "FAQPage" in r.text
    sm = client.get("/sitemap.xml")
    assert sm.status_code == 200 and "/classifier" in sm.text and "/faq" in sm.text
    rb = client.get("/robots.txt")
    assert rb.status_code == 200 and "sitemap.xml" in rb.text
