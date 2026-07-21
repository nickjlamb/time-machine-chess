# Changelog

All notable changes to Time-Machine Chess.

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

[0.1.0]: https://github.com/nickjlamb/time-machine-chess/releases/tag/v0.1.0
