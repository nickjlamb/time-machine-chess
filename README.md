# Time-Machine Chess

Play chess against the theory and style of a past era. See `docs/mvp-scope.md` for the full MVP scope and sprint plan.

## Status

- [x] Project scaffold, playable app with **heuristic era bots** (placeholder engines with era-flavored move selection)
- [ ] Era corpora built from dated PGN data (`scripts/`)
- [ ] Maia-2 fine-tuned era models (replaces heuristic engines)
- [ ] Validation page with era-signature charts

The app works end-to-end **today** using heuristic bots, so UX and game flow can be developed in parallel with training. Swap in trained models later via `backend/engines.py`.

## Quick start

```bash
pip install -r requirements.txt
uvicorn backend.app:app --reload
# open http://localhost:8000
```

## Data pipeline (Days 1–2)

1. Download a dated master-games database (free options):
   - **Lumbra's Gigabase** — https://lumbrasgigabase.com (largest free option, dated OTB games)
   - **Caissabase** — http://caissabase.co.uk
   Place the combined PGN at `data/master_games.pgn` (concatenate multiple files if needed).
2. Split into era corpora:
   ```bash
   python scripts/filter_eras.py data/master_games.pgn
   ```
   Writes `data/eras/romantic.pgn`, `classical.pgn`, `soviet.pgn` per the date ranges in `config/eras.yaml`.
3. Check corpus health:
   ```bash
   python scripts/corpus_stats.py
   ```
   Reports game counts, date histograms, and baseline era metrics (gambit rate, capture rate, game length) — these numbers become the validation-page baselines.

## Training (Days 3–4)

```bash
pip install maia2 torch

# 1. Convert era PGNs to Maia-2 training rows (~750k positions/era, minutes each)
python3 scripts/prepare_training.py romantic
python3 scripts/prepare_training.py classical --max-games 12000
python3 scripts/prepare_training.py soviet   --max-games 12000

# 2. Fine-tune per era (GPU: Colab/RunPod; or --device mps on Apple Silicon; CPU works overnight)
python3 training/finetune_era.py romantic
python3 training/finetune_era.py classical
python3 training/finetune_era.py soviet
```

Checkpoints land in `models/{era}.pt` with held-out accuracy in `models/{era}.meta.json`
(final_acc must beat base_acc — proof the model absorbed the era). Then set
`engine: maia2` per era in `config/eras.yaml` and restart the backend.

For Colab: upload the repo folder (or just `scripts/`, `training/`, `data/training/*.pkl`),
select a GPU runtime, and run the same commands.

**Day-4 sanity gate (do not skip):** run `python scripts/sanity_gate.py` once models are in place — it compares era models on a set of test positions. Romantic must prefer materially risky, attacking moves where Soviet consolidates. If the models aren't distinguishable, stop and fix before any UI work.

## License

Code: [MIT](LICENSE). Maia-2 (model + code): MIT, [CSSLab](https://github.com/CSSLab/maia2).
Training data: [Lumbra's Gigabase](https://lumbrasgigabase.com), CC BY-NC-SA 4.0 —
not redistributed in this repo; download it yourself per the data pipeline above.

## Repo layout

```
config/eras.yaml     era definitions: date ranges, engine params, flavor copy
scripts/             data pipeline + corpus stats + sanity gate
backend/             FastAPI app + pluggable era engines
frontend/            single-page app (served by the backend)
data/                PGN data (gitignored)
models/              trained checkpoints (gitignored)
validation/          era-signature analysis output for the validation page
```
