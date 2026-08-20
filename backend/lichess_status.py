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

Configure with LICHESS_BOT_USERNAME (comma-separated for multiple era
accounts later); unset means "no bot live yet".
"""
import json
import os
import time
import urllib.error
import urllib.request
from threading import Lock

API = "https://lichess.org/api/user/{}"
TTL_SECONDS = int(os.environ.get("LICHESS_STATUS_TTL", "600"))
TIMEOUT_SECONDS = 4
PERFS = ("blitz", "rapid", "classical")

_cache: dict = {}          # username -> {"at": float, "value": dict | None}
_lock = Lock()


def configured_usernames() -> list:
    raw = os.environ.get("LICHESS_BOT_USERNAME", "")
    return [u.strip() for u in raw.split(",") if u.strip()]


def _http_get_json(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "time-machine-chess"})
    with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS) as resp:
        return json.loads(resp.read().decode("utf-8"))


def summarize(user: dict) -> dict:
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
    return {
        "username": user.get("username") or user.get("id"),
        "url": f"https://lichess.org/@/{user.get('username') or user.get('id')}",
        "title": user.get("title"),
        "online": bool(user.get("online")),
        "playing": user.get("playing"),
        "gamesTotal": counts.get("all", 0),
        "best": best,
    }


def fetch(username: str, fetcher=None) -> dict | None:
    """One user's status, or None if Lichess didn't cooperate."""
    fetcher = fetcher or _http_get_json
    try:
        return summarize(fetcher(API.format(username)))
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
    usernames = configured_usernames()
    if not usernames:
        return {"enabled": False, "bots": []}

    out = []
    for username in usernames:
        with _lock:
            entry = _cache.get(username)
            fresh = entry and (now() - entry["at"]) < TTL_SECONDS
        if fresh:
            value = entry["value"]
        else:
            value = fetch(username, fetcher)
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
