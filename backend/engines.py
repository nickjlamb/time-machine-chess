"""Pluggable era engines.

- HeuristicEraEngine: placeholder with era-flavored move selection so the app
  is playable before any training. NOT the product — just scaffolding.
- Maia2Engine: integration point for fine-tuned Maia-2 checkpoints (Days 3-4).

Both expose: pick_move(board) -> chess.Move
         and pick_move_with_eval(board) -> (chess.Move, white_win_prob)
(the heuristic's win prob is a crude material sigmoid — enough to drive the
draw-agreement rule in backend/draws.py in tests/CI, where torch is absent).
"""
import math
import random

import chess

PIECE_VALUES = {
    chess.PAWN: 1, chess.KNIGHT: 3, chess.BISHOP: 3.2,
    chess.ROOK: 5, chess.QUEEN: 9, chess.KING: 0,
}
CENTER = {chess.D4, chess.E4, chess.D5, chess.E5}


def material_balance(board: chess.Board) -> float:
    """Material score from White's perspective, in pawns."""
    return sum(
        val * (len(board.pieces(pt, chess.WHITE)) - len(board.pieces(pt, chess.BLACK)))
        for pt, val in PIECE_VALUES.items()
    )


class HeuristicEraEngine:
    def __init__(self, style: dict):
        self.t = style.get("temperature", 0.6)
        self.capture_bonus = style.get("capture_bonus", 0.3)
        self.check_bonus = style.get("check_bonus", 0.3)
        self.sac_tolerance = style.get("sacrifice_tolerance", 0.1)
        self.king_safety = style.get("king_safety_weight", 0.5)
        self.development = style.get("development_weight", 0.7)

    def score_move(self, board: chess.Board, move: chess.Move) -> float:
        score = 0.0
        piece = board.piece_at(move.from_square)

        # Material: value captured minus risk of losing the mover on arrival.
        if board.is_capture(move):
            victim = board.piece_at(move.to_square)
            victim_val = PIECE_VALUES.get(victim.piece_type, 1) if victim else 1  # en passant
            score += self.capture_bonus + 0.3 * victim_val
        board.push(move)
        try:
            if board.is_checkmate():
                return 100.0
            if board.is_check():
                score += self.check_bonus
            # Risk: did we leave the moved piece en prise?
            attackers = board.attackers(board.turn, move.to_square)
            defenders = board.attackers(not board.turn, move.to_square)
            if attackers and not defenders and piece:
                hang = PIECE_VALUES.get(piece.piece_type, 1)
                score -= hang * (1.0 - self.sac_tolerance)
        finally:
            board.pop()

        # Development: minors off the back rank in the opening.
        if board.fullmove_number <= 12 and piece:
            back = 0 if piece.color == chess.WHITE else 7
            if (piece.piece_type in (chess.KNIGHT, chess.BISHOP)
                    and chess.square_rank(move.from_square) == back):
                score += self.development * 0.5
            if move.to_square in CENTER:
                score += self.development * 0.3
        # King safety: reward castling, punish early king walks.
        if board.is_castling(move):
            score += self.king_safety * 1.2
        elif piece and piece.piece_type == chess.KING and board.fullmove_number <= 20:
            score -= self.king_safety * 0.8
        return score

    def pick_move(self, board: chess.Board) -> chess.Move:
        moves = list(board.legal_moves)
        scores = [self.score_move(board, m) for m in moves]
        # Softmax sampling with era temperature.
        mx = max(scores)
        weights = [math.exp((s - mx) / max(self.t, 0.05)) for s in scores]
        return random.choices(moves, weights=weights, k=1)[0]

    def pick_move_with_eval(self, board: chess.Board):
        """Returns (move, white_win_prob) — same contract as Maia2Engine.

        The win prob is a material-balance sigmoid: crude, but deterministic
        for equal material (exactly 0.5), which is what the draw-agreement
        rule and its tests need when the trained models aren't available.
        """
        win_prob = 1.0 / (1.0 + math.exp(-0.5 * material_balance(board)))
        return self.pick_move(board), win_prob

    def move_probs(self, board: chess.Board) -> dict:
        """Full legal-move distribution {uci: prob} — the era classifier's
        contract. Softmax of the heuristic scores at the era temperature:
        the same distribution pick_move samples from, but returned whole.
        Deterministic (no sampling), which the classifier tests rely on."""
        moves = list(board.legal_moves)
        scores = [self.score_move(board, m) for m in moves]
        mx = max(scores)
        weights = [math.exp((s - mx) / max(self.t, 0.05)) for s in scores]
        total = sum(weights)
        return {m.uci(): w / total for m, w in zip(moves, weights)}


