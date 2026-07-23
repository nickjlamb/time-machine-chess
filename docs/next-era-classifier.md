# Handover brief: the era classifier ("Which era do you play like?")

Context doc for the next working session. Read alongside README.md (architecture,
pipeline) and validation/baselines.md. Successor to docs/next-draw-agreements.md,
which produced v0.2.0–v0.5.0.

## The goal

Turn the five era models into a mirror: a user supplies their games and gets back an
era diagnosis — "you are 68% Soviet, 20% Romantic, and your queen sacrifices are pure
1850." Cheap to serve, methodologically honest, and the most shareable feature the
project can build from assets it already has.

## Design sketch (agreed)

- **Methodology**: per-move log-likelihood under each era model. For every position in
  the user's games, `inference_each` yields a legal-move probability distribution;
  sum log P(move actually played) per era; normalize across eras → the era mix.
  "Which era's model predicts your moves best" — same spirit as the validation page.
- **Input**: raw PGN paste first (no external dependency, works in tests), lichess
  username second (lichess.org/api/games/user/{username}, NDJSON, no auth — but the
  Claude sandbox cannot reach lichess, so that path is built blind and tested on the
  Mac). Only classify the user's own moves (their color per game).
- **Sampling**: cap positions (~200–400 across up to ~20 games). Skip the first ~6
  plies (opening memory, not style) and consider skipping positions where one side is
  totally lost (forced-ish moves carry no signal). Tune on real data.
- **Serving order matters**: Railway runs MAX_LOADED_MODELS=1. Iterate MODELS in the
  outer loop and positions in the inner loop (load romantic → score every position →
  evict → next era). Per-position-per-era order would LRU-thrash five swaps per move.
- **Performance**: `inference_each` is one position at a time. Five eras × 300
  positions at ~50–100ms each is minutes, not seconds. Investigate maia2's batch
  inference path before building; if batching works, this is seconds. Consider an
  async job endpoint or streamed progress either way.
- **Output**: era percentages + a verdict line in era voice + per-era "most
  characteristic move you played" (the position where that era's model most preferred
  your move relative to the others — this is the shareable artifact).
- **Validation (the house discipline)**: classify held-out historical games and show
  the confusion matrix — 1880s games should come out Romantic, 1970s games Soviet.
  That's the receipt that makes the feature honest, and it belongs on /validation.
  Note the classifier's noise floor: single games are noisy, ~20 games is a diagnosis.
- **Frontend**: one new page (or a card on the main page) in the existing
  zero-dependency style. PGN textarea → results. Era percentages render naturally
  with the existing meter component.

## Key facts the repo doesn't state explicitly

- **The server is stateless**; era list is config-driven EVERYWHERE (argparse
  choices, analyzer, fetch_models, Dockerfile, tests all read config/eras.yaml).
  The classifier must iterate `CFG["eras"]`, never a hardcoded list.
- Engines: backend/engines.py. `Maia2Engine.pick_move_with_eval` wraps
  `inference.inference_each(net, prepared, fen, 1900, 1900)` → (move_probs dict,
  white_win_prob). NOMINAL_ELO 1900 is load-bearing and must match training.
- `HeuristicEraEngine` fallback exists when checkpoints are missing — CI has no
  torch and relies on it. Tests set TMC_FORCE_HEURISTIC=1 (backend/app.py get_engine)
  so results are deterministic even on machines WITH weights. The classifier needs
  the same split: plumbing tested on heuristics in CI, accuracy validated on the Mac
  with real models. The real models' win-prob/eval behavior on artificial test
  positions is uncalibrated (one rated an equal R-vs-R endgame 0.12) — never assert
  on a neural model's opinion in tests.
- Social layer: backend/draws.py + backend/manners.py, per-era params in eras.yaml
  with the full tuning history in comments. Not directly relevant to the classifier
  but the same "signal → era params → validate" pattern.
- Tests: 31 pass without weights (pytest tests/, CI = GitHub Actions, python 3.11).
  Frontend is one file, zero deps; all square DOM writes go through setSquare().
- Weights live in the GitHub release `weights-v1` (`gh release upload weights-v1
  models/{era}.pt`); the Dockerfile pulls them tolerantly (missing era → heuristic).

## Operational gotchas (learned the hard way)

- Nick's shell is zsh: **no inline # comments in suggested commands**; one command
  per line.
- macOS: python3/pip3; training/inference work with `--device mps`.
- Railway auto-deploys on push; a missed webhook is fixed with an empty commit push.
  PORT=8000 is load-bearing; DATA_DIR volume holds stats; MAX_LOADED_MODELS=1 there.
- The Claude sandbox cannot reach: GitHub raw/releases, Wikimedia, Railway, lichess,
  CDNs. Anything needing those runs on Nick's Mac. The sandbox CAN run the backend
  and full test suite (heuristic engines; no torch there). In the sandbox, pip
  install `chess` (the `python-chess` name is a broken legacy alias) — and if the
  sdist build fails, extract the pure-Python package from the tarball.
- Self-play/validation noise at 150 games: draw-rate σ ≈ 3.5 points. Don't tune past
  the noise; the classifier equivalent is not over-claiming accuracy from few games.
- git hygiene: Lumbra source PGNs and data/eras/ never get committed (CC BY-NC-SA).

## State at handover

v0.5.0 live at chess.pharmatools.ai. Five validated eras spanning 1840–2019
(romantic / classical / soviet / digital "Engine Dawn" / modern "Engine Era"), each
with draw agreements and resignation manners tuned to its historical record — draw
rates within ~3 points, game length within ~5 plies, all five. The draw-culture
curve (rises 150 years, plateaus in the engine age) is documented on /validation.
Portraits: Anderssen et al. (public domain), Carlsen (Kontokanis, CC BY-SA 2.0),
Deep Blue (James the photographer, CC BY 2.0) — attribution in README. 31 tests
green. Distribution: "resigns like it's 1974" LinkedIn post shipped
(docs/linkedin-post.md); r/chess and TalkChess variants unwritten. Roadmap after
the classifier: year slider (one era-conditioned model — unlocks the theory
explorer), era commentary, a 2020s era, mobile PWA polish.
