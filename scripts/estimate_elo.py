#!/usr/bin/env python3
"""Estimate each era bot's playing strength against a calibrated ladder.

"What am I up against?" deserves a measured answer, not the conditioning
value: NOMINAL_ELO 1900 is Maia-2's skill-conditioning INPUT, not the bots'
strength — fine-tuning on master games pulls one way, temperature sampling
without search pulls the other. This plays each era bot against Stockfish at
several UCI_Elo anchor levels (alternating colors, the era's own resignation
manners applied) and fits a performance rating by maximum likelihood, with a
bootstrap confidence interval. It is also the receipt for the design claim
that eras differ in STYLE, not strength — the five estimates should land
close together.

Caveats to keep us honest: Stockfish's UCI_Elo is itself an approximation of
human strength (and floors at 1320 in SF16), and engine-vs-engine ratings
transfer imperfectly to human opponents. Treat the result as an anchor and a
cross-era comparison, not a FIDE certificate — say "~1800 vs engines".

Run on the Mac with the real models (heuristic engines will run the plumbing
but measure nothing meaningful). Expect ~1.5–2h at the defaults:

    brew install stockfish
    python3 scripts/estimate_elo.py
    python3 scripts/estimate_elo.py --eras romantic --games 10 --anchors 1600,2000

Writes validation/elo.json.
"""
import argparse
import json
import random
import shutil
import sys
from pathlib import Path

import chess
import chess.engine
import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backend.app import CFG, get_engine  # noqa: E402
from backend.manners import update_resign_streak, wants_to_resign  # noqa: E402

ERAS = list(CFG["eras"])


def find_stockfish(explicit):
    if explicit:
        return explicit
    for cand in ("stockfish", "/usr/games/stockfish", "/opt/homebrew/bin/stockfish",
                 "/usr/local/bin/stockfish"):
        if shutil.which(cand) or Path(cand).exists():
            return shutil.which(cand) or cand
    raise SystemExit("stockfish not found — brew install stockfish (or --stockfish PATH)")


def play_game(bot, resign_params, sf, movetime, bot_is_white, max_plies):
    """Returns the era bot's score for one game: 1 / 0.5 / 0."""
    board = chess.Board()
    resign_streak = 0
    while not board.is_game_over(claim_draw=True) and board.ply() < max_plies:
        bot_to_move = (board.turn == chess.WHITE) == bot_is_white
        if bot_to_move:
            move, win_prob = bot.pick_move_with_eval(board)
            own = win_prob if board.turn == chess.WHITE else 1.0 - win_prob
            if resign_params:
                resign_streak = update_resign_streak(resign_streak, own, resign_params)
                if wants_to_resign(resign_streak, board.ply(), resign_params):
                    return 0.0                      # the era resigns in period
            board.push(move)
        else:
            result = sf.play(board, chess.engine.Limit(time=movetime))
            board.push(result.move)
    if board.ply() >= max_plies:
        return 0.5                                   # adjudicated: nobody broke through
    result = board.result(claim_draw=True)
    if result == "1/2-1/2":
        return 0.5
    white_won = result == "1-0"
    return 1.0 if white_won == bot_is_white else 0.0


def expected(rating, opp):
    return 1.0 / (1.0 + 10 ** ((opp - rating) / 400.0))


def fit_elo(games):
    """games: list of (anchor_elo, score). MLE rating via bisection on the
    monotone score equation Σ expected(R) = Σ score."""
    total = sum(s for _, s in games)
    lo, hi = 400.0, 3400.0
    for _ in range(60):
        mid = (lo + hi) / 2
        if sum(expected(mid, e) for e, _ in games) < total:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def bootstrap_ci(games, n=1000, seed=0):
    rng = random.Random(seed)
    fits = sorted(fit_elo([games[rng.randrange(len(games))] for _ in games])
                  for _ in range(n))
    return fits[int(0.025 * n)], fits[int(0.975 * n)]


def main(eras, anchors, games_per_anchor, movetime, max_plies, sf_path, out_path):
    sf = chess.engine.SimpleEngine.popen_uci(sf_path)
    results = {}
    try:
        for era in eras:
            bot = get_engine(era)
            resign_params = CFG["eras"][era].get("resign")
            era_games = []
            by_anchor = {}
            for anchor in anchors:
                sf.configure({"UCI_LimitStrength": True, "UCI_Elo": anchor})
                score = 0.0
                for g in range(games_per_anchor):
                    s = play_game(bot, resign_params, sf, movetime,
                                  bot_is_white=(g % 2 == 0), max_plies=max_plies)
                    era_games.append((anchor, s))
                    score += s
                by_anchor[anchor] = score
                print(f"{era:<12} vs SF{anchor}: {score:.1f}/{games_per_anchor}")
            elo = fit_elo(era_games)
            lo, hi = bootstrap_ci(era_games)
            total = sum(s for _, s in era_games)
            results[era] = {
                "elo": round(elo), "ci95": [round(lo), round(hi)],
                "games": len(era_games),
                "score_by_anchor": {str(a): s for a, s in by_anchor.items()},
            }
            if total == 0:
                results[era]["note"] = "lost every game — true rating is below the ladder; add lower anchors"
            elif total == len(era_games):
                results[era]["note"] = "won every game — true rating is above the ladder; add higher anchors"
            print(f"{era:<12} -> ~{elo:.0f} (95% CI {lo:.0f}–{hi:.0f})"
                  + (f"  [{results[era]['note']}]" if "note" in results[era] else "") + "\n")
    finally:
        sf.quit()
    out = {
        "method": "vs Stockfish UCI_LimitStrength ladder, MLE performance rating, "
                  "bootstrap 95% CI; era resignation manners applied; "
                  "engine-calibrated — treat as approximate for human opponents",
        "anchors": anchors, "movetime": movetime, "eras": results,
    }
    json.dump(out, open(out_path, "w"), indent=2)
    print(f"Wrote {out_path}")
    ratings = [r["elo"] for r in results.values()]
    if len(ratings) > 1:
        print(f"Spread across eras: {max(ratings) - min(ratings)} Elo "
              "(small spread = the 'style, not strength' claim holds)")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--eras", help="comma-separated era ids (default: all from config)")
    p.add_argument("--anchors", default="1400,1700,2000,2300",
                   help="Stockfish UCI_Elo ladder (SF16 floor is 1320)")
    p.add_argument("--games", type=int, default=30, help="games per era per anchor")
    p.add_argument("--movetime", type=float, default=0.05, help="SF seconds/move")
    p.add_argument("--max-plies", type=int, default=300)
    p.add_argument("--stockfish", help="path to stockfish binary")
    p.add_argument("--out", default=str(ROOT / "validation" / "elo.json"))
    a = p.parse_args()
    eras = a.eras.split(",") if a.eras else ERAS
    unknown = set(eras) - set(ERAS)
    if unknown:
        raise SystemExit(f"Unknown era(s): {sorted(unknown)}")
    main(eras, [int(x) for x in a.anchors.split(",")], a.games,
         a.movetime, a.max_plies, find_stockfish(a.stockfish), a.out)
