# LinkedIn post — "resigns like it's 1974"

My chess bot resigns like it's 1974.

Side project: Time-Machine Chess — neural networks fine-tuned on 150 years of chess
history, so you can play against the gambit-happy attackers of 1850 or the Soviet
school of 1970.

At launch, validation showed the bots played in period — but with one honest gap:
their games ran ~25 moves too long, with too few draws. The reason was charming.
The bots had learned each era's *moves*, but not its *manners*. Real players resign
lost positions and agree draws (the famous Soviet "grandmaster draw"). Neural
networks grind on to checkmate.

So the latest update models the social layer. Each era now resigns and offers draws
according to its own culture, driven by the model's own win-probability estimate:
the Soviet bot resigns promptly and happily splits the point; the 1850 Romantic
refuses draws and plays on toward mate — being brilliantly mated was part of the
theatre.

After tuning against the historical record (fun discovery: the two behaviours
interact — prompt resignation eats would-be draws), draw rates now land within ~3
points of history and game length within ~5 moves, in all three eras.

The lesson I keep re-learning in my day job building AI for healthcare: the gap
between a model and reality is often not knowledge but behaviour — and behaviour
can be measured, modelled, and validated like anything else.

Free, no signup, open source: chess.pharmatools.ai

---

### Notes
- ~200 words; paste as plain text, LinkedIn keeps the line breaks.
- First line is the hook that shows before "…see more" — it stands alone on purpose.
- Optional comment-bait closer if you want engagement: "Offer the 1850 bot a draw
  and tell me what it says."
- Validation receipts if anyone asks: chess.pharmatools.ai/validation
