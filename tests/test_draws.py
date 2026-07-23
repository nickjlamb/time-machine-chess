"""Draw-rule coverage: fifty-move rule is server-side (halfmove clock is in the
FEN); threefold repetition is client-side (history isn't in the FEN) and is
covered by the frontend, so here we just pin the server behaviour.

Draw-agreement tests run on the heuristic engines (no model weights in CI),
whose win prob is a material sigmoid — equal material evaluates to exactly 0.5,
inside every era's dead-equal band."""
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


# ---- draw agreements (era-specific willingness; see backend/draws.py) ----

EQUAL = "1r2k3/8/8/8/8/8/8/1R2K3 w - - 0 {n}"          # R vs r — dead equal
QUEEN_UP = "1r2k3/8/8/8/8/8/3Q4/1R2K3 w - - 0 {n}"     # white is a queen up


def play(era, fen, move, streak=0):
    r = client.post("/api/play",
                    json={"era": era, "fen": fen, "move": move, "drawStreak": streak})
    assert r.status_code == 200
    return r.json()


def offer(era, fen, streak):
    r = client.post("/api/draw-offer",
                    json={"era": era, "fen": fen, "drawStreak": streak})
    assert r.status_code == 200
    return r.json()


def test_play_surfaces_winprob_and_advances_streak():
    r = play("soviet", EQUAL.format(n=40), "b1b2", streak=0)
    assert abs(r["winProb"] - 0.5) < 0.01
    assert r["drawStreak"] == 1
    assert r["botMove"] is not None


def test_streak_resets_when_position_is_unbalanced():
    r = play("soviet", QUEEN_UP.format(n=40), "d2d3", streak=5)
    assert r["winProb"] > 0.9
    assert r["drawStreak"] == 0
    assert r["botOffersDraw"] is False


def test_bot_offers_draw_when_era_is_willing():
    # soviet: streak 4 needed from move 18 — dead-equal streak reaching 4 => offer
    r = play("soviet", EQUAL.format(n=40), "b1b2", streak=3)
    assert r["drawStreak"] == 4
    assert r["botOffersDraw"] is True


def test_bot_respects_min_move_threshold():
    r = play("soviet", EQUAL.format(n=10), "b1b2", streak=3)
    assert r["drawStreak"] == 4
    assert r["botOffersDraw"] is False  # too early, even for the Soviet school


def test_romantic_era_almost_never_agrees():
    r = play("romantic", EQUAL.format(n=40), "b1b2", streak=50)
    assert r["botOffersDraw"] is False  # min_move 70 — the attack goes on


def test_draw_offer_era_willingness_gradient():
    fen = EQUAL.format(n=40)
    assert offer("soviet", fen, streak=10)["accepted"] is True
    assert offer("classical", fen, streak=10)["accepted"] is True
    assert offer("romantic", fen, streak=10)["accepted"] is False


def test_draw_offer_needs_accumulated_streak():
    # willingness can't be manufactured by clicking — the streak comes from play
    assert offer("soviet", EQUAL.format(n=40), streak=0)["accepted"] is False


def test_draw_offer_declined_in_unbalanced_position():
    assert offer("soviet", QUEEN_UP.format(n=40), streak=10)["accepted"] is False


def test_draw_offer_unknown_era_404s():
    r = client.post("/api/draw-offer",
                    json={"era": "atomic", "fen": EQUAL.format(n=40), "drawStreak": 0})
    assert r.status_code == 404
