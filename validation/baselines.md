# Historical era baselines (from Lumbra's Gigabase, 2026-07-08 release)

Computed 2026-07-20. Corpora: `data/eras/*.pgn`. Move-level metrics from 400-game
random samples (byte-offset sampling); header metrics (draws, openings) from full corpora.
These are the targets the trained era bots get compared against on the validation page.

| Metric | Romantic (1840–1885) | Classical (1900–1939) | Soviet (1950–1985) |
|---|---|---|---|
| Games | 10,693 | 62,779 | 597,511 |
| Avg plies | 73.5 | 80.4 | 77.3 |
| Capture rate (per ply) | 0.230 | 0.213 | 0.212 |
| Gambit-like openings* | 47.8% | 44.2% | 38.5% |
| Draw rate | **13.9%** | 24.1% | **31.9%** |
| King's Gambit (ECO C30–C39) | **13.28%** | 2.57% | **0.68%** |
| QGD (ECO D30–D39) | 1.38% | 5.72% | 2.45% |

*Crude proxy (pawn en prise in first 12 plies) — noisy, prefer ECO-based metrics.

## Headline signatures (for validation page + launch post)

- King's Gambit: **20× more common** in the Romantic era than the Soviet era.
- Draw rate **more than doubles** from 1850 to the Soviet era.
- Trained bots must reproduce these gradients in self-play to pass validation.

## Training notes

- Soviet corpus (597k) dwarfs Romantic (10.7k). For fine-tuning, cap Soviet/Classical
  or weight sampling so eras get comparable training signal.
- Lumbra data: games <11 moves already removed; annotations/variations present in
  some movetext — strip variations when converting to training format.
- License: CC BY-NC-SA 4.0 (non-commercial; attribution required).
