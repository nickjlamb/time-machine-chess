# Handover brief: draw-agreement modeling

Context doc for the next working session. Read alongside README.md (architecture, pipeline)
and validation/baselines.md (targets).

## The goal

Close the documented validation gap: bot draw rates run 8–10 points below history and games
~25 plies too long because bots never *agree* to draws (see "Honest residuals" on /validation).
Model the draw offer/agreement as social behavior, then re-run validation and update the page.

## Design sketch (agreed)

- Signal: the model's own win-probability head (`Maia2Engine.pick_move_with_eval` returns
  `(move, white_win_prob)` — already used for resignation in `scripts/selfplay.py`).
- A bot offers/accepts a draw when win-prob has stayed in a dead-equal band (e.g. 0.45–0.55)
  for N consecutive evaluations AND move number ≥ era threshold.
- Era-specific willingness (add params to `config/eras.yaml` per era, like `style` params):
  Soviet agrees readily (low move threshold, wide band), Classical moderate, Romantic almost
  never. Tune constants against historical draw rates: 12.0% / 25.0% / 28.75%.
- Self-play: implement in `scripts/selfplay.py` (both "players" same engine — model mutual
  agreement as one check). Re-run 150 games/era, `scripts/analyze_selfplay.py`, commit new
  `validation/results.json`. Success = bot draw rates within a few points of history AND
  avg plies closer to ~73–77.
- Live play: bot may offer a draw (UI banner with Accept/Decline), and an "Offer draw" button
  next to Resign (`frontend/index.html`, game controls card) — bot accepts/declines using the
  same rule. `/api/play` response would need the win-prob surfaced (small backend addition).
- Update the validation page footnote ("Honest residuals") once numbers improve — that
  residual text lives in `frontend/validation.html`.

## Key facts the repo doesn't state explicitly

- **The server is stateless** — every request carries a FEN. Threefold repetition is therefore
  detected client-side from the `positions[]` history (see `isThreefold()` in index.html).
  Draw-offer state (consecutive-equal counter) will need the same treatment: either client-side
  or passed in the request.
- Engines: `backend/engines.py`. `Maia2Engine` lazy-loads via LRU in `backend/app.py`
  (`MAX_LOADED_MODELS`, default 3 local / 1 on Railway). Heuristic fallback exists when
  checkpoints are missing — CI relies on it (no torch in CI).
- `positions[]` on the frontend stores `{fen, move, san}` per ply — powers replay, sounds,
  threefold. Extend rather than duplicate.
- Frontend is one file, zero dependencies, no build step. Sounds are Web Audio modal synthesis
  (`woodTap`). All square DOM writes must go through `setSquare()` (preserves coord labels).
- Tests: `pytest` (13 tests, run without model weights). CI = GitHub Actions.

## Operational gotchas (learned the hard way)

- Nick's shell is zsh: **no inline `#` comments in suggested commands** (parentheses in
  comments break parsing). One command per line.
- macOS: `python3`/`pip3`, training works with `--device mps`.
- Railway auto-deploys on push, but a webhook occasionally misses — fix with
  `git commit --allow-empty -m "Trigger Railway deploy" && git push`. Volume is attached
  (stats at DATA_DIR=/data); PORT=8000 variable is load-bearing.
- The Claude sandbox cannot reach: GitHub raw/releases, Google Drive, Wikimedia, Railway,
  CDNs. Anything needing those downloads runs on Nick's Mac. The sandbox CAN run the backend,
  tests, and models (weights are in the mounted folder).
- Self-play reruns happen on Nick's Mac (`python3 scripts/selfplay.py <era> --games 150`,
  ~15–25 min each; delete `validation/selfplay/*.pgn` first when regenerating).
- Model training conditioning: fixed nominal Elo 1900 everywhere (prepare_training.py and
  Maia2Engine must stay in sync).

## State at handover

Live at chess.pharmatools.ai (Railway, ~$10/mo of included credit). v0.1.0 released; launch
distribution in progress (HN flagged — email to hn@ycombinator.com pending; r/chess needs
modmail; r/ComputerChess + TalkChess friendly alternatives). Games counter live past 25 games.
Roadmap after draws: 4th era (1990s), era commentary, year slider (await launch feedback).
