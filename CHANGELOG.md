# Changelog

All notable changes to Time-Machine Chess.

## [0.3.0] — 2026-07-23

Era-accurate resignation manners — and the last big validation residual closed. 🏳️

### Added
- **Resignation manners** (`backend/manners.py`): each era resigns by its own culture —
  threshold, streak and minimum ply on the model's win-probability head. The Soviet school
  resigns promptly and correctly; the Classical era concedes to sound technique; Romantics
  play on toward the mate. Params per era in `config/eras.yaml`.
- **The bot can resign to you** in live play, with era-voiced banners ("lays down the king
  with a flourish" / "resigns without ceremony"). Client-carried `resignStreak`, same
  stateless pattern as draw offers.
- **Material advantage indicator** beside the captured pieces (lichess-style "+3"),
  computed from the board so promotions count correctly.
- `TMC_FORCE_HEURISTIC` env var: tests now get deterministic material-sigmoid evals even
  on machines with the trained checkpoints installed.

### Changed
- **Captured-pieces layout**: the bot's captures sit in a permanent strip above the board,
  yours below it — board and sidebar tops stay aligned, everything fits without scrolling,
  and the board never shifts mid-game.
- **Draw + resignation constants co-tuned** against history (they interact — prompt
  resignation eats would-be draws). Final validation, 150 games/era: draw rates
  15.3% / 24.7% / 26.0% vs 12.0% / 25.0% / 28.75% historical; average game length
  79.1 / 74.5 / 69.1 plies vs 73.9 / 77.5 / 72.7. The launch residual ("8–10 points
  fewer draws, ~25 plies longer") is closed.

### Fixed
- **Board orientation**: the bottom-right square is now light (h1/a8), as the rulebook
  demands. Spotted by a player — of course.

## [0.2.0] — 2026-07-23

The social layer: era bots now agree to draws. 🤝

### Added
- **Draw-agreement modeling** (`backend/draws.py`): a bot offers or accepts a draw once its
  own win-probability head has sat in a dead-equal band for an era-specific stretch of moves.
  The Soviet school concedes readily (the grandmaster draw lives), the Classical era is
  moderate, Romantics almost never agree. Willingness params per era in `config/eras.yaml`.
- **Live play**: "½ Offer draw" button — the era declines in period voice; bot draw offers
  with an Accept/Decline banner; moving with an offer open declines it (proper etiquette),
  and both sides observe cooldowns. `/api/play` carries the dead-equal streak client-side
  (the server stays stateless) and surfaces `winProb`; new `/api/draw-offer` endpoint that
  deliberately never advances the streak, so button-spamming can't manufacture agreement.
- **Validation**: mutual agreement adjudicated in self-play (`Termination: draw agreed`).
  Bot draw rates now land within ~1.5 points of history in all three eras —
  13.3% / 25.3% / 30.0% vs. 12.0% / 25.0% / 28.75% historical — closing the largest
  documented residual. `/validation` residuals updated accordingly.
- Heuristic fallback engines gained a material-sigmoid `pick_move_with_eval`, so draw logic
  (and its 9 new tests) runs without model weights in CI.

## [0.1.0] — 2026-07-21

First public release. 🎉

### The idea
Chess engines fine-tuned per historical era, validated against the record: play the 1850 meta.

### Added
- **Three era models** fine-tuned from Maia-2 (NeurIPS 2024) on Lumbra's Gigabase OTB games:
  Romantic (1840–1885), Classical (1900–1939), Soviet (1950–1985). All beat pre-finetune
  move-prediction baselines (+4.8 / +3.8 / +3.4 points held-out accuracy).
- **Validation pipeline**: 150 self-play games per era with resignation adjudication from the
  model's own win-probability head, scored on identical move-sequence metrics vs. historical
  corpora. Headline: King's Gambit gradient 22% → 4.7% → 0.7% (history: 14% → 3.5% → 1.25%).
  Live at `/validation`, honest residuals documented.
- **Web app** (zero-dependency frontend): era picker with public-domain portraits, era-themed
  board palettes and piece sets (Merida / cburnett / Alpha), theory snapshots (style meters,
  typical openings, great players), play as White or Black, click-to-move with legal-move
  highlighting, move animation, synthesized Web Audio move sounds, PGN-style scoresheet,
  era ◀ ▶ navigation.
- **Engine serving**: FastAPI backend, policy sampling without search, opening-diversity
  temperature schedule, lazy LRU model cache (`MAX_LOADED_MODELS`), optimistic client-side move
  rendering (zero-latency player moves), humanized bot thinking delay.
- **Data + training tooling**: era corpus builder, Maia-2 training-row converter (mirroring,
  fixed-Elo conditioning), fine-tune script (CUDA/MPS/CPU), sanity gate, corpus statistics.
- **Ops**: Dockerfile (CPU torch, weights pulled from GitHub Releases), Railway config,
  GitHub Actions CI, API test suite that runs without model weights.

### Deployed
- Live at [chess.pharmatools.ai](https://chess.pharmatools.ai) (Railway, ~1GB RAM footprint).

[0.3.0]: https://github.com/nickjlamb/time-machine-chess/releases/tag/v0.3.0
[0.2.0]: https://github.com/nickjlamb/time-machine-chess/releases/tag/v0.2.0
[0.1.0]: https://github.com/nickjlamb/time-machine-chess/releases/tag/v0.1.0
