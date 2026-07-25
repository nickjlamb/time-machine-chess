# Handover brief: the year slider ("play any year")

Context doc for the next working session. Read alongside README.md (architecture,
pipeline) and validation/baselines.md. Successor to docs/next-era-classifier.md,
which produced v0.6.0 (the classifier, social sharing, chess.com support). The
format works: keep this open, build in the sandbox on heuristics, validate on
the Mac with real models.

**PARKED (July 2026), with a revised ordering agreed at parking time.** The
slider-as-play-feature is the weak claim — the classifier's confusion matrix
shows adjacent decades are imperceptible, so "play 1943" adds little over the
era buttons, and a shared conditioned model risks flattening the era character
that IS the product. The strong ideas extracted from it, in recommended order:
1. **Theory explorer on the five existing checkpoints** (days, not weeks):
   probe_position.py swept across eras for a fixed position, curves rendered
   in house style — "watch the King's Gambit die" is the shareable artifact
   and needs no new model. Build this first on resume.
2. **Phase 0 conditioning experiment** (~1 day, Mac): the elo-slot decade
   hack below. Its result — crisp gradients vs mush — decides whether the
   full slider ever gets built. Don't build past the receipts.
3. Full slider only if Phase 0 earns it. The design sketch below stands.

**Maia-3 watch (assessed July 2026, not adopted).** CSSLab released Maia-3
(github.com/CSSLab/maia3): "Chessformer" transformers (paper:
arxiv.org/abs/2605.19091), 3M–79M params, UCI engine with Elo conditioning,
temperature/top-p sampling, and 8-move history input. Three blockers ruled it
out for now: (1) inference-only repo — no training/fine-tuning code, and era
fine-tuning is this project; (2) no value/win-probability head — the entire
tuned social layer (draws, resignation) and eval-driven serving depend on
Maia-2's; (3) AGPL-3.0 vs Maia-2's MIT. Why it stays on watch: the 5M model
could hold ALL era models resident in less RAM than one Maia-2 checkpoint
(kills MAX_LOADED_MODELS, instant era switching, fast classifier), and 3M
makes in-browser inference conceivable. **Tripwire: if CSSLab ships training
code AND a value head, spend half a day probing it on the Mac.** The
Chessformer paper is also relevant reading before any year-slider work — a
history-aware transformer with conditioning slots is the shape a
year-conditioned model wants.

## The goal

One year-conditioned model instead of five era checkpoints: drag a slider from
1840 to 2019 and play that year. Beyond the UI, this unlocks the **theory
explorer** — fix a position, sweep the year, and watch the King's Gambit die in
real time — and collapses ~2.6GB of checkpoints into one, making Railway's
MAX_LOADED_MODELS juggling obsolete.

## Design sketch (proposed, not yet discussed)

- **Conditioning**: Maia-2 already conditions on (elo_self, elo_oppo) category
  embeddings; we fix both at NOMINAL_ELO 1900. Two paths:
  - **Phase 0 (de-risk, ~1 day)**: repurpose the elo_oppo slot as a decade
    category — no architecture change, no fork. Train one model on all decades
    with rows tagged (elo_cat_1900, decade_cat). If one epoch of fine-tuning
    makes the conditioning bite (probe_position.py sweep shows KG probability
    falling with decade), the concept works.
  - **Phase 1 (real thing)**: a proper year embedding added to the maia2 model.
    maia2 is pip-installed — read `maia2/model.py` (61 lines, small) and
    training/finetune_era.py first; the likely move is a vendored/subclassed
    model with an extra embedding summed where the elo embeddings enter, loaded
    from pretrained with strict=False. Decade buckets (18) are plenty —
    the classifier's confusion matrix says adjacent decades blur anyway.
- **Data**: per-decade balanced subsets (~10k games each), same discipline as
  eras. Raw Lumbra files on disk cover 1840–1999 and 2010–2019, including the
  gap years the eras skip (1886–99, 1940–49, 1986–89 are in the source files,
  just never filtered). **2000–2009 is missing entirely** — download that
  Lumbra decade file first or the slider has a hole in it. filter_eras.py
  splits by configured era windows only; write a decade-mode variant (or
  drive it from a decades section in eras.yaml — keep it config-driven).
- **Validation (the receipt)**: two layers. (1) Self-play at sampled years
  (1850, 1900, 1930, 1960, 1990, 2015) through the existing
  selfplay/analyze_selfplay machinery — the era gradients must reproduce
  *monotonically along the slider*: KG rate falls, draw rate rises, 1.d4/1.c4
  share rises. (2) The classifier methodology, rotated: score held-out games
  of known year under a grid of slider years, report predicted-vs-true year
  MAE. Expect ±15–20 years — the era classifier's 42%/88% numbers and its
  soviet/modern blur bound how sharp year identification can possibly be.
  Don't over-claim past that noise floor.
