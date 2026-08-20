"""Time-Machine Chess API. Run: uvicorn backend.app:app --reload"""
from pathlib import Path

import chess
import chess.svg
import yaml
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from backend import classifier
from backend.draws import in_band, update_streak, wants_draw
from backend.engines import HeuristicEraEngine, Maia2Engine
from backend.manners import update_resign_streak, wants_to_resign

ROOT = Path(__file__).resolve().parent.parent
CFG = yaml.safe_load((ROOT / "config" / "eras.yaml").read_text())

app = FastAPI(title="Time-Machine Chess")
(ROOT / "frontend" / "img").mkdir(parents=True, exist_ok=True)
app.mount("/img", StaticFiles(directory=ROOT / "frontend" / "img"), name="img")
(ROOT / "frontend" / "pieces").mkdir(parents=True, exist_ok=True)
app.mount("/pieces", StaticFiles(directory=ROOT / "frontend" / "pieces"), name="pieces")

# Lazy-loading engine cache. Maia-2 era models are ~700MB RAM each, so we keep
# at most MAX_LOADED_MODELS resident (LRU eviction) — set to 3 locally for zero
# load pauses, 1 on small cloud instances to stay ~1GB.
import os
from collections import OrderedDict
from threading import Lock

MAX_LOADED_MODELS = int(os.environ.get("MAX_LOADED_MODELS", "3"))
_maia_cache: "OrderedDict[str, Maia2Engine]" = OrderedDict()
_heuristics = {era_id: HeuristicEraEngine(era.get("style", {}))
               for era_id, era in CFG["eras"].items()}
_lock = Lock()


def get_engine(era_id: str):
    era = CFG["eras"][era_id]
    if era.get("engine") != "maia2":
        return _heuristics[era_id]
    # Tests set this to get deterministic material-sigmoid evals even on
    # machines where the trained checkpoints exist (CI has no weights anyway).
    if os.environ.get("TMC_FORCE_HEURISTIC"):
        return _heuristics[era_id]
    with _lock:
        if era_id in _maia_cache:
            _maia_cache.move_to_end(era_id)
            return _maia_cache[era_id]
        checkpoint = ROOT / "models" / f"{era_id}.pt"
        if not checkpoint.exists():
            print(f"[warn] {checkpoint.name} not found — using heuristic engine. "
                  "Run scripts/fetch_models.py for the trained era models.")
            return _heuristics[era_id]
        engine = Maia2Engine(str(checkpoint))
        _maia_cache[era_id] = engine
        while len(_maia_cache) > MAX_LOADED_MODELS:
            evicted, _ = _maia_cache.popitem(last=False)
            print(f"Evicted era model: {evicted}")
        return engine


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
        engine = get_engine(req.era)
        era_cfg = CFG["eras"][req.era]
        draw_params = era_cfg.get("draws")
        resign_params = era_cfg.get("resign")
        if (draw_params or resign_params) and hasattr(engine, "pick_move_with_eval"):
            bot_move, win_prob = engine.pick_move_with_eval(board)
            resp["winProb"] = round(win_prob, 4)
            if resign_params:
                own = win_prob if board.turn == chess.WHITE else 1.0 - win_prob
                rstreak = update_resign_streak(req.resignStreak, own, resign_params)
                resp["resignStreak"] = rstreak
                if wants_to_resign(rstreak, board.ply(), resign_params):
                    # The era resigns rather than move — its manners, its era.
                    resp.update({
                        "botResigns": True, "fen": board.fen(), "gameOver": True,
                        "result": "0-1" if board.turn == chess.WHITE else "1-0",
                        "check": False,
                    })
                    return resp
            if draw_params:
                streak = update_streak(req.drawStreak, win_prob, draw_params)
                resp["drawStreak"] = streak
                # The bot offers with its move (proper etiquette); the client
                # shows the offer banner and ends the game if the player accepts.
                resp["botOffersDraw"] = wants_draw(streak, board.fullmove_number, draw_params)
        else:
            bot_move = engine.pick_move(board)
        resp["botSan"] = board.san(bot_move)
        resp["botMove"] = bot_move.uci()
        board.push(bot_move)
        if board.is_game_over(claim_draw=True):
            resp["botOffersDraw"] = False  # the move itself ended the game
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
    engine = get_engine(req.era)
    draw_params = CFG["eras"][req.era].get("draws")
    if not draw_params or not hasattr(engine, "pick_move_with_eval"):
        return {"accepted": False}
    _, win_prob = engine.pick_move_with_eval(board)
    accepted = (in_band(win_prob, draw_params)
                and wants_draw(req.drawStreak, board.fullmove_number, draw_params))
    return {"accepted": accepted, "winProb": round(win_prob, 4)}


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
