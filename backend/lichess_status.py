"""Live status of our Lichess BOT accounts, for the homepage trust signal.

"Challenge TimeMachine1858 — currently rated 1712 on Lichess" is a better
claim than any blurb we could write: it is a public, independently-kept
number, and if it lands near the measured Elo in validation/elo.json the two
receipts corroborate each other.

Design constraints, learned the boring way:
  - the website must not depend on lichess.org being up. Every failure path
    returns the last good value, or "unavailable", never a 500 and never a
    slow page;
  - one cached fetch per TTL for the whole server, not one per visitor;
  - if no bot account is configured, the endpoint says so and the homepage
    simply doesn't render the widget.

Configure with LICHESS_BOT_USERNAME, comma-separated for several accounts.
Each entry is either a bare username or `era:username` — the second form tells
the site which era that account plays, so the homepage can show it in the era's
own name and portrait rather than as an anonymous handle. The era is validated
against config/eras.yaml; unset means "no bot live yet".

    LICHESS_BOT_USERNAME=romantic:TimeMachine1858
"""
import json
import os
import time
import urllib.error
import urllib.request
from threading import Lock

from backend.engine_pool import CFG

API = "https://lichess.org/api/user/{}"
TTL_SECONDS = int(os.environ.get("LICHESS_STATUS_TTL", "600"))
TIMEOUT_SECONDS = 4
PERFS = ("blitz", "rapid", "classical")

_cache: dict = {}          # username -> {"at": float, "value": dict | None}
_lock = Lock()


def parse_account(entry: str):
    """`era:username` or plain `username` -> (era_id | None, username).

    An era that isn't in config/eras.yaml is ignored rather than fatal: a typo
    in an env var should cost the portrait, not the whole card.
    """
    entry = entry.strip()
    if ":" in entry:
        era, _, username = entry.partition(":")
        era = era.strip().lower()
        if era in CFG["eras"]:
            return era, username.strip()
        return None, entry            # not an era prefix — treat it as a name
    return None, entry


def configured_accounts() -> list:
    raw = os.environ.get("LICHESS_BOT_USERNAME", "")
    return [parse_account(e) for e in raw.split(",") if e.strip()]


def configured_usernames() -> list:
    return [username for _, username in configured_accounts()]


def _http_get_json(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "time-machine-chess"})
    with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS) as resp:
        return json.loads(resp.read().decode("utf-8"))


def summarize(user: dict, era: str | None = None) -> dict:
    """Reduce Lichess's user payload to what the homepage shows.

    Picks the time control the bot has actually played most — a rapid-only
    bot shouldn't advertise an empty blitz rating — and passes the
    provisional flag through so we can mark an unsettled number as such.
    """
    perfs = user.get("perfs") or {}
    best = None
    for key in PERFS:
        perf = perfs.get(key) or {}
        games = perf.get("games") or 0
        if games and (best is None or games > best["games"]):
            best = {"perf": key, "rating": perf.get("rating"), "games": games,
                    "provisional": bool(perf.get("prov", False))}
    counts = user.get("count") or {}
    era_cfg = CFG["eras"].get(era) if era else None
    return {
        "era": era,
        "eraName": era_cfg.get("name") if era_cfg else None,
        "eraYears": era_cfg.get("years") if era_cfg else None,
        "username": user.get("username") or user.get("id"),
        "url": f"https://lichess.org/@/{user.get('username') or user.get('id')}",
        "title": user.get("title"),
        "online": bool(user.get("online")),
        "playing": user.get("playing"),
        "gamesTotal": counts.get("all", 0),
        "best": best,
    }


def fetch(username: str, fetcher=None, era: str | None = None) -> dict | None:
    """One user's status, or None if Lichess didn't cooperate."""
    fetcher = fetcher or _http_get_json
    try:
        return summarize(fetcher(API.format(username)), era=era)
    except (urllib.error.URLError, urllib.error.HTTPError, ValueError,
            TimeoutError, OSError):
        return None


def get_status(fetcher=None, now=time.monotonic) -> dict:
    """Cached status for every configured account.

    Stale-on-error: a failed refresh keeps serving the previous value rather
    than blanking the widget, because a Lichess hiccup shouldn't make the
    homepage claim the bot doesn't exist.
    """
    # Resolved per call, not bound as a default, so tests (and anything else)
    # can swap the transport — and so no test accidentally hits lichess.org.
    fetcher = fetcher or _http_get_json
    accounts = configured_accounts()
    if not accounts:
        return {"enabled": False, "bots": []}

    out = []
    for era, username in accounts:
        with _lock:
            entry = _cache.get(username)
            fresh = entry and (now() - entry["at"]) < TTL_SECONDS
        if fresh:
            value = entry["value"]
        else:
            value = fetch(username, fetcher, era=era)
            if value is None and entry is not None:
                value = entry["value"]          # keep the last good answer
            with _lock:
                _cache[username] = {"at": now(), "value": value}
        if value:
            out.append(value)
    return {"enabled": bool(out), "bots": out}


def reset_cache() -> None:
    """Test hook."""
    with _lock:
        _cache.clear()
