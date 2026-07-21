# Contributing to Time-Machine Chess

Thanks for your interest! This project has a simple philosophy: **the historical context is the
star**. We'd rather ship one era that demonstrably plays in period than ten that don't.

## Getting set up

```bash
git clone https://github.com/nickjlamb/time-machine-chess.git
cd time-machine-chess
pip install -r requirements.txt httpx pytest
uvicorn backend.app:app --reload   # runs with heuristic bots, no weights needed
pytest                             # same suite CI runs
```

For model work: `pip install maia2 torch` and `python3 scripts/fetch_models.py`.

## What we're looking for

- **New eras** — add a block to `config/eras.yaml` (date range, flavor, style params) and run the
  pipeline in the README. A new era PR should include its validation numbers: self-play metrics
  vs. its historical corpus. That's the bar — *"it plays in period, here's the data."*
- **Better era-signature metrics** — sacrifice detection, pawn-structure fingerprints, castling
  timing. Metrics must be computable identically on bot games and historical PGNs.
- **Frontend polish** — the constraint is hard: no frameworks, no build step, no external
  requests. One HTML file per page.
- **Bug fixes** — always welcome, with a test where practical.

## What we'll probably decline

Engine evaluations, clocks, arrows, opening databases, chat, ratings. This isn't a Chess.com
competitor — it answers one question: *how would masters from this era have approached this
position?* Clutter dilutes that.

## Ground rules

- Keep the zero-dependency frontend rule (see above).
- `pytest` must pass; add tests for new API surface.
- Training data: don't commit PGNs or weights to git. Weights ship via GitHub Releases; data is
  CC BY-NC-SA and stays out of the repo.
- One PR = one idea. Small and reviewable beats big and impressive.

## Releases

Tagged releases follow `vX.Y.Z` for code; model weights are released separately as
`weights-vN` with training provenance in `models/*.meta.json`.
