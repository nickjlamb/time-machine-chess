# Recreating Historical Chess Style with Policy-Only Fine-Tuning and Quantitative Validation

**Nick Lamb**
Medcopywriter Ltd, United Kingdom — ORCID 0009-0009-6266-8499
July 2026 · Licensed CC BY 4.0

*Preprint. An interactive demonstration is available at https://chess.pharmatools.ai;
source code (MIT) at https://github.com/nickjlamb/time-machine-chess.*

## Abstract

Chess engines optimize for move quality and, in doing so, converge on a single
contemporary style. Chess *style*, however, is historically situated: opening
repertoires, draw culture, and resignation habits all changed measurably between 1840
and 2019. We present Time-Machine Chess, a family of five era-specific chess models
produced by one epoch of fine-tuning Maia-2 — a human-move-prediction network — on
balanced corpora of dated over-the-board games (1840–1885, 1900–1939, 1950–1985,
1990–1999, 2010–2019). Models are served policy-only (no search), with a temperature
schedule that preserves period opening diversity, and a rule-based "social layer"
that derives era-appropriate draw agreements and resignations from the model's own
win-probability head. We validate the era claim three ways: (1) self-play reproduces
historical opening, draw-rate, and game-length gradients within ~3 percentage points
and ~5 plies respectively; (2) used as a generative classifier on held-out historical
games, the models identify a game's era at 42% (single game, 20% chance) and 88%
(20-game batches), with a confusion structure that itself tracks chess history; and
(3) strength measured against a calibrated engine ladder places all five models
within a 181-point Elo band (~1580–1760), supporting the design goal that eras differ
in style rather than strength. Total training cost is under one laptop-hour; serving
requires no GPU.

## 1. Introduction

Superhuman chess engines are stylistically ahistorical: whatever their architecture,
optimization pressure drives them toward the same narrow set of moves. Yet the human
game has a documented stylistic history. The King's Gambit appeared in 14% of
surviving 1840–1885 master games and is effectively extinct in modern over-the-board
play; draw rates rose from 12% to over 31% across 150 years before plateauing in the
engine age; entire opening families rose and fell with theory and culture.

This work asks whether that history can be recreated as a playable artifact: a set of
opponents that make the moves — and the non-move decisions, such as when to agree a
draw or resign — characteristic of a specific era. The contribution is less any
single technique than the combination of (a) a deliberately minimal modeling recipe
(brief policy-only fine-tuning of an existing human-imitation model) with (b) a
quantitative validation programme that treats every stylistic claim as testable
against the historical record, and reports its residuals and noise floors.

## 2. Background

Maia [1] demonstrated that a policy network trained on human games predicts human
moves far better than engines do, and that skill-conditioned variants capture
rating-specific behavior. Maia-2 [2] unified this into a single model conditioned on
the ratings of both players, trained on large volumes of online chess. Both model
*what humans play* rather than what is best, which makes them natural substrates for
style transfer: an era corpus is, in effect, a description of what a particular
population of humans played.

We are not aware of prior work that fine-tunes human-imitation chess models on
historical era corpora with quantitative validation against those corpora, though the
components — fine-tuning, generative classification, engine-ladder strength
estimation — are all standard.

## 3. Method

### 3.1 Data

Games come from Lumbra's Gigabase [3], a database of ~10M dated over-the-board games
(used under CC BY-NC-SA terms; not redistributed). A streaming filter partitions
games by year into five era corpora: Romantic (1840–1885; 10,693 games — effectively
the entire surviving record), Classical (1900–1939; 62,779), Soviet (1950–1985;
597,511), Engine Dawn (1990–1999; 500,000), and Engine Era (2010–2019; 500,000).
Pre-1840 chess is data-starved — roughly 670 game scores survive — and was excluded.

From each corpus we draw a balanced fine-tuning subset (10,000–12,000 games; 0.73M to
0.95M positions per era) so that eras receive comparable training signal despite
corpus sizes varying by a factor of 56.

### 3.2 Fine-tuning

