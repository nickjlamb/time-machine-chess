"""Adapter: hands the era brain to the lichess-bot framework.

lichess-bot resolves `engine.name` in config.yml against the module named
`homemade` sitting in its own checkout, so this file is COPIED into the
lichess-bot directory at deploy time (see the Dockerfile and README here).
It is the only file in this project that imports the framework — everything
with judgement in it lives in engine.py, which stays testable in CI.

TMC_ROOT must point at the Time-Machine Chess checkout (default /app, which
is where the Dockerfile puts it) so `backend.*` is importable from inside
the lichess-bot directory.
"""
import logging
import os
import sys

_ROOT = os.environ.get("TMC_ROOT", "/app")
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import chess  # noqa: E402
from chess.engine import PlayResult  # noqa: E402
from lib.engine_wrapper import MinimalEngine  # noqa: E402

from lichess_bot.engine import EraBot  # noqa: E402

logger = logging.getLogger(__name__)


class ExampleEngine(MinimalEngine):
    """Kept because the framework's own `test_bot.homemade` does
    `from homemade import ExampleEngine` at import time — and
    `get_homemade_engine()` imports that module unconditionally, even when
    resolving a non-test engine. Replacing the stock homemade.py without this
    name makes lichess-bot fail to start at all, with an ImportError that
    reads as if our engine were missing. (Found by wiring this file into a
    real lichess-bot checkout; see tests/test_lichess_bot.py.)"""


class TimeMachineEra(MinimalEngine):
    """A Time-Machine Chess era, playing as itself on Lichess.

    Set `engine.name: TimeMachineEra` in config.yml with
    `engine.protocol: homemade`; pick the era with the TMC_ERA env var.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.bot = EraBot()
        logger.info("Time-Machine Chess: playing the %s", self.bot.name)

    def search(self, board: chess.Board, time_limit, ponder: bool,
               draw_offered: bool, root_moves) -> PlayResult:
        """One move, with the era's draw and resignation manners attached.

        Note on draws: on the Lichess board API, offering a draw when one is
        already on the table *is* accepting it — so a single `draw_offered`
        flag covers both, exactly as the era rule intends (it offers and
        accepts by the same test).
        """
        decision = self.bot.decide(board, draw_offered=draw_offered)
        if decision.resign:
            # lichess-bot ignores the move and sends a resignation.
            return PlayResult(decision.move, None, resigned=True)
        return PlayResult(decision.move, None, draw_offered=decision.offer_draw)
