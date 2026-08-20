# Lichess account bios

Paste into **Profile → Bio** on the bot account. Lichess allows **400
characters**; each block below fits (there's a test in
`tests/test_lichess_bot.py` that fails if one stops fitting).

Lichess doesn't linkify bio text, so the URLs are written bare — short enough
to type, and the account's games are the reason anyone reads this at all.

The voice comes from each era's `flavor`/`verdict` copy in
`config/eras.yaml`, so the bot's profile, the era picker and the classifier's
verdict all sound like the same character.

## TimeMachine1858 — the Romantic Era (1840–1885) · pilot

```
A neural network that has never seen a game played after 1885.

Maia-2 fine-tuned on the Romantic era alone: gambits accepted, material given for initiative, king hunts seen through. No search, no engine eval.

Play all five eras, or find which era you play like:
chess.pharmatools.ai
chess.pharmatools.ai/classifier

Open source: github.com/nickjlamb/time-machine-chess
```

## For the other four, when the pilot proves out

### TM-ClassicalEra — 1900–1939

```
A neural network that has never seen a game played after 1939.

Maia-2 fine-tuned on 1900-1939 alone: sound development, prophylaxis, technique - nothing before its time. No search, no engine eval.

Play all five eras, or find which era you play like:
chess.pharmatools.ai
chess.pharmatools.ai/classifier

Open source: github.com/nickjlamb/time-machine-chess
```

### TM-SovietSchool — 1950–1985

```
A neural network that has never seen a game played after 1985.

Maia-2 fine-tuned on the Soviet school alone: deep preparation, dynamic imbalance, no fear of complications. No search, no engine eval.

Play all five eras, or find which era you play like:
chess.pharmatools.ai
chess.pharmatools.ai/classifier

Open source: github.com/nickjlamb/time-machine-chess
```

### TM-EngineDawn — 1990–1999

```
A neural network that has never seen a game played after 1999.

Maia-2 fine-tuned on the 1990s alone: the decade humans started checking their ideas against silicon, and playing like it. No search, no engine eval.

Play all five eras, or find which era you play like:
chess.pharmatools.ai
chess.pharmatools.ai/classifier

Open source: github.com/nickjlamb/time-machine-chess
```

### TM-EngineEra — 2010–2019

```
A neural network trained on 2010-2019 alone: the engine-checked era - precise, patient, allergic to unsound sacrifices. No search, no engine eval of its own.

Play all five eras, or find which era you play like:
chess.pharmatools.ai
chess.pharmatools.ai/classifier

Open source: github.com/nickjlamb/time-machine-chess
```

## Also worth setting on the account

- **Location:** the era's home ground — Paris for 1858, Moscow for the Soviet
  bot. Small, and it lands.
- **Real name field:** the era's display name ("The Romantic Era"), so the
  profile header reads as the character rather than the handle.
- **Link to the preprint** if the bio has room after a rating settles — but
  the site link matters more; the site has the preprint on it.