- **Social layer**: draws/resign constants are tuned per era (eras.yaml, with
  history in comments). For the slider, linearly interpolate the constants
  between era anchor years as a first cut — but that's an assumption; check
  draw rates at mid-gap years (e.g. 1943) look sane before shipping.
- **Serving**: /api/move and /api/play gain an optional `year`; era ids map to
  a representative year for back-compat (era buttons become slider presets).
  One resident model ends the LRU dance, but keep the five era checkpoints
  and code paths until the year model validates — era bots are the shipped
  product, the slider is the experiment.
- **Frontend**: slider on the board page with era-anchor tick labels and the
  five portraits as stops. Theory explorer as a separate page or /validation
  section: probe a fixed position across the year sweep, render move-prob
  curves (zero-dependency SVG polylines fit the house style).

## Key facts the repo doesn't state explicitly

- Everything in docs/next-era-classifier.md's version of this section still
  holds: config-driven era list everywhere, TMC_FORCE_HEURISTIC test split,
  NOMINAL_ELO 1900 load-bearing, never assert on a neural model's opinion.
- New since: `backend/classifier.py` (sampling + scoring utilities — reuse
  `sample_positions`/`score_positions` for year-MAE validation),
  `Maia2Engine.move_probs` / `move_probs_batch` (batched via maia2's
  `inference_batch`, which **rounds probs to 4dp** — floor before log, see
  PROB_FLOOR), `scripts/probe_position.py` (per-era move distributions for
  any position — the theory explorer is this script plus a sweep and a chart),
  `scripts/classify_validation.py` (held-out exclusion pattern: training
  subsets reproduce with seed 42 + caps romantic=10000, others=12000 —
  verified byte-exact against the pkls).
- Training corpora: data/training/*.pkl are the actual subsets used
  (725k–946k rows each). Corpus offsets verified unchanged since training.
- Classifier validation receipts (validation/classifier.json, on /validation):
  single-game 42% vs 20% chance, 20-game batches 88%. Confusion structure:
  romantic unmistakable, digital↔modern nearly one era, soviet the universal
  donor. The year model will inherit these blurs — design the receipts to
  show gradients, not decade-sharp claims.
- Corpus-grep receipts technique (good for Reddit threads and commentary):
  the era PGNs are plain text on the Mac; regex over movetext answers "what
  did period players actually do here" in seconds. Example that shipped: the
  Romantics accepted the King's Gambit 81% (1,114/1,377) but declined the
  Vienna Gambit 92% — accepting is bad there and they knew it.

## Operational gotchas (learned the hard way)

- Nick's shell is zsh: no inline # comments in suggested commands; one
  command per line.
- The Claude sandbox cannot reach: GitHub raw/releases, Wikimedia, Railway,
  lichess, chess.com, CDNs. API integrations get built blind and tested on
  the Mac (both the lichess and chess.com fetch paths worked first try —
  the pattern is fine, just test promptly). The sandbox CAN run the backend,
  the full test suite (46 tests, heuristic engines, no torch), and Playwright
  (chromium at /opt/pw-browsers/chromium-1194/chrome-linux/chrome,
  args=['--no-sandbox']) for frontend verification — screenshot everything
  before shipping frontend changes.
- In the sandbox, pip `chess` sdist build fails — extract the pure-Python
  package from the tarball into site-packages instead.
- The device bridge's Linux VM has python3 and the mounted repo (grep/pickle
  work on corpora and pkls in place) but no torch — model inference only on
  the Mac (`--device mps` for training).
- macOS: python3/pip3. Railway auto-deploys on push (empty commit re-pushes a
  missed webhook); PORT=8000 and MAX_LOADED_MODELS=1 are load-bearing.
- Weights: GitHub release weights-v1, `gh release upload weights-v1
  models/{era}.pt`; Dockerfile pulls tolerantly. A year model is a new
  artifact name — extend fetch_models.py and the Dockerfile the same way.
- git hygiene: Lumbra PGNs, data/eras/, data/training/ never get committed
  (CC BY-NC-SA). validation/*.json DO get committed (the pages read them).

## State at handover

v0.6.0 live at chess.pharmatools.ai, 46 tests green. The era classifier
shipped end to end: lichess + chess.com username fetch and PGN paste, NDJSON
streaming progress, era mix with evidence-budget softening (REFERENCE_POSITIONS
in classifier.py — the calibration knob), verdict lines per era in eras.yaml,
characteristic-move cards with after-move diagrams and lichess deep links
(/black#ply — chess.com has no move-anchor URLs, confirmed), stateless share
links (?r=era:pct,…) with native/X/Reddit/WhatsApp sharing, confusion matrix
on /validation, cross-link card on the main page sidebar, page restructured
into numbered steps with a poster-style verdict panel. Distribution: classifier
announcement + two technical replies (Vienna Gambit receipts, "how does a
policy net play unseen positions") posted to Reddit by Nick. Roadmap after
the slider: era commentary (probe_position.py + corpus-grep receipts are
halfway there), a 2020s era, mobile PWA polish, per-result OG images for
richer share previews.