Each era model is initialized from the pretrained Maia-2 rapid checkpoint and
fine-tuned for a single epoch on its era subset (Apple M-series laptop, minutes per
era). Positions with Black to move are mirrored per Maia-2 convention. Because
historical games generally lack ratings, all positions are conditioned on a fixed
nominal rating of 1900 for both players, at training and at inference. The intent is
that era models should differ in *style* while holding strength approximately
constant; Section 4.3 tests whether this held.

### 3.3 Policy-only serving

At play time the era model's policy head yields a probability distribution over legal
moves, from which the served move is sampled directly — no search of any kind. The
first 10 plies are sampled at temperature 1.0, later moves at temperature 0.6: era
character is disproportionately carried by opening *diversity*, which sharpening
destroys, while unsharpened middlegame sampling produces uncharacteristic errors.
Serving is CPU-only (~50–100 ms per move; checkpoints are 89 MB).

### 3.4 The social layer

Draw agreements and resignations are not moves, and a policy network therefore never
learns them; without them, initial validation showed games ~25 plies too long and
draw rates 8–10 points below history. We model both as era-specific threshold rules
on the model's own win-probability head: a draw is offered/agreed when the evaluation
has remained within a dead-equal band for a required number of consecutive moves past
a minimum move number; the model resigns when its own win probability has remained
below a threshold for a required number of moves. Constants were tuned per era
against the historical record. The two rules interact — prompt resignation consumes
games that would otherwise have reached draw-agreement territory — and were tuned
jointly.

## 4. Validation

### 4.1 Self-play against the historical record

Each era model played 150 self-play games at serving temperature; identical
move-sequence metrics (no annotation metadata) were computed on these games and on
random samples of the corresponding era corpus.

| Metric | Romantic hist/bot | Classical hist/bot | Soviet hist/bot | E. Dawn hist/bot | E. Era hist/bot |
|---|---|---|---|---|---|
| King's Gambit % | 14.0 / 18.0 | 3.5 / 9.3 | 1.25 / 0.0 | 0.75 / 0.0 | 0.0 / 0.0 |
| Draw rate % | 12.0 / 15.3 | 25.0 / 24.7 | 28.75 / 26.0 | 31.75 / 34.7 | 31.75 / 28.7 |
| Mean length (plies) | 73.9 / 79.1 | 77.5 / 74.5 | 72.7 / 69.1 | 75.2 / 70.8 | 78.4 / 78.0 |

The historical gradients reproduce: the King's Gambit dies on schedule; draw rates
rise for 150 years and plateau in the engine age (the plateau itself — coincident
with games reaching their historical maximum length — is a finding the tuning did
not target); the 2010s model plays 1.c4 at exactly the historical 8.0%. The principal
residual is a first-move lean toward 1.e4 beyond historical rates in older eras: one
epoch moves Maia-2's modern opening prior most, but not all, of the way. At 150
games the draw-rate standard error is ~3.5 points; social-layer constants were tuned
to within ~3 points of history and no further.

### 4.2 Held-out era classification

If each model best predicts its own era's moves, the ensemble is a generative
classifier, and its accuracy on held-out games is an independent test of era
separability. For each game, each era model assigns a probability to every move
actually played (positions sampled after the first 6 plies, excluding forced moves
and decided positions); the era with the highest summed log-likelihood is the
prediction. Test games (100 per era) were drawn from the corpora with the training
subsets reproduced by seed and excluded.

Confusion matrix (rows = true era, columns = predicted):

| | Rom. | Cla. | Sov. | Dawn | Era |
|---|---|---|---|---|---|
| Romantic | **60** | 14 | 2 | 12 | 12 |
| Classical | 15 | **42** | 12 | 16 | 15 |
| Soviet | 17 | 13 | **28** | 22 | 20 |
| E. Dawn | 10 | 15 | 12 | **43** | 20 |
| E. Era | 14 | 4 | 10 | 35 | **37** |

