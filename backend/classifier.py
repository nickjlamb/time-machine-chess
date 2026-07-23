"""Era classifier: which era do you play like?

Methodology (see docs/next-era-classifier.md): per-move log-likelihood under
each era model. For every sampled position in the user's games, each era
engine yields a legal-move probability distribution; we sum log P(move
actually played) per era and normalize across eras into an era mix —
"which era's model predicts your moves best", the same spirit as /validation.

Serving order matters: eras form the OUTER loop and positions the inner one,
so each era model is loaded once, scores everything, and is evicted
(MAX_LOADED_MODELS=1 in production would otherwise LRU-thrash five model
swaps per move). The era list comes from config/eras.yaml — never hardcode.
"""
import io
import math
import urllib.error
import urllib.parse
import urllib.request

import chess
import chess.pgn

from backend.engines import material_balance

# ---- sampling constants (tuned on real data; see classify_validation.py) ----
MAX_GAMES = 20          # cap games considered
MAX_POSITIONS = 300     # cap sampled positions across all games
SKIP_PLIES = 6          # opening plies are memory, not style
LOST_MATERIAL = 9       # skip positions where a side is a queen down —
                        # forced-ish moves carry no era signal
MIN_LEGAL_MOVES = 2     # a forced move says nothing about style

# inference_batch rounds probabilities to 4 dp, so a rare-but-played move can
# come back as 0.0; floor at half the rounding quantum before taking logs.
PROB_FLOOR = 5e-5

# Evidence budget for the reported mix. The true posterior over eras
# multiplies per-move likelihood ratios across every sampled position — with
# 300 positions it saturates to ~100/0 for any consistent signal. We report
# the posterior computed as if REFERENCE_POSITIONS positions had been seen,
# so the mix reads as a style blend rather than a binary verdict. Calibrated
# against scripts/classify_validation.py; raise it for sharper diagnoses.
REFERENCE_POSITIONS = 25


# ---------------------------------------------------------------- input ----

def parse_pgn_games(pgn_text: str, max_games: int = MAX_GAMES):
    """Parse up to max_games games from concatenated PGN text."""
    stream = io.StringIO(pgn_text)
    games = []
    while len(games) < max_games:
        try:
            game = chess.pgn.read_game(stream)
        except ValueError:
            break
        if game is None:
            break
        if any(True for _ in game.mainline_moves()):
            games.append(game)
    return games


def identify_player(games, player: str | None = None):
    """Whose moves do we classify? An explicit name wins; otherwise the name
    appearing most often across White/Black headers (the common player in an
    exported game set). Returns None when no name repeats and none is given —
    callers then default to the White player of each game."""
    if player:
        return player
    counts: dict[str, int] = {}
    for game in games:
        for side in ("White", "Black"):
            name = game.headers.get(side, "").strip()
            if name and name != "?":
                counts[name] = counts.get(name, 0) + 1
    if not counts:
        return None
    name, n = max(counts.items(), key=lambda kv: kv[1])
    return name if n > 1 or len(games) == 1 else None


def _player_color(game, player):
    """Which color the classified player has in this game (default White)."""
    if player:
        w = game.headers.get("White", "").strip().lower()
        b = game.headers.get("Black", "").strip().lower()
        p = player.strip().lower()
        if p and p == b and p != w:
            return chess.BLACK
    return chess.WHITE


def _game_label(game):
    w = game.headers.get("White", "?")
    b = game.headers.get("Black", "?")
    date = game.headers.get("Date", "")
    year = date[:4] if date[:4].isdigit() else ""
    return f"{w}–{b}" + (f", {year}" if year else "")


def sample_positions(games, player=None, both_colors=False,
                     max_positions: int = MAX_POSITIONS,
                     skip_plies: int = SKIP_PLIES):
    """Yield sampled positions as dicts:
    {fen, move (uci), san, ply, gameIndex, gameLabel}.

    Rules (docs/next-era-classifier.md): only the classified player's moves
    (unless both_colors — validation classifies whole historical games), skip
    the opening plies, skip forced moves and totally lost positions, and if
    the candidate pool exceeds max_positions, thin it evenly (deterministic —
    no RNG, so tests and repeat runs agree)."""
    candidates = []
    for gi, game in enumerate(games):
        color = _player_color(game, player)
        label = _game_label(game)
        board = game.board()
        for move in game.mainline_moves():
            ply = board.ply()
            if (ply >= skip_plies
                    and (both_colors or board.turn == color)
                    and abs(material_balance(board)) < LOST_MATERIAL):
                legal = list(board.legal_moves)
                if len(legal) >= MIN_LEGAL_MOVES and move in legal:
                    candidates.append({
                        "fen": board.fen(),
                        "move": move.uci(),
                        "san": board.san(move),
                        "ply": ply,
                        "gameIndex": gi,
                        "gameLabel": label,
                    })
            try:
                board.push(move)
            except (ValueError, AssertionError):
                break
    if len(candidates) > max_positions:
        # Even thinning across the whole pool keeps every game represented.
        step = len(candidates) / max_positions
        candidates = [candidates[int(i * step)] for i in range(max_positions)]
    return candidates


