# Launch post — three versions

One canonical blog post, then short variants for Show HN and r/chess. Facts are all from the
repo's validation data; nothing here overstates what was measured.

---

## 1. Blog post (pharmatools.ai / Medium)

# I trained chess engines on 150 years of history — and the 1850 one plays *more* Romantic than the Romantics

Modern chess engines all have the same personality: none. Stockfish plays the objectively best
move, which means every engine game converges on the same silicon style. But human chess has a
history. In 1850, declining a gambit was borderline dishonorable. By 1920, Capablanca had made
chess look like clean technique. By 1970, the Soviet school had turned preparation and
prophylaxis into an industrial process. The King's Gambit — *the* opening of the Romantic era —
appeared in 14% of master games in 1850 and 0.7% by the Soviet era. Draw rates more than doubled.

So I built [Time-Machine Chess](https://chess.pharmatools.ai): pick a century, play its theory.

## How it works

Each era bot starts from [Maia-2](https://github.com/CSSLab/maia2), the NeurIPS 2024 human-like
chess model from the University of Toronto's CSSLab. Maia-2 predicts what a *human* would play,
not what's best. I fine-tuned it three times on era corpora cut from dated over-the-board games
(Lumbra's Gigabase): the Romantic era (1840–1885), the Classical era (1900–1939), and the Soviet
era (1950–1985) — about 2.5 million positions from period games, balanced so the data-rich
Soviet era doesn't drown out the sparse 1850s. Training ran on a MacBook in an afternoon.

The bots play with no search at all — they sample directly from the policy network, which keeps
them human-shaped by construction and cheap enough to serve on a $10/month instance. Historical
games mostly lack Elo ratings, so every era trains and plays at a fixed nominal rating: the eras
differ in *style*, not strength.

## The receipts

My day job is building AI for regulated healthcare, where "trust me, it works" doesn't fly. So
the centerpiece of this project is a [validation page](https://chess.pharmatools.ai/validation):
each bot played 150 games against itself, and identical move-sequence metrics were computed on
the bot games and on random samples of the historical corpora.

| Metric | Romantic (history → bot) | Classical | Soviet |
|---|---|---|---|
| King's Gambit rate | 14.0% → **22.0%** | 3.5% → 4.7% | 1.25% → 0.7% |
| 1.e4 / 1.d4 / 1.c4 | 88/6/3 → 97/1/0 | 48/40/6 → 63/29/4 | 50/28/11 → 69/15/9 |
| Draw rate | 12.0% → 20.7% | 25.0% → 15.3% | 28.75% → 20.0% |

The era gradients reproduce — a 30× spread in King's Gambit frequency across the bots, tracking
history. My favorite result: the Romantic bot plays the King's Gambit *more* often than the
historical average. It's more Romantic than the Romantics.

Two honest gaps, documented on the validation page. The bots still lean 1.e4 harder than
history — one epoch of fine-tuning moves Maia-2's modern prior a long way, but not all the way.
And bot games run ~25 plies longer than period games with fewer draws, because the bots resign
(adjudicated from the model's own win-probability head) but never *agree* to draws — and the
negotiated grandmaster draw is a huge feature of real tournament chess, especially Soviet-era.
That one's on the roadmap.

## Try it

Play at **[chess.pharmatools.ai](https://chess.pharmatools.ai)** — no signup, free, open source
([GitHub](https://github.com/nickjlamb/time-machine-chess), MIT). Try declining a gambit against
the Romantic era and see what it does to you.

*Built on Maia-2 (CSSLab, MIT), Lumbra's Gigabase (CC BY-NC-SA), and lichess piece sets. Every
sound in the app is synthesized in-browser — the wooden thock is three bandpass resonators over
a noise burst.*

---

## 2. Show HN

**Title:** Show HN: Play chess against the theory of 1850, 1920, or the Soviet school

**Comment (post as first comment or text):**

I fine-tuned Maia-2 (the human-like chess model, NeurIPS 2024) on era-sliced corpora of dated
OTB games: Romantic (1840–1885), Classical (1900–1939), Soviet (1950–1985). The bots sample the
policy net directly — no search — so they play era-shaped moves rather than best moves.

The part I care most about is validation: each bot played 150 self-play games, scored with the
same move-sequence metrics as the historical corpora. King's Gambit rate goes 22% → 4.7% → 0.7%
across the bots (history: 14% → 3.5% → 1.25%); first-move fashions and draw-rate direction
reproduce too. Honest residuals are documented on the /validation page — the bots still lean
1.e4 beyond history, and they never agree to draws, which real Soviet-era players famously did.

Stack: PyTorch fine-tune (one epoch per era, MacBook), FastAPI, zero-dependency frontend, ~1GB
RAM with LRU model swapping. MIT: https://github.com/nickjlamb/time-machine-chess

**URL:** https://chess.pharmatools.ai

---

## 3. r/chess

**Title:** I trained bots on 150 years of chess history — you can now play against the 1850 meta

Ever wondered what it was like to face the King's Gambit era? I fine-tuned a human-like neural
network (Maia-2) separately on master games from 1840–1885, 1900–1939, and 1950–1985, and put
them online to play: https://chess.pharmatools.ai

The Romantic bot opens 1.e4 97% of the time and plays the King's Gambit in 22% of its games —
actually *more* than the 14% historical rate. The Soviet bot castles quietly, plays the English,
and grinds. There's a validation page showing self-play stats vs. the real historical numbers,
including the gaps (the bots never agree to draws, so they're more bloodthirsty than real
Soviet-era players were).

Free, no signup, open source. Fair warning: they play like *humans* of their era, not engines —
around club strength, with period-appropriate brilliancies and blunders. Try declining a gambit
against the 1850 bot and see how long your position survives.

---

### Posting notes

- Blog first, then Show HN linking the site (HN prefers the product over the blog post), then
  r/chess a day later. Cross-link the blog from the HN comment only if asked.
- Optional line for the blog if you want it: the whole thing was built in a few days of intense
  AI pair-programming — fits your "one-man agency" writing, your call whether to include.
- `?era=soviet` deep links work if you want era-specific hooks in replies.