Single-game accuracy is 42% against a 20% chance baseline; aggregating evidence over
20-game batches yields 88%. The error structure is historically interpretable: the
Romantic era is by far the most identifiable; the two engine-age eras substantially
merge (scored as one class, their combined accuracy is ~68%), consistent with a
converged modern game; and the Soviet era is the weakest diagonal, its sound,
theory-driven play passing plausibly in any later era.

### 4.3 Measured playing strength

The fixed rating conditioning (Section 3.2) is an input, not a measurement. Each era
model therefore played 120 games against Stockfish 16 [4] at four limited-strength
anchor levels (UCI_Elo 1400/1700/2000/2300; colors alternated; era resignation rules
applied), and a performance rating was fitted by maximum likelihood with a bootstrap
95% interval.

| Era | Fitted rating | 95% CI |
|---|---|---|
| Romantic | 1690 | 1597–1786 |
| Classical | 1579 | 1487–1677 |
| Soviet | 1652 | 1561–1742 |
| Engine Dawn | 1760 | 1656–1862 |
| Engine Era | 1701 | 1607–1794 |

All five models fall within a 181-point band with overlapping intervals — roughly
one rating class — supporting the style-not-strength design goal to first order.
Stockfish's limited-strength mode itself approximates human rating, and
engine-calibrated ratings transfer imperfectly to human opponents; we report these
as engine-referenced estimates.

## 5. Limitations

The models inherit Maia-2's modern online-chess prior, visible as the residual 1.e4
lean. Policy-only serving means no tactical verification: in positions far from any
era's data the move distribution flattens, and play degrades — a property consistent
with the goal of human-like era play but unsuitable for applications requiring
soundness. The social layer is rule-based, not learned; its constants are tuned to
aggregate era statistics and interact with each other. Era classification is noisy
at single-game granularity by the nature of the signal, and adjacent eras are
genuinely non-separable in part. Strength estimates are engine-calibrated. Finally,
the historical record itself is a biased sample — early corpora preserve
disproportionately notable games — and "era style" as learned here is the style of
*recorded* games.

## 6. Conclusion

A minimal recipe — brief policy-only fine-tuning of a human-imitation model on era
corpora, plus a rule-based social layer driven by the model's own evaluation —
suffices to recreate measurable, validated historical chess style at negligible
compute cost. The validation programme was not overhead on the artifact: it produced
the principal findings, including the draw-culture plateau, the near-merger of the
engine-age eras, the Soviet school's stylistic universality, and the gap between
conditioning inputs and measured strength. We suggest the same
imitate/fine-tune/validate pattern applies to recreating historical or school styles
in other domains where dated human decision records exist.

## Data and code availability

Source code, validation scripts, and all validation outputs are available under MIT
license at https://github.com/nickjlamb/time-machine-chess. Model checkpoints are
distributed via the repository's releases. Training data (Lumbra's Gigabase [3]) is
CC BY-NC-SA and is not redistributed. An interactive demonstration, including the
era classifier and all validation receipts, is at https://chess.pharmatools.ai.

## Acknowledgements

Built on Maia-2 by the Computational Social Science Lab, University of Toronto [2].
Historical games from Lumbra's Gigabase [3]. Board interaction uses python-chess [5].

## References

[1] R. McIlroy-Young, S. Sen, J. Kleinberg, A. Anderson. Aligning Superhuman AI with
Human Behavior: Chess as a Model System. *Proc. 26th ACM SIGKDD*, 2020.
arXiv:2006.01855.

[2] Z. Tang, D. Jiao, R. McIlroy-Young, J. Kleinberg, S. Sen, A. Anderson. Maia-2: A
Unified Model for Human-AI Alignment in Chess. *NeurIPS*, 2024. arXiv:2409.20553.

[3] Lumbra's Gigabase. https://lumbrasgigabase.com (accessed July 2026).

[4] The Stockfish developers. Stockfish 16. https://stockfishchess.org.

[5] N. Fiekas. python-chess. https://github.com/niklasf/python-chess.

[6] A. Elo. *The Rating of Chessplayers, Past and Present.* Arco, 1978.
