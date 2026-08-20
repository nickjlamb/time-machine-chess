# Handover: put the era bots on Lichess as real BOT accounts

**Goal.** Let anyone on Lichess challenge the era bots directly (e.g.
`BOT TimeMachine1858`). Every game played there is exposure; each bot's
profile bio links to https://chess.pharmatools.ai and the classifier
("Which era do you play like?") — that's the funnel. This was priority #4
of the growth plan (after Show HN, OG share cards — both done).

## Project state (1 minute)

Time-Machine Chess = five chess bots fine-tuned from Maia-2 on historical
era corpora, served policy-only (no search) at chess.pharmatools.ai
(FastAPI on Railway, auto-deploys on push to GitHub
`nickjlamb/time-machine-chess`). Eras are config-driven from
`config/eras.yaml` — **never hardcode the era list anywhere**. Eras:
romantic 1840–1885, classical 1900–1939, soviet 1950–1985, digital
("Engine Dawn") 1990–1999, modern ("Engine Era") 2010–2019. Measured Elo
~1580–1760 (validation/elo.json).

Key code to reuse — do not reimplement:

- `backend/engines.py` — `Maia2Engine` (checkpoint loading, `move_probs`,
  NOMINAL_ELO 1900 conditioning) and `HeuristicEraEngine` fallback.
- `backend/app.py` — the move-selection recipe lives in the `/api/play`
  handler: sample from the policy with temperature 1.0 for the first 10
  plies, 0.6 after. A Lichess bot must play identically; extract this
  into a shared function rather than copying it.
- `backend/draws.py` / `backend/manners.py` — era-appropriate draw offers
  and resignations (threshold rules on the win-prob head, per-era params
  in eras.yaml). Wiring these in is what makes the bots feel in-period
  (the Romantic bot resigning gallantly is part of the show).
- Era model checkpoints: `models/{era}.pt` (~gitignored; fetched from the
  GitHub release `weights-v1` — see `scripts/fetch_models.py` and the
  Dockerfile). Maia-2 base at `maia2_models/rapid_model.pt`. Roughly
  700MB RAM per resident era model.

## Recommended architecture

Use the maintained **lichess-bot framework**
(github.com/lichess-bot-devs/lichess-bot) with a "homemade" engine class
wrapping our era engine — it handles event streaming, challenge
queueing, reconnects, abort/timeout rules, so we only write the
move-selection glue. One lichess-bot process = one Lichess account.

Proposed layout in the repo:

```
lichess_bot/
  engine.py       # homemade engine: era engine + temperature schedule
                  #   + draws/manners hooks; era chosen by env var TMC_ERA
  config.yml.tmpl # lichess-bot config template (token + era filled per bot)
  README.md       # setup + run instructions
```

**Pilot with ONE bot first** — the Romantic era (most charismatic, the
gambit-accepting persona already has a Reddit fanbase). Prove the setup
end-to-end for a week, then clone to the other four. Five concurrent
bots ≈ 5 processes × ~700MB model ≈ needs an ~8GB box; one bot runs in
~2GB. Don't solve five-bot hosting until the pilot works.

Config choices for the pilot (in config.yml): accept blitz + rapid,
casual AND rated, max 1–2 concurrent games (CPU inference), decline
correspondence, matchmaking OFF initially (let challenges come to it).
CPU policy inference is ~fast enough for blitz; verify move latency
locally before accepting bullet.

## What Nick must do manually (can't be automated)

1. Create a fresh Lichess account for the bot (suggested names, ≤20
   chars, letters/digits/_/-): `TimeMachine1858`, or per-era later:
   `TM-RomanticEra`, `TM-SovietSchool`, etc. **The account must have
   played ZERO games** — bot upgrade is refused otherwise, and the
   upgrade is irreversible.
2. Create a personal API token for that account with the `bot:play`
   scope (lichess.org/account/oauth/token).
3. Upgrade to BOT: `POST https://lichess.org/api/bot/account/upgrade`
   with the token (lichess-bot has a helper flag for this).
4. Write the bio (era voice — reuse the `verdict` lines in eras.yaml)
   with links to chess.pharmatools.ai and /classifier.
5. Hosting: the Railway web service is sized for the website; run the
   bot as a separate always-on process — options: a second small Railway
   service, or a cheap VPS (a ~2GB instance is fine for the pilot).
   Needs outbound HTTPS only.

## Environment facts for the new chat

- Sandbox repo copy: `/root/tmc`. Nick's Mac (device bridge):
  `/Users/NickLamb/Time-Machine Chess`. Workflow: edit in sandbox → run
  tests → SendUserFile + device_commit_files → give Nick git commands.
- Git commands must be zsh-safe: no inline `#` comments, one command per
  line, `cd ~/Time-Machine\ Chess` first. Railway auto-deploys on push.
- The sandbox **cannot reach lichess.org, GitHub releases, or most CDNs**
  — so the bot cannot be integration-tested here. Test strategy: unit
  tests with mocked lichess event streams + `TMC_FORCE_HEURISTIC=1` for
  deterministic engine output (never assert on neural model opinions);
  Nick runs the real thing locally/on the VPS.
- Tests: `TMC_FORCE_HEURISTIC=1 python -m pytest tests/ -q` (53 passing).
- pip in sandbox needs `--break-system-packages`; the `chess` package
  sdist fails to build — extract the pure-Python package from the
  tarball instead if needed (python-chess is already available).

## Open decisions (ask Nick early)

1. Pilot bot name (needs to be free on Lichess) — check availability
   before writing bios/config.
2. Rated from day one, or casual-only week first? (Rated games give the
   bot a public rating — fun to compare with our measured Elo ~1690,
   and a "the bot's live rating matches the preprint" moment is
   marketable. Recommend rated on.)
3. Where it runs (second Railway service vs VPS).
4. Whether bot games should feed a "games played" stat on the site —
   note the site counter only counts games played ON the site; decide
   whether to show a separate "live on Lichess" widget instead
   (lichess API exposes the bot's game count/rating — a nice trust
   signal on the homepage, e.g. "Challenge BOT TimeMachine1858 —
   currently rated 1712 on Lichess").

## Definition of done for the pilot

- `lichess_bot/` code merged, unit-tested, documented in README.
- Romantic bot live on Lichess, playable, resigning/offering draws in
  period manner, bio funnels to the site.
- Homepage gets a small "Challenge the bot on Lichess" link (era card or
  colophon) once live.
- After ~1 week: check games played, rating vs measured 1690, CPU/RAM
  headroom → then decide on rolling out the other four eras.
