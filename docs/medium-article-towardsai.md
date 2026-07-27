# Resigns Like It's 1974: Recreating 180 Years of Chess Style with Policy-Only Fine-Tuning

*How five small neural networks learned to play like 1850, 1920, 1965, 1995, and 2015 —
and how we know they actually do. A technical companion to Time-Machine Chess, an
open-source (MIT) side project.*

---

Modern chess engines all play the same way: perfectly. Stockfish and Leela differ in
approach, but at the board they converge on the same narrow ridge of best play. Chess
*style*, though, has a history. The King's Gambit ruled 1850 and was extinct by 1950.
Draw rates tripled over a century, then plateaued. The English Opening rose from
nothing. None of this survives in an engine that only wants the best move.

Time-Machine Chess asks a different question: **how would the masters of each era have
approached this position?** Not "what's best" but "what would 1858 have played" — the
gambit-happy attackers of the Romantic era, the technicians of the 1920s, the Soviet
school's grinders, the database-armed dynamos of the 1990s, the engine-hardened
defenders of the 2010s.

This article is about the two decisions that made it work, and — more importantly —
about the validation discipline that makes the claim honest. Anyone can fine-tune a
model and *say* it plays like 1850. The interesting problem is proving it.

## Decision one: imitate, don't optimize

The base model is [Maia-2](https://github.com/CSSLab/maia2) (CSSLab, University of
Toronto, NeurIPS 2024), a network trained to predict *what a human would play* rather
than what's best. That lineage matters, because the whole architecture of the project
falls out of one choice: **there is no search**. The engine is a policy head. Given a
position, it produces a probability distribution over legal moves, and we sample from
it.

Policy-only serving buys three things at once. It's human-like by construction —
search is precisely the thing humans don't do the way engines do, and a policy trained
on human games encodes human move preferences, blunders and all. It's CPU-cheap — one
forward pass per move, ~50–100ms on a small cloud instance, no GPU anywhere in
production. And it makes *style* the primary output rather than a side effect:
sampling from the distribution reproduces the variety of period play, where an argmax
(or any search) would collapse it back toward a single "best" line.

The cost is equally clear: no tactical safety net. Drag the bot into positions no
19th-century game ever reached and its predictions flatten — there's no calculation to
rescue it. We consider that a feature. The bots are meant to lose like 1858, too.

## Decision two: fine-tune per era, condition on nothing new

