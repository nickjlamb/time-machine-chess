"""The Lichess BOT account glue (lichess_bot/).

The sandbox this was built in can't reach lichess.org, and CI has neither the
lichess-bot framework nor the model weights — so nothing here talks to a
network. Instead:

  - EraBot is exercised directly with a stub engine (the framework only ever
    calls it through one method, so this is the whole surface);
  - the framework adapter in homemade.py is imported against a *fake*
    `lib.engine_wrapper` module, which is enough to prove the translation into
    a PlayResult is right — the part that would otherwise only be discovered
    live, mid-game, on a rated account;
  - the config renderer is checked for the failure that is invisible in
    production: a greeting Lichess silently refuses to deliver.

Nick runs the real integration locally (`python -m lichess_bot.engine
--selfcheck`, then a casual challenge) before pointing it at a rated account.
"""
import os
import sys
import types
from pathlib import Path

os.environ["TMC_FORCE_HEURISTIC"] = "1"

import chess
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from backend.engine_pool import CFG  # noqa: E402
from lichess_bot.engine import EraBot, era_from_env  # noqa: E402
from lichess_bot.render_config import check_greetings, render  # noqa: E402

from tests.test_turn import StubEngine  # noqa: E402

ERA_IDS = list(CFG["eras"])


# ---------------------------------------------------------------- era selection

def test_era_defaults_to_the_pilot(monkeypatch):
    monkeypatch.delenv("TMC_ERA", raising=False)
    assert era_from_env() == "romantic"


def test_era_is_case_and_space_tolerant(monkeypatch):
    monkeypatch.setenv("TMC_ERA", "  Soviet ")
    assert era_from_env() == "soviet"


def test_unknown_era_refuses_to_start(monkeypatch):
    monkeypatch.setenv("TMC_ERA", "victorian")
    with pytest.raises(SystemExit) as exc:
        era_from_env()
    assert "victorian" in str(exc.value)


@pytest.mark.parametrize("era", ERA_IDS)
def test_every_configured_era_can_run_a_bot(era):
    """No hardcoded era list anywhere: whatever is in eras.yaml must work."""
    bot = EraBot(era=era, engine=StubEngine())
    assert bot.name == CFG["eras"][era]["name"]
    decision = bot.decide(chess.Board())
    assert decision.move in chess.Board().legal_moves


# ---------------------------------------------------------------- playing rules

def test_streaks_are_per_game_not_per_process():
    """lichess-bot builds an engine per game; two games must not share manners."""
    game_one = EraBot(era="romantic", engine=StubEngine(win_prob=0.5))
    game_two = EraBot(era="romantic", engine=StubEngine(win_prob=0.5))
    board = chess.Board("3rk3/8/8/8/8/8/8/3RK3 w - - 0 40")
    for _ in range(5):
        game_one.decide(board)
    assert game_one.draw_streak == 5
    assert game_two.draw_streak == 0


def test_bot_resigns_in_period():
    era = CFG["eras"]["romantic"]
    lost = chess.Board("7k/8/8/8/8/8/6q1/K7 w - - 0 40")
    bot = EraBot(era="romantic", engine=StubEngine(win_prob=era["resign"]["threshold"] / 2))
    decisions = [bot.decide(lost) for _ in range(era["resign"]["streak"])]
    assert [d.resign for d in decisions[:-1]] == [False] * (era["resign"]["streak"] - 1)
    assert decisions[-1].resign is True
    assert decisions[-1].move is not None      # the move it would have played


def test_bot_accepts_a_draw_offer_by_the_same_rule_it_offers_by():
    """An offer arriving on our turn is accepted only if the era would have
    offered anyway — so the opponent can't talk it into a draw early."""
    bot = EraBot(era="classical", engine=StubEngine(win_prob=0.5))
    quiet = chess.Board("3rk3/8/8/8/8/8/8/3RK3 w - - 0 40")
    params = CFG["eras"]["classical"]["draws"]

    early = bot.decide(quiet, draw_offered=True)
    assert early.offer_draw is False, "accepted before the era was willing"

    for _ in range(params["streak"]):
        last = bot.decide(quiet, draw_offered=True)
    assert last.offer_draw is True


def test_a_winning_bot_ignores_a_draw_offer():
    bot = EraBot(era="classical", engine=StubEngine(win_prob=0.95))
    winning = chess.Board("3rk3/8/8/8/8/8/8/3RK3 w - - 0 40")
    for _ in range(20):
        decision = bot.decide(winning, draw_offered=True)
    assert decision.offer_draw is False


def test_decision_reports_latency_and_evaluation():
    decision = EraBot(era="romantic", engine=StubEngine(win_prob=0.42)).decide(chess.Board())
    assert decision.win_prob == 0.42
    assert decision.seconds >= 0.0


# ---------------------------------------------------- the lichess-bot adapter

