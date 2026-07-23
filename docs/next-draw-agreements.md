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

## Implementation status (2026-07-23)

Implemented per the design sketch above. What landed:

- `backend/draws.py` (new): the shared rule — `in_band` / `update_streak` / `wants_draw`.
  Negative streak values act as a cooldown after a declined offer.
- `config/eras.yaml`: per-era `draws:` params (band / streak / min_move) — soviet 0.10/4/18,
  classical 0.06/5/30, romantic 0.02/12/70. **Starting constants, untuned** — tune against
  12.0% / 25.0% / 28.75% after the self-play rerun.
- `backend/engines.py`: `HeuristicEraEngine.pick_move_with_eval` (material sigmoid, equal
  material = exactly 0.5) so draw logic and tests run without torch/CI weights.
- `backend/app.py`: `/api/play` accepts + echoes `drawStreak` (client-carried; server stays
  stateless), returns `winProb` and `botOffersDraw` (offer rides along with the bot's move,
  computed on the pre-move eval). New `/api/draw-offer` endpoint for the player's button —
  same willingness rule; deliberately does NOT advance the streak (no spam-to-agreement).
- `scripts/selfplay.py`: mutual agreement as one check; PGN `Termination: draw agreed
  (adjudicated)`. Smoke-tested with a pinned-0.5 stub: agreement fires at move 18/30/70.
- `frontend/index.html`: "½ Offer draw" button next to Resign; bot-offer banner with
  Accept/Decline; era-flavored decline lines; moving while an offer is open declines it;
  decline cooldowns both ways (bot waits ~6 moves to re-offer, player button rests 5).
- `tests/test_draws.py`: 9 new tests (era gradient, min-move, streak reset, offer endpoint).

**Done — validated and tuned (2026-07-23).** First rerun: romantic 13.3% and classical
25.3% landed on target immediately; soviet overshot to 64% on (0.10/4/18), retuned to
(0.07/5/25) — slightly more willing than classical, whose constants hit exactly — and
landed at 30.0% vs 28.75% historical (26 of 45 draws by agreement). All eras within
~1.5 points. Updated: validation.html (method + residuals), README (receipts table,
design choices, API example, roadmap box ticked), CHANGELOG (v0.2.0). Remaining
residual is resignation timing — decisive games run ~15–20 plies long — already on
the README roadmap as "era-accurate resignation manners".

## Addendum: resignation manners and the joint tune (v0.3.0)

Era resignation followed (`backend/manners.py`, `resign:` params per era) and revealed an
interaction: prompt resignation truncates games before they reach the draw-agreement zone,
so the two social layers must be **tuned jointly**. Four tuning rounds later (history in
the eras.yaml comments), final numbers vs history: draws 15.3/24.7/26.0 vs 12/25/28.75,
avg plies 79.1/74.5/69.1 vs 73.9/77.5/72.7 — era gradient reproduced, launch residual
closed. Also learned: tests must force heuristic engines (`TMC_FORCE_HEURISTIC`) because
the real models' win-prob head is uncalibrated on artificial test positions (it rated an
equal R-vs-R endgame 0.12 for White). Remaining honest residual: the 1.e4 first-move lean.

## State at handover

Live at chess.pharmatools.ai (Railway, ~$10/mo of included credit). v0.1.0 released; launch
distribution in progress (HN flagged — email to hn@ycombinator.com pending; r/chess needs
modmail; r/ComputerChess + TalkChess friendly alternatives). Games counter live past 25 games.
Roadmap after draws: 4th era (1990s), era commentary, year slider (await launch feedback).