# ---------------------------------------------------------------- lichess ----

LICHESS_URL = ("https://lichess.org/api/games/user/{username}"
               "?max={max_games}&moves=true&tags=true&clocks=false"
               "&evals=false&opening=false"
               "&perfType=blitz,rapid,classical,correspondence")


def fetch_lichess_pgn(username: str, max_games: int = MAX_GAMES) -> str:
    """Fetch a user's recent games from lichess as PGN (no auth needed).
    Built blind — the dev sandbox can't reach lichess; tested on the Mac."""
    url = LICHESS_URL.format(username=urllib.parse.quote(username),
                             max_games=max_games)
    req = urllib.request.Request(url, headers={
        "Accept": "application/x-chess-pgn",
        "User-Agent": "time-machine-chess/classifier (chess.pharmatools.ai)",
    })
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8", "replace")


# ---------------------------------------------------------------- scoring ----

def score_positions(engine, positions):
    """Log-likelihood of each played move under one era engine.
    Prefers the engine's batched path (Maia2Engine.move_probs_batch: one
    forward pass per 64 positions) and falls back to per-position scoring
    (HeuristicEraEngine has no batch path; per-position is instant there)."""
    pairs = [(p["fen"], p["move"]) for p in positions]
    if hasattr(engine, "move_probs_batch"):
        dists = engine.move_probs_batch(pairs)
    else:
        dists = [engine.move_probs(chess.Board(fen)) for fen, _ in pairs]
    return [math.log(max(dist.get(uci, 0.0), PROB_FLOOR))
            for dist, (_, uci) in zip(dists, pairs)]


def _era_mix(logliks_by_era: dict[str, list[float]]) -> dict[str, float]:
    """Softmax posterior over eras at the fixed evidence budget (uniform
    prior). See REFERENCE_POSITIONS for why not the full-N posterior."""
    n = len(next(iter(logliks_by_era.values())))
    budget = min(n, REFERENCE_POSITIONS)
    scores = {era: (sum(ll) / n) * budget for era, ll in logliks_by_era.items()}
    mx = max(scores.values())
    exp = {era: math.exp(s - mx) for era, s in scores.items()}
    total = sum(exp.values())
    return {era: e / total for era, e in exp.items()}


def _characteristic_moves(positions, logliks_by_era):
    """Per era, the position where that era's model most preferred the played
    move relative to the other eras — the shareable artifact."""
    eras = list(logliks_by_era)
    out = {}
    for era in eras:
        others = [e for e in eras if e != era]
        best_i, best_margin = None, -math.inf
        for i in range(len(positions)):
            margin = (logliks_by_era[era][i]
                      - sum(logliks_by_era[o][i] for o in others) / len(others))
            if margin > best_margin:
                best_i, best_margin = i, margin
        if best_i is not None:
            p = positions[best_i]
            out[era] = {
                "fen": p["fen"], "move": p["move"], "san": p["san"],
                "ply": p["ply"], "gameLabel": p["gameLabel"],
                "margin": round(best_margin, 3),
                "prob": round(math.exp(logliks_by_era[era][best_i]), 4),
            }
    return out


def classify_stream(positions, era_ids, get_engine, era_meta=None):
    """Generator yielding progress events, then the final result.

    era_ids MUST come from CFG["eras"] (config-driven everywhere) and forms
    the outer loop; get_engine(era_id) is called once per era so the LRU
    cache loads each model exactly once.

    Events: {"type": "era_start"|"era_done", ...} then {"type": "result", ...}.
    """
    logliks: dict[str, list[float]] = {}
    n_eras = len(era_ids)
    for i, era in enumerate(era_ids):
        yield {"type": "era_start", "era": era, "index": i, "total": n_eras}
        logliks[era] = score_positions(get_engine(era), positions)
        yield {"type": "era_done", "era": era, "index": i, "total": n_eras,
               "meanLogLik": round(sum(logliks[era]) / len(logliks[era]), 4)}
    mix = _era_mix(logliks)
    ranked = sorted(mix.items(), key=lambda kv: -kv[1])
    result = {
        "type": "result",
        "mix": {era: round(100 * v, 1) for era, v in mix.items()},
        "topEra": ranked[0][0],
        "meanLogLik": {era: round(sum(ll) / len(ll), 4)
                       for era, ll in logliks.items()},
        "positions": len(positions),
        "characteristicMoves": _characteristic_moves(positions, logliks),
    }
    if era_meta:
        result["verdict"] = era_meta.get(ranked[0][0], {}).get("verdict", "").strip()
    yield result
