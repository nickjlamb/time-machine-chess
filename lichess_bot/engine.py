"""The era brain behind a Lichess BOT account.

Deliberately free of any lichess-bot framework imports: everything here is
plain Python + python-chess, so it can be unit-tested in CI (where neither
the framework nor the model weights exist). The thin framework adapter — the
`MinimalEngine` subclass lichess-bot actually instantiates — lives next door
in homemade.py and does nothing but translate `EraBot.decide()` into a
`chess.engine.PlayResult`.

One process serves one era, chosen by the TMC_ERA environment variable
(default: romantic, the pilot). The era list is read from config/eras.yaml —
never hardcoded here.

Manual check on a box with the weights (prints move latency, which is what
decides whether this account can safely accept blitz):

    TMC_ERA=romantic python -m lichess_bot.engine --selfcheck
"""
import logging
import os
import sys
import time
from dataclasses import dataclass

import chess

from backend.engine_pool import CFG, get_engine
from backend.turn import play_turn, would_accept_draw

logger = logging.getLogger(__name__)

DEFAULT_ERA = "romantic"


def era_from_env() -> str:
    """Which era this process plays. Validated against config/eras.yaml."""
    era = os.environ.get("TMC_ERA", DEFAULT_ERA).strip().lower()
    if era not in CFG["eras"]:
        raise SystemExit(
            f"TMC_ERA={era!r} is not a configured era. "
            f"Choose one of: {', '.join(CFG['eras'])}"
        )
    return era


@dataclass
class BotDecision:
    """What the bot wants lichess-bot to do with this turn."""
    move: chess.Move | None
    resign: bool = False
    offer_draw: bool = False     # also how an incoming offer is accepted
    win_prob: float | None = None
    seconds: float = 0.0


class EraBot:
    """One era, one game. Holds the draw/resignation streak counters.

    lichess-bot builds a fresh engine per game, so instance state is
    per-game state — which is exactly what the streak counters need. (On the
    website the same counters ride along with the browser instead, because
    that server is stateless. Same rules, different carrier.)
    """

    def __init__(self, era: str | None = None, engine=None):
        self.era = era or era_from_env()
        self.era_cfg = CFG["eras"][self.era]
        self._engine = engine          # injectable for tests
        self.draw_streak = 0
        self.resign_streak = 0
        self.moves_played = 0

    @property
    def engine(self):
        """The era engine, loaded on first use (~700MB for a real checkpoint)."""
        if self._engine is None:
            self._engine = get_engine(self.era)
            kind = type(self._engine).__name__
            if kind != "Maia2Engine":
                logger.warning(
                    "Era %r is being served by %s, NOT the trained checkpoint. "
                    "Run scripts/fetch_models.py — otherwise this account plays "
                    "the placeholder heuristic on Lichess.", self.era, kind)
            else:
                logger.info("Era %r loaded from the trained checkpoint.", self.era)
        return self._engine

    @property
    def name(self) -> str:
        return self.era_cfg.get("name", self.era)

    def decide(self, board: chess.Board, draw_offered: bool = False) -> BotDecision:
        """Choose this turn's action. `board` has the era to move; not mutated."""
        started = time.monotonic()
        turn = play_turn(self.engine, self.era_cfg, board,
                         draw_streak=self.draw_streak,
                         resign_streak=self.resign_streak)
        self.draw_streak = turn.draw_streak
        self.resign_streak = turn.resign_streak
        elapsed = time.monotonic() - started

        if turn.resigns:
            logger.info("[%s] resigns on move %d (win prob %.3f) — era manners",
                        self.era, board.fullmove_number, turn.win_prob or 0.0)
            return BotDecision(move=turn.move, resign=True,
                               win_prob=turn.win_prob, seconds=elapsed)

        offer = turn.offers_draw
        if draw_offered and not offer:
            # Accepting is the same rule as offering, judged on the evaluation
            # we just computed (the freshest one available at our turn).
            offer = would_accept_draw(self.era_cfg, turn.win_prob,
                                      self.draw_streak, board.fullmove_number)
            if offer:
                logger.info("[%s] accepts the draw offer on move %d",
                            self.era, board.fullmove_number)
        elif offer:
            logger.info("[%s] offers a draw on move %d (streak %d)",
                        self.era, board.fullmove_number, self.draw_streak)

        self.moves_played += 1
        logger.debug("[%s] %s in %.2fs (win prob %s)", self.era,
                     turn.move.uci() if turn.move else "-", elapsed,
                     f"{turn.win_prob:.3f}" if turn.win_prob is not None else "n/a")
        if elapsed > 5.0:
            logger.warning("[%s] move took %.1fs — too slow for blitz; check CPU "
                           "headroom or reduce accepted time controls.", self.era, elapsed)
        return BotDecision(move=turn.move, offer_draw=offer,
                           win_prob=turn.win_prob, seconds=elapsed)


def _selfcheck(max_plies: int = 60) -> int:
    """Play the era against itself locally: proves the checkpoint loads and
    measures per-move latency. No network, no Lichess account needed."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    bot = EraBot()
    # Two seats sharing one loaded model: the manners counters are per-player,
    # so a single instance playing both sides would mix them.
    seats = {chess.WHITE: bot, chess.BLACK: EraBot(era=bot.era, engine=bot.engine)}
    print(f"Era: {bot.era} ({bot.name})")
    board = chess.Board()
    times = []
    while not board.is_game_over(claim_draw=True) and board.ply() < max_plies:
        decision = seats[board.turn].decide(board)
        times.append(decision.seconds)
        if decision.resign:
            print(f"  resigned at ply {board.ply()}")
            break
        print(f"  {board.fullmove_number}. {board.san(decision.move)}"
              f"   [{decision.seconds:.2f}s"
              + (f", win prob {decision.win_prob:.3f}" if decision.win_prob is not None else "")
              + (", offers draw" if decision.offer_draw else "") + "]")
        board.push(decision.move)
    if times:
        print(f"\nEngine: {type(bot.engine).__name__}")
        print(f"Moves: {len(times)}   mean {sum(times)/len(times):.2f}s   "
              f"max {max(times):.2f}s")
        print("Blitz (3+2) is comfortable under ~1s/move; bullet needs ~0.2s.")
    return 0


if __name__ == "__main__":
    sys.exit(_selfcheck() if "--selfcheck" in sys.argv else
             print(__doc__.strip()) or 0)
