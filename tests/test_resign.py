"""Era resignation manners (backend/manners.py). Runs on the heuristic
engines (material-sigmoid win prob, no model weights needed): a bare king
against Q+R evaluates as hopeless for every era's threshold.

All thresholds are read from config/eras.yaml so tuning the constants
can't break these tests, and TMC_FORCE_HEURISTIC keeps the evals
deterministic on machines where trained checkpoints exist."""
import os
import sys
from pathlib import Path

os.environ["TMC_FORCE_HEURISTIC"] = "1"

import yaml
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from backend.app import app  # noqa: E402

client = TestClient(app)

RESIGN = {era_id: era.get("resign") for era_id, era in yaml.safe_load(
    (Path(__file__).resolve().parent.parent / "config" / "eras.yaml").read_text()
)["eras"].items()}

# Bot (black) has a bare king against Q+R; white plays the quiet Qd1-d2.
HOPELESS = "k7/7R/8/8/8/8/8/K2Q4 w - - 0 {n}"
# Mirror: the bot has the Q+R, the player is the one being ground down.
DOMINANT = "k2q4/8/8/8/8/8/7r/K7 w - - 0 40"
EQUAL = "1r2k3/8/8/8/8/8/8/1R2K3 w - - 0 40"


def play(era, fen, move, streak=0):
    r = client.post("/api/play", json={"era": era, "fen": fen, "move": move,
                                       "resignStreak": streak})
    assert r.status_code == 200
    return r.json()


def fen_at_ply(target_ply):
    """HOPELESS fen whose ply (after white's quiet move) is >= target_ply."""
    return HOPELESS.format(n=target_ply // 2 + 1)


def test_every_era_has_resign_params():
    for era_id, params in RESIGN.items():
        assert params and {"threshold", "streak", "min_ply"} <= set(params), era_id


def test_bot_resigns_when_hopeless():
    p = RESIGN["soviet"]
    r = play("soviet", fen_at_ply(p["min_ply"] + 20), "d1d2", streak=p["streak"] - 1)
    assert r["resignStreak"] == p["streak"]
    assert r["botResigns"] is True
    assert r["gameOver"] is True and r["result"] == "1-0"  # bot was black
    assert r["botMove"] is None


def test_no_resignation_before_min_ply():
    p = RESIGN["soviet"]
    r = play("soviet", HOPELESS.format(n=3), "d1d2", streak=p["streak"] + 5)
    assert r["botResigns"] is False
    assert r["botMove"] is not None  # plays on instead


def test_romantic_plays_on_longer():
    # a ply where the prompt Soviet school resigns but the Romantic fights on
    rom, sov = RESIGN["romantic"], RESIGN["soviet"]
    assert rom["min_ply"] > sov["min_ply"], "gradient assumption"
    fen = fen_at_ply(sov["min_ply"] + 2)
    ply = 2 * (int(fen.split()[-1]) - 1) + 1  # ply after white's move
    if ply < rom["min_ply"]:
        big = max(rom["streak"], sov["streak"]) + 5
        assert play("soviet", fen, "d1d2", streak=big)["botResigns"] is True
        assert play("romantic", fen, "d1d2", streak=big)["botResigns"] is False


def test_romantic_does_resign_eventually():
    p = RESIGN["romantic"]
    r = play("romantic", fen_at_ply(p["min_ply"] + 20), "d1d2", streak=p["streak"] - 1)
    assert r["botResigns"] is True


def test_streak_resets_when_not_hopeless():
    r = play("soviet", EQUAL, "b1b2", streak=5)
    assert r["resignStreak"] == 0
    assert r["botResigns"] is False


def test_bot_does_not_resign_when_winning():
    p = RESIGN["soviet"]
    r = play("soviet", DOMINANT, "a1b1", streak=p["streak"] + 5)
    assert r["resignStreak"] == 0  # the bot is the one winning
    assert r["botResigns"] is False
    assert r["winProb"] < 0.5  # white (the player) is losing
