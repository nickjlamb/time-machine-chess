"""Time-Machine Chess API. Run: uvicorn backend.app:app --reload"""
from pathlib import Path

import chess
import chess.svg
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from backend import classifier
from backend.engine_pool import CFG, ROOT, get_engine
from backend.lichess_status import get_status as lichess_bot_status
from backend.turn import accepts_draw, play_turn

app = FastAPI(title="Time-Machine Chess")
(ROOT / "frontend" / "img").mkdir(parents=True, exist_ok=True)
app.mount("/img", StaticFiles(directory=ROOT / "frontend" / "img"), name="img")
(ROOT / "frontend" / "pieces").mkdir(parents=True, exist_ok=True)
app.mount("/pieces", StaticFiles(directory=ROOT / "frontend" / "pieces"), name="pieces")

# Engine loading, the era config and the LRU model cache now live in
# backend/engine_pool.py so the Lichess bot can share them (see lichess_bot/).
import os
from threading import Lock

ENGINES = CFG["eras"]  # era ids; kept for membership checks


# ---- games-played counter (file-backed; point DATA_DIR at a persistent volume) ----
import json as _json

STATS_PATH = Path(os.environ.get("DATA_DIR", ROOT / "data")) / "stats.json"
_stats_lock = Lock()


def _load_stats():
    try:
        return _json.loads(STATS_PATH.read_text())
    except (OSError, ValueError):
        return {"games_total": 0, "per_era": {}}


def record_game_start(era_id: str):
    with _stats_lock:
        stats = _load_stats()
        stats["games_total"] += 1
        stats["per_era"][era_id] = stats["per_era"].get(era_id, 0) + 1
        STATS_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = STATS_PATH.with_suffix(".tmp")
        tmp.write_text(_json.dumps(stats))
        tmp.replace(STATS_PATH)
        return stats


class GameStartEvent(BaseModel):
    era: str


@app.post("/api/event/game-start", status_code=204)
def game_start(ev: GameStartEvent):
    if ev.era in CFG["eras"]:
        record_game_start(ev.era)


@app.get("/api/stats")
def stats():
    s = _load_stats()
    return {"games_total": s["games_total"], "per_era": s["per_era"]}


class MoveRequest(BaseModel):
    era: str
    fen: str


class PlayRequest(BaseModel):
    era: str
    fen: str
    move: str  # player's move, UCI
    # Consecutive dead-equal / hopeless evaluation counters (draw-agreement and
    # resignation state). The server is stateless, so the client carries these
    # and we echo them back updated.
    drawStreak: int = 0
    resignStreak: int = 0


class DrawOfferRequest(BaseModel):
    era: str
    fen: str
    drawStreak: int = 0


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
    resp = {"playerSan": player_san, "botMove": None, "botSan": None,
            "fenAfterPlayer": board.fen(),
            "winProb": None, "drawStreak": req.drawStreak, "botOffersDraw": False,
            "resignStreak": req.resignStreak, "botResigns": False}
    if not board.is_game_over(claim_draw=True):
        # One shared recipe for the era's turn — the same call the Lichess bot
        # makes (backend/turn.py), so the bot on Lichess and the bot on the
        # site are the same player.
        t = play_turn(get_engine(req.era), CFG["eras"][req.era], board,
                      draw_streak=req.drawStreak, resign_streak=req.resignStreak)
        resp["winProb"] = round(t.win_prob, 4) if t.win_prob is not None else None
        resp["drawStreak"] = t.draw_streak
        resp["resignStreak"] = t.resign_streak
        if t.resigns:
            resp.update({
                "botResigns": True, "fen": board.fen(), "gameOver": True,
                "result": "0-1" if board.turn == chess.WHITE else "1-0",
                "check": False,
            })
            return resp
        # The bot offers with its move (proper etiquette); the client shows the
        # offer banner and ends the game if the player accepts.
        resp["botOffersDraw"] = t.offers_draw
        resp["botSan"] = board.san(t.move)
        resp["botMove"] = t.move.uci()
        board.push(t.move)
    resp.update({
        "fen": board.fen(),
        "gameOver": board.is_game_over(claim_draw=True),
        "result": board.result(claim_draw=True) if board.is_game_over(claim_draw=True) else None,
        "check": board.is_check(),
    })
    return resp


