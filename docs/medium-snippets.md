# Code snippets for the Medium article

All real code from the repo (lightly trimmed docstrings). Medium: use a code
block and set the language to Python for highlighting. Recommended: use 2–3 of
these, not all four — each goes directly under the paragraph indicated.

---

## 1. Policy-only serving with the temperature schedule

**Place under:** "Temperature schedule at serving" (end of *Decision two*).
**Lead-in line:** The entire serving engine is a sample from the policy head:

```python
def pick_move_with_eval(self, board):
    """Returns (move, white_win_prob) — no search, just the policy."""
    move_probs, win_prob = self._inference.inference_each(
        self.net, self._prepared, board.fen(), NOMINAL_ELO, NOMINAL_ELO
    )
    # Era character lives in opening *diversity*: sample the model's true
    # distribution for 10 plies, then sharpen toward its favourites.
    t = self.opening_temperature if board.ply() < self.opening_plies else self.temperature
    moves, probs = zip(*move_probs.items())
    sharpened = [max(p, 1e-9) ** (1.0 / t) for p in probs]
    chosen = random.choices(moves, weights=sharpened, k=1)[0]
    return chess.Move.from_uci(chosen), win_prob
```

---

## 2. The entire social layer

**Place under:** the social-layer section, after "the constants tuned per era
against the historical record."
**Lead-in line:** The whole social layer — 150 years of draw culture and
resignation manners — is four functions:

```python
# Draw agreements: willing once the game has looked dead equal for a while
def in_band(white_win_prob, params):
    return abs(white_win_prob - 0.5) <= params["band"]

def update_streak(streak, white_win_prob, params):
    return streak + 1 if in_band(white_win_prob, params) else min(streak, 0)

def wants_draw(streak, fullmove_number, params):
    return streak >= params["streak"] and fullmove_number >= params["min_move"]

# Resignation: ready once your own chances have stayed hopeless long enough
def update_resign_streak(streak, own_win_prob, params):
    return streak + 1 if own_win_prob < params["threshold"] else 0

def wants_to_resign(streak, ply, params):
    return streak >= params["streak"] and ply >= params["min_ply"]
```

**Optional follow-on (very human, shows the tuning-against-history process —
the inline comments are the actual tuning log):**

```yaml
# config/eras.yaml — two eras' social constants, tuning history in comments
romantic:
  draws:
    band: 0.02      # |win_prob - 0.5| <= band counts as dead equal
    streak: 12      # consecutive dead-equal evaluations required
    min_move: 70    # earliest move to agree — Romantics fight on
  resign:
    threshold: 0.05 # tuned up from 0.04: too-stubborn resignation left
    streak: 4       # long grinds ending as natural draws (17.3% vs 12%
    min_ply: 26     # target, +12 plies). Still the most stubborn era.
soviet:
  draws:
    band: 0.085     # tuning history: (0.10/4/18) 64% pre-resignation;
    streak: 4       # (0.07/5/25) 30% pre- / 20.7% post-resignation ...
    min_move: 28    # later agreement zone, same culture
  resign:
    threshold: 0.07 # softened: over-prompt resignation truncated games
    streak: 3       # and starved the draw zone. Still resigns promptly
    min_ply: 24     # and correctly — just not prematurely.
```

---

## 3. The classifier's core: per-move log-likelihood

**Place under:** *Validation two*, after "sum log-probabilities per era; the
era whose model predicts the game best wins."
**Lead-in line:** The classifier is one loop:

```python
def score_positions(engine, positions):
    """Log-likelihood of each played move under one era model."""
    pairs = [(p["fen"], p["move"]) for p in positions]
    dists = engine.move_probs_batch(pairs)   # one forward pass per 64 positions
    return [math.log(max(dist.get(uci, 0.0), PROB_FLOOR))
            for dist, (_, uci) in zip(dists, pairs)]

# Outer loop: eras, not positions — each 89MB checkpoint loads exactly once
for era in CFG["eras"]:
    logliks[era] = score_positions(get_engine(era), positions)
```

---

## 4. Fitting the Elo estimate

**Place under:** *Validation three*, after the method sentence about maximum
likelihood.
**Lead-in line:** The rating fit is a bisection on the one-unknown score
equation:

```python
def expected(rating, opp):
    return 1.0 / (1.0 + 10 ** ((opp - rating) / 400.0))

def fit_elo(games):                      # games: [(anchor_elo, score), ...]
    total = sum(score for _, score in games)
    lo, hi = 400.0, 3400.0
    for _ in range(60):                  # bisection: expected() is monotone
        mid = (lo + hi) / 2
        if sum(expected(mid, e) for e, _ in games) < total:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2
```