class Maia2Engine:
    """Serve a fine-tuned Maia-2 era checkpoint (models/{era}.pt).

    Uses maia2.inference.inference_each, which handles black-to-move mirroring
    internally and returns a legal-move probability distribution. We temperature-
    sample from it (T<1 sharpens toward the era's most characteristic moves).
    NOMINAL_ELO must match scripts/prepare_training.py.
    """

    NOMINAL_ELO = 1900

    def __init__(self, checkpoint_path: str, temperature: float = 0.6,
                 opening_temperature: float = 1.0, opening_plies: int = 10):
        import torch
        from maia2 import model as maia2_model, inference

        self.temperature = temperature
        # Sample the model's true distribution in the opening: era character
        # lives in opening *diversity* (sharpening over-concentrates on 1.e4).
        self.opening_temperature = opening_temperature
        self.opening_plies = opening_plies
        self.net = maia2_model.from_pretrained(type="rapid", device="cpu")
        self.net.load_state_dict(torch.load(checkpoint_path, map_location="cpu"))
        self.net.eval()
        self._inference = inference
        self._prepared = inference.prepare()

    def pick_move(self, board: chess.Board) -> chess.Move:
        return self.pick_move_with_eval(board)[0]

    def pick_move_with_eval(self, board: chess.Board):
        """Returns (move, white_win_prob) — win prob from White's perspective."""
        move_probs, win_prob = self._inference.inference_each(
            self.net, self._prepared, board.fen(), self.NOMINAL_ELO, self.NOMINAL_ELO
        )
        t = self.opening_temperature if board.ply() < self.opening_plies else self.temperature
        moves, probs = zip(*move_probs.items())
        sharpened = [max(p, 1e-9) ** (1.0 / t) for p in probs]
        chosen = random.choices(moves, weights=sharpened, k=1)[0]
        return chess.Move.from_uci(chosen), win_prob

    def move_probs(self, board: chess.Board) -> dict:
        """Model's raw legal-move distribution {uci: prob} (no temperature —
        the classifier scores the model's actual beliefs, not the serving
        sharpening)."""
        probs, _ = self._inference.inference_each(
            self.net, self._prepared, board.fen(), self.NOMINAL_ELO, self.NOMINAL_ELO
        )
        return probs

    def move_probs_batch(self, fens_moves):
        """Batched distributions for [(fen, played_uci), ...] -> list of
        {uci: prob} dicts, in order.

        Uses maia2.inference.inference_batch (one forward pass per 64
        positions via a DataLoader) instead of position-at-a-time
        inference_each — the difference between minutes and seconds when the
        classifier scores hundreds of positions against five era models.
        The played move is passed through because inference_batch's schema
        requires a 'move' column (it computes top-1 accuracy on it).
        Falls back to the per-position path if the batch path fails.
        NOTE: inference_batch rounds probabilities to 4 decimal places, so
        callers must floor probabilities before taking logs."""
        try:
            import pandas as pd
            data = pd.DataFrame({
                "board": [fen for fen, _ in fens_moves],
                "move": [uci for _, uci in fens_moves],
                "active_elo": [self.NOMINAL_ELO] * len(fens_moves),
                "opponent_elo": [self.NOMINAL_ELO] * len(fens_moves),
            })
            data, _acc = self._inference.inference_batch(
                data, self.net, verbose=False, batch_size=64, num_workers=0
            )
            return list(data["move_probs"])
        except Exception as exc:  # pragma: no cover - depends on maia2 internals
            print(f"[warn] batch inference failed ({exc}); falling back to per-position")
            return [self.move_probs(chess.Board(fen)) for fen, _ in fens_moves]