@app.post("/api/draw-offer")
def draw_offer(req: DrawOfferRequest):
    """Player offers a draw. The bot accepts by the same era rule it offers by:
    current evaluation dead equal AND the client-carried streak long enough AND
    the game deep enough. The streak is NOT advanced here (only real moves in
    /api/play advance it), so spamming the button can't manufacture agreement."""
    if req.era not in ENGINES:
        raise HTTPException(404, f"Unknown era '{req.era}'")
    try:
        board = chess.Board(req.fen)
    except ValueError:
        raise HTTPException(400, "Invalid FEN")
    if board.is_game_over(claim_draw=True):
        return {"accepted": False, "gameOver": True}
    accepted, win_prob = accepts_draw(get_engine(req.era), CFG["eras"][req.era],
                                      board, req.drawStreak)
    return {"accepted": accepted,
            "winProb": round(win_prob, 4) if win_prob is not None else None}


def _load_elo():
    """Measured playing strength (scripts/estimate_elo.py) — optional."""
    try:
        return _json.loads((ROOT / "validation" / "elo.json").read_text())["eras"]
    except (OSError, ValueError, KeyError):
        return {}


ELO_DATA = _load_elo()


@app.get("/api/eras")
def eras():
    out = {}
    for era_id, e in CFG["eras"].items():
        out[era_id] = {"name": e["name"], "years": e["years"], "flavor": e["flavor"].strip(),
                       "verdict": e.get("verdict", "").strip()}
        if era_id in ELO_DATA:
            out[era_id]["elo"] = ELO_DATA[era_id]["elo"]
    return out


@app.get("/api/lichess-bot")
def lichess_bot():
    """Live status of our BOT accounts on Lichess (cached; see
    backend/lichess_status.py). Returns {"enabled": false} when no account is
    configured, which is the homepage's cue to render nothing."""
    return lichess_bot_status()


@app.get("/api/elo")
def elo_data():
    path = ROOT / "validation" / "elo.json"
    if not path.exists():
        raise HTTPException(404, "Run scripts/estimate_elo.py first")
    return FileResponse(path, media_type="application/json")


@app.post("/api/move")
def move(req: MoveRequest):
    if req.era not in ENGINES:
        raise HTTPException(404, f"Unknown era '{req.era}'")
    try:
        board = chess.Board(req.fen)
    except ValueError:
        raise HTTPException(400, "Invalid FEN")
    if board.is_game_over(claim_draw=True):
        return {"gameOver": True, "result": board.result(claim_draw=True)}
    bot_move = get_engine(req.era).pick_move(board)
    san = board.san(bot_move)
    board.push(bot_move)
    return {
        "move": bot_move.uci(),
        "san": san,
        "fen": board.fen(),
        "gameOver": board.is_game_over(claim_draw=True),
        "result": board.result(claim_draw=True) if board.is_game_over(claim_draw=True) else None,
    }


@app.get("/api/piece/{code}.svg")
def piece_svg(code: str):
    """Serve cburnett piece SVGs from python-chess (e.g. wK, bQ)."""
    if len(code) != 2 or code[0] not in "wb" or code[1] not in "PNBRQK":
        raise HTTPException(404, "Unknown piece")
    symbol = code[1] if code[0] == "w" else code[1].lower()
    svg = chess.svg.piece(chess.Piece.from_symbol(symbol), size=128)
    return Response(svg, media_type="image/svg+xml",
                    headers={"Cache-Control": "public, max-age=604800"})


# ---- era classifier: which era do you play like? ----
from fastapi.responses import StreamingResponse
import urllib.error


class ClassifyRequest(BaseModel):
    pgn: str | None = None
    lichessUsername: str | None = None
    chesscomUsername: str | None = None
    player: str | None = None  # whose moves to classify (PGN header name)


def _fetch_user_games(fetch, username: str, site: str) -> str:
    try:
        return fetch(username.strip())
    except urllib.error.HTTPError as e:
        if e.code in (301, 404):   # chess.com returns 301 for unknown users
            raise HTTPException(404, f"{site} user '{username}' not found")
        raise HTTPException(502, f"{site} returned {e.code}")
    except urllib.error.URLError:
        raise HTTPException(502, f"Could not reach {site}")


