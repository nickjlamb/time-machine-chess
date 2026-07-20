# Time-Machine Chess — MVP Scope

**One-liner:** Play chess against the theory and style of a past era. Pick 1850, 1920, or 1975 and face a bot trained only on games from that period.

**Constraints:** Solo build, 1–2 week focused sprint, light training budget (<$50 GPU), standalone web app.

---

## MVP feature set

**In scope**

1. Three era bots (fewer, better — resist adding more):
   - **Romantic (1840–1885)** — gambits, sacrifices, king hunts. The headline act.
   - **Classical/Hypermodern (1900–1939)** — Capablanca-to-Nimzowitsch positional era.
   - **Soviet Era (1950–1985)** — deep prep, prophylaxis, grind.
2. Web app: era picker → chessboard → play a full game. Mobile-friendly.
3. Era "flavor" on the picker: 2–3 sentences + a famous game reference per era.
4. **Validation page** — the differentiator. Charts proving each bot plays in period: gambit frequency, sacrifice rate, ECO opening distribution, average game length per era vs. the historical baseline. This is the PharmaTools "prove it works" move.

**Out of scope (v2 backlog)**

- Era-conditioned single model (year slider instead of 3 buttons)
- User accounts, ratings, game history
- "Drop a modern engine line into 1900" mode
- Play-by-year granularity, more eras, engine-era bot
- Commentary/explanations of era-typical moves

---

## Architecture

```
[React + chessground UI] → [FastAPI backend] → [3 fine-tuned policy models]
                                             → [python-chess for rules]
                                             → [optional Stockfish blunder-check]
```

- **Base model:** Maia-2 (CSSLab, PyTorch, open source) — fine-tune per era. PyTorch fine-tuning is far less friction than the lc0/TensorFlow Maia-1 pipeline.
- **Move selection:** sample from the policy head (temperature ~0.5) — no search. Human-like by construction, CPU-cheap to serve.
- **Blunder guard (optional flag):** reject any sampled move Stockfish scores >3 pawns worse than best; resample once. Keeps era flavor while avoiding one-move hangs. Ship it off by default for the Romantic bot — blunders are period-accurate.
- **Hosting:** single small VPS or Fly.io instance; models run CPU inference (~ms per move at nodes=0). ~$10/mo.

## Data plan

- **Source:** Lumbra's Gigabase or Caissabase (free, dated OTB master games, 1800s–present). Filter by date range per era.
- **Expected volume:** Romantic era is thin (~30–60k usable games) — fine for *fine-tuning*, not from-scratch training. Later eras are abundant; cap at ~500k games each so eras are comparable.
- **Cleaning:** dedupe, drop games <10 moves, drop unknown dates. Keep result + ECO tags for the validation page.

## Training plan

- Fine-tune Maia-2 checkpoint separately on each era corpus (3 runs).
- Budget: a few hours per run on a rented GPU (Colab Pro / Lambda / RunPod) — total <$50.
- Sanity gate before building UI: from 20 test positions, the Romantic model should prefer gambit lines / sacrifices where the Soviet model castles and consolidates. If the eras aren't distinguishable at this gate, stop and fix (see Risks).

## Sprint plan (10 working days)

| Days | Work |
|---|---|
| 1–2 | Data: download, filter into 3 era corpora, convert to Maia-2 training format |
| 3–4 | Fine-tune 3 models; run the sanity gate |
| 5 | Backend: FastAPI move endpoint, policy sampling, blunder guard |
| 6–7 | Frontend: era picker, board, game flow, mobile pass |
| 8 | Validation analysis: era-metric charts (gambit %, sac rate, ECO distribution, game length) comparing bot self-play vs. historical corpus |
| 9 | Validation page + era flavor copy |
| 10 | Deploy, playtest, fix, soft-launch post |

## Risks & mitigations

1. **Era models feel "weak," not "period."** Biggest risk. Mitigation: blunder guard + temperature tuning; frame Romantic-era bravado as the feature, not a bug.
2. **Fine-tuning washes out era style** (base model dominates). Mitigation: more epochs / higher LR on era data; fallback is training a small policy net from scratch on the two data-rich eras and accepting a weaker Romantic bot.
3. **Maia-2 pipeline friction.** Mitigation: timebox to day 4; fallback is Maia-1/lc0 route or a simple ResNet policy trained from scratch (~1 day extra).
4. **Romantic data too thin.** Mitigation: widen window to 1830–1900; it's the era users care most about, so protect it.

## Success criteria

- A stranger can play the 1850 bot on their phone within 30 seconds of landing.
- Validation charts show statistically distinct era signatures (e.g., Romantic gambit rate ≥3× Soviet rate).
- Sacrifices happen against you in Romantic games often enough to be felt.

## Launch angle

"I trained chess AIs on 150 years of history so you can play the 1850 meta — and here's the data proving each one plays in period." One blog post (Medium + PharmaTools), Hacker News, r/chess. The validation charts are the shareable asset.
