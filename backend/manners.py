"""Era-accurate resignation manners — the second social layer.

Sibling of backend/draws.py (draw agreements). Policy networks grind lost
positions to mate; humans resign — and *when* they resign varied by era.
The Soviet school resigned promptly and correctly; Romantics played on
toward the mate (being mated by a brilliancy was part of the theatre).

The rule: a player becomes ready to resign once their own win probability
(from the model's win-probability head, the same signal draws use) has
stayed below an era threshold for a streak of consecutive evaluations,
past a minimum ply. Era params live in config/eras.yaml under `resign:`.

Used by backend/app.py (live play — the streak counter travels with the
client because the server is stateless) and scripts/selfplay.py
(validation adjudication).
"""


def update_resign_streak(streak: int, own_win_prob: float, params: dict) -> int:
    """Advance the consecutive-hopeless counter with a new evaluation
    (own_win_prob is from the potential resigner's seat)."""
    return streak + 1 if own_win_prob < params["threshold"] else 0


def wants_to_resign(streak: int, ply: int, params: dict) -> bool:
    """Would this era resign here?"""
    return streak >= params["streak"] and ply >= params["min_ply"]