@app.post("/api/classify")
def classify(req: ClassifyRequest):
    """Classify a player's games against every era model. Streams NDJSON
    progress events (one line per era start/done — real-model scoring loads
    ~700MB checkpoints, so the client shows which era is thinking) and ends
    with a {"type": "result", ...} line. The server stays stateless: no jobs,
    no polling, one response."""
    if req.lichessUsername and req.lichessUsername.strip():
        player = req.lichessUsername.strip()
        pgn_text = _fetch_user_games(classifier.fetch_lichess_pgn, player, "lichess")
    elif req.chesscomUsername and req.chesscomUsername.strip():
        player = req.chesscomUsername.strip()
        pgn_text = _fetch_user_games(classifier.fetch_chesscom_pgn, player, "chess.com")
    elif req.pgn and req.pgn.strip():
        pgn_text = req.pgn
        player = req.player
    else:
        raise HTTPException(400, "Provide pgn, lichessUsername or chesscomUsername")

    games = classifier.parse_pgn_games(pgn_text)
    if not games:
        raise HTTPException(400, "No games could be parsed from the PGN")
    player = classifier.identify_player(games, player)
    positions = classifier.sample_positions(games, player)
    if len(positions) < 10:
        raise HTTPException(400, "Not enough classifiable positions "
                                 f"({len(positions)}) — supply longer or more games")

    era_ids = list(CFG["eras"])  # config-driven, never hardcoded

    def stream():
        yield _json.dumps({"type": "start", "games": len(games),
                           "positions": len(positions), "player": player,
                           "eras": era_ids}) + "\n"
        for event in classifier.classify_stream(positions, era_ids, get_engine,
                                                era_meta=CFG["eras"]):
            if event["type"] == "result":
                event["games"] = len(games)
                event["player"] = player
            yield _json.dumps(event) + "\n"

    return StreamingResponse(stream(), media_type="application/x-ndjson",
                             headers={"Cache-Control": "no-store",
                                      "X-Accel-Buffering": "no"})


class HintRequest(BaseModel):
    era: str
    fen: str


@app.post("/api/hint")
def hint(req: HintRequest):
    """What would this era play here? Top moves from the policy head with
    probabilities — the bot as a teacher of period style."""
    if req.era not in ENGINES:
        raise HTTPException(404, f"Unknown era '{req.era}'")
    try:
        board = chess.Board(req.fen)
    except ValueError:
        raise HTTPException(400, "Invalid FEN")
    if board.is_game_over(claim_draw=True):
        return {"hints": [], "gameOver": True}
    probs = get_engine(req.era).move_probs(board)
    top = sorted(probs.items(), key=lambda kv: -kv[1])[:3]
    return {"hints": [
        {"uci": uci, "san": board.san(chess.Move.from_uci(uci)), "prob": round(p, 4)}
        for uci, p in top
    ]}


class LichessImportRequest(BaseModel):
    pgn: str


@app.post("/api/lichess-import")
def lichess_import(req: LichessImportRequest):
    """Proxy a PGN to lichess's import API (browsers hit CORS going direct)."""
    if not req.pgn.strip() or len(req.pgn) > 20000:
        raise HTTPException(400, "Provide a PGN under 20KB")
    try:
        return {"url": classifier.import_to_lichess(req.pgn)}
    except urllib.error.HTTPError as e:
        raise HTTPException(502, f"lichess returned {e.code}")
    except (urllib.error.URLError, KeyError, ValueError):
        raise HTTPException(502, "Could not reach lichess")


@app.get("/api/classifier-validation")
def classifier_validation_data():
    path = ROOT / "validation" / "classifier.json"
    if not path.exists():
        raise HTTPException(404, "Run scripts/classify_validation.py first")
    return FileResponse(path, media_type="application/json")


# ---- share-link unfurls -------------------------------------------------
# A classifier share link carries the whole result in its query string
# (?r=era:pct,...&p=player&g=games — see shareData() in classifier.html).
# Crawlers don't run JS, so to make those links unfurl with a personalised
# card we (a) render a per-result OG image and (b) swap the static OG meta
# block for a personalised one when /classifier is fetched with a payload.

import html
import re
from urllib.parse import urlencode

from backend import og as og_cards