Training data comes from [Lumbra's Gigabase](https://lumbrasgigabase.com), ~10M dated
over-the-board games. A streaming filter splits it into five era corpora by year:
Romantic (1840–1885, 10.7k games — that's *all* that survives), Classical (1900–1939,
62.8k), Soviet (1950–1985, 597k), Engine Dawn (1990–1999, 500k), Engine Era
(2010–2019, 500k). Pre-1840 is officially data-starved: only ~670 OTB game scores
survive from before systematic recording began with the first chess magazines. The
past kept poor receipts.

From each corpus we sample a balanced fine-tuning subset — 10–12k games, roughly 0.8M
positions per era — so every era gets comparable training signal regardless of corpus
size. Each era model is then **one epoch** of fine-tuning from the Maia-2 checkpoint.
One epoch, on a MacBook (`--device mps`), in minutes. The entire model zoo for 180
years of chess history trains in under an hour of laptop time.

Two details are load-bearing:

**Fixed skill conditioning.** Maia-2 conditions on player rating. Historical games
mostly lack ratings, so every training position gets a fixed nominal 1900 — and the
same value is used at inference. The intent: eras should differ in *style*, not
strength. (Whether that intent survived training is an empirical question. We measured
it. See below.)

**Temperature schedule at serving.** Era character lives disproportionately in opening
*diversity* — sharpening the distribution over-concentrates on 1.e4 and erases the
period repertoire. So the first ten plies are sampled at temperature 1.0 (the model's
true distribution) and later moves at 0.6 (sharpened toward the era's most
characteristic choices).

## The social layer: draws and resignations are not in the policy

The first validation run exposed a structural gap. The bots' *moves* were in period,
but the games weren't: draw rates 8–10 points below history, games ~25 plies too long.
The reason is obvious in hindsight — a policy network never learns to *agree to a
draw* or *resign*, because those aren't moves. They're social behavior, and they have
their own history.

The fix uses a part of the model the policy path ignores: Maia-2's win-probability
head. Each era gets a draw-agreement rule (agree when the evaluation has sat inside a
dead-equal band for N consecutive moves, past a minimum move number) and a resignation
rule (resign when own win probability has been below a threshold for M moves), with
the constants tuned per era against the historical record. The Soviet school agrees
draws readily and resigns promptly; Romantics play on toward mate and almost never
shake hands.

Tuning revealed the two constants *interact* — prompt resignation eats would-be draws,
because games that would have drifted into the agreement zone end first. The pairs had
to be tuned jointly. After tuning, draw rates land within ~3 points of history and
average game length within ~5 plies, in all five eras.

The tuned system also reproduced a finding we didn't put in: the **draw-culture
curve**. Historical draw rates rise for 150 years (12% → 25% → 28.75% → 31.75%) and
then *plateau* in the engine age — Sofia rules and fighting-chess culture flatten the
curve exactly as games stretch to their historical maximum length. The bots track
every step.

## Validation one: self-play against the historical record

The house rule for the whole project: **no claim without a measurement against the
corpus the model learned from.** Each bot played 150 self-play games at its serving
temperature; the same analyzer computed identical move-sequence metrics (no ECO tags,
no cherry-picking) on the bot games and on random samples of the era corpora.

| Metric | Romantic (hist → bot) | Classical | Soviet | Engine Dawn | Engine Era |
|---|---|---|---|---|---|
| King's Gambit rate | 14.0% → **18.0%** | 3.5% → **9.3%** | 1.25% → **0.0%** | 0.75% → **0.0%** | 0.0% → **0.0%** |
| Draw rate | 12.0% → **15.3%** | 25.0% → **24.7%** | 28.75% → **26.0%** | 31.75% → **34.7%** | 31.75% → **28.7%** |
| Avg length (plies) | 73.9 → **79.1** | 77.5 → **74.5** | 72.7 → **69.1** | 75.2 → **70.8** | 78.4 → **78.0** |

The gradients reproduce: the King's Gambit dies on schedule, draws rise and plateau,
the 2010s bot plays 1.c4 at exactly the historical 8.0%. The honest residual: first
moves lean 1.e4 beyond the historical rate in the older eras. One epoch moves Maia-2's
modern opening prior a long way, but not all the way.

The corpus itself doubles as an arbiter of style disputes. When a Reddit user
complained that the Romantic bot *declined* his Vienna Gambit — "I thought declining
gambits was borderline dishonorable" — the corpus settled it: 1840–1885 masters
accepted the actual King's Gambit 81% of the time (1,114 of 1,377 games) but declined
the Vienna Gambit 92% of the time, because 3...exf4 there concedes the center with
tempo, and they knew it. Even in 1855, 3...d5 was the main move. The bot had read the
same books. Honor demanded you accept a gambit — not a bad one.

## Validation two: turn the models around and make them classify

If five models each predict their own era's moves best, they can act as a *classifier*
— and the classifier's accuracy on held-out historical games is an independent test of
whether the eras are actually distinguishable, or whether we've been fooling ourselves
with opening statistics.

The method is per-move log-likelihood: for each position in a game, each era model
assigns a probability to the move actually played; sum log-probabilities per era; the
era whose model predicts the game best wins. (This also became the site's most
shareable feature — paste your own games, or a lichess/chess.com username, and get an
era diagnosis: "you are 28% Romantic, and your queen sacrifices are pure 1850.")

Run blind on 100 held-out games per era (training subsets reproduced by seed and
excluded), single games classify at **42%** against a 20% chance baseline. Diagnosing
twenty games together: **88%**. Single games are a mood; twenty games is a diagnosis
— and we print that noise floor on the results page rather than hiding it.

The confusion matrix's *errors* turn out to be the most historically interesting
output:

- **The Romantics are unmistakable** — 60% single-game accuracy, far above every
  other era. Nothing else plays like 1850.
- **The Engine Dawn and Engine Era blur into one continuum** (43%/37%, heavily
  confused with each other) — ten years apart in a converged game.
- **The Soviet school is the universal donor** (28%): sound, patient, theory-driven
  chess that passes plausibly in any century — because it became *the* chess.

## Validation three: measure the strength claim instead of assuming it

The fixed 1900 conditioning was supposed to make eras differ in style, not strength.
"Supposed to" is not a measurement — and it's tempting to just tell players "the bots
play at 1900" because that number is in the code. It isn't the bots' strength; it's an
input.

So: each era played 120 games against a ladder of limited-strength Stockfish levels
(UCI_Elo 1400/1700/2000/2300, era resignation manners applied), and a performance
rating was fitted by maximum likelihood with a bootstrap 95% interval. Results:
Romantic ~1690, Classical ~1579, Soviet ~1652, Engine Dawn ~1760, Engine Era ~1701 —
with ±~95-point intervals.

Two conclusions. First, the design claim survives to first order: a 181-point spread
across five independently fine-tuned models is within about one rating class, with
overlapping intervals. Five eras, one strength, five styles. Second, the honest
number for players — "you're facing roughly 1650–1750, strong club strength" — is
*not* the 1900 anyone would have quoted from the code. Conditioning values are not
measurements. (Caveats apply in both directions: Stockfish's limited-strength mode is
itself an approximation of human Elo, and engine-calibrated ratings transfer
imperfectly to humans. We publish it as "~1700 vs engines," not a FIDE certificate.)

## What didn't work, and what's noise

A few residuals and floors, because a validation story without them isn't one:

- **The 1.e4 lean.** Fine-tuning from a modern-online-chess base leaves a first-move
  prior the era data doesn't fully overwrite. Documented, not hidden; it doesn't
  affect the in-period style signals above.
- **Self-play noise.** At 150 games, draw-rate standard error is ~3.5 points. We
  tuned the social constants to land within ~3 points of history and stopped —
  tuning past the noise is how you fool yourself.
- **Neural evaluations on artificial positions are uncalibrated.** One era model
  rated a dead-equal rook endgame 0.12 for White. Tests never assert on a neural
  model's opinion; CI runs deterministic heuristic stand-ins, and accuracy claims
  come only from the corpus-validated pipelines above.
- **Single-game classification is noisy by nature** — 42% is genuinely useful
  evidence and genuinely not an oracle, which is why the product asks for twenty
  games and says why.

## Why this recipe generalizes

Strip out the chess and the recipe is: **(1)** take a model trained to imitate humans
in a domain, **(2)** fine-tune it briefly on era- (or school-, or author-) specific
corpora, **(3)** handle the behaviors that aren't in the action space — the social
layer — as separate, tunable rules driven by the model's own value signal, and
**(4)** validate every claim against held-out historical data, publishing the
confusion structure and the noise floor along with the wins.

Step 4 is the one that's usually skipped, and it's where all the interesting findings
lived: the draw-culture plateau, the Soviet school as chess's universal donor, the
Engine Dawn/Era continuum, the gap between conditioning inputs and measured strength.
The validation wasn't overhead on the fun result. It *was* the result.

Everything here — training, validation, the Elo ladder, the classifier — ran on one
laptop and serves from one small cloud instance with one model resident at a time.
Total footprint: five 89MB checkpoints, no GPU, no search.

*Time-Machine Chess is open source under the MIT licence — the era models,
every validation script, and all measured outputs included — and the playable
version carries the era classifier and the full validation data alongside the
bots. Built on [Maia-2](https://github.com/CSSLab/maia2) (CSSLab, University of
Toronto); historical games from [Lumbra's Gigabase](https://lumbrasgigabase.com).*