@pytest.fixture
def homemade(monkeypatch):
    """Import lichess_bot.homemade against a fake lichess-bot framework."""
    fake_wrapper = types.ModuleType("lib.engine_wrapper")

    class MinimalEngine:
        def __init__(self, *args, **kwargs):
            pass

    fake_wrapper.MinimalEngine = MinimalEngine
    fake_lib = types.ModuleType("lib")
    fake_lib.engine_wrapper = fake_wrapper
    monkeypatch.setitem(sys.modules, "lib", fake_lib)
    monkeypatch.setitem(sys.modules, "lib.engine_wrapper", fake_wrapper)
    monkeypatch.delitem(sys.modules, "lichess_bot.homemade", raising=False)
    monkeypatch.setenv("TMC_ERA", "romantic")

    import importlib
    return importlib.import_module("lichess_bot.homemade")


def test_adapter_returns_a_playresult_with_the_move(homemade):
    engine = homemade.TimeMachineEra()
    engine.bot = EraBot(era="romantic", engine=StubEngine(win_prob=0.5))
    result = engine.search(chess.Board(), None, False, False, None)
    assert result.move in chess.Board().legal_moves
    assert result.resigned is False
    assert result.draw_offered is False


def test_adapter_keeps_the_example_engine_name(homemade):
    """lichess-bot's get_homemade_engine() imports test_bot.homemade, which does
    `from homemade import ExampleEngine` — so a homemade.py without that name
    makes the bot fail to start, with an ImportError that looks like our engine
    is missing. Caught once against a real checkout; pinned here forever."""
    assert hasattr(homemade, "ExampleEngine")


def test_adapter_flags_resignation(homemade):
    era = CFG["eras"]["romantic"]
    engine = homemade.TimeMachineEra()
    engine.bot = EraBot(era="romantic",
                        engine=StubEngine(win_prob=era["resign"]["threshold"] / 2))
    lost = chess.Board("7k/8/8/8/8/8/6q1/K7 w - - 0 40")
    for _ in range(era["resign"]["streak"]):
        result = engine.search(lost, None, False, False, None)
    assert result.resigned is True


def test_adapter_passes_the_draw_offer_through(homemade):
    engine = homemade.TimeMachineEra()
    engine.bot = EraBot(era="classical", engine=StubEngine(win_prob=0.5))
    quiet = chess.Board("3rk3/8/8/8/8/8/8/3RK3 w - - 0 40")
    for _ in range(CFG["eras"]["classical"]["draws"]["streak"]):
        result = engine.search(quiet, None, False, True, None)
    assert result.draw_offered is True
    assert result.resigned is False


# ------------------------------------------------------------- config rendering

@pytest.mark.parametrize("era", ERA_IDS)
def test_rendered_config_fits_lichess_chat_limits(era):
    """Lichess drops chat messages over 140 characters without telling anyone,
    so an era whose name pushes a greeting over the line must fail the build,
    not go quiet in production."""
    text = render(era)
    assert check_greetings(text) == []
    assert "%ERA_NAME%" not in text and "%ERA_YEARS%" not in text
    assert CFG["eras"][era]["name"] in text


def test_greeting_length_check_actually_catches_a_long_line():
    too_long = '  hello: "' + "x" * 200 + '"'
    assert check_greetings(too_long)


@pytest.mark.parametrize("era", ERA_IDS)
def test_rendered_config_is_valid_yaml_with_the_expected_switches(era):
    import yaml
    cfg = yaml.safe_load(render(era))
    assert cfg["engine"]["protocol"] == "homemade"
    assert cfg["engine"]["name"] == "TimeMachineEra"
    # Our era rules own draws and resignations, not the framework's cp heuristics.
    assert cfg["engine"]["draw_or_resign"]["resign_enabled"] is False
    assert cfg["engine"]["draw_or_resign"]["offer_draw_enabled"] is False
    assert cfg["challenge"]["variants"] == ["standard"]
    assert "bullet" not in cfg["challenge"]["time_controls"]
    assert "correspondence" not in cfg["challenge"]["time_controls"]
    assert set(cfg["challenge"]["modes"]) == {"casual", "rated"}
    assert cfg["matchmaking"]["allow_matchmaking"] is False


# ------------------------------------------------------------------ account bio

def test_account_bios_fit_the_lichess_400_character_limit():
    """The bios in lichess_bot/bio.md are pasted into a field Lichess truncates
    at 400 characters — and the funnel links live at the bottom of each one."""
    text = (Path(__file__).resolve().parent.parent / "lichess_bot" / "bio.md").read_text()
    blocks = text.split("```")[1::2]
    assert len(blocks) >= 1
    for block in blocks:
        bio = block.strip()
        assert len(bio) <= 400, f"bio is {len(bio)} characters:\n{bio}"
        assert "chess.pharmatools.ai" in bio
