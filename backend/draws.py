"""Draw-agreement modeling: the social layer chess engines lack.

Bots never *agree* to draws, so their games run long and their draw rates sit
below history (see the "Honest residuals" note on /validation). The rule here
models the agreement as behavior: a player becomes willing to agree when the
game has looked dead equal for a while and enough of the game has been played
— with era-specific willingness (config/eras.yaml `draws:` per era).

The signal is the model's own win-probability head (the same one used for
resignation adjudication in scripts/selfplay.py). The server is stateless —
every request carries a FEN — so the consecutive-equal counter (`streak`)
travels with the client and is echoed back updated on each /api/play response.

Used by backend/app.py (live play) and scripts/selfplay.py (validation).
"""


def in_band(white_win_prob: float, params: dict) -> bool:
    """Is this evaluation inside the era's dead-equal band around 0.5?"""
    return abs(white_win_prob - 0.5) <= params["band"]


def update_streak(streak: int, white_win_prob: float, params: dict) -> int:
    """Advance the consecutive-dead-equal counter with a new evaluation.

    Negative values act as a cooldown (e.g. after a declined offer): the
    counter must climb back through zero before willingness can rebuild.
    """
    return streak + 1 if in_band(white_win_prob, params) else min(streak, 0)


def wants_draw(streak: int, fullmove_number: int, params: dict) -> bool:
    """Would this era agree to a draw here? (offer and accept use the same rule)"""
    return streak >= params["streak"] and fullmove_number >= params["min_move"]