_OG_BLOCK = re.compile(r"<!-- og:begin.*?<!-- og:end -->", re.S)


def _clean_player(p: str) -> str:
    return re.sub(r"[^\w .\-]", "", p or "")[:24].strip()


def _parse_share_query(params) -> "dict | None":
    """Mirror of loadShared() in classifier.html — same validation rules."""
    mix = []
    for part in (params.get("r") or "").split(","):
        era, _, pct = part.partition(":")
        try:
            v = float(pct)
        except ValueError:
            continue
        if era in CFG["eras"] and 0 <= v <= 100 and era not in dict(mix):
            mix.append((era, round(v)))
    if len(mix) < 2:
        return None
    mix.sort(key=lambda ep: -ep[1])
    try:
        games = max(0, min(int(params.get("g") or 0), 100000))
    except ValueError:
        games = 0
    return {"mix": mix, "top": mix[0],
            "player": _clean_player(params.get("p")), "games": games}


@app.get("/api/og-image.png")
def og_image(era: str, pct: int = 0, p: str = "", g: int = 0):
    if era not in CFG["eras"]:
        raise HTTPException(404, "Unknown era")
    e = CFG["eras"][era]
    png = og_cards.share_card_png(era, e["name"], tuple(e["years"]),
                                  max(0, min(100, pct)), _clean_player(p),
                                  max(0, min(g, 100000)))
    return Response(png, media_type="image/png",
                    headers={"Cache-Control": "public, max-age=86400"})


@app.get("/classifier")
def classifier_page(request: Request):
    page = (ROOT / "frontend" / "classifier.html").read_text(encoding="utf-8")
    share = _parse_share_query(request.query_params)
    if share is None:
        return HTMLResponse(page)

    top_era, top_pct = share["top"]
    name = CFG["eras"][top_era]["name"]
    who = share["player"]
    title = f"{who} plays like {name} — {top_pct}% match" if who else \
        f"I play like {name} — {top_pct}% match"
    desc = ", ".join(f"{p}% {CFG['eras'][e]['name'].replace('The ', '')}"
                     for e, p in share["mix"] if p >= 5)
    if share["games"]:
        desc += f" · {share['games']} games analysed"
    desc += " · Which era do you play like?"

    img_q = {"era": top_era, "pct": top_pct}
    if who:
        img_q["p"] = who
    if share["games"]:
        img_q["g"] = share["games"]
    page_q = {"r": ",".join(f"{e}:{p}" for e, p in share["mix"])}
    if who:
        page_q["p"] = who
    if share["games"]:
        page_q["g"] = share["games"]

    block = f"""<meta property="og:type" content="website">
<meta property="og:site_name" content="Time-Machine Chess">
<meta property="og:title" content="{html.escape(title)}">
<meta property="og:description" content="{html.escape(desc)}">
<meta property="og:url" content="{SITE}/classifier?{html.escape(urlencode(page_q))}">
<meta property="og:image" content="{SITE}/api/og-image.png?{html.escape(urlencode(img_q))}">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta name="twitter:card" content="summary_large_image">"""
    return HTMLResponse(_OG_BLOCK.sub(block, page, count=1))


@app.get("/api/validation")
def validation_data():
    path = ROOT / "validation" / "results.json"
    if not path.exists():
        raise HTTPException(404, "Run scripts/selfplay.py + scripts/analyze_selfplay.py first")
    return FileResponse(path, media_type="application/json")


@app.get("/validation")
def validation_page():
    return FileResponse(ROOT / "frontend" / "validation.html")


@app.get("/faq")
def faq_page():
    return FileResponse(ROOT / "frontend" / "faq.html")


SITE = "https://chess.pharmatools.ai"
PAGES = ["/", "/classifier", "/validation", "/faq"]


@app.get("/sitemap.xml")
def sitemap():
    urls = "\n".join(f"  <url><loc>{SITE}{p}</loc></url>" for p in PAGES)
    return Response(
        f'<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n{urls}\n</urlset>\n',
        media_type="application/xml")


@app.get("/robots.txt")
def robots():
    return Response(f"User-agent: *\nAllow: /\nSitemap: {SITE}/sitemap.xml\n",
                    media_type="text/plain")


@app.get("/")
def index():
    return FileResponse(ROOT / "frontend" / "index.html")
