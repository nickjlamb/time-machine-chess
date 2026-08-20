# The era bots on Lichess

Each era model can hold a real Lichess **BOT** account, so anyone can
challenge it from lichess.org without ever visiting the site. Every game is
exposure; the account bio funnels back to chess.pharmatools.ai and the era
classifier.

Pilot: **TimeMachine1858** — the Romantic Era (1840–1885). One account first,
for a week, before cloning to the other four.

## How it fits together

```
lichess-bot (framework)      ← event streaming, challenge queue, reconnects
   └── homemade.py           ← 40-line adapter, copied in at deploy time
         └── lichess_bot/engine.py    EraBot: one era, one game, its manners
               └── backend/turn.py    THE move recipe — shared with the website
                     ├── backend/engines.py    Maia-2 era checkpoint
                     ├── backend/draws.py      era draw agreement
                     └── backend/manners.py    era resignation
```

The point of `backend/turn.py`: the bot on Lichess and the bot on the website
are the same player, by construction rather than by good intentions. Anything
that changes how an era plays changes both.

Era is chosen by `TMC_ERA` (default `romantic`) and validated against
`config/eras.yaml` — the era list is never hardcoded.

## What Nick has to do by hand (once per account)

1. **Register a fresh Lichess account.** It must have played **zero** games —
   Lichess refuses the bot upgrade otherwise, and the upgrade is
   **irreversible**. Name: `TimeMachine1858` (≤20 chars, letters/digits/_/-).
2. **Create a token** at <https://lichess.org/account/oauth/token/create>
   with the **`bot:play`** scope. Copy it; it's shown once.
3. **Upgrade the account to BOT:**
   ```
   curl -d '' https://lichess.org/api/bot/account/upgrade \
     -H "Authorization: Bearer lip_yourtokenhere"
   ```
4. **Set the bio** — see `bio.md` next to this file (Lichess allows 400
   characters; the copy there fits).
5. **Deploy** (below), then challenge it yourself from a second account to
   confirm it plays, offers, resigns and greets.

## Deploy: a second Railway service

The website's service is sized for the website; the bot runs as its own
always-on worker off the same repo and the same push.

1. Railway → the Time-Machine Chess project → **New Service → GitHub repo**,
   pick `nickjlamb/time-machine-chess` (the same repo the site deploys from).
2. Service **Settings → Config-as-code → Config file path**: `railway.bot.json`
   (that's what points it at `Dockerfile.bot` instead of the website's
   `Dockerfile`).
3. **Variables:**
   | Variable | Value |
   | --- | --- |
   | `LICHESS_BOT_TOKEN` | the `bot:play` token from step 2 |
   | `TMC_ERA` | `romantic` |
   | `MAX_LOADED_MODELS` | `1` (already the image default) |
4. Deploy. The logs should show, in order: the era and its checkpoint, the
   rendered config, then lichess-bot's own startup banner and
   `TimeMachine1858 is online`.
5. Leave **no** public networking / no healthcheck on this service — it never
   listens on a port. (That's why `railway.bot.json` has no `healthcheckPath`:
   a healthcheck would fail forever and restart-loop the bot.)

Also add `LICHESS_BOT_USERNAME=romantic:TimeMachine1858` to the **website**
service — that's what turns on the "Play the Romantic Era on Lichess" card on
the homepage, with its live rating. Unset, the card doesn't render at all.

The `era:username` prefix is what lets the card name the account as the era and
show its portrait, pulled from `config/eras.yaml`; a bare username still works
but renders as an anonymous handle. The value is a comma-separated list, so
adding accounts later is one variable:

    LICHESS_BOT_USERNAME=romantic:TimeMachine1858, soviet:TM-SovietSchool

An era that isn't in `eras.yaml` is ignored rather than fatal — a typo costs
the portrait, not the card. (The homepage renders the first account in the
list; showing several at once is a frontend change, not a config one.)

Anywhere else with Docker works the same:

```
docker build -f Dockerfile.bot -t tmc-bot .
docker run -e LICHESS_BOT_TOKEN=lip_xxx -e TMC_ERA=romantic tmc-bot
```

Sizing: one era model resident is ~700MB, ~1.2GB RSS for the process. A 2GB
instance is comfortable for one bot; five concurrent era bots want ~8GB.

## Running it locally

```
python3 scripts/fetch_models.py romantic          # just this era + the base
export LICHESS_BOT_TOKEN=lip_yourtokenhere
export TMC_ERA=romantic

# 1. does the checkpoint load, and how fast does it move?
python -m lichess_bot.engine --selfcheck

# 2. the real thing (same commit the image pins — the project's git tags stop
#    at 1.1.3 in 2019 and are a different, incompatible bot; it versions by date)
git clone https://github.com/lichess-bot-devs/lichess-bot.git
git -C lichess-bot checkout df7e730de58cc3ef2f1415a0dc2eeda842d39167
pip install -r lichess-bot/requirements.txt
TMC_ROOT=$(pwd) python -m lichess_bot.render_config lichess-bot/config.yml
cp lichess_bot/homemade.py lichess-bot/homemade.py
cd lichess-bot && TMC_ROOT=$(cd .. && pwd) python lichess-bot.py -v
```

`--selfcheck` is the latency gate: the config accepts blitz and rapid only.
Blitz is comfortable under ~1s/move; if the mean is worse than that on the
deploy target, drop `blitz` from `time_controls` in `config.yml` before going
live rather than after flagging a rated game.

## Configuration choices, and why

`config.yml` here is the whole configuration; it is rendered per era at
startup by `render_config.py` (greetings get the era's name and dates) and
written into the lichess-bot checkout. The token never appears in it — it
comes from `LICHESS_BOT_TOKEN`.

- **blitz + rapid, no bullet, no correspondence.** CPU policy inference is
  fast but not bullet-fast, and a correspondence game would pin a model slot
  for days.
- **casual + rated.** Rated from day one: the public rating is the payoff —
  a number Lichess keeps, sitting next to our measured ~1690 on /validation.
- **concurrency 2, one slot reserved for humans.** Two games is the honest
  ceiling for CPU inference, and other bots shouldn't be able to fill the
  queue so no human can get a game.
- **matchmaking off.** Let challenges come to it for the pilot week; turning
  it on means the account starts hunting other bots for games, which changes
  what the rating means.
- **the framework's own draw/resign logic off.** It reasons in centipawns
  from an engine score; ours reasons from the model's win-probability head
  with per-era thresholds. Ours is the whole point — the Romantic bot
  resigning late and gallantly is part of the show.
- **`quit_after_all_games_finish: true`.** A redeploy finishes its games
  instead of abandoning opponents mid-game.

## After a week

The definition-of-done review:

- games played, and the rating Lichess settled on vs our measured ~1690
  (`validation/elo.json`) — if they're close, that's a receipt worth writing up;
- draw and resignation rates vs the era's historical targets in
  `validation/baselines.md` — do the manners look in-period in real games?
- CPU/RAM headroom on the instance during two concurrent games;
- then decide about the other four eras (`TM-ClassicalEra`,
  `TM-SovietSchool`, …). The same image serves any of them: new account, new
  token, new service, `TMC_ERA` set accordingly — the weights for that era are
  fetched on first boot.

To keep the games for that review, mount a volume and uncomment
`pgn_directory` in `config.yml`; without a volume the PGNs die with the
container on the next deploy.

## Testing

`tests/test_lichess_bot.py` covers the era brain and the framework adapter
(against a fake `lib.engine_wrapper`, since the framework isn't a dependency
of this repo), plus the config rendering — including the 140-character
Lichess chat limit, which is enforced at startup because Lichess drops longer
greetings without an error.

Nothing in the suite touches the network. The live integration is Nick,
locally, with a casual challenge, before the account is pointed at rated
games.
