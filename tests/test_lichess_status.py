"""The homepage's live-Lichess widget (backend/lichess_status.py + /api/lichess-bot).

The rule this file exists to enforce: lichess.org being slow, down, or
rate-limiting us must never make chess.pharmatools.ai slow, down, or wrong.
Every test here stubs the HTTP call — no network, in CI or anywhere else.
"""
import os
import sys
from pathlib import Path

os.environ["TMC_FORCE_HEURISTIC"] = "1"

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from backend import lichess_status  # noqa: E402
from backend.app import app  # noqa: E402

client = TestClient(app)

USER_PAYLOAD = {
    "id": "timemachine1858",
    "username": "TimeMachine1858",
    "title": "BOT",
    "online": True,
    "playing": "https://lichess.org/abcd1234",
    "perfs": {
        "blitz": {"games": 140, "rating": 1712, "prov": False},
        "rapid": {"games": 12, "rating": 1755, "prov": True},
        "bullet": {"games": 0, "rating": 1500, "prov": True},
    },
    "count": {"all": 152, "rated": 140},
}


@pytest.fixture(autouse=True)
def clean_cache():
    lichess_status.reset_cache()
    yield
    lichess_status.reset_cache()


def stub(payload=USER_PAYLOAD, calls=None):
    def fetcher(url):
        if calls is not None:
            calls.append(url)
        return payload
    return fetcher


def test_summary_uses_the_time_control_the_bot_actually_plays():
    """140 blitz games beats 12 provisional rapid ones — don't advertise the
    rating with the least evidence behind it."""
    s = lichess_status.summarize(USER_PAYLOAD)
    assert s["best"] == {"perf": "blitz", "rating": 1712, "games": 140, "provisional": False}
    assert s["gamesTotal"] == 152
    assert s["url"] == "https://lichess.org/@/TimeMachine1858"
    assert s["online"] is True


def test_a_brand_new_bot_has_no_rating_yet():
    fresh = {"username": "TimeMachine1858", "perfs": {"blitz": {"games": 0, "rating": 1500}},
             "count": {"all": 0}}
    assert lichess_status.summarize(fresh)["best"] is None


def test_disabled_when_no_account_is_configured(monkeypatch):
    monkeypatch.delenv("LICHESS_BOT_USERNAME", raising=False)
    assert lichess_status.get_status(fetcher=stub()) == {"enabled": False, "bots": []}
    assert client.get("/api/lichess-bot").json()["enabled"] is False


def test_status_is_cached_not_fetched_per_visitor(monkeypatch):
    monkeypatch.setenv("LICHESS_BOT_USERNAME", "TimeMachine1858")
    calls = []
    fetcher = stub(calls=calls)
    for _ in range(5):
        out = lichess_status.get_status(fetcher=fetcher, now=lambda: 1000.0)
    assert len(calls) == 1
    assert out["enabled"] is True and out["bots"][0]["best"]["rating"] == 1712


def test_cache_expires_after_the_ttl(monkeypatch):
    monkeypatch.setenv("LICHESS_BOT_USERNAME", "TimeMachine1858")
    calls = []
    fetcher = stub(calls=calls)
    lichess_status.get_status(fetcher=fetcher, now=lambda: 0.0)
    lichess_status.get_status(fetcher=fetcher, now=lambda: lichess_status.TTL_SECONDS + 1)
    assert len(calls) == 2


def test_a_lichess_outage_keeps_serving_the_last_good_value(monkeypatch):
    monkeypatch.setenv("LICHESS_BOT_USERNAME", "TimeMachine1858")
    lichess_status.get_status(fetcher=stub(), now=lambda: 0.0)

    def broken(url):
        raise OSError("lichess is having a moment")

    out = lichess_status.get_status(fetcher=broken,
                                    now=lambda: lichess_status.TTL_SECONDS + 1)
    assert out["enabled"] is True
    assert out["bots"][0]["best"]["rating"] == 1712


def test_an_outage_with_no_cached_value_hides_the_widget(monkeypatch):
    monkeypatch.setenv("LICHESS_BOT_USERNAME", "TimeMachine1858")

    def broken(url):
        raise OSError("lichess is having a moment")

    assert lichess_status.get_status(fetcher=broken) == {"enabled": False, "bots": []}


def test_multiple_era_accounts(monkeypatch):
    monkeypatch.setenv("LICHESS_BOT_USERNAME", "TimeMachine1858, TM-SovietSchool")
    out = lichess_status.get_status(fetcher=stub())
    assert len(out["bots"]) == 2


def test_endpoint_never_500s_when_lichess_misbehaves(monkeypatch):
    monkeypatch.setenv("LICHESS_BOT_USERNAME", "TimeMachine1858")
    monkeypatch.setattr(lichess_status, "_http_get_json",
                        lambda url: (_ for _ in ()).throw(OSError("boom")))
    r = client.get("/api/lichess-bot")
    assert r.status_code == 200
    assert r.json() == {"enabled": False, "bots": []}


# ------------------------------------------------- era-tagged account entries

def test_plain_username_still_works(monkeypatch):
    monkeypatch.setenv("LICHESS_BOT_USERNAME", "TimeMachine1858")
    out = lichess_status.get_status(fetcher=stub())
    assert out["bots"][0]["username"] == "TimeMachine1858"
    assert out["bots"][0]["era"] is None
    assert out["bots"][0]["eraName"] is None


def test_era_prefix_names_the_account(monkeypatch):
    """`romantic:TimeMachine1858` lets the homepage show the era's own name and
    portrait instead of an anonymous handle."""
    monkeypatch.setenv("LICHESS_BOT_USERNAME", "romantic:TimeMachine1858")
    out = lichess_status.get_status(fetcher=stub())
    bot = out["bots"][0]
    assert bot["username"] == "TimeMachine1858"
    assert bot["era"] == "romantic"
    assert bot["eraName"] == lichess_status.CFG["eras"]["romantic"]["name"]
    assert bot["eraYears"] == lichess_status.CFG["eras"]["romantic"]["years"]


def test_unknown_era_prefix_costs_the_portrait_not_the_card(monkeypatch):
    monkeypatch.setenv("LICHESS_BOT_USERNAME", "victorian:TimeMachine1858")
    assert lichess_status.parse_account("victorian:TimeMachine1858") == (
        None, "victorian:TimeMachine1858")


def test_mixed_entries(monkeypatch):
    monkeypatch.setenv("LICHESS_BOT_USERNAME", "romantic:TimeMachine1858, TM-Soviet")
    assert lichess_status.configured_accounts() == [
        ("romantic", "TimeMachine1858"), (None, "TM-Soviet")]
